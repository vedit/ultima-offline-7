"""Reach the upstairs chest via the original stair run and use the carried investigation key."""

import hashlib
import json
import struct
import time

from .player_replay import open_actor, read_registry, send_reply
from .stables_replay import bag_contents, path_to, saved_source_item


def confirm_height(conn, expected):
    conn.game.sendall(b"\x22\0\0")
    frame = conn.expect({0x20}, predicate=lambda f: struct.unpack_from(">I", f, 1)[0] == conn.serial)
    x, y, _, facing, z = struct.unpack_from(">HHHBb", frame, 11)
    if (x, y) != conn.position[:2] or z != expected:
        raise ValueError(f"Estate stair expected {conn.position[:2]} Z {expected}, server reported {(x,y,z)}")
    conn.position = (x,y,z)
    conn.sequence, conn.facing = 0, facing & 7
    return [x,y,z]


def chest_contents(conn, serial):
    conn.game.sendall(struct.pack(">BI",0x06,serial))
    conn.expect({0x24},predicate=lambda f:struct.unpack_from(">I",f,1)[0]==serial)
    frame = conn.expect({0x3C})
    if len(frame) != 5 + 20*struct.unpack_from(">H",frame,3)[0]:
        raise ValueError("Truncated native estate contents")
    return [(item, art, amount, parent) for item,art,_,amount,_,_,_,parent,_
            in struct.iter_unpack(">IHBHHHBIH",frame[5:])]


def read_scroll(conn, campaign, contents, seen):
    dialogue = json.loads((campaign / "dialogue.json").read_bytes())
    if "read scroll" not in dialogue["roots"]:
        return {"status":"not_run", "reason":"This staged build predates scroll translation"}
    scroll, = [o for o in contents if (o["shape"],o["quality_byte"]) == (797,5)]
    serial, = [s for s,art,_,_ in seen if art == scroll["uo_art"]]
    function, = [f for f in dialogue["program"]["functions"] if f["id"] == scroll["shape"]]
    rows = {pc:(op,args) for pc,op,args,_ in function["rows"]}
    if rows[217][0] != 0x1C or rows[220] != (0x33,[]):
        raise ValueError("Unexpected original estate scroll text instruction")
    expected = function["strings"][str(rows[217][1][0])]
    time.sleep(1.1)
    page = open_actor(conn, serial)
    if page["body"] != [expected.strip()] or list(page["buttons"].values()) != ["Close"]:
        raise ValueError("Displayed estate scroll differs from the original quality-five text")
    send_reply(conn,page,next(iter(page["buttons"])))
    return {"status":"passed","serial":serial,"source_id":scroll["id"],"function_id":797,
            "say_pc":220,"source_offset":function["base"]+220,"usecode_sha256":dialogue["source_sha256"],
            "text_sha256":hashlib.sha256(expected.encode()).hexdigest(),"gump_sha256":page["digest"]}


def play_estate(conn, sample, campaign, world, investigation, snapshot):
    seed = json.loads((campaign / "story-seed.json").read_bytes())
    tree, = seed["investigation_chests"]
    chest, *contents = tree["objects"]
    if (chest["world_xy"],chest["lift"],chest["shape"],chest["quality_byte"]) != ([972,2132],6,522,253):
        raise ValueError("Changed original investigation chest")
    route = path_to(sample, conn.position[:2], {(971,2139)})
    conn.walk(route)
    conn.resync()
    steps = []
    for x, height in ((970,4),(969,8),(968,12),(967,16),(966,20),(965,20)):
        conn.move(6)
        steps.append(confirm_height(conn,height))
    # Leave the treads onto the six-lift floor at their northern edge.
    conn.move(0)
    steps.append(confirm_height(conn,20))
    conn.move(0)
    steps.append(confirm_height(conn,24))
    route_up = [(965,2137),(965,2136),(966,2136),(967,2136),(968,2136),(969,2136),
                (970,2136),(971,2136),(971,2135),(971,2134),(971,2133)]
    conn.walk(route_up)
    confirm_height(conn,24)
    serial, = [s for s, loc in conn.ground_items.items() if loc == (chest["uo_art"],972,2132,24)]
    snapshot()
    def saved_chest(shape):
        item = saved_source_item(world, "UltimaOffline.Entities.CampaignChest",
                                 chest["id"], (chest["quality_byte"],shape))
        if item["serial"] != serial:
            raise ValueError("Saved estate chest differs from the targeted world object")
        return {**item,"shape":shape}
    locked = saved_chest(522)
    before,_ = read_registry(world / "UltimaOfflineDialogue/UltimaOfflineDialogue.bin")
    flag_before = before["Changes"].get("62",seed["flags"][62])
    if flag_before != 0:
        raise ValueError("Estate chest quest flag was already set before using the key")
    key = investigation["key_serial"]
    conn.game.sendall(struct.pack(">BI",0x06,key))
    cursor = conn.expect({0x6C})
    if len(cursor)!=19 or cursor[1]!=0:
        raise ValueError("Unexpected targeting cursor for the investigation key")
    time.sleep(1.1)
    conn.game.sendall(struct.pack(">BBIBIHHbBH",0x6C,0,int.from_bytes(cursor[2:6],"big"),0,serial,
                                  972,2132,0,24,chest["uo_art"]))
    barrier = bytes((0x73,113))
    conn.game.sendall(barrier)
    conn.expect({0x73},predicate=lambda f:f==barrier)
    time.sleep(1.1)
    seen = chest_contents(conn,serial)
    if (any(parent!=serial for _,_,_,parent in seen) or
        sorted((a,n) for _,a,n,_ in seen)!=sorted((o["uo_art"],o["amount"]) for o in contents)):
        raise ValueError(f"Native chest inventory differs from its original children: {seen}")
    scroll = read_scroll(conn, campaign, contents, seen)
    snapshot()
    unlocked = saved_chest(800)
    registry, digest = read_registry(world / "UltimaOfflineDialogue/UltimaOfflineDialogue.bin")
    if registry["Changes"].get("62") != 1:
        raise ValueError("Original key did not commit its quality-253 flag write")
    return {"status":"passed","chest_id":chest["id"],"chest_serial":serial,"key_serial":key,
            "source_lift":6,"steps":steps,"approach":list(conn.position),"world_route_steps":len(route)-1,
            "chest_position":[972,2132,24],"locked":locked,"unlocked":unlocked,"flag62_before":flag_before,
            "scroll":scroll,"backpack_serial":investigation["backpack_serial"],
            "contents":seen,"source_contents":[{k:o[k] for k in ("id","shape","frame","quality_byte","amount","uo_art")}
                                                for o in contents],"flag62":1,"registry_sha256":digest}


def reopen_estate(conn, evidence):
    if list(conn.position) != evidence["approach"]:
        raise ValueError("Player did not return beside the originally unlocked chest")
    seen = chest_contents(conn,evidence["chest_serial"])
    if seen != evidence["contents"]:
        raise ValueError("Reload changed the native chest, child identities, amounts or parents")
    time.sleep(1.1)
    bag, carried = bag_contents(conn)
    if bag != evidence["backpack_serial"] or evidence["key_serial"] not in carried:
        raise ValueError("Player did not retain the estate key in the same backpack after restart")
    return {"contents":seen,"same_chest_and_children":True,"descent":leave_estate(conn),
            "key_serial":evidence["key_serial"],"backpack_serial":bag}


def leave_estate(conn):
    conn.walk([(971,2133),(971,2134),(971,2135),(971,2136),(970,2136),(969,2136),(968,2136),
               (967,2136),(966,2136),(965,2136),(965,2137)])
    descent=[]
    for direction,z in ((4,20),(4,20),(2,20),(2,16),(2,12),(2,8),(2,4),(2,0)):
        conn.move(direction)
        descent.append(confirm_height(conn,z))
    return descent


def compare_estate(installation, session, verification):
    """Compare a native DOS unlock with the ordinary server replay and its reopened save."""
    from tools.oracle.investigation import qualify_stable
    from u7uo.u7 import seed_directory

    original = qualify_stable(session, installation)
    target = verification["player_replay"]["estate"]
    scroll = target["scroll"]
    if (verification["scenario"] != "estate" or verification["source_edition"] != "expanded"
            or target["status"] != "passed" or scroll["status"] != "passed"
            or scroll["usecode_sha256"] != original["edition_source_sha256"]):
        raise ValueError("Estate comparison requires the same original Forge Usecode and a completed scroll replay")
    stages = {}
    for label,phase,flag in (("before-chest","locked","flag62_before"),("estate-unlocked","unlocked","flag62")):
        saved, = [s for s in original["checkpoints"] if s["save_file"].startswith(label+"-")]
        raw = (session / saved["save_file"]).read_bytes()
        _, offset, size = seed_directory(raw)["flaginit"]
        dos = original["estate_chest"][label]
        item = target[phase]
        if (size <= 62 or raw[offset+62] != target[flag] or dos["shape"] != item["shape"]
                or item["serial"] != target["chest_serial"]
                or target["chest_position"] != [*dos["world_xyz"][:2],4*dos["world_xyz"][2]]
                or saved["key"]["actor_slot"] != 0):
            raise ValueError(f"Estate flag, lock, ownership or position disagrees at {phase}")
        stages[phase] = {"dos_save_sha256":saved["save_sha256"],"dos_chest_handle":dos["handle"],
                         "uo_item_sha256":item["payload_sha256"],"shape":dos["shape"],"flag62":target[flag]}
    children = original["estate_chest"]["estate-unlocked"]["children"]
    source = target["source_contents"]
    seen = target["contents"]
    if len(source) != len(children) or len(source) != len(seen):
        raise ValueError("Original and converted estate contents counts differ")
    for dos, obj, (serial,art,amount,parent) in zip(children,source,seen):
        if ((dos["shape"],dos["frame"],dos["attribute"]) != (obj["shape"],obj["frame"],obj["quality_byte"])
                or (art,amount,parent) != (obj["uo_art"],dos["attribute"] & 127 if dos["shape"]==644 else 1,
                                            target["chest_serial"])
                or dos["shape"] == 797 and serial != scroll["serial"]):
            raise ValueError("Estate child, quantity, parent or readable scroll differs")
    restored = target["reopened"]
    if (restored["contents"] != seen or restored["key_serial"] != target["key_serial"]
            or restored["backpack_serial"] != target["backpack_serial"]):
        raise ValueError("The restored chest or key differs from the completed unlock")
    return {"status":"passed","edition":original["edition"],"build_id":verification["build_id"],
            "usecode_sha256":scroll["usecode_sha256"],"stages":stages,"source_chest_id":target["chest_id"],
            "source_child_ids":[o["id"] for o in source],"restored_contents":seen,
            "scroll_source_text_sha256":scroll["text_sha256"],"uo_gump_sha256":scroll["gump_sha256"],
            "dos_observation_frames":original["estate_chest"]["observation_frames"]}


if __name__ == "__main__":
    import argparse
    from pathlib import Path
    parser = argparse.ArgumentParser(description="Compare the ordinary estate replay with the original game saves")
    parser.add_argument("verification",type=Path)
    parser.add_argument("dos_session",type=Path)
    parser.add_argument("--installation",type=Path,required=True)
    args = parser.parse_args()
    raw = args.verification.read_bytes()
    report = compare_estate(args.installation,args.dos_session,json.loads(raw.decode("utf-8-sig")))
    report["verification_sha256"] = hashlib.sha256(raw).hexdigest()
    print(json.dumps(report,indent=2))
