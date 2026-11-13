"""Drive the pinned portable game through the stock save dialog and read its output."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
import shutil

from reference import ROOT, members, stage, sha

def actor(saved, slot):
    npcs, items = saved["U7NBUF.DAT"], saved["U7IBUF.DAT"]
    offset = slot * 105
    record = npcs[offset:offset+105]
    handle, = struct.unpack_from("<H", record, 2)
    _, xy, shape, ext = struct.unpack_from("<4H", items, handle)
    region = items[ext + 2]
    level = record[82]
    if level >= 5:
        raise ValueError("invalid NPC schedule level")
    return {"slot":slot, "handle":handle, "name":record[89:105].split(b"\0")[0].decode("cp437"),
            "xyz":[(region % 12)*256 + (xy & 255), (region // 12)*256 + (xy >> 8), items[ext+5] >> 4],
            "shape":shape & 1023, "frame":shape >> 10, "work":record[10],
            "schedules":list(struct.iter_unpack("<BBhhB",record[46:46+7*(level+1)]))}

def state(saved):
    party = saved["PARTY"]
    handles = struct.unpack_from("<8H", party)[:party[16]]
    return {"clock":struct.unpack("<3H",saved["GAMETIMM.DAT"]),
            "rng":int.from_bytes(saved["RANDSEED.DAT"], "little"),
            "actors":[actor(saved,i) for i in (0,1,2,12)],
            "party":handles, "party_flags":list(party[18:18+party[16]]),
            "camera":saved["MAPCOORD.DAT"].hex(),
            "active_routes":[dict(slot=i,owner=struct.unpack_from("<H",saved["PATH.DAT"],15+2*i)[0],
                data=saved[f"PATH{i}.DAT"].hex()) for i,flag in enumerate(saved["PATH.DAT"][:15]) if flag],
            "members":{name:hashlib.sha256(data).hexdigest() for name,data in sorted(saved.items())}}

def run(name, exe, fixed=False, fixture=None):
    stage(name)
    folder = ROOT / "runs" / name
    seed = ROOT / "fixtures" / "Finnigan-before-chair.U7"
    if fixture:
        seed = ROOT / "fixtures" / (fixture + ".U7")
        parts = members(seed)
        for path in (folder / "GAMEDAT").iterdir():
            if path.name not in parts:
                path.unlink()
        for key, value in parts.items():
            (folder / "GAMEDAT" / key).write_bytes(value)
    save = folder / "GAME02.U7"
    shutil.copyfile(seed,save)
    exe = exe.resolve(strict=True)
    timeline = ("6000 shot scene.ppm; 6300 key s; 7000 shot dialog.ppm; "
                "7100 move 154 54; 7300 down; 7480 up; 8000 move 188 157; 8200 down; 8380 up; "
                "8800 move 298 108; 9000 down; 9180 up; 10600 shot saved.ppm; 11200 quit")
    if fixed: timeline = "fixed; " + timeline
    command = [str(exe),"--data",str(folder),"--program","u7","-p"]
    env = dict(os.environ, U7_TEST_INPUT=timeline)
    log = folder / "engine.log"
    with log.open("wb") as output:
        p = subprocess.run(command,cwd=folder,env=env,stdout=output,stderr=subprocess.STDOUT,timeout=300)
    changed = sha(save) != sha(seed)
    evidence = dict(command=command,timeline=timeline, executable_sha256=sha(exe),
                    exit_code=p.returncode, native_save_changed=changed,
                    before=state(members(seed)), frames={f.name:sha(f) for f in folder.glob("*.ppm")})
    if changed:
        evidence["after"] = state(members(save))
    (folder/"result.json").write_text(json.dumps(evidence,indent=2)+"\n")
    print(log.read_text(errors="replace")[-3000:])
    print(f"Exit {p.returncode}, native save changed {changed}, frames {list(evidence['frames'])}")
    return 0 if p.returncode == 0 and changed and "scene.ppm" in evidence["frames"] else 1

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("name")
    parser.add_argument("--exe",type=Path,default=ROOT/"build-host"/"playtest"/"Ultima7.exe")
    parser.add_argument("--fixed",action="store_true")
    parser.add_argument("--fixture",choices=["Iolo-inside","Iolo-edge","Iolo-outside"])
    args = parser.parse_args()
    raise SystemExit(run(args.name,args.exe,args.fixed,args.fixture))
