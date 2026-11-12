"""One ordinary player's accepted investigation, office visit and witness interviews."""
import hashlib
import json
import struct
import time

from .player_replay import BlockedStep, DIRECTIONS, compressed_gump, open_actor, read_registry, send_reply
from .gate_replay import refuse_passage
from .stables_replay import bag_contents, lift_to_backpack, path_to, play_stables, report_key, saved_source_item


def approach(conn, sample, position, *, stop_at=None):
    x,y = position[:2]
    targets={(x+dx,y+dy) for dx,dy in DIRECTIONS.values()}
    avoided={tuple(position[:2])}
    trail=[conn.position[:2]]
    for _ in range(128):
        route=path_to(sample,conn.position[:2],targets,avoid=avoided)
        for step in route[1:]:
            try:
                conn.walk([conn.position[:2],step])
            except BlockedStep:
                # Let the server's normal collision reply identify this cell.
                # Another route can lead around an occupied tile or an object.
                avoided.add(step)
                break
            trail.append(step)
            if stop_at is not None and stop_at(step):
                return trail
        else:
            conn.resync()
            return trail
    raise ValueError(f"Too many blocked walk attempts while approaching {position}")


def saved_regional_tool(world, row):
    return saved_source_item(world, "UltimaOffline.Entities.RegionalItem", row["id"],
                             source_payload=row["payload"])


def pick_up_smithy_tongs(conn, sample, manifest, world, snapshot):
    # The ordinary tongs on the smithy's work surface are a separate IREG
    # instance from the investigation key. Identify them in the installed seed.
    rows = json.loads(manifest.read_bytes())["objects"]
    matches = [row for row in rows if row["shape"] == 994 and row["xy"] == [1079,2185]
               and row["kind"] == "simple" and row["parent"] is None]
    if len(matches) != 1:
        raise ValueError("Expected one mapped pair of smithy tongs in the Trinsic source")
    row = matches[0]
    before = saved_regional_tool(world, row)
    serial = before["serial"]
    path = approach(conn, sample, row["xy"])
    ground = (row["art"], *row["xy"], row["lift"] * 4)
    if conn.ground_items.get(serial) != ground:
        raise ValueError(f"The smithy tongs differ from the saved source placement at {ground}")
    bag, _ = lift_to_backpack(conn, serial, row["art"])
    snapshot()
    carried = saved_regional_tool(world, row)
    if carried["serial"] != serial:
        raise ValueError("Picking up the smithy tongs changed their native identity")
    return {"source":row, "path":path, "ground_packet":ground, "player":conn.serial,
            "backpack":bag, "before":before, "carried":carried}


def restore_smithy_tongs(conn, visit, world, inventory):
    row = visit["source"]
    restored = saved_regional_tool(world, row)
    bag, contents = inventory
    serial = visit["before"]["serial"]
    if (restored["serial"] != serial or conn.serial != visit["player"] or bag != visit["backpack"] or
            contents.get(serial) != (row["art"], 1, bag) or serial in conn.ground_items):
        raise ValueError("Restored smithy tongs differ from the original item or backpack owner")
    return {"status":"passed", "native_item":restored, "player":conn.serial, "backpack":bag,
            "art":row["art"], "amount":1}


def interview(conn, page, topics, *, geography=None, logs=None):
    """Answer only controls actually presented; retain each visible page in order."""
    if logs is None:
        logs=[]
    for ordinal in range(220):
        labels=list(page["buttons"].values())
        event={"gump_sha256":page["digest"],"images":page["images"],
               "body_hashes":[hashlib.sha256(s.encode()).hexdigest() for s in page["body"]]}
        if labels==["Answer"] and geography is not None:
            questions,manual_hash=geography
            question=page["body"][0].strip('"')
            if page["entries"]!=[0] or question not in questions:
                raise ValueError("Unexpected numeric control or geography question")
            number=questions[question]
            encoded=str(number).encode("utf-16-be")
            header=struct.pack(">BHIIIII",0xB1,27+len(encoded),page["sender"],page["kind"],1,0,1)
            conn.game.sendall(header+struct.pack(">HH",0,len(encoded)//2)+encoded)
            logs.append({**event,"numeric_player_response":number,"steam_booklet_sha256":manual_hash})
            page=compressed_gump(conn.expect({0xDD}))
            continue
        if labels==["Continue"]:
            selected="Continue"
        elif "Alden" in labels and set(labels)<={"Alden","Avatar"}:
            # The original Spark introduction requests the player's chosen name.
            selected="Alden"
            event["choices"]=labels
        elif topics and topics[0] in labels:
            selected=topics.pop(0)
            event["choices"]=labels
        else:
            raise ValueError(f"Expected next {topics[:1]} in ordinary menu, received {labels}")
        event["selected"]=selected
        logs.append(event)
        send_reply(conn,page,next(k for k,v in page["buttons"].items() if v==selected))
        if not topics or topics==["bye"]:
            # A packet barrier distinguishes an actual terminal return from a final farewell SAY.
            barrier=bytes((0x73,ordinal))
            conn.game.sendall(barrier)
            response=conn.expect({0x73,0xDD},predicate=lambda f:f[0]==0xDD or f==barrier)
            if response==barrier:
                return logs
            page=compressed_gump(response)
        else:
            page=compressed_gump(conn.expect({0xDD}))
    raise ValueError("Conversation exceeded its expected number of player controls")


def witness(conn, sample, seed, slot, topics, flag, world, snapshot, observed):
    if slot not in seed["walking_actor_slots"]:
        raise ValueError(f"Original witness NPC slot {slot} is outside this staged map")
    actor=seed["actors"][str(slot)]
    position=actor["source_position"]
    route=approach(conn,sample,position)
    serial=conn.actor(position,actor["name"])
    page=open_actor(conn,serial)
    visit={"id":actor["id"],"serial":serial,"position":position,"path":route,"pages":[]}
    observed[actor["name"]]=visit
    interview(conn,page,list(topics),logs=visit["pages"])
    snapshot()
    registry,digest=read_registry(world/"UltimaOfflineDialogue/UltimaOfflineDialogue.bin")
    if registry["Changes"].get(str(flag))!=1 or str(conn.serial) in registry["Active"]:
        raise ValueError(f"Witness {actor['name']} did not commit original flag {flag} and close")
    visit.update(flag=flag,result=1,registry_sha256=digest)
    if slot==13:
        visit["clock_ticks"]=registry["Gate"]["LastClockTicks"]


def toggle_portcullis(conn, sample, seed, closed, world, snapshot, *, exterior=False):
    guard=seed["actors"]["14"]
    anchor,=[g for g in seed["gate_objects"] if g["shape"]==271]
    gx,gy,_=anchor["position"]
    north=gy-anchor["footprint"][1]+1
    if closed and exterior:
        if conn.position[:2]!=(gx+5,north):
            raise ValueError("Exterior conversation did not start at the original DOS position")
        guard_path=[conn.position[:2]]
    else:
        guard_path=approach(conn,sample,guard["source_position"])
    talk_position=list(conn.position)
    serial=conn.actor(guard["source_position"],"Johnson")
    page=open_actor(conn,serial)
    pages=interview(conn,page,["password","Blackbird"])
    if exterior and closed:
        path=[(x,north) for x in range(gx+5,gx,-1)]
    else:
        path=path_to(sample,conn.position[:2],{(gx-1,north if exterior else gy)})
    conn.walk(path)
    conn.resync()
    snapshot()
    state,digest=read_registry(world/"UltimaOfflineDialogue/UltimaOfflineDialogue.bin")
    callbacks=[s.split() for s in state["Gate"]["Trace"] if " lift " in s and anchor["id"] in s]
    desired="0609" if closed else "0607"
    if (len(callbacks)<4 or [r[3] for r in callbacks[-4:]]!=[desired]*4 or state["Gate"]["Actions"] or
            state["Gate"]["Error"] or str(conn.serial) in state["Active"] or state["Changes"].get("61")!=1):
        raise ValueError(f"Expected four original {desired} lift callbacks and idle world: {callbacks}")
    z=0 if closed else 16
    footprint={p[2]:sid for sid,p in conn.ground_items.items() if p[0]==anchor["uo_art"] and p[1]==gx and p[3]==z}
    if set(footprint)!={gy-i for i in range(anchor["footprint"][1])}:
        raise ValueError(f"Client did not receive the entire gate footprint at lift {z}: {footprint}")
    if closed:
        direction=6 if exterior else 2
        trial=conn.move(direction,block=True)
        trial["requested_direction"]=direction
        conn.resync()
    else:
        before=len(conn.acknowledged)
        crossing_y=north if exterior else gy
        conn.walk([(gx-1,crossing_y),(gx,crossing_y),(gx+1,crossing_y)])
        beyond=list(conn.resync())
        excursion = None
        if sample.get("world_geometry"):
            # The original east road continues across the former quest-patch
            # boundary to the grass and sand on the approach to the docks.
            last_x = sample["source_origin"][0] + sample["width"] + 14
            join = [(gx+1,y) for y in range(crossing_y,gy+1)]
            road = join + [(x,gy) for x in range(gx+2,last_x+1)]
            conn.walk(road)
            coast = list(conn.resync())
            if coast != [last_x,gy,0]:
                raise ValueError(f"World road did not reach the expected coast approach: {coast}")
            conn.walk(road[::-1])
            returned = list(conn.resync())
            if returned!=beyond:
                raise ValueError("World road return did not reach the gate")
            excursion = {"coast_position":coast,"returned_to_gate":returned,"round_trip_steps":2*(len(road)-1)}
        if exterior:
            conn.walk([(x,north) for x in range(gx+1,gx+6)])
        else:
            conn.walk([(gx+1,gy),(gx,gy),(gx-1,gy)])
        conn.resync()
        trial={"acknowledged_crossing":conn.acknowledged[before:],"outside_position":beyond}
        if exterior:
            trial["dos_checkpoint_position"]=list(conn.position)
        if excursion:
            trial["world_road"] = excursion
    return {"status":"passed","guard_path":guard_path,"guard_serial":serial,"talk_position":talk_position,"pages":pages,
            "gate_path":path,"gate_id":anchor["id"],"lift_callbacks":callbacks[-4:],"wire_footprint":footprint,
            "native_registry_sha256":digest,"physical_crossing_test":trial}


def verify_award(conn, state, seed, *, inventory=None, program=None, expected_downed=()):
    gate=state["Gate"]
    coin,=[s.split() for s in gate["Trace"] if " coins " in s]
    if len(coin)!=6 or coin[3]!="-356" or int(coin[5])!=100:
        raise ValueError("Expected one ordinary 100-coin reward to the Avatar")
    bag,contents=bag_contents(conn) if inventory is None else inventory
    serial=int(coin[4])
    expected=seed["runtime_shapes"]["644"]["uo_item_id"]
    coins={"serial":serial,"source":coin[2],"amount":100,"art":expected}
    if serial in contents:
        if contents[serial]!=(expected,100,bag):
            raise ValueError("Reward stack differs in the player's backpack")
        coins.update(parent="backpack",parent_serial=bag,bag=bag)
    else:
        worn=conn.equipment.get(conn.serial,{}).get(serial)
        if worn not in ((expected,1),(expected,2)):
            raise ValueError("Reward is missing from the Avatar's hand and backpack")
        conn.game.sendall(struct.pack(">BHI",0xD6,7,serial))
        frame=conn.expect({0xD6},predicate=lambda f:len(f)>=19 and struct.unpack_from(">I",f,5)[0]==serial)
        label,length=struct.unpack_from(">IH",frame,15)
        if label!=1050039 or length>len(frame)-25 or length%2:
            raise ValueError("Missing equipped stack quantity in the player's item properties")
        amount=frame[21:21+length].decode("utf-16-le").split("\t")[0]
        if amount!="100":
            raise ValueError(f"Unexpected equipped reward quantity {amount}")
        coins.update(parent="avatar",parent_serial=conn.serial,source_slot=worn[1])
    party=state["Opening"]["Party"]+state["Opening"].get("DownedParty",[])
    if len(party)!=3 or set(party)!={-356,-1,-2}:
        raise ValueError(f"Unexpected party for the original shared award: {party}")
    result={"coins":coins}
    if "AwardRosters" in gate:
        receipt,=gate["AwardRosters"]
        reward_fn,=(f for f in program["functions"] if f["id"]==0x0911)
        site,=(pc for pc,op,args,_ in reward_fn["rows"] if op==0x38 and args==[0x23,0])
        recipients=[int(t.split()[2]) for t in gate["Trace"] if " experience " in t]
        active=[h for h in (-356,-1,-2) if h not in expected_downed]
        if (receipt["SourceOffset"]!=reward_fn["base"]+site or receipt["Downed"]!=list(expected_downed)
                or receipt["Active"]!=active or receipt["Returned"]!=receipt["Active"][::-1]
                or recipients!=receipt["Returned"]):
            raise ValueError("XP writes differ from the party returned at the original award instruction")
        result["award_roster"]={**receipt,"xp_recipients":recipients}
    elif expected_downed:
        raise ValueError("The conditional award requires a host with award-time roster receipts")
    progress={}
    for handle in party:
        actor=seed["actors"][str(0 if handle==-356 else -handle)]
        previous=actor["experience"]
        if handle in expected_downed:
            if actor["id"] in gate["Progress"]:
                raise ValueError("Excluded NPC received an experience write")
            progress[actor["id"]]={"initial_experience":previous,"Experience":previous,
                                   "initial_training":actor["training"],"Training":actor["training"]}
            continue
        xp=min(previous+50,999999)
        crossed=sum(previous < threshold <= xp for threshold in (100<<i for i in range(14)))
        expected={"Experience":xp,"Training":min(255,actor["training"]+3*crossed)}
        if gate["Progress"].get(actor["id"])!=expected:
            raise ValueError(f"Saved original experience or training differs for {actor['name']}")
        progress[actor["id"]]={"initial_experience":previous,"initial_training":actor["training"],**expected}
    return {**result,"party_progress":progress}


def journey(conn, sample, campaign, world, snapshot, observed, installation, expected_downed=(), witnesses_first=False):
    seed=json.loads((campaign/"story-seed.json").read_bytes())
    if not witnesses_first:
        observed["current"]="ask the dock guard before earning the password"
        observed["guard_before_password"]=refuse_passage(conn,sample,campaign)
    observed["current"]="acquire key"
    stables=play_stables(conn,sample,campaign,world,snapshot)
    observed["stables"]=stables
    if (campaign/"world-live.json").is_file():
        observed["current"]="pick up the source smithy tongs"
        observed["regional_item"]=pick_up_smithy_tongs(conn,sample,campaign/"world-live.json",world,snapshot)
    observed["current"]="find scheduled Mayor"
    # Advance normal game time while travelling to the seeded 06:00 office.
    schedule,=[r for r in seed["actors"]["12"]["schedule"] if r["time_slot"]==2 and r["activity"]==16]
    office=schedule["world_xy"]
    path=approach(conn,sample,office)
    observed["office_approach"]=path
    for _ in range(8):
        snapshot()
        registry,_=read_registry(world/"UltimaOfflineDialogue/UltimaOfflineDialogue.bin")
        gate=registry["Gate"]
        if gate.get("Error"):
            raise ValueError(gate["Error"])
        if gate.get("OfficeArrived") and (not seed.get("schedule_seats") or
                any(" seated " in event for event in gate["Trace"])):
            break
    else:
        raise ValueError(f"Scheduled office appointment not reached: {gate}")
    trace=[s.split() for s in gate["Trace"] if " office " in s]
    if not trace:
        raise ValueError("The active office appointment has no native arrival record")
    observed["office_schedule"]={"target":office,"row":schedule["offset"],"trace":gate["Trace"]}
    position=[int(trace[-1][2]),int(trace[-1][3]),0]
    if seed.get("schedule_seats"):
        from .appointment_replay import seated_mayor
        seat=seated_mayor(conn,world,seed,gate)
        observed["office_schedule"]["seat"]=seat
        position=seat["position"]
    finish=approach(conn,sample,position)
    observed["current"]="report actual key to scheduled Mayor"
    placement={"approach":list(conn.position),"actor":{"position":position}}
    travelled = [*observed.get("regional_item",{}).get("path",[]), *path, *finish]
    stables["mayor_report"]=report_key(conn,placement,stables,campaign,world,snapshot,
                                      return_path=[finish[-1]],travelled=travelled)
    if "read scroll" in json.loads((campaign/"dialogue.json").read_bytes())["roots"]:
        from .estate_replay import leave_estate, play_estate
        observed["current"]="inspect the original chest and read the scroll before reporting its contents"
        observed["estate"]=play_estate(conn,sample,campaign,world,stables,snapshot)
        observed["estate"]["descent"]=leave_estate(conn)
    observed["current"]="interview Spark"
    witness(conn,sample,seed,2,["murder","find","something","man","hook","No","bye"],67,world,snapshot,observed)
    observed["current"]="interview Gilberto"
    witness(conn,sample,seed,13,["murder","knocked","blow","Crown Jewel","bye"],64,world,snapshot,observed)
    observed["current"]="full Mayor report"
    route=approach(conn,sample,position)
    observed["report_route"]=route
    serial=conn.actor(position,"Finnigan")
    registry,_=read_registry(world/"UltimaOfflineDialogue/UltimaOfflineDialogue.bin")
    observed["before_report_flags"]={str(n):registry["Changes"].get(str(n),seed["flags"][n]) for n in (61,66)}
    page=open_actor(conn,serial)
    manual=installation/"Assets/UltimaVII-Steam/answers.pdf"
    digest=hashlib.sha256(manual.read_bytes()).hexdigest()
    if digest!="5e864b428671a2105f898f674099fc5e5ec844599a3f07573f525bd14e01ad0e":
        raise ValueError("The original witness-session geography reference is unavailable")
    functions=json.loads((campaign/"dialogue.json").read_bytes())["program"]["functions"]
    exam,=[f for f in functions if f["id"]==0x0886]
    # The installed booklet's first eight answers, in its printed order.
    # The licensed source emits its questions in this order from this APPEND array.
    questions=[exam["strings"][str(args[0])] for pc,op,args,_ in exam["rows"] if 0x253<=pc<=0x268 and op==0x1D]
    if len(questions)!=8:
        raise ValueError("The published Finnigan exam question sequence has changed")
    answers=dict(zip(questions[::-1],(120,60,120,0,30,60,60,60),strict=True))
    observed["report"]=[]
    interview(conn,page,["murder","report","Yes","blacksmith","a key","a chest","all of these",
        "Yes","hook","Crown Jewel","Yes","bye"],geography=(answers,digest),logs=observed["report"])
    snapshot()
    state,_=read_registry(world/"UltimaOfflineDialogue/UltimaOfflineDialogue.bin")
    observed["report_flags"]=state["Changes"]
    if state["Changes"].get("61")!=1:
        raise ValueError("The Mayor's ordinary player interview has not awarded the gate password")
    program=json.loads((campaign/"dialogue.json").read_bytes())["program"]
    observed["reward"]=verify_award(conn,state,seed,program=program,expected_downed=expected_downed)
    observed["current"]="pass through the lifted gate"
    exterior=state["Gate"].get("VisibleNpcTalk",False)
    observed["opened"]=toggle_portcullis(conn,sample,seed,False,world,snapshot,exterior=exterior)
    observed["current"]="close and retest the portcullis"
    observed["closed"]=toggle_portcullis(conn,sample,seed,True,world,snapshot,exterior=exterior)
    observed["passed_gate_reclose"]=True
