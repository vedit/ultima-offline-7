"""Exercise the production map readers using only authored synthetic terrain."""

import argparse
import json
import struct
import subprocess
import tempfile
from contextlib import contextmanager
from pathlib import Path


def make_profile(directory):
    # Rectangular offsets and unique signed heights expose a transposition or lost sign.
    width, height = 16, 24
    cells = [{"x": x, "y": y, "land_id": 0x30 + x + y * width, "z": x - 2 * y}
             for y in range(height) for x in range(width)]
    terrain = bytearray()
    for bx in range(width // 8):
        for by in range(height // 8):
            terrain.extend(bytes(4))
            for dy in range(8):
                for dx in range(8):
                    cell = cells[(by * 8 + dy) * width + bx * 8 + dx]
                    terrain.extend(struct.pack("<Hb", cell["land_id"], cell["z"]))
    (directory / "map0.mul").write_bytes(terrain)
    # Block (1,1), local (2,5). Duplicate placement checks multiset cardinality.
    marker = dict(id=219, x=10, y=13, z=-7, hue=31)
    indices = [struct.pack("<III", 0xffffffff, 0, 0)] * 6
    indices[4] = struct.pack("<III", 0, 14, 0)
    (directory / "staidx0.mul").write_bytes(b"".join(indices))
    (directory / "statics0.mul").write_bytes(struct.pack("<HBBbH", 219, 2, 5, -7, 31) * 2)
    (directory / "terrain.json").write_text(json.dumps(dict(width=width, height=height, cells=cells,
                                                            statics=[marker, marker])), encoding="utf-8")
    return terrain


def add_conflicting_uop(directory, terrain):
    # One uncompressed entry for the standard UO key build/map0legacymul/00000000.dat.
    payload = bytearray(terrain)
    struct.pack_into("<Hb", payload, 4, 1, 17)
    header = struct.pack("<IIIQII", 0x50594d, 5, 0xfd23ec43, 28, 1, 1)
    index = struct.pack("<IQ", 1, 0)
    record = struct.pack("<QIIIQIH", 74, 0, len(payload), len(payload), 0xdbb7afa433a3764b, 0, 0)
    (directory / "map0LegacyMUL.uop").write_bytes(header + index + record + payload)
    # The production installation-type check uses presence, not contents, for this file.
    (directory / "MainMisc.uop").touch()


def run(root, directory):
    command = [str(root / "Tools/dotnet/dotnet.exe"), str(root / "Cache/Readback/bin/Readback.dll"), str(directory)]
    result = subprocess.run(command, capture_output=True, text=True, timeout=60)
    if not result.stdout.strip():
        raise RuntimeError(result.stderr or f"readback exited {result.returncode} without JSON")
    return result.returncode, json.loads(result.stdout)


@contextmanager
def fixture_dir(parent):
    directory = Path(tempfile.mkdtemp(prefix="terrain-fixture-", dir=parent))
    try:
        yield directory
    finally:
        for name in ("terrain.json", "map0.mul", "staidx0.mul", "statics0.mul", "MainMisc.uop", "map0LegacyMUL.uop"):
            (directory / name).unlink(missing_ok=True)
        directory.rmdir()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(r"E:\UltimaOffline"))
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    with fixture_dir(args.root / "Cache/Readback") as directory:
        terrain = make_profile(directory)
        code, clean = run(args.root, directory)
        if code != 0 or clean["cells_matching_both_and_expected"] != 384:
            raise RuntimeError(f"asymmetric proof failed: {clean}")
        if not clean["statics"]["matched"] or clean["statics"]["expected_count"] != 2:
            raise RuntimeError("Both loaders must return the duplicate signed-Z static witness.")
        static_file = directory / "statics0.mul"
        old_statics = static_file.read_bytes()
        changed = bytearray(old_statics)
        changed[4] = 1
        static_file.write_bytes(changed)
        code, static_mismatch = run(args.root, directory)
        if code != 1 or static_mismatch["statics"]["matched"]:
            raise RuntimeError("Changed static lift went undetected")
        static_file.write_bytes(old_statics)
        add_conflicting_uop(directory, terrain)
        code, conflict = run(args.root, directory)
        if (code != 1 or conflict.get("same_effective_file") is not False or
                conflict.get("cells_with_loader_disagreement") != 1):
            raise RuntimeError(f"stock-precedence conflict went undetected: {conflict}")
        (directory / "map0LegacyMUL.uop").unlink()
        index = (directory / "staidx0.mul").read_bytes()
        (directory / "staidx0.mul").write_bytes(struct.pack("<III", 0, 7 * 1025, 0) + index[12:])
        (directory / "statics0.mul").write_bytes(bytes(7 * 1025))
        code, overflow = run(args.root, directory)
        if code != 1 or "overfull static block 0" not in overflow.get("diagnostic", ""):
            raise RuntimeError(f"1025-entry static block went undetected: {overflow}")
    report = dict(status="passed", asymmetric=clean, changed_static=static_mismatch, conflicting_resources=conflict,
                  overfull_statics=overflow)
    if args.report:
        args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print("Passed 384 asymmetric signed-height cells; detected conflicting UOP and 1,025-entry static block.")


if __name__ == "__main__":
    main()
