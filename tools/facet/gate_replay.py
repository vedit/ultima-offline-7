"""Observe the ordinary dock watch and closed east portcullis after the original opening."""
import json
import hashlib

from .player_replay import check_say, compressed_gump, open_actor, send_reply
from .stables_replay import path_to


def refuse_passage(conn, sample, campaign):
    seed = json.loads((campaign / "story-seed.json").read_bytes())
    guard = seed["actors"]["14"]
    pos = guard["source_position"]
    ox,oy = pos[:2]
    doc = json.loads((campaign / "dialogue.json").read_bytes())
    guard_script, = [f for f in doc["program"]["functions"] if f["id"] == guard["function_id"] == 0x040E]
    lines = {pc:guard_script["strings"][str(args[0])] for pc,op,args,_ in guard_script["rows"] if op == 0x1C}
    to_guard = path_to(sample,conn.position[:2],{(ox-1,oy),(ox+1,oy),(ox,oy-1),(ox,oy+1)})
    conn.walk(to_guard)
    conn.resync()
    serial = conn.actor(pos,"Johnson")
    page = open_actor(conn,serial)
    observations = []
    for pc,topic in ((0x96,"job"),(0xC3,"ship"),(0x139,"password"),(0x159,"Uhh, I don't know"),(0x1AA,"bye")):
        digest = check_say(page,lines[pc],f"040E:{pc:04X}")
        if 64014 not in page["images"]:
            raise ValueError("Johnson's original dockside portrait is absent")
        send_reply(conn,page,next(iter(page["buttons"])))
        shown = compressed_gump(conn.expect({0xDD}))
        choices = list(shown["buttons"].values())
        if topic not in choices or (pc==0x159 and ("Blackbird" in choices or len(choices)!=3)):
            raise ValueError(f"Missing or unexpected original guard response at {pc:04X}: {choices}")
        observations.append({"append_pc":pc,"say_sha256":digest,"choices":choices,"selected":topic,"portrait":64014})
        send_reply(conn,shown,next(k for k,v in shown["buttons"].items() if v==topic))
        if topic != "bye":
            page=compressed_gump(conn.expect({0xDD}))
    goodbye = compressed_gump(conn.expect({0xDD}))
    observations.append({"append_pc":0x1E7,"say_sha256":check_say(goodbye,lines[0x1E7],"040E:01E7")})
    send_reply(conn,goodbye,next(iter(goodbye["buttons"])))
    gate, = [g for g in seed["gate_objects"] if g["shape"]==271]
    gx,gy,gz = gate["position"]
    route = path_to(sample,conn.position[:2],{(gx-1,gy)})
    conn.walk(route)
    conn.resync()
    parts = {serial:p for serial,p in conn.ground_items.items() if p[0]==gate["uo_art"] and p[1]==gx and
             gy-gate["footprint"][1] < p[2] <= gy}
    if {tuple(p[1:]) for p in parts.values()}!={(gx,gy-i,gz*4) for i in range(gate["footprint"][1])}:
        raise ValueError(f"Original portcullis footprint is missing from the client view: {parts}")
    reject=conn.move(2,block=True)
    at=conn.resync()
    return {"status":"passed","guard":guard["id"],"guard_serial":serial,"guard_position":pos,"path_to_guard":to_guard,
            "conversation":observations,"path_to_gate":route,"gate_id":gate["id"],"closed_parts":parts,
            "blocked_move":reject,"server_position":list(at),"source_usecode_sha256":doc["source_sha256"]}


def compare_closed_gate(modern, original):
    source=original["closed_eastern_gate"]
    stop=source["blocked-east-gate"]
    start=source["east-gate-before-password"]
    guard=modern["player_replay"]["opening"]["dock_guard"]
    flags=modern["player_replay"]["opening"]["post_visit_flags"]
    visible={(p[1],p[2]) for p in guard["closed_parts"].values() if p[3]==0}
    if (guard["status"]!="passed" or flags.get("61",0)!=stop["flag61"] or stop["flag61"]!=0 or
            start["asset"]!=stop["asset"] or stop["asset"]["shape"]!=271 or
            set(map(tuple,stop["asset"]["cells"]))!=visible or guard["server_position"][:2]!=stop["avatar_xy"] or
            guard["blocked_move"]["packet"]!="0x21" or guard["blocked_move"]["direction"]!=2):
        raise ValueError("Original portcullis condition, footprint or eastward blocked walk differs")
    return {"status":"passed","build_id":modern["build_id"],"edition":original["edition"],"shape":271,
        "original_gate_handle":stop["asset"]["handle"],"converted_gate_id":guard["gate_id"],
        "original_saves":[start["save_sha256"],stop["save_sha256"]],"original_walk":source["ordinary_walk"],
        "matching_cells":sorted(visible),"matching_avatar_position":stop["avatar_xy"],"password_flag":0,
        "uo_packet":guard["blocked_move"]}


if __name__=="__main__":
    import argparse
    from pathlib import Path
    from tools.oracle.investigation import qualify_stable
    parser=argparse.ArgumentParser(description="Compare a private east-gate collision with original DOS native saves")
    parser.add_argument("verification",type=Path)
    parser.add_argument("dos_session",type=Path)
    parser.add_argument("--installation",type=Path,required=True)
    args=parser.parse_args()
    data=args.verification.read_bytes()
    result=compare_closed_gate(json.loads(data),qualify_stable(args.dos_session,args.installation))
    result["modern_verification_sha256"]=hashlib.sha256(data).hexdigest()
    print(json.dumps(result,indent=2))
