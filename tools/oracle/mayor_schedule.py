"""Compare Finnigan's saved DOS locations with his timetable and the converted office trace."""
import argparse
import hashlib
import json
import struct
from pathlib import Path

from tools.oracle.departure import native_actors, qualify_departure
from u7uo.containers import decode_member
from u7uo.story_seed import forge_clock
from u7uo.u7 import seed_directory
from u7uo.world import schedule_entries


def saved_npc_route(member, handle):
    """Decode the route owned by this actor in the original PATH.DAT slot table."""
    table = member("path.dat")
    if len(table) != 45 or any(flag not in (0, 1) for flag in table[:15]):
        raise ValueError("Invalid DOS route slot table")
    owners = struct.unpack_from("<15H", table, 15)
    slots = [i for i, owner in enumerate(owners) if table[i] and owner == handle]
    if not slots:
        return None
    if len(slots) != 1:
        raise ValueError("Actor owns multiple active DOS routes")
    slot = slots[0]
    raw = member(f"path{slot}.dat")
    if len(raw) < 38:
        raise ValueError("Truncated DOS route header")
    actor, held, _, x, y, z, index, failures, count = struct.unpack_from("<5Hb3H", raw, 21)
    if actor != handle or len(raw) != 38 + 5*count or index > count:
        raise ValueError("Invalid DOS route owner, index or waypoint count")
    return {"slot":slot, "actor":actor, "held_door":held, "destination":[x,y,z],
            "waypoint_index":index, "failures":failures,
            "waypoints":[list(p) for p in struct.iter_unpack("<HHb", raw[38:])]}


def appointment_state(raw):
    directory = seed_directory(raw)
    def member(name):
        _, offset, size = directory[name]
        return raw[offset:offset+size]
    npcs, items = member("u7nbuf.dat"), member("u7ibuf.dat")
    actors = native_actors(npcs, items, (0, 12))
    actors["12"]["saved_route"] = saved_npc_route(member, actors["12"]["handle"])
    mayor_offset = 105*12
    level = npcs[mayor_offset+82]
    if level >= 5:
        raise ValueError("Invalid native schedule stack index")
    actors["12"]["schedule_stack"] = [
        {"kind":kind, "state":state, "x":x, "y":y, "counter":count}
        for kind,state,x,y,count in struct.iter_unpack("<BBhhB",
            npcs[mayor_offset+46:mayor_offset+46+7*(level+1)])
    ]
    for slot in (0, 12):
        a = actors[str(slot)]
        ext = int.from_bytes(items[a["handle"]+6:a["handle"]+8], "little")
        a["lift"] = items[ext+5] >> 4
        a["hp"] = int.from_bytes(items[ext+6:ext+7], "little", signed=True)
        a["activity"] = npcs[105*slot+10]
        a["status_word"] = int.from_bytes(npcs[105*slot+4:105*slot+6], "little")
    return {"clock": forge_clock(raw, require_saved=True), "avatar": actors["0"], "mayor": actors["12"]}


def qualify_trial(root, session):
    from .topic_order import DEPARTURE_RECEIPT
    session = session.resolve()
    encoded = (session/"receipt.json").read_bytes()
    rec = json.loads(encoded)
    continuation = rec["native_continuation"]
    donor = Path(continuation["source"]).resolve()
    parent = root.resolve()/"Evidence/dos-reference"
    if (session.parent != parent or donor.parent.parent != parent or
            donor.name not in {"home-approach-GAME04.U7", "healer-approach-GAME02.U7"}):
        raise ValueError("Unexpected private appointment donor")
    ancestry = (donor.parent/"receipt.json").read_bytes()
    if hashlib.sha256(ancestry).hexdigest() != DEPARTURE_RECEIPT:
        raise ValueError("Unexpected original investigation")
    source = json.loads(ancestry)
    if (not rec.get("finished") or rec["inputs"] != source["inputs"] or
            rec["wasm_sha256"] != source["wasm_sha256"] or rec["config_sha256"] != source["config_sha256"] or
            hashlib.sha256((session/"dosbox.conf").read_bytes()).hexdigest() != source["config_sha256"]):
        raise ValueError("Incomplete trial or changed DOS inputs")
    raw = donor.read_bytes()
    sha = hashlib.sha256(raw).hexdigest()
    if continuation["sha256"] != sha or not any(c["file"] == donor.name and c["sha256"] == sha for c in source["checkpoints"]):
        raise ValueError("Changed appointment donor")
    initial = appointment_state(raw)
    _, offset, length = seed_directory(raw)["gametimm.dat"]
    before = raw[offset:offset+length]
    if rec["appointment_clock"] != {"member":"GAMEDAT/GAMETIMM.DAT", "before":before.hex(), "ticks":8875,
                                    "after":((8875).to_bytes(2,"little")+before[2:]).hex()}:
        raise ValueError("Expected the clock-only 05:55 preparation")
    observations = []
    for c in rec["checkpoints"]:
        if Path(c["file"]).name != c["file"]:
            raise ValueError("Unexpected save path")
        raw = (session/c["file"]).read_bytes()
        if hashlib.sha256(raw).hexdigest() != c["sha256"]:
            raise ValueError("Changed appointment sample")
        state = appointment_state(raw)
        if (state["clock"]["days"] != initial["clock"]["days"] or state["clock"]["rate"] != 1 or
                state["avatar"]["world_xy"] != initial["avatar"]["world_xy"] or
                state["mayor"]["handle"] != initial["mayor"]["handle"] or
                state["clock"]["ticks"] <= (observations[-1]["clock"]["ticks"] if observations else 8874)):
            raise ValueError("Invalid clock sequence, player position or actor identity")
        observations.append({**c, **state})
    earlier = [s for s in observations if s["clock"]["ticks"] < 9000]
    later = [s for s in observations if s["clock"]["ticks"] >= 9000]
    if not earlier or not later or any(s["mayor"]["activity"] != 14 for s in earlier) or any(s["mayor"]["activity"] != 16 for s in later):
        raise ValueError("Native saves did not bracket sleep and the major sit appointment")
    data = (root/"Assets/UltimaVII-Steam/STATIC/SCHEDULE.DAT").read_bytes()
    if hashlib.sha256(data).hexdigest() != rec["inputs"]["STATIC/SCHEDULE.DAT"]["sha256"]:
        raise ValueError("Changed Finnigan timetable")
    row, = [r for r in schedule_entries(data) if r["npc_slot"] == 12 and r["time_slot"] == 2]
    arrived = [s for s in later if s["mayor"]["world_xy"] == row["world_xy"]]
    if not arrived or row["activity"] != 16:
        raise ValueError("No saved arrival at the source appointment")
    x,y = initial["avatar"]["world_xy"]
    mx,my = initial["mayor"]["world_xy"]
    left, top = (x & ~15)-32, (y & ~15)-32
    resident = left <= mx < left+80 and top <= my < top+80
    walked = any(s["mayor"]["world_xy"] not in (initial["mayor"]["world_xy"],row["world_xy"]) for s in later)
    if resident and not walked:
        raise ValueError("No intermediate native tile for the resident control")
    first_arrival = observations.index(arrived[0])
    last_office_absence = observations[first_arrival-1]["clock"]["ticks"]
    return {"source_save":donor.name, "donor_sha256":sha, "receipt_sha256":hashlib.sha256(encoded).hexdigest(),
            "fixture_clock":rec["appointment_clock"], "initial":initial, "source_schedule":row, "resident":resident,
            "observations":observations, "transition_bracket_ticks":[earlier[-1]["clock"]["ticks"],later[0]["clock"]["ticks"]],
            "first_observed_arrival_tick":arrived[0]["clock"]["ticks"], "intermediate_tile_observed":walked,
            "arrival_bracket_ticks":[last_office_absence, arrived[0]["clock"]["ticks"]]}


def compare_arrival(trial, player_path, build_id):
    raw = player_path.read_bytes()
    player = json.loads(raw)
    fixture = player["fixture"]
    if (player["status"] != "passed" or not player["saved_and_restarted"] or player["build_id"] != build_id
            or fixture["native_receipt_sha256"] != trial["receipt_sha256"]
            or fixture["source_row"] != trial["source_schedule"] or player["office_xy"] != trial["source_schedule"]["world_xy"]):
        raise ValueError("Player run is incomplete or belongs to a different appointment or facet")
    low, high = trial["arrival_bracket_ticks"]
    arrival = player["arrival_tick"]
    result = {"donor":trial["source_save"], "resident":trial["resident"],
            "player_report_sha256":hashlib.sha256(raw).hexdigest(), "build_id":build_id,
            "native_arrival_bracket_ticks_exclusive_inclusive":[low,high],
            "target_arrival_tick":arrival, "target_walk_steps":player["walk_steps"],
            "target_within_observed_window":low < arrival <= high,
            "minimum_late_ticks":max(0, arrival-high), "minimum_early_ticks":max(0,low+1-arrival),
            "saved_and_restarted":True}
    if "observations" in trial:
        routes = [s["mayor"]["saved_route"] for s in trial["observations"] if s["mayor"].get("saved_route")]
        native_segments = []
        for route in routes:
            xy = route["destination"][:2]
            if not native_segments or xy != native_segments[-1]:
                native_segments.append(xy)
        plans = [t.split() for t in player["trace"] if " office-route " in t]
        target_segments = [[int(t[4]),int(t[5])] for t in plans]
        wake = [t.split() for t in player["trace"] if " wake " in t]
        result.update(native_route_targets_observed=native_segments, target_route_targets=target_segments,
                      native_first_observed_route_origin=routes[0]["waypoints"][0] if routes and routes[0]["waypoints"] else None,
                      target_bed_exit_xy=[int(wake[0][3]),int(wake[0][4])] if wake else None)
        arrival_sample = next(s for s in trial["observations"] if s["clock"]["ticks"]==high)
        result["native_schedule_stack_at_first_arrival"] = arrival_sample["mayor"].get("schedule_stack")
        result["target_saved_work"] = player["saved_work"]
        it = iter(target_segments)
        result["all_observed_native_segments_in_target_order"] = all(xy in it for xy in native_segments)
    return result


def observe(installation, session, replay):
    qualification = qualify_departure(session, installation)
    receipt = json.loads((session/"receipt.json").read_bytes())
    data = (installation/"Assets/UltimaVII-Steam/STATIC/SCHEDULE.DAT").read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    if digest != receipt["inputs"]["STATIC/SCHEDULE.DAT"]["sha256"]:
        raise ValueError("Changed DOS timetable")
    rows = [r for r in schedule_entries(data) if r["npc_slot"] == 12]
    result = []
    for record in receipt["checkpoints"]:
        raw = (session/record["file"]).read_bytes()
        if hashlib.sha256(raw).hexdigest() != record["sha256"]:
            raise ValueError("Changed original schedule checkpoint")
        state = appointment_state(raw)
        actor, clock = state["mayor"], state["clock"]
        period = clock["ticks"] // 4500
        row = min(rows, key=lambda r: (period-r["time_slot"]) % 8)
        result.append({"save": record["file"], "sha256": record["sha256"], "clock": clock,
                       "actor": actor, "nominal_schedule": row})
    raw = replay.read_bytes()
    target = json.loads(raw)
    target = target.get("player_replay", target)
    if target["status"] != "passed":
        raise ValueError("Expected a completed converted replay")
    office = target["opening"]["journey"]["office_schedule"]
    row, = [r for r in rows if r["offset"] == office["row"]]
    if row["world_xy"] != office["target"] or row["activity"] != 16:
        raise ValueError("Target office appointment differs from original schedule")
    arrival, = [t.split() for t in office["trace"] if " office " in t]
    _, _, arrival_x, arrival_y, steps = arrival
    native_report, = [s for s in result if s["save"] == "return-to-mayor-GAME05.U7"]
    if native_report["nominal_schedule"] != row:
        raise ValueError("DOS report did not fall within the staged appointment")
    # Major sit approaches a chair on the tile selected by its source frame's low two bits.
    # Match the settled actor to source placements. The save contains no selected chair handle.
    static = installation/"Assets/UltimaVII-Steam/STATIC"
    inputs = {}
    for name in ("INITGAME.DAT","TFA.DAT"):
        inputs[name] = (static/name).read_bytes()
        if hashlib.sha256(inputs[name]).hexdigest()!=receipt["inputs"]["STATIC/"+name]["sha256"]:
            raise ValueError("Changed source geometry for seated mayor")
    archive = inputs["INITGAME.DAT"]
    digest = hashlib.sha256(archive).hexdigest()
    x,y = row["world_xy"]
    directory = seed_directory(archive)
    chairs = []
    for sy in range(max(y-12,0)//256,min(y+12,3071)//256+1):
        for sx in range(max(x-12,0)//256,min(x+12,3071)//256+1):
            region = sy*12+sx
            _,off,size = directory[f"u7ireg{region:02x}"]
            objects,_ = decode_member(archive[off:off+size],inputs["TFA.DAT"],off,digest,region)
            for obj in objects:
                if obj["edge"]!="world" or obj["shape"] not in (873,292):
                    continue
                cx,cy = obj["world_xy"]
                dx,dy = ((0,-1),(1,0),(0,1),(-1,0))[obj["frame"]&3]
                if max(abs(cx-x),abs(cy-y))<=12 and [cx+dx,cy+dy]==native_report["actor"]["world_xy"]:
                    chairs.append({k:obj[k] for k in ("id","shape","frame","lift","world_xy","offset")})
    comparison = {"edition": qualification["edition"], "build_id": target["build_id"],
            "replay_sha256": hashlib.sha256(raw).hexdigest(), "timetable_sha256": digest,
            "checkpoints": result, "converted_office": office, "converted_arrival_xy": [int(arrival_x), int(arrival_y)],
            "converted_walk_steps": int(steps), "dos_pre_report_xy": native_report["actor"]["world_xy"],
            "source_chair_approaches_matching_pre_report_xy":chairs,
            "timing_and_path": "unverified between native checkpoints"}
    if "seat" in office:
        seat=office["seat"]
        source=seat["source"]
        cx,cy=source["world_xy"]
        dx,dy=((0,-1),(1,0),(0,1),(-1,0))[source["frame"]&3]
        if seat["position"]!=[cx+dx,cy+dy,4*source["lift"]] or seat["work"]!={"Kind":16,"State":3}:
            raise ValueError("Seated replay position or major schedule disagrees with source geometry")
        matching=next((c for c in chairs if c["id"]==source["id"]),None)
        comparison["seated_mayor"]={"source_id":source["id"],"anchor":[cx,cy],"position":seat["position"],
            "direction":2*(source["frame"]&3),"work":seat["work"],
            "matches_native_pre_report_position":seat["position"][:2]==native_report["actor"]["world_xy"],
            "consistent_with_native_pre_report_chair":matching is not None,
            "native_pre_report_frame":native_report["actor"]["frame"]}
    return comparison


def qualify_office_observer(root, session):
    """Verify a DOS continuation from the nonresident appointment, including the later seated pose."""
    session=session.resolve()
    evidence=root.resolve()/"Evidence/dos-reference"
    if session.parent!=evidence:
        raise ValueError("Office observer must be an archived native session")
    rec=json.loads((session/"receipt.json").read_bytes())
    origin=rec["native_continuation"]
    donor=Path(origin["source"]).resolve()
    if donor.parent.parent!=evidence or Path(origin["original_receipt"]).resolve()!=donor.parent/"receipt.json":
        raise ValueError("Unbound native office continuation")
    trial=qualify_trial(root,donor.parent)
    original=json.loads((donor.parent/"receipt.json").read_bytes())
    if (trial["resident"] or not rec.get("finished") or rec["inputs"]!=original["inputs"] or
            rec["wasm_sha256"]!=original["wasm_sha256"] or rec["scene_setup"]["method"]!="Original F2 debug menu" or
            rec["scene_setup"]["base_config_sha256"]!=original["config_sha256"] or
            hashlib.sha256((session/"dosbox.conf").read_bytes()).hexdigest()!=rec["config_sha256"]):
        raise ValueError("Office observer changed the original inputs or parent fixture")
    def checked(row, folder):
        name=row["file"]
        if Path(name).name!=name:
            raise ValueError("Invalid saved observation path")
        raw=(folder/name).read_bytes()
        if hashlib.sha256(raw).hexdigest()!=row["sha256"]:
            raise ValueError(f"Changed original office observation {name}")
        return raw
    source,=[row for row in original["checkpoints"] if row["file"]==donor.name and row["sha256"]==origin["sha256"]]
    initial=appointment_state(checked(source,donor.parent))
    office=trial["source_schedule"]["world_xy"]
    if initial["mayor"]["world_xy"]!=office or initial["mayor"]["schedule_stack"][-1]["kind"]!=16:
        raise ValueError("The original actor had not reached the office")
    observations=[]
    for row in rec["checkpoints"]:
        state=appointment_state(checked(row,session)); actor=state["mayor"]
        if (state["avatar"]["world_xy"]!=office or actor["handle"]!=initial["mayor"]["handle"] or
                state["clock"]["days"]!=initial["clock"]["days"] or
                state["clock"]["ticks"]<=(observations[-1]["ticks"] if observations else initial["clock"]["ticks"])):
            raise ValueError("Original observer, clock or actor identity differs")
        observations.append({"file":row["file"],"sha256":row["sha256"],"ticks":state["clock"]["ticks"],
            "xy":actor["world_xy"],"frame":actor["frame"],"stack":[[s["kind"],s["state"]] for s in actor["schedule_stack"]],
            "route":actor["saved_route"]})
    walks=[o for o in observations if o["stack"]==[[16,1],[35,5]] and o["route"]]
    sitting=[o for o in observations if o["stack"]==[[16,3]]]
    if (not walks or not sitting or observations[-1] not in sitting or
            not any(o["stack"]==[[16,1],[35,10]] for o in observations) or
            any(o["xy"]!=walks[0]["route"]["destination"][:2] or o["frame"]&15!=10 for o in sitting)):
        raise ValueError("Native observations do not link the chair route, posted script and settled mayor")
    for frame in rec["frames"]:
        checked(frame,session)
    return {"source_trial":donor.parent.name,"source_save":donor.name,"donor_sha256":origin["sha256"],
            "receipt_sha256":hashlib.sha256((session/"receipt.json").read_bytes()).hexdigest(),
            "office":office,"walk_destination":walks[0]["route"]["destination"],"settled_frame":sitting[-1]["frame"],
            "observations":observations}


def compare_chair_restarts(root, observer, clear, occupied, retry=None):
    """Check two original-process restarts of the same active chair route, with one controlled cell change."""
    native=qualify_office_observer(root,observer)
    evidence=root.resolve()/"Evidence/dos-reference"
    parent=json.loads((observer/"receipt.json").read_bytes())
    result={}
    for label,folder in (("clear",clear),("occupied",occupied)):
        if folder.resolve().parent!=evidence:
            raise ValueError("Unbound chair restart")
        raw=(folder/"receipt.json").read_bytes()
        rec=json.loads(raw)
        origin=rec["native_continuation"]
        donor=Path(origin["source"]).resolve()
        if (donor.parent!=observer.resolve() or Path(origin["original_receipt"]).resolve()!=observer.resolve()/"receipt.json" or
                any(rec[k]!=parent[k] for k in ("inputs","wasm_sha256","config_sha256")) or
                not rec.get("finished") or hashlib.sha256((folder/"dosbox.conf").read_bytes()).hexdigest()!=rec["config_sha256"]):
            raise ValueError("Original chair restart changed its inputs")
        original=donor.read_bytes()
        digest=hashlib.sha256(original).hexdigest()
        if (digest!=origin["sha256"] or not any(s["file"]==donor.name and s["sha256"]==digest and
                s["stack"]==[[16,1],[35,5]] for s in native["observations"])):
            raise ValueError("Donor is not a verified active native seat search")
        initial=appointment_state(original)
        actor=initial["mayor"]
        target=actor["saved_route"]["destination"]
        if actor["world_xy"] in (native["office"],target[:2]):
            raise ValueError("Expected a partially walked original chair route")
        avatar=initial["avatar"]
        expected_xy=avatar["world_xy"]
        if label=="occupied":
            if result["clear"]["donor_sha256"]!=digest:
                raise ValueError("Occupied control used another initial world")
            _,off,size=seed_directory(original)["u7ibuf.dat"]
            data=bytearray(original[off:off+size])
            offset=avatar["handle"]+2
            change={"member":"GAMEDAT/U7IBUF.DAT","actor":avatar["handle"],"offset":offset,
                    "before":expected_xy,"after":target[:2],"original_sha256":hashlib.sha256(data).hexdigest()}
            if ([v//16 for v in expected_xy]!=[v//16 for v in target[:2]] or avatar["lift"]!=target[2] or
                    list(data[offset:offset+2])!=[v%256 for v in expected_xy]):
                raise ValueError("Occupied fixture changed chunk, lift or source identity")
            data[offset:offset+2]=bytes(v%256 for v in target[:2])
            change["modified_sha256"]=hashlib.sha256(data).hexdigest()
            if change!=rec.get("occupied_chair"): raise ValueError("Unverified native occupancy override")
            expected_xy=target[:2]
        elif rec.get("occupied_chair"):
            raise ValueError("Clear control modified the source placement")
        rows=[]
        for row in rec["checkpoints"]:
            if Path(row["file"]).name!=row["file"]: raise ValueError("Unexpected checkpoint path")
            saved=(folder/row["file"]).read_bytes()
            if hashlib.sha256(saved).hexdigest()!=row["sha256"]: raise ValueError("Changed chair restart checkpoint")
            state=appointment_state(saved); mayor=state["mayor"]
            if (state["avatar"]["world_xy"]!=expected_xy or state["avatar"]["handle"]!=avatar["handle"] or
                    mayor["handle"]!=actor["handle"] or state["clock"]["days"]!=initial["clock"]["days"] or
                    state["clock"]["ticks"]<=(rows[-1]["ticks"] if rows else initial["clock"]["ticks"])):
                raise ValueError("Changed observer, actor or clock during native control")
            rows.append({"file":row["file"],"sha256":row["sha256"],"ticks":state["clock"]["ticks"],"xy":mayor["world_xy"],
                         "frame":mayor["frame"],"stack":[[s["kind"],s["state"]] for s in mayor["schedule_stack"]],
                         "route":mayor["saved_route"]})
        if len(rows)<2: raise ValueError("Need a continuing observation after the first restored sample")
        if label=="clear":
            if (rows[-1]["stack"]!=[[16,3]] or rows[-1]["xy"]!=target[:2] or rows[-1]["frame"]!=native["settled_frame"]):
                raise ValueError("Reopened original route failed to restore its seated outcome")
        elif (any(s["stack"][0][0]!=11 or s["xy"]==target[:2] for s in rows) or
              max(abs(a-b) for a,b in zip(rows[0]["xy"],target[:2]))!=1):
            raise ValueError("Occupied control did not stop adjacent and switch to loiter")
        result[label]={"session":folder.name,"receipt_sha256":hashlib.sha256(raw).hexdigest(),"donor_sha256":digest,
                       "initial_xy":actor["world_xy"],"target":target,"observer_xy":expected_xy,"samples":rows}
    if retry is not None:
        if retry.resolve().parent!=evidence: raise ValueError("Unbound appointment retry")
        raw=(retry/"receipt.json").read_bytes()
        rec=json.loads(raw)
        final=result["occupied"]["samples"][-1]
        donor=occupied/final["file"]
        origin=rec["native_continuation"]
        if (Path(origin["source"]).resolve()!=donor.resolve() or origin["sha256"]!=final["sha256"] or
                Path(origin["original_receipt"]).resolve()!=(occupied/"receipt.json").resolve() or
                any(rec[k]!=parent[k] for k in ("inputs","wasm_sha256","config_sha256")) or
                not rec.get("finished") or rec.get("occupied_chair") or
                hashlib.sha256((retry/"dosbox.conf").read_bytes()).hexdigest()!=rec["config_sha256"]):
            raise ValueError("Following native appointment differs from the obstruction donor")
        boundary=(final["ticks"]//375+1)*375
        initial=appointment_state(donor.read_bytes())
        samples=[]
        for row in rec["checkpoints"]:
            if Path(row["file"]).name!=row["file"]: raise ValueError("Invalid retry checkpoint")
            data=(retry/row["file"]).read_bytes()
            if hashlib.sha256(data).hexdigest()!=row["sha256"]: raise ValueError("Changed retry checkpoint")
            a=appointment_state(data);m=a["mayor"];ticks=a["clock"]["ticks"]
            if (a["avatar"]["world_xy"]!=initial["avatar"]["world_xy"] or a["clock"]["days"]!=initial["clock"]["days"] or
                    m["handle"]!=initial["mayor"]["handle"] or not boundary<=ticks<boundary+375 or
                    samples and ticks<=samples[-1]["ticks"]):
                raise ValueError("Invalid next-quarter observation")
            samples.append({"file":row["file"],"sha256":row["sha256"],"ticks":ticks,"xy":m["world_xy"],
                            "frame":m["frame"],"stack":[[s["kind"],s["state"]] for s in m["schedule_stack"]]})
        if (len(samples)<2 or samples[0]["stack"]!=[[16,0],[49,1]] or samples[-1]["stack"]!=[[16,3]] or
                samples[-1]["frame"]&15!=10 or samples[-1]["xy"]==initial["avatar"]["world_xy"]):
            raise ValueError("Expected return to the appointed office and an unobstructed seat")
        result["next_appointment"]={"boundary_tick":boundary,"session":retry.name,"donor_sha256":final["sha256"],
                                    "receipt_sha256":hashlib.sha256(raw).hexdigest(),"samples":samples}
    return result


def chair_player_results(reference,clear_file,occupied_file,build):
    """Compare branch outcomes without assuming either engine picked the other's chair or clock."""
    result={}
    for label,path in (("clear",clear_file),("occupied",occupied_file)):
        raw=path.read_bytes()
        run=json.loads(raw)
        cut=run["chair_restart"]
        child=cut["child"]
        if (run["status"]!="passed" or run["build_id"]!=build or not run["saved_and_restarted"] or
                child["State"]!=5 or not 0<len(child["Path"])<cut["route_length"] or cut["old_pid"]==cut["new_pid"]):
            raise ValueError("Player did not restart with a partially consumed native chair route")
        selection=(child["SeatId"],child["Target"],cut["route_length"],child["Path"],cut["saved_rng"])
        target=[child["Target"][axis] for axis in "XYZ"]
        row={"file":path.name,"sha256":hashlib.sha256(raw).hexdigest(),"build_id":build,"target":target,
             "pending_directions":child["Path"],"initial_length":cut["route_length"],"saved_rng":cut["saved_rng"]}
        if label=="clear":
            control=selection
            seat=run["restored_seat"]
            if (seat!=run["seat"] or seat["source"]["id"]!=child["SeatId"] or seat["position"]!=target or
                    seat["work"]!={"Kind":16,"State":3} or reference[label]["samples"][-1]["stack"]!=[[16,3]]):
                raise ValueError("Unobstructed chair outcomes differ")
            row["restored_seat"]=seat
        else:
            if (selection!=control or run["blocker"]["position"]!=target or run["saved_work"]!=run["restored_work"] or
                    run["restored_work"]["Kind"]!=reference[label]["samples"][0]["stack"][0][0] or
                    max(abs(a-b) for a,b in zip(run["blocked_position"][:2],target[:2]))!=1):
                raise ValueError("Occupied player control changed the saved route or missed the loiter transition")
            after=run["next_appointment"]
            if (after["ticks"]%375 or after["seat"]["source"]["id"]==child["SeatId"] or
                    after["seat"]["work"]!={"Kind":16,"State":3} or
                    reference["next_appointment"]["samples"][-1]["stack"]!=[[16,3]]):
                raise ValueError("Following office appointment did not restore the major sit schedule")
            row.update(blocked_position=run["blocked_position"],loiter=run["restored_work"],next_appointment=after)
        result[label]=row
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for arg in ("installation", "session", "replay"):
        parser.add_argument(arg, type=Path)
    parser.add_argument("--trial", action="append", type=Path, default=[])
    parser.add_argument("--office-observer",type=Path)
    parser.add_argument("--chair-restarts",nargs=2,type=Path,metavar=("CLEAR","OCCUPIED"))
    parser.add_argument("--chair-retry",type=Path,help="Native continuation through the next appointment with the chair occupied")
    parser.add_argument("--chair-player",nargs=2,type=Path,metavar=("CLEAR","OCCUPIED"))
    parser.add_argument("--player", action="append", type=Path, default=[],
                        help="Matched target report for each --trial, in the same order and on the replay build")
    args = parser.parse_args()
    result = observe(args.installation, args.session, args.replay)
    if args.office_observer:
        result["office_observer"]=qualify_office_observer(args.installation,args.office_observer)
    if args.chair_restarts:
        if not args.office_observer: parser.error("Chair restarts require their parent office observer")
        result["chair_restarts"]=compare_chair_restarts(args.installation,args.office_observer,*args.chair_restarts,args.chair_retry)
    elif args.chair_retry:
        parser.error("The next-quarter control needs both chair restarts")
    if args.chair_player:
        if not args.chair_retry: parser.error("The paired player reports need the native restarts and next appointment")
        result["chair_player"]=chair_player_results(result["chair_restarts"],*args.chair_player,result["build_id"])
    if args.trial:
        result["morning_trials"] = [qualify_trial(args.installation, path) for path in args.trial]
    if args.player:
        if len(args.player) != len(args.trial):
            parser.error("Supply one --player per --trial")
        result["morning_comparison"] = [compare_arrival(t,p,result["build_id"])
                                        for t,p in zip(result["morning_trials"], args.player)]
    print(json.dumps(result, indent=2))
