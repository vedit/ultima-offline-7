"""Qualify the original DOS investigation, earned password and two east-gate crossings."""

import argparse
import json
import struct
from pathlib import Path

from .investigation import inspect_save, qualify_stable, read_gate
from .qualify import TEXT, mask, sha
from u7uo.u7 import seed_directory, usecode_inventory


# These rectangles and foreground colors were read from the original rendered game.
# The room's light level changes the DOS text palette during the two witness scenes.
SPEECH = [
    ("spark-original-hook-testimony", 0x402, b"All I saw of him", "d39e00",
     "8ebd2eb57ad9980fb0501c89f32f1b34a9c946c8b4179b55c047c362e542aa85"),
    ("gilberto-original-crown-jewel-testimony", 0x40D, b"Did I forget to say?", "cb9a10",
     "3b715b0e59a41164d6ceb5850ea1f037fe6ec9dc7aa4ca181b80d7448c9ad46f"),
    ("mayor-accepts-authentic-investigation", 0x884, b"The Mayor is pleased.", "dfdf00",
     "f9198755828bc1e6f515ec04ee5b95656807e0c57e6e773c250d6e0647d4b929"),
    ("read-finnigan-quiz-result", 0x884, b"Excellent! I have no doubt", "dfdf00",
     "7a9b4b4f9302f49d9abfb95cb91d599268965507de39a1ba9cdced25f735ab15"),
    ("receive-original-town-password", 0x884, b"Blackbird", "dfdf00",
     "a3b9cf8a3986d179c07defc38c04191b5e7f5fe919bd3f58669b5a728ec159a0"),
    ("give-johnson-the-earned-password", 0x40E, b"Very well, thou mayest pass.", "dfdf00",
     "47708a4d01c391b580886ee4bae138b1ddc294d1f1b4c3fc4e281f34f59c27bf"),
]


def _frame(session, receipt, label):
    matches = [f for f in receipt["frames"] if f["file"].endswith("-" + label + ".png")]
    if len(matches) != 1:
        raise ValueError(f"Expected one DOS frame for {label}")
    record = matches[0]
    path = (session / record["file"]).resolve()
    if path.parent != session or record["width"] != 320 or record["height"] != 200:
        raise ValueError("Invalid DOS video observation")
    raw = path.read_bytes()
    if sha(raw) != record["sha256"]:
        raise ValueError(f"Changed original frame for {label}")
    return {**record, "id": label}, raw


def native_actors(npcs, items, slots):
    actors = {}
    for slot in slots:
        handle = struct.unpack_from("<H", npcs, slot*105 + 2)[0]
        _, xy, shape_frame, ext = struct.unpack_from("<4H", items, handle)
        region = items[ext + 2]
        actors[str(slot)] = {"handle": handle, "shape": shape_frame & 1023, "frame": shape_frame >> 10,
                             "world_xy": [region%12*256 + xy%256, region//12*256 + (xy>>8)]}
    return actors


def _state(session, receipt, label, tfa, lift):
    actions = [a for a in receipt["actions"] if a["type"] == "state" and a.get("label") == label]
    if len(actions) != 1:
        raise ValueError(f"Expected exactly one native export for {label}")
    action = actions[0]
    file = f"{label}-GAME0{action['slot']}.U7"
    records = [c for c in receipt["checkpoints"] if c["file"] == file]
    raw = (session / file).read_bytes()
    if len(records) != 1 or records[0]["bytes"] != len(raw) or records[0]["sha256"] != sha(raw):
        raise ValueError(f"Invalid exported original save for {label}")
    state = inspect_save(session / file)
    if state["key"].get("actor_slot") != 0:
        raise ValueError("Investigation key missing from the original Avatar")
    idx = seed_directory(raw)
    def member(name):
        _, off, size = idx[name]
        return raw[off:off+size]
    party = member("party")
    if len(party) != 191 or party[16] > 8 or party[-1] > 16:
        raise ValueError("Invalid original active/downed party table")
    actors = native_actors(member("u7nbuf.dat"), member("u7ibuf.dat"), (0,1,2,12,13,14))
    return {**state, "actors": actors, "avatar_xy": actors["0"]["world_xy"],
            "gate": read_gate(session / file, tfa, lift), "elapsed_ms": action["elapsed_ms"],
            "active_party_handles": list(struct.unpack_from("<8H", party)[:party[16]]),
            "downed_party_handles": list(struct.unpack_from("<16H", party, 158)[:party[-1]])}


def qualify_departure(session, installation):
    session, installation = session.resolve(), installation.resolve()
    receipt = json.loads((session / "receipt.json").read_bytes())
    continuation = receipt.get("native_continuation", {})
    checkpoint = Path(continuation["source"]).resolve()
    qualified_root = (installation / "Evidence/dos-reference").resolve()
    if (not checkpoint.is_relative_to(qualified_root) or not session.is_relative_to(qualified_root) or
            Path(continuation["original_receipt"]).resolve() != checkpoint.parent / "receipt.json" or
            continuation["restore"] != "Original Load Gump" or receipt["fresh_filesystem"]):
        raise ValueError("Expected a native original-game continuation from an owned campaign")
    prior = json.loads((checkpoint.parent / "receipt.json").read_bytes())
    previous = qualify_stable(checkpoint.parent, installation)
    if not previous["estate_chest"] or not previous["closed_eastern_gate"]:
        raise ValueError("Unqualified estate investigation or initial closed gate")
    raw = checkpoint.read_bytes()
    if (not any(c["file"] == checkpoint.name and c["sha256"] == sha(raw) for c in prior["checkpoints"]) or
            sha(raw) != continuation["sha256"] or len(raw) != continuation["bytes"] or
            any(receipt[k] != prior[k] for k in ("inputs", "config_sha256", "wasm_sha256", "backend_version"))):
        raise ValueError("Native save ancestry or original game input mismatch")
    _, source_flags, _ = seed_directory(raw)["flaginit"]
    if [raw[source_flags + n] for n in (60, 61, 64, 67, 72, 90)] != [1,0,0,0,1,1]:
        raise ValueError("Unexpected investigation state in native donor slot")
    source = installation / "Assets/UltimaVII-Steam"
    usecode, tfa = (source/"STATIC/USECODE").read_bytes(), (source/"STATIC/TFA.DAT").read_bytes()
    records = {r["id"]: r for r in usecode_inventory(usecode)["records"]}
    observations = []
    for name, fid, fragment, color, expected in SPEECH:
        f, png = _frame(session, receipt, name)
        if mask(png, TEXT, bytes.fromhex(color)) != expected:
            raise ValueError(f"Native rendered text differs for {name}")
        row = records[fid]
        start = row["offset"] + 6
        matches = []
        for literal in usecode[start:start + row["data_length"]].split(b"\0"):
            if fragment in literal:
                matches.append({"offset": start, "sha256": sha(literal)})
            start += len(literal) + 1
        if not matches or len({m["sha256"] for m in matches}) != 1:
            raise ValueError(f"Original Usecode literal differs for {name}")
        observations.append({**f, "function_id": fid, "source_string_sha256": matches[0]["sha256"],
                             "matching_source_string_offsets": [m["offset"] for m in matches],
                             "glyph_mask_sha256": expected, "foreground_rgb": color, "rect": TEXT})
    if [f["elapsed_ms"] for f in observations] != sorted(f["elapsed_ms"] for f in observations):
        raise ValueError("Original witness, mayor and guard frames out of order")
    checkpoints = {}
    # flag 64 comes from Gilberto, 67 from Spark. 61 means the password has been earned.
    stages = [
        ("spark-hook", 0,0,0,1,0), ("gilberto-ship", 0,0,1,1,0),
        ("return-to-mayor", 0,0,1,1,0), ("earned-password", 0,1,1,1,0),
        ("gate-open", 4,1,1,1,1), ("outside-east-gate", 4,1,1,1,1),
        ("gate-reclosed", 0,1,1,1,1), ("blocked-reentry", 0,1,1,1,1),
    ]
    for name, lift, password, ship, hook, operated in stages:
        state = _state(session, receipt, name, tfa, lift)
        if any(state["flags"][str(n)] != v for n, v in (
                (60,1), (61,password), (64,ship), (67,hook), (72,1), (87,operated), (90,1))):
            raise ValueError(f"Original quest flags differ for {name}")
        if any(state["flags"][str(n)] != password for n in range(94,100)):
            raise ValueError(f"Original six report answers differ for {name}")
        if checkpoints and (state["elapsed_ms"] <= next(reversed(checkpoints.values()))["elapsed_ms"] or
                            state["gate"]["handle"] != checkpoints["spark-hook"]["gate"]["handle"]):
            raise ValueError("Original checkpoints or live gate identity disagree")
        checkpoints[name] = state
    passed, outside, closed, blocked = [checkpoints[k] for k in
                                            ("gate-open","outside-east-gate","gate-reclosed","blocked-reentry")]
    if ([s["avatar_xy"] for s in (passed, outside, closed, blocked)] !=
            [[1091,2214],[1107,2214],[1107,2214],[1103,2214]] or
            outside["actors"]["2"]["world_xy"] != [1105,2216]):
        raise ValueError("Original post-password crossing or reclosed entrance differs")
    def walk(before, after, direction):
        moves = [a for a in receipt["actions"] if before["elapsed_ms"] < a["elapsed_ms"] < after["elapsed_ms"]
                 and a["type"] == "click" and a.get("button") == 1]
        if len(moves) != 1 or moves[0].get("hold",0) < 600 or (
                moves[0]["x"] < .8 if direction == "east" else moves[0]["x"] > .2):
            raise ValueError("Missing the corresponding genuine mouse walk")
        return moves[0]
    official = sha((source/"answers.pdf").read_bytes())
    if official != "5e864b428671a2105f898f674099fc5e5ec844599a3f07573f525bd14e01ad0e":
        raise ValueError("Unrecognized Steam geography sheet")
    quiz = []
    for label, question, answer, digits in [
        ("verify-terfin-answer-120", "Terfin longitude", 120,
         "706514b1f4b76385e4b7c36a68fc0af9aa88f4e9d1bab095f6d3a2ea5564e61a"),
        ("set-official-skara-brae-latitude", "Skara Brae latitude", 30,
         "a604eabc7231853ecc8069ac6e7a24e6b1f64e589c78634f09a6ffb5d4d0153b"),
        ("set-official-skara-brae-longitude", "Skara Brae longitude", 60,
         "a06c52d1ec83cbd793602097739b1ed593fffcf2fb2589db9e81ef21dc783511"),
    ]:
        frame, png = _frame(session, receipt, label)
        if mask(png, (210, 62, 232, 74), bytes(3)) != digits:
            raise ValueError(f"Original numeric answer differs for {question}")
        quiz.append({**frame, "question": question, "answer_displayed": answer})
    loaded, _ = _frame(session, receipt, "confirm-unaltered-checkpoint")
    return {"schema":1, "status":"passed", "edition":previous["edition"],
            "backend":receipt["backend"], "wasm_sha256":receipt["wasm_sha256"],
            "edition_source_sha256":previous["edition_source_sha256"],
            "inputs_checked":previous["inputs_checked"], "native_continuation":{**continuation, "load_frame":loaded},
            "stable_investigation":str(checkpoint.parent/"stable-investigation-check.json"),
            "checkpoints":checkpoints, "observations":observations,
            "geography_quiz":{"official_steam_pdf_sha256":official, "observations":quiz},
            "crossing":{"inside_xy":passed["avatar_xy"], "outside_xy":outside["avatar_xy"],
                        "gate_cells":outside["gate"]["cells"], "ordinary_east_walk":walk(passed,outside,"east"),
                        "reclosed_xy":closed["avatar_xy"], "blocked_return_xy":blocked["avatar_xy"],
                        "ordinary_west_walk":walk(closed,blocked,"west")},
            "scope":"Original DOS Forge campaign, two witnessed leads, original earned password and eastern gate."}


if __name__=="__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("session", type=Path)
    parser.add_argument("--installation", type=Path, required=True)
    args = parser.parse_args()
    result = qualify_departure(args.session, args.installation)
    output = args.session / "earned-departure-check.json"
    output.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(output)
