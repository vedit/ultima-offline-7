"""Compare the original DOS mountain boundary with an ordinary private-facet replay."""

import argparse
import hashlib
import json
import struct
from pathlib import Path

from tools.oracle.departure import _frame
from u7uo.u7 import seed_directory


def avatar_xy(raw):
    members = seed_directory(raw)
    def member(name):
        _, offset, size = members[name]
        return raw[offset:offset+size]
    npcs, items = member("u7nbuf.dat"), member("u7ibuf.dat")
    handle, = struct.unpack_from("<H",npcs,2)
    if not handle or handle%8 or handle+8>len(items):
        raise ValueError("Invalid original Avatar handle")
    _, xy, _, extra = struct.unpack_from("<4H",items,handle)
    if not extra or extra%8 or extra+8>len(items) or items[extra+2]>=144:
        raise ValueError("Invalid original Avatar extension or region")
    region = items[extra+2]
    return [region%12*256+(xy&255),region//12*256+(xy>>8)]


def compare(root, session, target):
    session = session.resolve()
    receipt = json.loads((session/"receipt.json").read_bytes())
    if receipt.get("scene_setup",{}).get("method")!="Original F2 debug menu":
        raise ValueError("Expected the original game teleport setup")
    for name in ("U7.EXE","STATIC/U7MAP","STATIC/U7CHUNKS","STATIC/TFA.DAT","STATIC/INITGAME.DAT"):
        raw = (root/"Assets/UltimaVII-Steam"/name).read_bytes()
        if hashlib.sha256(raw).hexdigest()!=receipt["inputs"][name]["sha256"]:
            raise ValueError(f"Original game input differs for {name}")
    proof = json.loads(target.read_bytes())
    replay = proof["player_replay"]
    route = replay["walking"]
    fixture = route["mountain_fixture"]
    denied = route["rejected_mountain_step"]
    if (proof["integrity"]!="passed" or replay["status"]!="passed" or not replay["saved_and_restarted"]
            or (fixture["x"],fixture["y"],fixture["shape"],fixture["frame"])!=(499,2319,395,2)
            or denied["packet"]!="0x21" or denied["direction"]!=4):
        raise ValueError("Missing converted player collision proof")
    frames = [_frame(session,receipt,label)[0] for label in
              ("start-location","after-walking-west","attempt-south-into-mountain")]
    for before,after,point in zip(frames,frames[1:],[(129/320,.49),(.5,.68)]):
        right = [a for a in receipt["actions"] if before["elapsed_ms"]<a["elapsed_ms"]<after["elapsed_ms"]
                 and a["type"]=="click" and a.get("button")==1]
        if len(right)!=1 or (right[0]["x"],right[0]["y"])!=point:
            raise ValueError("Missing original ordinary movement input")
    saves = []
    for label in ("start","west","blocked"):
        name = f"mountain-{label}-GAME05.U7"
        raw = (session/name).read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        if not any(c["file"]==name and c["sha256"]==digest and c["bytes"]==len(raw) for c in receipt["checkpoints"]):
            raise ValueError(f"Unverified native save {name}")
        saves.append({"file":name,"sha256":digest,"avatar_xy":avatar_xy(raw)})
    original = [s["avatar_xy"] for s in saves]
    converted = [replay["start"][:2],route["approach"][:2],denied["position"][:2]]
    if (original != [[497,2315],[496,2315],[496,2315]] or original != converted
            or route["saved_position_after_restart"]!=[*original[-1],0]):
        raise ValueError("Original and converted mountain movement differ")
    assets = Path(proof["loaders"]["client_effective_map"]).parent
    facet = json.loads((assets.parent/"facet.json").read_bytes())
    if facet["build_id"]!=proof["build_id"]:
        raise ValueError("Staged map belongs to a different player replay")
    footprints = []
    with (assets/"staidx0.mul").open("rb") as index, (assets/"statics0.mul").open("rb") as data:
        for x,y in [original[0],original[1],[496,2316]]:
            block = x//8*(facet["height"]//8)+y//8
            index.seek(12*block)
            at,size,_ = struct.unpack("<iii",index.read(12))
            records = []
            if size:
                data.seek(at)
                for art,dx,dy,z,hue in struct.iter_unpack("<HBBbH",data.read(size)):
                    if (dx,dy)==(x%8,y%8):
                        records.append([art,z,hue])
            footprints.append({"xy":[x,y],"statics":records})
    if [f["statics"] for f in footprints] != [[],[],[[art,z,0] for art,z in fixture["target_layers"]]]:
        raise ValueError("Unexpected additional obstacle on the mountain route")
    return {"status":"passed","edition":"Steam FORGE","original_session":str(session),
            "scene_setup":receipt["scene_setup"],"original_saves":saves,"original_frames":frames,
            "target_build":proof["build_id"],"fixture_id":fixture["id"],"attempted_xy":[496,2316],
            "converted_xy":converted,"staged_cells":footprints,"reopened":route["saved_position_after_restart"]}


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("installation",type=Path)
    parser.add_argument("session",type=Path)
    parser.add_argument("target",type=Path)
    args=parser.parse_args()
    print(json.dumps(compare(args.installation,args.session,args.target),indent=2))
