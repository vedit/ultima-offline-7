"""Freeze Steam FORGE reference inputs and unpack a DOS save into a new private run."""
from pathlib import Path
import argparse
import hashlib
import json
import re
import shutil
import struct
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from install_paths import INSTALL as SOURCE, RUNTIME as ROOT
EVIDENCE = SOURCE / "Evidence"
GAME = SOURCE / "Assets" / "UltimaVII-Steam"
CHAIR = EVIDENCE / "forge-chair-route-comparison-01.json"
DONOR = EVIDENCE / "dos-reference" / "session-30TQF4" / "observer-1-GAME02.U7"
PIN = "a244c201f3d50284be2d605a9d8926161c697e61397efae435d4681c71f73536"
INVESTIGATION = EVIDENCE / "dos-reference" / "session-jrKbjq" / "accepted-GAME00.U7"
INVESTIGATION_PIN = "8d772efc424a6d2d74c5da7d4ed2f37fc5be98b9a0849a80925b1b76eb1372dd"

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def checked(path, expected):
    actual = sha(path)
    if actual != expected:
        raise ValueError(f"{path}: expected {expected}, found {actual}")
    return actual

def members(path):
    data = path.read_bytes()
    count, = struct.unpack_from("<I", data, 0x54)
    result = {}
    for index in range(count):
        offset, size = struct.unpack_from("<II", data, 128 + index * 8)
        if size == 0:
            continue
        if offset < 128 + count * 8 or size < 13 or offset + size > len(data):
            raise ValueError(f"invalid member {index}")
        name = data[offset:offset+13].split(b"\0", 1)[0].decode("ascii")
        if not re.fullmatch(r"[A-Z0-9_]{1,8}(?:\.[A-Z0-9_]{1,3})?", name) or name in result:
            raise ValueError(f"invalid member name {name}")
        result[name] = data[offset+13:offset+size]
    return result

def freeze():
    native = json.loads(CHAIR.read_text())["native"]
    manifest = {"edition": "Steam FORGE development", "donor": checked(DONOR, PIN), "checkpoints": []}
    manifest["investigation"] = checked(INVESTIGATION, INVESTIGATION_PIN)
    for label in ("clear", "occupied"):
        row = native[label]
        session = EVIDENCE / "dos-reference" / row["session"]
        receipt = session / "receipt.json"
        checked(receipt, row["receipt_sha256"])
        for sample in row["samples"]:
            path = session / sample["file"]
            checked(path, sample["sha256"])
            saved = members(path)
            manifest["checkpoints"].append(dict(sample, case=label, file=str(path), receipt=str(receipt),
                members=len(saved), randseed=saved["RANDSEED.DAT"].hex(),
                states={k: hashlib.sha256(saved[k]).hexdigest() for k in
                    ("AV_FLAGS.DAT", "FLAGINIT", "PARTY", "U7NBUF.DAT", "U7IBUF.DAT", "PATH.DAT", "MAPCOORD.DAT")}))
    inputs = json.loads((EVIDENCE / "dos-reference" / native["clear"]["session"] / "receipt.json").read_text())["inputs"]
    manifest["installed_inputs"] = {k: checked(GAME / k,v["sha256"]) for k,v in inputs.items()
        if k.startswith("STATIC/") or k == "U7.EXE"}
    for folder in ("evidence", "fixtures", "runs"):
        (ROOT / folder).mkdir(parents=True, exist_ok=True)
    (ROOT / "evidence" / "dos-reference.json").write_text(json.dumps(manifest, indent=2) + "\n")
    shutil.copyfile(DONOR, ROOT / "fixtures" / "Finnigan-before-chair.U7")
    shutil.copyfile(INVESTIGATION, ROOT / "fixtures" / "Investigation.U7")
    print(f"Verified {len(manifest['installed_inputs'])} game files and {len(manifest['checkpoints'])} DOS checkpoints")

def stage(name):
    if not re.fullmatch("[a-zA-Z0-9_-]+", name):
        raise ValueError("use a simple run name")
    fixture = ROOT / "fixtures" / "Finnigan-before-chair.U7"
    checked(fixture, PIN)
    saved = members(fixture)
    dest = ROOT / "runs" / name
    dest.mkdir(parents=True, exist_ok=False)
    shutil.copytree(GAME / "STATIC", dest / "STATIC")
    shutil.copyfile(GAME / "U7.CFG", dest / "U7.CFG")
    (dest / "GAMEDAT").mkdir()
    for filename, data in saved.items():
        (dest / "GAMEDAT" / filename).write_bytes(data)
    print(f"{dest}: {len(saved)} private native save members")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage")
    args = parser.parse_args()
    freeze()
    if args.stage:
        stage(args.stage)
