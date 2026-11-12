"""Compare the converted source indices with Exult's independently decoded frame."""

import argparse
import hashlib
import json
import struct
import subprocess
import tempfile
from pathlib import Path

from u7uo.portrait import face_frame
from u7uo.u7 import flex_directory


def pcx_indices(data):
    if len(data) < 128 or data[:4] != bytes((10, 5, 1, 8)) or data[65] != 1:
        raise ValueError("Expected an 8-bit, single-plane Exult PCX")
    left, top, right, bottom = struct.unpack_from("<HHHH", data, 4)
    width, height = right - left + 1, bottom - top + 1
    stride, = struct.unpack_from("<H", data, 66)
    if width <= 0 or height <= 0 or stride < width:
        raise ValueError("Invalid PCX layout")
    scanlines = bytearray()
    pos = 128
    while len(scanlines) < height * stride:
        if pos >= len(data):
            raise ValueError("Truncated PCX packet")
        value, count = data[pos], 1
        pos += 1
        if value >= 0xC0:
            count = value & 63
            if not count or pos == len(data):
                raise ValueError("Invalid PCX run")
            value = data[pos]
            pos += 1
        scanlines.extend([value] * count)
    if len(scanlines) != height * stride:
        raise ValueError("Overlong PCX scanlines")
    return width, height, b"".join(scanlines[y * stride:y * stride + width] for y in range(height))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(r"E:\UltimaOffline"))
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    static = args.root / "Assets/UltimaVII-Steam/STATIC"
    executable = args.root / "Tools/ExultTools/tools/shp2pcx.exe"
    cache = args.root / "Cache/Readback"
    scratch = Path(tempfile.mkdtemp(prefix="portrait-oracle-", dir=cache))
    names = ("face.shp", "colors.pal", "face00.pcx")
    try:
        for filename, slot, target in (("FACES.VGA", 12, names[0]), ("PALETTES.FLX", 0, names[1])):
            data = (static / filename).read_bytes()
            start, length = flex_directory(data)[slot]
            (scratch / target).write_bytes(data[start:start + length])
        subprocess.run([str(executable), names[0], "face", names[1]], cwd=scratch, check=True, timeout=60)
        width, height, pixels, _, origin = face_frame((scratch / names[0]).read_bytes(), 0)
        decoded_width, decoded_height, indices = pcx_indices((scratch / names[2]).read_bytes())
        if (width, height) != (decoded_width, decoded_height) or bytes(p or 0 for p in pixels) != indices:
            raise ValueError("Exult's decoded frame differs from the converter")
        result = dict(status="passed", shape=12, frame=0, width=width, height=height,
                      pixel_indices_matching=len(indices), origin=origin, opaque_black_index=pixels.count(0),
                      transparent=pixels.count(None), indexed_sha256=hashlib.sha256(indices).hexdigest(),
                      exult_binary_sha256=hashlib.sha256(executable.read_bytes()).hexdigest(),
                      scope="Exult PCX flattens transparent pixels to index zero. Alpha is tested with ClassicUO.")
        if args.report:
            args.report.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        print(f"Matched {len(indices)} Exult PCX palette indices ({width} by {height}).")
    finally:
        for name in names:
            (scratch / name).unlink(missing_ok=True)
        scratch.rmdir()


if __name__ == "__main__":
    main()
