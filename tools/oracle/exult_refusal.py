"""Qualify an Exult debug replay of Finnigan's refusal against a native DOS replay."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import xml.etree.ElementTree as ET

from .qualify import qualify as qualify_dos
from u7uo.u7 import usecode_inventory


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def activation(trace, function, event):
    header = rf"^Running usecode {function:04x} \(.*?\) with event {event}, depth 0$"
    hits = list(re.finditer(header, trace, re.M))
    if len(hits) != 1:
        raise ValueError(f"Expected one root activation of {function:04x} event {event}")
    block = trace[hits[0].end():]
    next_root = re.search(r"^Running usecode .+ with event \d+, depth 0$", block, re.M)
    return block[:next_root.start()] if next_root else block


def ordered(block, patterns):
    end = 0
    matches = []
    for pattern in patterns:
        found = re.search(pattern, block[end:], re.M)
        if not found:
            raise ValueError(f"Missing trace evidence: {pattern}")
        end += found.end()
        matches.append(found)
    return matches


def opening(trace):
    block = activation(trace, 0x401, 3)
    avatar, _, result, _, _ = ordered(block, [
        r"\[0x22\]: get_avatar_ref\(\) = ([0-9a-f]+)$",
        r"^\.\.\.back into usecode 0401$",
        r"000A: callis\s+_get_party_list@0\s+; 0023\s+\[0x23\]: get_party_list\(\) = \[ ([0-9a-f]+) \]",
        r"004D: calli\s+_play_music@2\s+; 002E\s+\[0x2e\]: play_music\(0023, 0000\)",
        r"Audio subsystem request: Music track # 35",
    ])
    if int(avatar[1], 16) == 0 or int(avatar[1], 16) != int(result[1], 16):
        raise ValueError("The initial party did not contain just the observed Avatar")


def rendered_mask(path, box):
    # PrintWindow returns a normal Windows PNG. Sample the dialogue glyphs
    # at the calibrated window size, ignoring changing scenery and the pointer.
    script = """
$ErrorActionPreference='Stop'
Add-Type -AssemblyName System.Drawing
$r=[int[]]($env:EXULT_BOX.Split(','))
$b=[Drawing.Bitmap]::new($env:EXULT_FRAME)
try {
    if ($b.Width -ne 1024 -or $b.Height -ne 768) {throw 'Unqualified Exult window size'}
    $mask=[Collections.Generic.List[byte]]::new()
    for ($y=$r[1];$y -lt $r[3];$y+=2) {
        for ($x=$r[0];$x -lt $r[2];$x+=2) {
            $c=$b.GetPixel($x,$y)
            $mask.Add([byte]($c.R -eq 222 -and $c.G -eq 222 -and $c.B -eq 0))
        }
    }
    $hash=[Security.Cryptography.SHA256]::Create()
    try {[BitConverter]::ToString($hash.ComputeHash($mask.ToArray())).Replace('-','').ToLowerInvariant()}
    finally {$hash.Dispose()}
} finally {$b.Dispose()}
"""
    env = {**os.environ, "EXULT_FRAME": str(path.resolve()), "EXULT_BOX": ",".join(map(str, box))}
    return subprocess.check_output(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
                                   env=env, text=True, timeout=20).strip()


def compare(installation, session, dos):
    run = json.loads((session / "run.json").read_bytes())
    for key in ("archive", "executable", "build_log"):
        if sha(Path(run[key])) != run[key + "_sha256"]:
            raise ValueError(f"Changed Exult {key}")
    if (run["revision"] != "cacb4f584901dab59ff288c750d3622d3378435b" or
            run["archive_sha256"] != "da5d2fd858ff143613b4312dc66aff9c3ddfed9fd87524b1f43bf48973728127"):
        raise ValueError("Unexpected Exult source revision")
    config = ET.parse(session / "probe.cfg")
    source = installation / "Assets/UltimaVII-Steam"
    game = config.find("./disk/game/forgeofvirtue")
    if (game is None or Path(game.findtext("path")).resolve() != source.resolve() or
            Path(game.findtext("gamedat_path")).resolve() != (session / "gamedat").resolve() or
            config.findtext("./debug/trace/intrinsics") != "yes" or
            config.findtext("./debug/trace/usecode") != "verbose"):
        raise ValueError("Unqualified game or trace configuration")
    trace = (session / "stdout.txt").read_text(encoding="utf-8", errors="replace")
    ordered(trace, [r"Exult version 1\.12\.1", r"Compile-time options: DEBUG,",
                    r"found game with identity 'FORGE'", r"Creating 'gamedat' files\.", r"Reading usecode file\."])
    opening(trace)
    ordered(activation(trace, 0x401, 2), [
        r"0187: calli\s+_show_npc_face@2\s+; 0003\s+\[0x03\]: show_npc_face\(ffff, 0000\)",
        r"0191: addsi\s+L0151", r"019A: say",
    ])
    mayor = activation(trace, 0x40c, 1)
    ordered(mayor, [
        r"01B9: addsi\s+L060E", r"Running usecode 090a \(\) with event 1, depth 1",
        r'\[0x05\]: add_answer\(\[ "Yes", "No" \]\)', r"Returning \(0000\) from usecode 090a",
        r"\.\.\.back into usecode 040c", r"01C6: jne\s+0216\s+\(jump taken\)",
        r"0216: addsi\s+L083C", r"0219: say", r"021B: popf\s+flag:\[0059\]",
        r"Setting global flag: 89", r"Aborting from usecode 040c",
    ])
    ordered(trace, [r"Aborting from usecode 040c", r"NPC write", r"Creating screenshot for savegame"])
    native = qualify_dos(dos, installation)
    if native["status"] != "passed" or native["visible_outcome"] != "refusal" or native["original_save_state"] != "passed":
        raise ValueError("Original DOS refusal lacks visible and saved evidence")
    code = (source / "STATIC/USECODE").read_bytes()
    records = {r["id"]: r for r in usecode_inventory(code)["records"]}
    sites = {}
    for fid, pc, expected in ((0x401, 10, "38230000"), (0x401, 77, "392e0002"), (0x401, 401, "1c5101"),
                              (0x40c, 0x216, "1c3c08"), (0x40c, 0x21b, "435900")):
        at = records[fid]["code_offset"] + pc
        decoded = bytes.fromhex(expected)
        if code[at:at+len(decoded)] != decoded:
            raise ValueError("Original instruction differs from the Exult trace")
        sites[f"{fid:04x}+{pc:04x}"] = at
    refusal, = (o for o in native["observations"] if o["observation"] == "refusal")
    if refusal["usecode_file_offset"] != sites["040c+0216"]:
        raise ValueError("The DOS and Exult refusal identify different string instructions")
    exult_flags = (session / "gamedat/flaginit").read_bytes()
    if len(exult_flags) != 2048 or any(exult_flags[int(k)] != v["save"] for k,v in native["flags_checked"].items()):
        raise ValueError("Exult quicksave differs from DOS on a checked flag")
    frames = {}
    for name, box, signature in [
        ("finnigan-yes-no-05.png", (342,303,561,350), "d69cdaed095ceaba1c78c695a98cb472cabe1654f3c4b90a4a776a456e0ba86e"),
        ("decline-by-option-two.png", (182,74,990,163), "8632150333b537ad9e49d2092897fbaf71ab55c932309d60d078cb4829d58820"),
    ]:
        file = session / name
        if rendered_mask(file, box) != signature:
            raise ValueError(f"Exult's rendered answer menu or refusal has changed: {name}")
        frames[name] = {"sha256": sha(file), "glyph_mask_sha256": signature, "rectangle": box}
    return {"status": "passed", "edition": "FORGE", "run": run, "exult_session": str(session),
            "dos_session": str(dos), "usecode_sha256": hashlib.sha256(code).hexdigest(),
            "initgame_sha256": sha(source/"STATIC/INITGAME.DAT"), "dos_executable_sha256": sha(source/"U7.EXE"),
            "dos_wasm_sha256": native["wasm_sha256"], "config_sha256": sha(session/"probe.cfg"),
            "trace_sha256": sha(session/"stdout.txt"), "original_instruction_offsets": sites,
            "exult_frames": frames, "dos_refusal": refusal, "dos_choice": native["choice_input"],
            "flags": native["flags_checked"], "dos_save_sha256": native["save_sha256"],
            "exult_quicksave_flags_sha256": hashlib.sha256(exult_flags).hexdigest(),
            "opening": {"function": "0401", "event": 3, "party_at_pc_10": ["Avatar"], "music": 35},
            "refusal": {"function": "040c", "event": 1, "answer": "No", "new_flag": 89}}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for argument in ("installation", "exult_session", "dos_session"):
        parser.add_argument(argument, type=Path)
    args = parser.parse_args()
    print(json.dumps(compare(args.installation, args.exult_session, args.dos_session), indent=2))
