"""Compare a legitimate earned Trinsic crossing in DOS and on the converted facet."""

import argparse
import hashlib
import json
from pathlib import Path

from tools.oracle.reward import compare_reward
from u7uo.u7 import seed_directory


def compare_departure(verification, session, installation, original):
    player = verification["player_replay"]
    journey = player["opening"]["journey"]
    source_sha = hashlib.sha256((installation/"Assets/UltimaVII-Steam/STATIC/USECODE").read_bytes()).hexdigest()
    if (verification["source_edition"]!="expanded" or player["status"]!="passed"
            or journey["guard_before_password"]["source_usecode_sha256"]!=source_sha
            or not player["opening"]["checks"]["final_gate_and_reward_after_restart"]
            or original["status"]!="passed"):
        raise ValueError("A qualified original continuation and a successful same-edition player journey are required")
    checkpoints = original["checkpoints"]
    native_receipt = json.loads((session/"receipt.json").read_bytes())
    def checkpoint(name):
        row = checkpoints[name]
        filename = row["save_file"]
        if Path(filename).name!=filename:
            raise ValueError("Original checkpoint must name a file in its session")
        data = (session/filename).read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        if digest!=row["save_sha256"] or not any(
                c["file"]==filename and c["sha256"]==digest for c in native_receipt["checkpoints"]):
            raise ValueError(f"DOS save identity differs at {name}")
        _,off,length = seed_directory(data)["flaginit"]
        flags = data[off:off+length]
        if any(flags[int(i)]!=v for i,v in row["flags"].items()):
            raise ValueError(f"Original recorded flags differ from native save at {name}")
        return row,flags
    stages = {}
    for name,witness,flag in (("spark-hook","Spark",67),("gilberto-ship","Gilberto",64)):
        row,flags = checkpoint(name)
        visit = journey[witness]
        if flags[61] or flags[flag]!=1 or visit["flag"]!=flag or visit["result"]!=1:
            raise ValueError(f"Witness outcome differs for {witness}")
        stages[name] = {"dos_save_sha256":row["save_sha256"],"flag":flag,"value":1,
                        "uo_registry_sha256":visit["registry_sha256"]}
    earned,flags = checkpoint("earned-password")
    common = (60,61,62,64,67,68,72,90,94,95,96,97,98,99)
    if any(flags[i]!=1 or journey["report_flags"].get(str(i))!=flags[i] for i in common):
        raise ValueError("The original report flags disagree at the earned password")
    stages["password"] = {"dos_save_sha256":earned["save_sha256"],"matching_flags":list(common)}
    raised,_ = checkpoint("gate-open")
    outside,_ = checkpoint("outside-east-gate")
    original_gate = raised["gate"]
    gx,gy = original_gate["anchor"]
    cells = sorted(original_gate["cells"])
    opened = journey["opened"]
    end = opened["physical_crossing_test"]["outside_position"]
    first = journey["guard_before_password"]
    if (original_gate["shape"]!=271 or original_gate["lift"]!=4 or original_gate["frame"]!=0
            or original_gate["handle"]!=outside["gate"]["handle"]
            or sorted([gx,int(y)] for y in opened["wire_footprint"])!=cells
            or any(r[2]!=first["gate_id"] or r[3]!="0607" for r in opened["lift_callbacks"])
            or [int(r[5]) for r in opened["lift_callbacks"]]!=[1,2,3,4]
            or not (raised["avatar_xy"][0]<gx<outside["avatar_xy"][0] and end[0]>gx)):
        raise ValueError("Successful original and converted gate footprints, lifts or passage disagree")
    stages["crossing"] = {"dos_gate_save":raised["save_sha256"],"dos_outside_save":outside["save_sha256"],
                          "original_gate_handle":original_gate["handle"],"source_id":first["gate_id"],
                          "source_lift":4,"footprint":cells,"dos_endpoint":outside["avatar_xy"],
                          "uo_endpoint":end,"uo_registry_sha256":opened["native_registry_sha256"]}
    reclosed,_=checkpoint("gate-reclosed")
    blocked,_=checkpoint("blocked-reentry")
    closed=journey["closed"]
    collision=closed["physical_crossing_test"]
    restored=journey["restored"]["blocked_walk"]
    observed_outside=opened["physical_crossing_test"].get("dos_checkpoint_position")
    if (any(row["gate"]["handle"]!=original_gate["handle"] or row["gate"]["lift"]!=0
            or sorted(row["gate"]["cells"])!=cells for row in (reclosed,blocked))
            or closed["gate_id"]!=first["gate_id"] or sorted([gx,int(y)] for y in closed["wire_footprint"])!=cells
            or any(r[2]!=first["gate_id"] or r[3]!="0609" for r in closed["lift_callbacks"])
            or [int(r[5]) for r in closed["lift_callbacks"]]!=[3,2,1,0]
            or collision["packet"]!="0x21" or restored["packet"]!="0x21"
            or restored["position"]!=collision["position"]):
        raise ValueError("Gate identity, lowering, footprint or restored collision differs")
    if observed_outside is not None and (
            observed_outside!=outside["avatar_xy"]+[0] or closed["talk_position"]!=reclosed["avatar_xy"]+[0]
            or collision["position"]!=blocked["avatar_xy"]+[0] or
            any(r["direction"]!=6 for r in (collision,restored))):
        raise ValueError("Original outside guard interaction or westbound reentry differs")
    stages["reclosure"]={"dos_closed_save_sha256":reclosed["save_sha256"],"dos_blocked_save_sha256":blocked["save_sha256"],
                         "dos_guard_talk":reclosed["avatar_xy"],"uo_guard_talk":closed.get("talk_position"),
                         "dos_blocked":blocked["avatar_xy"],"uo_blocked":collision["position"],
                         "restored_blocked":restored["position"],"same_exterior_approach":observed_outside is not None}
    previous = next(c for c in native_receipt["checkpoints"] if c["file"].startswith("return-to-mayor-"))
    before = session/previous["file"]
    if hashlib.sha256(before.read_bytes()).hexdigest()!=previous["sha256"]:
        raise ValueError("Original pre-report save digest differs")
    reward = compare_reward(before,session/earned["save_file"],journey["reward"])
    return {"build_id":verification["build_id"],"source_usecode_sha256":source_sha,
            "earned_departure":"passed","checkpoints":stages,"reward_comparison":reward,
            "native_continuation":original["native_continuation"]}


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("verification",type=Path)
    parser.add_argument("dos_session",type=Path)
    parser.add_argument("--installation",type=Path,required=True)
    args=parser.parse_args()
    raw=args.verification.read_bytes()
    oracle=(args.dos_session/"earned-departure-check.json").read_bytes()
    result=compare_departure(json.loads(raw),args.dos_session,args.installation,json.loads(oracle))
    result.update(verification_sha256=hashlib.sha256(raw).hexdigest(),original_receipt_sha256=hashlib.sha256(oracle).hexdigest())
    print(json.dumps(result,indent=2))
