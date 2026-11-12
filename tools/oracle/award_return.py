"""Check the actual DOS party-list result before Finnigan's XP loop and compare the earned reward."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import struct

from .party_award import compare, digest, progress, verify_snapshot
from u7uo.u7 import STEAM_FORGE_USECODE, usecode_inventory


def verify_observer(root, receipt):
    game = root/"Assets/UltimaVII-Steam"
    raw = (game/"STATIC/USECODE").read_bytes()
    if hashlib.sha256(raw).hexdigest() != STEAM_FORGE_USECODE:
        raise ValueError("Expected the qualified Steam Forge archive")
    fn, = (r for r in usecode_inventory(raw)["records"] if r["id"] == 0x911)
    source, record = fn["code_offset"], fn["offset"]
    # The observer only uses the temporaries that the original loop overwrites.
    # It formats length, next index and the element, then resumes at original PC 7.
    loop = bytes.fromhex("44 7c 12 0500 2e 02 0200 0300 0400 0100 1300 "
                         "2f 0300 2f 0500 2f 0200 2f 0500 2f 0400 33 06 e2ff")
    trace = receipt["award_trace"]
    if (raw[source:source+7] != bytes.fromhex("38230000120100") or trace["source_offset"] != source
            or trace["insert_after_pc"] != 7 or bytes.fromhex(trace["inserted_hex"]) != loop):
        raise ValueError("The original call or the observation point changed")
    private = bytearray(raw[:source+7] + loop + raw[source+7:])
    size, = struct.unpack_from("<H", raw, record+2)
    struct.pack_into("<H", private, record+2, size+len(loop))
    dep1 = bytearray((game/"STATIC/LINKDEP1").read_bytes())
    dep2 = bytearray((game/"STATIC/LINKDEP2").read_bytes())
    entries = [o for o, in struct.iter_unpack("<I", dep2)]
    groups = []
    for fid in range(len(dep1)//4-1):
        start, length, end = struct.unpack_from("<HHH", dep1, 4*fid)
        count = entries[start:end].count(record)
        if count:
            groups.append(fid)
            struct.pack_into("<H", dep1, 4*fid+2, length+count*len(loop))
    if groups != trace["preload_groups"] or 0x40c not in groups:
        raise ValueError("Finnigan's loader must contain the traced routine")
    for i, offset in enumerate(entries):
        if offset > record:
            struct.pack_into("<I", dep2, i*4, offset+len(loop))
    changes = {"STATIC/USECODE":private,"STATIC/LINKDEP1":dep1,"STATIC/LINKDEP2":dep2}
    for name, info in receipt["inputs"].items():
        data = changes[name] if name in changes else (game/name).read_bytes()
        if len(data) != info["bytes"] or hashlib.sha256(data).hexdigest() != info["sha256"]:
            raise ValueError(f"Unverified guest input {name}")
    parent = json.loads(Path(receipt["native_continuation"]["original_receipt"]).read_bytes())
    if (set(parent["inputs"]) != set(receipt["inputs"]) or
            any(digest(game/name) != info["sha256"] for name,info in parent["inputs"].items()) or
            digest(root/"Tools/js-dos-8.5.3/package/dist/wdosbox.wasm") != receipt["wasm_sha256"]):
        raise ValueError("Changed installed game or DOS emulator")
    return source


def read_element(memory, index, length):
    pattern = rb"(?<![0-9])([1-8])\|"+str(index+1).encode()+rb"\|([0-9]{1,5})\x00"
    matches = list(re.finditer(pattern, memory))
    values = {(int(m[1]), int(m[2])) for m in matches}
    if len(values) != 1:
        raise ValueError("Missing or ambiguous live DOS formatter result")
    count, handle = values.pop()
    if count != length or index > count or not 0 < handle <= 65535 or handle % 8:
        raise ValueError("Invalid native list element")
    return handle, {m.start() for m in matches}


def read_pages(session, root):
    receipt = json.loads((session/"receipt.json").read_bytes())
    source = verify_observer(root, receipt)
    checkpoint = receipt["native_continuation"]
    if (not receipt.get("finished") or digest(Path(checkpoint["source"])) != checkpoint["sha256"] or
            digest(session/"dosbox.conf") != receipt["config_sha256"]):
        raise ValueError("Incomplete or unverified native session")
    observations = receipt["party_observations"]
    rows = [r for r in observations if r.get("cache_snapshot",{}).get("file","").startswith("native-return-")]
    post, = (r for r in observations if r.get("cache_snapshot",{}).get("file") == "after-traced-award.bin")
    if not rows or not all(a["elapsed_ms"] < b["elapsed_ms"] for a,b in zip(rows, rows[1:]+[post])):
        raise ValueError("Missing or unordered native return observations")
    active, downed = rows[0]["active"], rows[0]["downed"]
    returned, pages = [], []
    common = None
    for index, row in enumerate(rows, 1):
        snap = verify_snapshot(session, row)
        if snap["file"] != f"native-return-{index}.bin" or row["active"] != active or row["downed"] != downed:
            raise ValueError("Changed party or missing native result element")
        memory = (session/snap["file"]).read_bytes()
        handle, offsets = read_element(memory, index, len(rows))
        if progress(row) != progress(rows[0]):
            raise ValueError("XP changed before inspection")
        common = offsets if common is None else common & offsets
        frame = min(receipt["frames"], key=lambda f:abs(f["elapsed_ms"]-row["elapsed_ms"]))
        if abs(frame["elapsed_ms"]-row["elapsed_ms"]) > 2000 or digest(session/frame["file"]) != frame["sha256"]:
            raise ValueError("Missing corresponding DOS renderer frame")
        pages.append({"index":index,"handle":handle,"snapshot":snap,"frame":frame["file"],"frame_sha256":frame["sha256"]})
        returned.append(handle)
    verify_snapshot(session, post)
    if (not common or returned != active[::-1] or set(downed) & set(returned)
            or any(post[k]!=rows[0][k] for k in ("active","downed"))):
        raise ValueError("DOS formatter buffers, actual return or party tables disagree")
    before, after = progress(rows[0]), progress(post)
    if ([h for h,_,_ in before] != [h for h,_,_ in after] or
            any(xp2-xp != (50 if h in returned else 0) for (h,xp,_),(_,xp2,_) in zip(before,after))):
        raise ValueError("The resumed original XP loop disagrees with the observed result")
    return {"session":str(session),"source_offset":source,"checkpoint_sha256":checkpoint["sha256"],
            "active":active,"downed":downed,"returned":returned,"pages":pages,
            "formatter_addresses":sorted(common),"before":before,"after":after}


def qualify(root, baseline_file, downed_session, recovered_session):
    baseline = json.loads(baseline_file.read_bytes())
    baseline = compare(root, Path(baseline["dos_receipt"]).parent, Path(baseline["conditional"]), Path(baseline["healthy"]))
    down = read_pages(downed_session,root)
    recovered = read_pages(recovered_session,root)
    if not (down["checkpoint_sha256"] == recovered["checkpoint_sha256"] == baseline["before_sha256"]):
        raise ValueError("Conditions do not share the same earned checkpoint")
    actors = [baseline["party"][str(i)] for i in range(3)]
    handles = [actor["dos_before"]["handle"] for actor in actors]
    names = dict(zip(handles,(-356,-1,-2),strict=True))
    target = baseline["converted"]
    for key in ("Active","Downed","Returned"):
        if [names[h] for h in down[key.lower()]] != target[key]:
            raise ValueError(f"Converted {key} differs from the actual DOS instruction")
    if (down["downed"] != [handles[1]] or down["after"] != [(h,a["dos_after"]["experience"],a["dos_after"]["training"])
            for h,a in zip(handles,actors)] or recovered["downed"] or recovered["returned"][0] != handles[1]
            or recovered["before"] != down["before"] or target["xp_recipients"] != target["Returned"]
            or target["SourceOffset"] != down["source_offset"]):
        raise ValueError("Award conditions or post-award progress differ from the controls")
    return {"status":"passed","edition":"Steam Forge","downed_dos":down,"recovered_dos":recovered,
            "converted_downed":target,"unmodified_comparison":str(baseline_file),"reloaded_gold":baseline["reloaded_gold"],
            "recovered_converted_route":"not_run"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("installation","baseline","downed_session","recovered_session"):
        parser.add_argument(name,type=Path)
    args = parser.parse_args()
    print(json.dumps(qualify(args.installation,args.baseline,args.downed_session,args.recovered_session),indent=2))
