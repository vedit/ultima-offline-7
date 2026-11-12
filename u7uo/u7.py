"""Inspect original DOS Black Gate data. All reported paths are relative to the input."""

from __future__ import annotations

import hashlib
import re
import struct
import zlib
from pathlib import Path


# Exult gamemgr/modmgr.cc and files/crc.cc at this revision define both markers.
EDITION_SOURCE = "https://github.com/exult/exult/blob/dba00df48237c4b33862f0a9892a8001f75d6eb8/gamemgr/modmgr.cc#L458-L565"
MENU_VARIANTS = {
    0xAFC35523: ("ULTIMA7", "en"),
    0x36AF707F: ("ULTIMA7", "fr"),
    0x157CA514: ("ULTIMA7", "de"),
    0x6D7B7323: ("ULTIMA7", "es"),
    0x8A74C26B: ("FORGE", "en"),
    0xF98F5F3E: ("SERPENT ISLE", "en"),
    0x96F66A7A: ("SERPENT ISLE", "es"),
    0xDBDC2676: ("SERPENT ISLE", "en"),
    0x3E18F9A0: ("SILVER SEED", "en"),
}
STEAM_FORGE_USECODE = "49a3fcaf8a763972d0a6006571e8d8eef11eb1602f88898808b520523d0a8576"
STEAM_FORGE_STATIC = "f2fdf025c36c099697572e7825bf381019b6dcc452b5f7ae03b3351132b3bfa9"
ART_ARCHIVES = {"FACES.VGA", "FONTS.VGA", "GUMPS.VGA", "PALETTES.FLX", "SHAPES.VGA", "TEXT.FLX"}
FIXED_REGIONS = {f"U7IFIX{n:02X}" for n in range(144)}
MOVABLE_REGIONS = {f"u7ireg{n:02x}" for n in range(144)}
REQUIRED_STATIC = ART_ARCHIVES | FIXED_REGIONS | {
    "INITGAME.DAT", "MAINSHP.FLX", "SCHEDULE.DAT", "TFA.DAT", "U7CHUNKS", "U7MAP", "USECODE",
}


def flex_directory(data: bytes) -> list[tuple[int, int]]:
    """Return indexed (offset, length) pairs for an original DOS FLEX file."""
    if len(data) < 128 or data[80:84] != b"\x00\x1a\xff\xff":
        raise ValueError("invalid DOS FLEX header")
    count = struct.unpack_from("<I", data, 84)[0]
    end = 128 + count * 8
    if end > len(data):
        raise ValueError("truncated FLEX directory")
    entries = list(struct.iter_unpack("<II", memoryview(data)[128:end]))
    used = []
    for slot, (offset, size) in enumerate(entries):
        if size:
            if offset < end or offset + size > len(data):
                raise ValueError(f"FLEX slot {slot} points outside the data region")
            used.append((offset, offset + size))
    used.sort()
    if any(left[1] > right[0] for left, right in zip(used, used[1:])):
        raise ValueError("overlapping FLEX members")
    return entries


def seed_directory(data: bytes) -> dict[str, tuple[int, int, int]]:
    """Index INITGAME entries by DOS name, with payload offsets after the 13-byte prefix."""
    names = {}
    for slot, (offset, size) in enumerate(flex_directory(data)):
        if not size:
            continue
        if size < 13:
            raise ValueError(f"seed slot {slot} has a truncated filename")
        name = data[offset:offset + 13].split(b"\0", 1)[0].decode("ascii").lower()
        if not re.fullmatch(r"[a-z0-9_-]{1,8}(?:\.[a-z0-9_-]{0,3})?", name):
            raise ValueError(f"invalid DOS filename in seed slot {slot}")
        # DOS writes extensionless entries such as 'flaginit.' with a trailing dot.
        name = name.rstrip(".")
        if name in names:
            raise ValueError(f"duplicate seed member {name}")
        names[name] = (slot, offset + 13, size - 13)
    return names


def usecode_inventory(data: bytes) -> dict:
    """Index retail 16-bit function records and check the string and extern tables."""
    records = []
    seen = set()
    offset = 0
    while offset < len(data):
        if len(data) - offset < 4:
            raise ValueError(f"truncated Usecode function header at {offset}")
        function, size = struct.unpack_from("<HH", data, offset)
        end = offset + 4 + size
        if function in (0xFFFE, 0xFFFF):
            raise ValueError(f"unsupported extended Usecode header at {offset}")
        if function in seen:
            raise ValueError(f"duplicate Usecode function {function:04X} at {offset}")
        if end > len(data) or size < 8:
            raise ValueError(f"invalid size for Usecode function {function:04X} at {offset}")
        data_size = struct.unpack_from("<H", data, offset + 4)[0]
        tables = offset + 6 + data_size
        if tables + 6 > end:
            raise ValueError(f"truncated string table in Usecode function {function:04X}")
        args, locals_count, links = struct.unpack_from("<HHH", data, tables)
        code = tables + 6 + 2 * links
        if code > end:
            raise ValueError(f"truncated extern table in Usecode function {function:04X}")
        records.append({
            "id": function, "offset": offset, "body_length": size, "data_length": data_size,
            "arguments": args, "locals": locals_count, "extern_count": links,
            "code_offset": code, "code_length": end - code,
        })
        seen.add(function)
        offset = end
    if not records:
        raise ValueError("empty Usecode file")
    return {"count": len(records), "records": records, "sha256": hashlib.sha256(data).hexdigest()}


def exult_crc32(data: bytes) -> int:
    # Exult starts its CRC register at zero and leaves the final bits uncomplemented.
    return zlib.crc32(data, 0xFFFFFFFF) ^ 0xFFFFFFFF


def _inspect_static(paths: dict[str, Path], report: dict) -> None:
    contents = {}
    fingerprint = hashlib.sha256()
    for name, path in sorted(paths.items()):
        raw = path.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        report["static_files"].append({"path": f"STATIC/{name}", "bytes": len(raw), "sha256": digest})
        fingerprint.update(f"{name}\t{len(raw)}\t{digest}\n".encode("utf-8"))
        if name in REQUIRED_STATIC and not raw:
            raise ValueError(f"empty required file STATIC/{name}")
        if name in ART_ARCHIVES | FIXED_REGIONS:
            try:
                entries = flex_directory(raw)
                if name in FIXED_REGIONS and (len(entries) != 256 or any(size % 4 for _, size in entries)):
                    raise ValueError("expected 256 chunk entries containing four-byte fixed records")
            except ValueError as exc:
                raise ValueError(f"STATIC/{name}: {exc}") from exc
        if name in {"INITGAME.DAT", "USECODE", "MAINSHP.FLX", "U7CHUNKS", "U7MAP"}:
            contents[name] = raw
    report["static_fingerprint"] = fingerprint.hexdigest()
    missing = sorted(REQUIRED_STATIC - paths.keys())
    if missing:
        report["status"] = "missing"
        report["diagnostics"].append("Missing STATIC files: " + ", ".join(missing))
        return

    raw = contents["INITGAME.DAT"]
    members = seed_directory(raw)
    for name, (slot, start, size) in members.items():
        report["seed_members"].append({
            "name": name, "slot": slot, "offset": start, "bytes": size,
            "sha256": hashlib.sha256(raw[start:start + size]).hexdigest(),
        })
    required_seed = MOVABLE_REGIONS | {"identity", "npc.dat"}
    absent = sorted(required_seed - members.keys())
    if absent:
        raise ValueError("INITGAME.DAT lacks seed members: " + ", ".join(absent))
    if not members["npc.dat"][2]:
        raise ValueError("INITGAME.DAT has empty npc.dat")
    _, start, size = members["identity"]
    identity_bytes = re.split(rb"[\x1a\r\n\x00]", raw[start:start + size], maxsplit=1)[0]
    marker = identity_bytes.decode("ascii")
    report["identity"] = marker
    report["usecode"] = usecode_inventory(contents["USECODE"])

    chunks = contents["U7CHUNKS"]
    placements = contents["U7MAP"]
    if len(placements) != 12 * 12 * 16 * 16 * 2 or len(chunks) % 512:
        raise ValueError("invalid DOS Black Gate U7MAP or U7CHUNKS dimensions")
    if any(i >= len(chunks) // 512 for (i,) in struct.iter_unpack("<H", placements)):
        raise ValueError("U7MAP references a missing U7CHUNKS terrain record")
    report["world"] = {
        "chunk_definitions": len(chunks) // 512, "placed_chunks": len(placements) // 2,
        "fixed_regions": len(FIXED_REGIONS), "movable_regions": len(MOVABLE_REGIONS),
    }
    crc = exult_crc32(contents["MAINSHP.FLX"])
    report["menu_crc_exult"] = f"{crc:08x}"
    menu = MENU_VARIANTS.get(crc)
    if menu and marker != menu[0]:
        report["status"] = "mixed"
        report["diagnostics"].append(f"INITGAME.DAT identifies {marker!r}; MAINSHP.FLX identifies {menu[0]!r}")
        return
    if marker != "FORGE" and report["usecode"]["sha256"] == STEAM_FORGE_USECODE:
        report["status"] = "mixed"
        report["diagnostics"].append(f"INITGAME.DAT identifies {marker!r}; USECODE matches English Steam Forge")
        return
    if not menu or marker not in {"ULTIMA7", "FORGE"}:
        report["diagnostics"].append(f"Unrecognized or unsupported edition markers {marker!r}, menu CRC {crc:08x}")
        return
    report["language"] = menu[1]
    report["status"] = {"ULTIMA7": "vanilla", "FORGE": "expanded"}[marker]
    if menu[1] != "en":
        report["diagnostics"].append(f"The conversion targets English data; detected language {menu[1]}")
        return
    report["ready"] = True
    if report["static_fingerprint"] == STEAM_FORGE_STATIC:
        report["matched_profile"] = "steam-3067540-build-25535931-forge"
    else:
        report["diagnostics"].append("Edition markers recognized; no complete retail STATIC fingerprint match")


def inspect_u7(root: Path) -> dict:
    """Inspect the installation's STATIC directory. GAMEDAT is never a new-game input."""
    report = {
        "status": "unknown", "ready": False, "identity": None, "language": None,
        "matched_profile": None, "edition_source": EDITION_SOURCE,
        "vanilla_gameplay_qualification": "not_run",
        "seed_source": "STATIC/INITGAME.DAT", "static_files": [], "static_fingerprint": None,
        "seed_members": [], "usecode": None, "diagnostics": [],
    }
    try:
        if not root.is_dir():
            raise FileNotFoundError("Ultima VII installation directory is missing")
        static_dirs = [p for p in root.iterdir() if p.name.upper() == "STATIC" and p.is_dir()]
        if not static_dirs:
            raise FileNotFoundError("Ultima VII STATIC directory is missing")
        if len(static_dirs) != 1:
            raise ValueError("multiple DOS-equivalent STATIC directories")
        paths = {}
        for path in static_dirs[0].iterdir():
            if path.is_file():
                name = path.name.upper()
                if name in paths:
                    raise ValueError(f"duplicate DOS filename STATIC/{name}")
                paths[name] = path
        _inspect_static(paths, report)
    except FileNotFoundError as exc:
        report["status"] = "missing"
        report["diagnostics"].append(str(exc))
    except (OSError, ValueError) as exc:
        report["diagnostics"].append(str(exc))
    return report
