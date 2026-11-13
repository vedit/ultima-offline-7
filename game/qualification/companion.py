"""Construct paired DOS controls in the same native chunk with an exhausted route budget."""
import json
import struct
from baseline import actor
from reference import ROOT, checked, members

def create():
    seed = ROOT/"fixtures"/"Iolo-on-route.U7"
    checked(seed,"ecf980b7b4db0ff81a317486cb00423330694acd4091a62397ea6e941fe4db5c")
    original = seed.read_bytes()
    contents = members(seed)
    iolo = actor(contents,1)
    cx,cy = struct.unpack_from("<HH", contents["MAPCOORD.DAT"])
    handle = iolo["handle"]
    assert contents["PARTY"][20] & 6 == 6
    assert struct.unpack_from("<H",contents["PATH0.DAT"],21)[0] == handle
    directory = {}
    for index in range(struct.unpack_from("<I", original,84)[0]):
        at,size = struct.unpack_from("<II", original,128+8*index)
        if size:
            directory[original[at:at+13].split(b"\0")[0].decode()] = at+13
    summary = []
    for case,dy in [("inside",11),("edge",12),("outside",13)]:
        data = bytearray(original)
        x,y,z = iolo["xyz"]
        yy = cy + dy
        assert yy//16 == y//16 and abs(x-cx) <= 20
        data[directory["U7IBUF.DAT"]+handle+3] = yy%256
        # Native Route::walk compares attempts to limit+limit/2 before moving.
        # The original route is intact. Only its saved budget and actor Y are staged.
        struct.pack_into("<HH",data,directory["PATH0.DAT"]+2,18,11)
        target = ROOT/"fixtures"/f"Iolo-{case}.U7"
        target.write_bytes(data)
        summary.append(dict(case=case, camera=[cx,cy], iolo=[x,yy,z], attempts=18, limit=11,
            changed_offsets=[n for n,(a,b) in enumerate(zip(original,data)) if a!=b]))
    (ROOT/"evidence"/"companion-setup.json").write_text(json.dumps(summary,indent=2)+"\n")

if __name__ == "__main__":
    create()
