"""Collect the ordinary player's on-wire view of the isolated Forge opening."""
import hashlib
import json
import struct
import time

from .player_replay import PlayerConnection, compressed_gump, replay_dialogue, replay_refusal, reopen_refusal, send_reply, source_pages


def observe_opening(game, root, campaign, *, automatic_mayor=False):
    seed = json.loads((campaign / "story-seed.json").read_bytes())
    gate = seed["runtime_shapes"]["157"]["uo_item_id"]
    score = json.loads((campaign / "music.json").read_bytes())["tracks"]["35"]["client_slot"]
    events = []
    def observe(f):
        kind = f[0]
        if kind == 0x6D:
            events.append({"kind":"music", "slot":struct.unpack_from(">H", f, 1)[0]})
        elif kind == 0xF3 and struct.unpack_from(">H",f,8)[0] == gate:
            events.append({"kind":"gate","serial":struct.unpack_from(">I",f,4)[0],
                           "position":list(struct.unpack_from(">HHb",f,15)), "item_art":gate})
        elif kind in (0x1C,0xAE):
            n = 14 if kind == 0x1C else 18
            name = f[n:n+30].rstrip(b"\0").decode("latin1")
            msg = f[n+30:].decode("latin1" if kind == 0x1C else "utf-16-be").rstrip("\0")
            if name in ("Petre","Iolo"):
                events.append({"kind":"bark","speaker":name,"serial":struct.unpack_from(">I",f,3)[0],
                               "text_sha256":hashlib.sha256(msg.encode()).hexdigest()})
        elif kind == 0x20:
            x,y,_,direction,z = struct.unpack_from(">HHHBb",f,11)
            events.append({"kind":"player_update","position":[x,y,z],"direction":direction & 7})
        elif kind == 0x1D:
            events.append({"kind":"remove","serial":struct.unpack_from(">I",f,1)[0]})
    conn = PlayerConnection(game,root,observe)
    start = conn.enter()
    pages, error = [], None
    mayor = None
    source = source_pages(campaign) if automatic_mayor else None
    try:
        for _ in range(100):
            g = compressed_gump(conn.expect({0xDD},timeout=35 if automatic_mayor else 20))
            if automatic_mayor and g["body"] == [source["first"]]:
                if automatic_mayor=="accept":
                    mayor = replay_dialogue(conn,None,source,first_page=g,suspend=False)
                else:
                    mayor = replay_refusal(conn,None,source,first_page=g)
                break
            buttons = g["buttons"]
            pages.append({"sha256":g["digest"],"portraits":g["images"],"buttons":buttons,
                          "text_sha256":[hashlib.sha256(s.encode()).hexdigest() for s in g["body"]]})
            if list(buttons.values()) != ["Continue"]:
                break
            send_reply(conn,g,next(iter(buttons)))
    except ValueError as exc:
        error = str(exc)
    # Query the actual player's position with the normal client resync packet.
    conn.game.sendall(b"\x22\0\0")
    p = conn.expect({0x20},predicate=lambda f:struct.unpack_from(">I",f,1)[0]==conn.serial)
    x,y,_,_,z = struct.unpack_from(">HHHBb",p,11)
    return {"start":start, "player_serial":conn.serial, "server_position":[x,y,z], "requested_moves":0,
            "music_slot":score,"events":events,"pages":pages,"diagnostic":error,"automatic_mayor":mayor}


def check_opening(capture):
    state = capture["saved_opening"]
    trace = [s.split() for s in state["Trace"]]
    bark_lines = [r for r in trace if r[1] == "bark"]
    bark_packets = [e for e in capture["events"] if e["kind"] == "bark"]
    speakers = ["Iolo","Petre"] * 4 + ["Iolo"]
    gates = [e for e in capture["events"] if e["kind"]=="gate"]
    serials = {e["serial"] for e in gates}
    unique_serial = next(iter(serials)) if len(serials)==1 else None
    return {
        "cached_egg":bool(trace) and trace[0][1:4]==["call","0401","3"] and state["Owner"]==capture["player_serial"],
        "score_35":[e["slot"] for e in capture["events"] if e["kind"]=="music"].count(capture["music_slot"]) >= 2,
        "nine_source_barks":[e["speaker"] for e in bark_packets[:9]]==speakers and
                           [e["text_sha256"] for e in bark_packets[:9]]==[r[-1] for r in bark_lines[:9]],
        "summoned_gate":bool(gates) and all(e["position"]==[1080,2215,0] for e in gates) and
                        any(e["kind"]=="remove" and e["serial"]==unique_serial for e in capture["events"]),
        "source_steps":[r[2:] for r in trace if r[1]=="step"][:3]==[["1078","2214"],["1077","2214"],["1076","2214"]],
        "player_position":capture["server_position"]==[1076,2214,0] and capture["requested_moves"]==0,
        "opening_faces":{64001,64011}.issubset({i for page in capture["pages"] for i in page["portraits"]}),
        "final_tip_callback":any(r[1:4]==["call","06FA","2"] for r in trace),
        "source_flags":all(capture.get("saved_flags",{}).get(str(i))==1 for i in (20,59,92)),
        "party_and_queue":state.get("Party")==[-356,-1] and state.get("Actions")==[],
        "completed":state["Status"]=="complete" and not state["Locked"] and capture["diagnostic"] is None,
    }


def walk_to_mayor(conn, sample, campaign, hatched_egg):
    from u7uo.walking import _find_route
    ox,oy = sample["source_origin"]
    local = conn.position[0]-ox, conn.position[1]-oy
    approach = tuple(sample["route"][-2])
    npc = sample["finnigan"]["source"]
    impassable = {a["id"] for a in sample["static_rules"].values() if a["flags"] & 0x40}
    blocked = {(s["x"],s["y"]) for s in sample["statics"] if s["z"]==0 and s["id"] in impassable}
    # The scripted westward steps leave the Avatar standing on the hatched
    # egg itself. Its trigger occupies a coordinate without blocking movement.
    for obj in sample["ireg_objects_deferred"]:
        if obj["id"]==hatched_egg and obj["shape"]==275 and obj["world_xy"]==list(conn.position[:2]):
            continue
        blocked.add((obj["world_xy"][0]-ox,obj["world_xy"][1]-oy))
    blocked.add((npc[0]-ox,npc[1]-oy))
    path = [(x+ox,y+oy) for x,y in _find_route(local,approach,blocked)]
    conn.walk(path)
    real = conn.resync()
    serial = conn.actor(npc,"Finnigan")
    witnesses = source_pages(campaign)
    refusal = replay_refusal(conn,serial,witnesses)
    visit = {"path":path, "movement_acks":conn.acknowledged, "server_position":real,
             "actor":{"name":"Finnigan","position":npc,"serial":serial}, "dialogue":refusal}
    time.sleep(1)
    reopen_refusal(conn,visit,witnesses)
    return visit
