"""Compile the original water below the Trinsic inventory witness."""

import hashlib
import struct
from pathlib import Path

from .terrain import TerrainSource, _child, _json_bytes, encode_land_mul


def water_material(tiledata):
    for land_id in range(168, 172):
        offset = land_id // 32 * 964 + 4 + land_id % 32 * 30
        flags, _, name = struct.unpack_from("<QH20s", tiledata, offset)
        if flags != 0xC0 or name.rstrip(b"\0") != b"water":
            raise ValueError(f"Unexpected water flags or material at UO land {land_id}")
    return 168, 4


def produce_water(u7_root, uo_root, output_dir):
    u7, uo, out = map(Path, (u7_root, uo_root, output_dir))
    if any(out.resolve().is_relative_to(p.resolve()) for p in (u7, uo)):
        raise ValueError("Water proof must be outside both input installations")
    static = _child(u7, "STATIC")
    raw = {name: _child(static, name).read_bytes() for name in ("U7MAP", "U7CHUNKS", "TFA.DAT")}
    raw["tiledata.mul"] = uo_data = _child(uo, "tiledata.mul").read_bytes()
    if len(uo_data) != 3188736 or len(raw["TFA.DAT"]) < 3072:
        raise ValueError("Unsupported UO tiledata or U7 TFA layout for water")
    first_water, variants = water_material(uo_data)
    source = TerrainSource(raw["U7MAP"], raw["U7CHUNKS"])
    left, top = 1136, 2208
    cells = []
    for y in range(16):
        for x in range(16):
            tile = source.tile(left + x, top + y)
            if tile["shape"] >= 150 or not raw["TFA.DAT"][tile["shape"] * 3] & 0x10:
                raise ValueError(f"Unmapped non-water at original tile ({left+x},{top+y})")
            cells.append({**tile, "x": x, "y": y, "z": 0, "land_id": first_water + tile["frame"] % variants})
    artifacts = {"map0.mul": encode_land_mul(16, 16, [(c["land_id"], 0) for c in cells]),
                 "staidx0.mul": struct.pack("<iii", -1, 0, 0) * 4, "statics0.mul": b""}
    report = {"schema": 1, "kind": "trinsic-barge-water", "source_origin": [left, top],
              "width": 16, "height": 16, "cell_count": 256, "blocks": 4, "cells": cells, "statics": [],
              "status": "water-substrate", "source_sha256": {k: hashlib.sha256(v).hexdigest() for k,v in raw.items()},
              "output_sha256": {k: hashlib.sha256(v).hexdigest() for k,v in artifacts.items()}}
    out.mkdir(parents=True, exist_ok=True)
    for name, value in artifacts.items():
        (out / name).write_bytes(value)
    (out / "terrain.json").write_bytes(_json_bytes(report))
    return report
