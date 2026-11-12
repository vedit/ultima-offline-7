"""Install the Finnigan portrait into a private ClassicUO Gump UOP."""

from __future__ import annotations

import hashlib
import json
import os
import re
import struct
import tempfile
import zlib
from pathlib import Path


GUMP_ID = 64012
# ClassicUO.IO.UOFileUop.CreateHash("build/gumpartlegacymul/00064012.tga").
GUMP_HASH = 0xD47F86C7883AC6B4
# Verified with the pinned ClassicUO CreateHash for the corresponding .tga paths.
SLOTS = {1: (64001, 0x39C114DD85FDC2EA), 11: (64011, 0x43E89843B3574319), 12: (GUMP_ID, GUMP_HASH),
         14: (64014, 0xCD135E3875F02C73), 2: (64002, 0xCDBBD3A41F73E1C7), 13: (64013, 0x661159FCFA84042F)}
ARCHIVE = "gumpartLegacyMUL.uop"
FRAME_SLOTS = {(face, 0): resource for face, resource in SLOTS.items()}
FRAME_SLOTS[2, 1] = (64102, 0x6C40659A16D103F5)
HEADER = struct.Struct("<IIIQII")
BLOCK = struct.Struct("<IQ")
ENTRY = struct.Struct("<QIIIQIH")


def _directory(data, expected_version=4):
    if len(data) < HEADER.size:
        raise ValueError("Truncated Gump UOP header")
    magic, version, _, block, capacity, advertised = HEADER.unpack_from(data)
    if magic != 0x50594D or version != expected_version or not 1 <= capacity <= 65536 or not block:
        raise ValueError("Unsupported UOP header")
    seen, entries = set(), {}
    occupied = [(0, HEADER.size)]
    while block:
        if block in seen or not HEADER.size <= block <= len(data) - BLOCK.size:
            raise ValueError("Cyclic or out-of-bounds Gump UOP directory")
        seen.add(block)
        count, following = BLOCK.unpack_from(data, block)
        pos = block + BLOCK.size
        if count > capacity or pos + count * ENTRY.size > len(data):
            raise ValueError("Invalid Gump UOP directory span")
        occupied.append((block, pos + count * ENTRY.size))
        for i in range(count):
            entry = ENTRY.unpack_from(data, pos + i * ENTRY.size)
            offset, header_len, stored, original, key, _, flag = entry
            if not offset:
                continue
            if key in entries or not (stored and original) or flag not in {0,1,3}:
                raise ValueError("Invalid or duplicate Gump UOP entry")
            if offset + header_len + stored > len(data):
                raise ValueError("Gump UOP entry extends beyond the archive")
            occupied.append((offset, offset + header_len + stored))
            entries[key] = entry
        last, block = block, following
    if advertised != len(entries):
        raise ValueError("Gump UOP header count differs from occupied entries")
    occupied.sort()
    if any(a[1] > b[0] for a,b in zip(occupied, occupied[1:])):
        raise ValueError("Overlapping Gump UOP member and directory spans")
    return capacity, last, entries


def overlay_bytes(stock, gump, slot=GUMP_ID, member_hash=GUMP_HASH):
    """Append a v4 directory block while keeping stock entries at their original offsets."""
    capacity, last, before = _directory(stock)
    if member_hash in before:
        raise ValueError(f"Stock Gump slot {slot} is occupied")
    block = len(stock)
    data_offset = block + BLOCK.size + capacity * ENTRY.size
    # UOP per-file header: field type 3, eight bytes of file-time metadata.
    # Hash is Adler-32 of this per-file header, as in the retail UOP.
    metadata = struct.pack("<HHQ", 3, 8, 0)
    record = ENTRY.pack(data_offset, len(metadata), len(gump), len(gump), member_hash,
                        zlib.adler32(metadata), 0)
    out = bytearray(stock)
    struct.pack_into("<I", out, 24, len(before) + 1)
    struct.pack_into("<Q", out, last + 4, block)
    out.extend(BLOCK.pack(1, 0) + record + bytes((capacity - 1) * ENTRY.size) + metadata + gump)
    _, _, after = _directory(out)
    added = after.pop(member_hash)
    if before != after or out[added[0] + added[1]:added[0] + added[1] + added[2]] != gump:
        raise ValueError("Gump UOP readback differs from the stock directory or generated member")
    return out, len(before)


def _check_slot(folder, slot):
    custom = folder / "Gumps"
    if custom.is_dir():
        for p in custom.iterdir():
            if p.suffix.lower() == ".gump" and p.stem.isdecimal() and int(p.stem) == slot:
                raise ValueError(f"Private Gump slot {slot} has a loose-file override")
    aliases = folder / "gump.def"
    if aliases.is_file():
        for line in aliases.read_text(encoding="ascii", errors="replace").splitlines():
            if re.search(rf"\b{slot}\b", line.partition("#")[0]):
                raise ValueError(f"Private Gump slot {slot} is referenced by gump.def")


def _validate_runs(data, width, height, spec):
    if len(data) % 4 or len(data) < 4*height or not (1 <= width <= 1024 and 1 <= height <= 1024):
        raise ValueError("Invalid portrait scanline table size")
    first = [v for (v,) in struct.iter_unpack("<I", data[:4*height])] + [len(data) // 4]
    if first[0] != height or any(a >= b for a,b in zip(first, first[1:])):
        raise ValueError("Invalid portrait scanline offsets")
    digest = hashlib.sha256()
    opaque = 0
    for a,b in zip(first,first[1:]):
        size = 0
        for color,run in struct.iter_unpack("<HH", data[a*4:b*4]):
            if not run or size + run > width:
                raise ValueError("Invalid portrait pixel run")
            size += run
            rgba = bytes(4)
            if color:
                rgba = bytes([((color >> shift) & 31) * 255 // 31 for shift in (10,5,0)] + [255])
                opaque += run
            digest.update(rgba*run)
        if size != width:
            raise ValueError("Incomplete portrait scanline")
    if digest.hexdigest() != spec["expected_rgba_sha256"] or opaque != spec["opaque_pixels"]:
        raise ValueError("Portrait pixel digest or opacity differs from the source proof")


def stage_gump_overlay(stock_assets: Path, staged_assets: Path, portrait_dir: Path, companions=()) -> dict:
    stock_assets, staged_assets, portrait_dir = map(lambda p: Path(p).resolve(), (stock_assets, staged_assets, portrait_dir))
    if staged_assets.is_relative_to(stock_assets) or stock_assets.is_relative_to(staged_assets):
        raise ValueError("The private staged asset directory must be separate from the stock installation")
    stockfile, destination = stock_assets / ARCHIVE, staged_assets / ARCHIVE
    if destination.resolve() != destination or not (staged_assets / "MainMisc.uop").is_file():
        raise ValueError("The private stage does not select the traditional Gump UOP")
    stock = stockfile.read_bytes()
    stock_sha = hashlib.sha256(stock).hexdigest()
    if destination.exists():
        with destination.open("rb") as stream:
            if hashlib.file_digest(stream, "sha256").hexdigest() != stock_sha:
                raise ValueError("Private Gump UOP differs from the stock asset selected for staging")
    out = stock
    members = []
    for face, directory in [(12, portrait_dir), *companions]:
        data, member = _portrait_member(directory, face)
        slot, key = FRAME_SLOTS[face, member["frame"]]
        _check_slot(stock_assets, slot)
        _check_slot(staged_assets, slot)
        out, prior_count = overlay_bytes(out, data, slot, key)
        members.append(member)
    stock_count = prior_count + 1 - len(members)
    with tempfile.NamedTemporaryFile(dir=staged_assets, prefix=".gump-", delete=False) as tmp:
        temporary = Path(tmp.name)
    try:
        temporary.write_bytes(out)
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)
    return {**members[0], "companions": members[1:], "stock_entries": stock_count,
            "overlay_entries": stock_count + len(members), "stock_sha256": stock_sha,
            "overlay_sha256": hashlib.sha256(out).hexdigest()}


def _portrait_member(portrait_dir, face):
    spec = json.loads((portrait_dir / "portrait.json").read_bytes())
    if spec["shape"] != face or (face, spec["frame"]) not in FRAME_SLOTS or spec["binding"]["npc_ref"] != -face:
        raise ValueError("Unrecognized portrait binding")
    if face == 12 and (spec["character"], spec["binding"]["function"]) != ("Finnigan", 0x40C):
        raise ValueError("Unexpected Finnigan portrait binding")
    idx = (portrait_dir / "gumpidx.mul").read_bytes()
    art = (portrait_dir / "gumpart.mul").read_bytes()
    i = spec["gump_id"] * 12
    if i < 0 or i + 12 > len(idx):
        raise ValueError("Invalid standalone portrait index")
    start, length, dimensions = struct.unpack_from("<III", idx, i)
    width, height = dimensions >> 16, dimensions & 0xffff
    if (not width or not height or not length or start + length > len(art)
            or (width,height) != (spec["width"],spec["height"])):
        raise ValueError("Invalid standalone portrait data or dimensions")
    pixels = art[start:start+length]
    _validate_runs(pixels, width, height, spec)
    data = struct.pack("<II", width, height) + pixels
    slot, key = FRAME_SLOTS[face, spec["frame"]]
    return data, {"schema": 1, "character": spec["character"], "shape": face, "gump_id": slot, "file": ARCHIVE,
            "member": f"build/gumpartlegacymul/{slot:08d}.tga", "member_hash": f"{key:016x}",
            "function_id": spec["binding"]["function"], "frame": spec["frame"],
            "width": width, "height": height, "opaque_pixels": spec["opaque_pixels"],
            "expected_rgba_sha256": spec["expected_rgba_sha256"], "new_member_sha256": hashlib.sha256(data).hexdigest()}
