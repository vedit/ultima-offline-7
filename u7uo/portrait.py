"""Extract Finnigan's Usecode-selected face and compile a standalone UO Gump proof."""

import hashlib
import json
import struct
import zlib
from itertools import groupby
from pathlib import Path

from .u7 import flex_directory, usecode_inventory


def _member(archive, slot, name):
    directory = flex_directory(archive)
    if not 0 <= slot < len(directory) or not directory[slot][1]:
        raise ValueError(f"Missing {name} slot {slot}")
    offset, length = directory[slot]
    return archive[offset:offset + length], offset


def face_frame(shape, frame):
    """Read one DOS shape's signed-origin spans; unwritten pixels are transparent."""
    if len(shape) < 8:
        raise ValueError("Short face shape")
    length, first = struct.unpack_from("<II", shape)
    if length != len(shape) or first < 8 or first % 4 or first >= length:
        raise ValueError("Invalid face frame directory")
    offsets = [v for v, in struct.iter_unpack("<I", shape[4:first])] + [length]
    if not 0 <= frame < len(offsets) - 1 or any(a >= b for a, b in zip(offsets, offsets[1:])):
        raise ValueError("Invalid face frame offsets or frame number")
    data = memoryview(shape)[offsets[frame]:offsets[frame + 1]]
    cursor = 0

    def take(size):
        nonlocal cursor
        if cursor + size > len(data):
            raise ValueError("Truncated face span or missing terminator")
        chunk = data[cursor:cursor + size]
        cursor += size
        return chunk

    right, left, above, below = struct.unpack("<hhhh", take(8))
    width, height = left + right + 1, above + below + 1
    if not 0 < width <= 1024 or not 0 < height <= 1024:
        raise ValueError("Invalid face extents")
    pixels = [None] * (width * height)
    while True:
        tag, = struct.unpack("<H", take(2))
        if tag == 0:
            break
        span = tag >> 1
        dx, dy = struct.unpack("<hh", take(4))
        x, y = left + dx, above + dy
        if not span or x < 0 or y < 0 or y >= height or x + span > width:
            raise ValueError("Face span exceeds frame bounds")
        start = y * width + x
        if any(value is not None for value in pixels[start:start + span]):
            raise ValueError("Overlapping face spans")
        if not tag & 1:
            pixels[start:start + span] = take(span)
            continue
        written = 0
        while written < span:
            packet = take(1)[0]
            count = packet >> 1
            if not count or written + count > span:
                raise ValueError("Invalid RLE run in face span")
            run = [take(1)[0]] * count if packet & 1 else take(count)
            pixels[start + written:start + written + count] = run
            written += count
    if cursor != len(data):
        raise ValueError("Unexpected bytes after the end of the face frame")
    return width, height, pixels, offsets[frame], (left, above)


def compile_gump(width, height, pixels, palette):
    """Encode ClassicUO RGB555 runs with a distinct value for transparent pixels."""
    if len(palette) != 768 or width <= 0 or height <= 0 or len(pixels) != width * height:
        raise ValueError("Invalid portrait dimensions or palette")
    lookup, runs, rgba = bytearray(), bytearray(), bytearray()
    for y in range(height):
        lookup += struct.pack("<I", height + len(runs) // 4)
        colors = []
        for index in pixels[y * width:(y + 1) * width]:
            if index is None:
                colors.append(0)
                rgba.extend(bytes(4))
                continue
            r, g, b = palette[index * 3:index * 3 + 3]
            if max(r, g, b) > 63:
                raise ValueError(f"Used palette index {index} exceeds the VGA DAC range")
            r, g, b = r >> 1, g >> 1, b >> 1
            # Zero uniquely represents transparency; 0x8000 preserves opaque black.
            colors.append(0x8000 | (r << 10) | (g << 5) | b)
            rgba.extend((r * 255 // 31, g * 255 // 31, b * 255 // 31, 255))
        for color, run in groupby(colors):
            runs += struct.pack("<HH", color, sum(1 for _ in run))
    return lookup + runs, rgba


def _preview_png(width, height, rgba):
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
    header = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    stride = width * 4
    lines = b"".join(b"\x00" + rgba[pos:pos + stride] for pos in range(0, len(rgba), stride))
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", zlib.compress(lines, 9)) + chunk(b"IEND", b"")


def _speaker(usecode):
    record = next((r for r in usecode_inventory(usecode)["records"] if r["id"] == 0x40C), None)
    if record is None:
        raise ValueError("No Finnigan function 0x040C in this edition")
    code = usecode[record["code_offset"]:record["code_offset"] + record["code_length"]]
    # Event 1 is tested at function entry. Its observed fall-through begins by
    # pushing frame zero, NPC reference -12 and calling BG intrinsic 0x03 (two args).
    if (code[:6] != bytes.fromhex("48 1f 01 00 22 05") or
            code[8:18] != bytes.fromhex("1f 00 00 1f f4 ff 39 03 00 02")):
        raise ValueError("Unrecognized Finnigan show_npc_face call site")
    return {"function": 0x40C, "event": 1, "intrinsic": 3, "npc_ref": -12,
            "call_file_offset": record["code_offset"] + 14}


def produce_portrait(u7_root, output_dir, actor=None, *, frame=0):
    root, output = Path(u7_root), Path(output_dir)
    if output.resolve().is_relative_to(root.resolve()):
        raise ValueError("Portrait output must be outside the U7 installation")
    def child(directory, name):
        matches = [p for p in directory.iterdir() if p.name.casefold() == name.casefold()]
        if len(matches) != 1:
            raise ValueError(f"Expected one {name} in {directory}")
        return matches[0]
    static = child(root, "STATIC")
    files = {name: child(static, name).read_bytes() for name in ("USECODE", "FACES.VGA", "PALETTES.FLX")}
    if actor is None:
        binding = _speaker(files["USECODE"])
        character, face = "Finnigan", -binding["npc_ref"]
    else:
        binding = {"function": actor["function_id"], "npc_ref": -actor["npc_slot"],
                   "source_actor_id": actor["id"], "face_file_offset": actor["file_offset"] + 29}
        character, face = actor["name"], actor["face"]
    shape, shape_offset = _member(files["FACES.VGA"], face, "FACES.VGA")
    palette, palette_offset = _member(files["PALETTES.FLX"], 0, "PALETTES.FLX")
    width, height, pixels, frame_offset, origin = face_frame(shape, frame)
    data, rgba = compile_gump(width, height, pixels, palette)
    # This is a private, standalone archive; IDs must be allocated again at facet integration.
    gump_id = face
    index = struct.pack("<iii", -1, -1, -1) * gump_id + struct.pack("<III", 0, len(data), width << 16 | height)
    report = {
        "schema": 1, "character": character, "binding": binding, "shape": face, "frame": frame,
        "shape_offset": shape_offset, "frame_file_offset": shape_offset + frame_offset,
        "palette_slot": 0, "palette_offset": palette_offset, "origin": list(origin),
        "width": width, "height": height, "opaque_pixels": sum(p is not None for p in pixels),
        "gump_id": gump_id, "source_sha256": {n: hashlib.sha256(b).hexdigest() for n, b in files.items()},
        "expected_rgba_sha256": hashlib.sha256(rgba).hexdigest(),
        "scope": "Standalone portrait archive. Target palette uses five bits per channel.",
    }
    output.mkdir(parents=True, exist_ok=True)
    (output / "gumpart.mul").write_bytes(data)
    (output / "gumpidx.mul").write_bytes(index)
    (output / "preview.png").write_bytes(_preview_png(width, height, rgba))
    (output / "portrait.json").write_text(json.dumps(report, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    return report
