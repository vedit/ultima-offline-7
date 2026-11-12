"""Exercise the campaign appointment using a qualified DOS clock and actor placement."""
import hashlib
import json
import struct
import time

from tools.oracle.mayor_schedule import qualify_trial
from .player_replay import PlayerConnection, read_registry


def prepare(root, trial, release, record, campaign):
    reference = qualify_trial(root, trial)
    seed_file = campaign / "story-seed.json"
    original = seed_file.read_bytes()
    seed = json.loads(original)
    initial = reference["initial"]
    npc = initial["mayor"]
    actor = seed["actors"]["12"]
    if actor["shape"] != npc["shape"] or reference["source_schedule"] not in actor["schedule"]:
        raise ValueError("Facet actor or timetable differs from the native fixture")
    x,y = npc["world_xy"]
    block = (x//8)*(record["height"]//8) + y//8
    with (release/"assets/map0.mul").open("rb") as f:
        f.seek(196*block + 4 + 3*(8*(y%8)+x%8))
        land, = struct.unpack("<H", f.read(2))
    actor.update(source_position=[x,y,npc["lift"]], staged_land_id=land, activity=npc["activity"],
                 status_word=npc["status_word"], hit_points=npc["hp"])
    for flag, mask in ((1,0x80),(7,0x1000),(4,0x8000)):
        actor["item_flags"][str(flag)] = bool(npc["status_word"] & mask)
    actor["can_act"] = npc["hp"] > 0 and not any(actor["item_flags"][str(i)] for i in (1,7,4))
    seed["clock"] = {**initial["clock"], "ticks":reference["fixture_clock"]["ticks"]}
    seed_file.write_text(json.dumps(seed, separators=(",",":"))+"\n", encoding="utf-8")
    avatar = initial["avatar"]
    exterior = []
    if reference["resident"] and "fence_art" in seed:
        for fence in seed["town_fences"]:
            x,y = fence["world_xy"]
            w,h = fence["footprint"]
            for dx in range(w):
                for dy in range(h):
                    if y-dy==2256 and 1040<=x-dx<=1045:
                        exterior.append([fence["art"],x-dx,y-dy,4*fence["lift"]])
        if len(exterior)!=6 or {v[1] for v in exterior}!=set(range(1040,1046)):
            raise ValueError("Missing original fence span along Finnigan's house")
    return [*avatar["world_xy"],4*avatar["lift"]], {
        "source_session":trial.name, "donor":reference["source_save"],
        "native_receipt_sha256":reference["receipt_sha256"], "resident":reference["resident"],
        "source_row":reference["source_schedule"], "initial_mayor":npc,
        "start_tick":seed["clock"]["ticks"], "native_departure_bracket":reference["transition_bracket_ticks"],
        "native_first_observed_arrival":reference["first_observed_arrival_tick"],
        "published_seed_sha256":hashlib.sha256(original).hexdigest(),
        "fixture_seed_sha256":hashlib.sha256(seed_file.read_bytes()).hexdigest(),
        "exterior_fence_cells":sorted(exterior)}


def visible_fence(conn, cells):
    wanted = {tuple(c) for c in cells}
    matches = {str(serial):list(obj) for serial,obj in conn.ground_items.items() if obj in wanted}
    if len(matches)!=len(wanted) or {tuple(v) for v in matches.values()}!=wanted:
        raise ValueError("Player did not receive the six original fence cells")
    return matches


def reopen_fence(conn, fixture, before):
    conn.resync()
    conn.resync()
    if visible_fence(conn,fixture["exterior_fence_cells"])!=before:
        raise ValueError("Fence art, location or serial changed after restart")
    for direction in (6,6,6,0,0,0):
        conn.move(direction)
    if conn.position!=(1045,2257,0):
        raise ValueError("Could not approach the east end of the source fence")
    denied=conn.move(0,block=True)
    conn.move(2)
    conn.move(0)
    conn.resync()
    if conn.position!=(1046,2256,0):
        raise ValueError("Original east-side passage unavailable")
    return {"same_serials":True,"blocked":denied,"east_passage":list(conn.position)}


def seated_mayor(conn, world, seed, gate):
    events=[s.split() for s in gate["Trace"] if " seated " in s]
    event,=events
    seat,=[v for v in seed["schedule_seats"] if v["id"]==event[6]]
    position=[*seat["sitting_xy"],4*seat["lift"]]
    state,_=read_registry(world/"UltimaOfflineDialogue/UltimaOfflineDialogue.bin")
    work=state["Work"][seed["actors"]["12"]["id"]]
    if (list(map(int,event[2:5]))!=position or int(event[5])!=2*(seat["frame"]&3) or
            work!={"Kind":16,"State":3} or gate["OfficeSeat"]["SeatId"]!=seat["id"]):
        raise ValueError("Resting work state, actor tile or facing differs from the selected source chair")
    conn.resync()
    actor_serial=conn.actor(position,"Finnigan")
    chair_serial,=[serial for serial,item in conn.ground_items.items() if item==(seat["art"],*position)]
    return {"source":seat,"position":position,"work":work,"actor_serial":actor_serial,"serial":chair_serial}


def play_office(game,root,state,start,seed,sample,office,*,interrupt=False,resumed=None,blocked_child=None):
    from .journey_replay import approach
    conn=PlayerConnection(game,root)
    if list(conn.enter())!=start or resumed and conn.serial!=resumed["player_serial"]:
        raise ValueError("Office observer entered away from the distant appointment donor")
    world=state/"world"
    registry=world/"UltimaOfflineDialogue/UltimaOfflineDialogue.bin"
    route=None
    deadline=time.monotonic()+100
    while time.monotonic()<deadline:
        conn.resync()
        if registry.is_file():
            saved,_=read_registry(registry)
            gate=saved["Gate"]
            if gate["Error"]:
                raise ValueError(gate["Error"])
            if route is None and gate["OfficeArrived"]:
                if interrupt:
                    def enters_window(point):
                        return all((target-(observed&~15)+32)%3072<80 for target,observed in zip(office,point))
                    route=approach(conn,sample,office,stop_at=enters_window)
                    # The actor resumes when this acknowledged player step brings its chunk into range.
                    # Disconnect while it is walking. Autosave then persists the unfabricated queue.
                    time.sleep(.56)
                    return {"observer_position":list(conn.position),"player_serial":conn.serial,"approach":route}
                route=[] if blocked_child else approach(conn,sample,office)
            if blocked_child and any(" chair-loiter " in e for e in gate["Trace"]):
                blocked,=[e.split() for e in gate["Trace"] if " chair-blocked " in e]
                work=saved["Work"][seed["actors"]["12"]["id"]]
                if (work!={"Kind":11,"State":1} or gate["OfficeSeat"] is not None or blocked[2]!=blocked_child["SeatId"] or
                        any(" seated " in e for e in gate["Trace"])):
                    raise ValueError("Obstructed chair did not return to the loiter schedule")
                pos=[int(blocked[3]),int(blocked[4]),blocked_child["Target"]["Z"]]
                return {"blocked_position":pos,
                        "saved_work":work,"trace":gate["Trace"],"player_serial":conn.serial,
                        "observer_position":list(conn.position),"approach":route}
            if blocked_child and any(" seated " in e for e in gate["Trace"]):
                raise ValueError("Mayor sat after a player occupied his active route destination")
            if any(" seated " in e for e in gate["Trace"]):
                seat=seated_mayor(conn,world,seed,gate)
                return {"seat":seat,"trace":gate["Trace"],"saved_child":gate["OfficeSeat"],"player_serial":conn.serial,
                        "observer_position":list(conn.position),"approach":route}
        time.sleep(.25)
    raise ValueError("No saved seated state within the office observation")


def play(game, root, state, start, fixture, *, interrupt=False, previous=None):
    conn = PlayerConnection(game, root)
    if list(conn.enter()) != start:
        raise ValueError("Player entered away from the original observer location")
    registry = state / "world/UltimaOfflineDialogue/UltimaOfflineDialogue.bin"
    actor = fixture["initial_mayor"]
    serial = previous["actor_serial"] if previous else None
    positions = list(previous["seen_positions"]) if previous else []
    if previous and conn.serial!=previous["player_serial"]:
        raise ValueError("A different player resumed the incomplete appointment")
    deadline = time.monotonic()+190
    while time.monotonic() < deadline:
        conn.resync()
        if serial is None:
            xy = (*actor["world_xy"], 4*actor["lift"])
            found = [s for s,p in conn.mobiles.items() if p == xy and s != conn.serial]
            if len(found) == 1:
                serial = found[0]
        if serial in conn.mobiles:
            point = list(conn.mobiles[serial])
            if not positions or point != positions[-1]:
                positions.append(point)
        if registry.is_file():
            saved,_ = read_registry(registry)
            gate = saved["Gate"]
            if gate["Error"]:
                raise ValueError(gate["Error"])
            if interrupt and gate["OfficeSteps"]>0 and gate["OfficePath"] and not gate["OfficeArrived"]:
                if serial is None:
                    raise ValueError("Active route lacks a witnessed actor serial")
                return {"gate":gate, "work":saved["Work"], "actor_serial":serial,
                        "player_serial":conn.serial, "seen_positions":positions}
            if gate["OfficeArrived"]:
                if interrupt:
                    raise ValueError("No partial route was saved before arrival")
                break
        time.sleep(0.3)
    else:
        raise ValueError("No saved morning office arrival within 190 seconds")
    assignment, = [t.split() for t in gate["Trace"] if " appointment " in t]
    arrival, = [t.split() for t in gate["Trace"] if " office " in t]
    row = fixture["source_row"]
    target = list(map(int,arrival[2:4]))
    tick = fixture["start_tick"]+int(assignment[0])
    if (tick != 9000 or list(map(int,assignment[2:])) != [row["offset"],2,16,*row["world_xy"]] or
            target != row["world_xy"] or (int(arrival[4])>0) != fixture["resident"] or
            not gate["OfficeWokeFromSleep"] or (fixture["resident"] and len(positions)<2)):
        raise ValueError(f"Office source timing, location or movement differs: {assignment}, {arrival}, {positions}")
    return {"assignment_tick":tick, "arrival_tick":fixture["start_tick"]+int(arrival[0]),
            "walk_steps":int(arrival[4]), "actor_positions_visible_to_player":positions,
            "office_xy":target, "trace":gate["Trace"], "saved_work":saved["Work"],
            "player_serial":conn.serial, "visible_fence":visible_fence(conn,fixture["exterior_fence_cells"])}
