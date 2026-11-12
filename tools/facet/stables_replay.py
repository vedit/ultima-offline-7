"""Check the stables egg and key using ordinary movement, drag/drop and native saves."""
from collections import deque
import hashlib
import json
import struct
import time

from .player_replay import DIRECTIONS, check_say, compressed_gump, open_actor, read_registry, send_reply


def path_to(sample, start, targets, *, avoid=()):
    ox, oy = sample["source_origin"]
    ground = {(ox + cell["x"], oy + cell["y"]) for cell in sample["cells"]}
    solid = {r["id"] for r in sample["static_rules"].values() if r["flags"] & 0x40}
    blocked = {(ox + s["x"], oy + s["y"]) for s in sample["statics"] if s["z"] == 0 and s["id"] in solid}
    blocked.update(tuple(r["world_xy"]) for r in sample["ireg_objects_deferred"] if r["shape"] != 275)
    blocked.update(avoid)
    blocked.add(tuple(sample["finnigan"]["source"][:2]))
    prev = {start: None}
    queue = deque([start])
    while queue:
        pos = queue.popleft()
        if pos in targets:
            path = [pos]
            while prev[path[-1]] is not None:
                path.append(prev[path[-1]])
            return path[::-1]
        for dx, dy in DIRECTIONS.values():
            step = pos[0] + dx, pos[1] + dy
            if step in ground and step not in prev and step not in blocked:
                prev[step] = pos
                queue.append(step)
    raise ValueError(f"No walkable stables path from {start} to {sorted(targets)}")


def saved_key(world, key):
    return saved_source_item(world, "UltimaOffline.Entities.CampaignInvestigationItem",
                             key["id"], (key["shape"],key["frame"],key["quality_byte"]))


def saved_source_item(world, item_type, source_id, fields=(), *, source_payload=None):
    index = (world / "Items/Items.idx").read_bytes()
    data = (world / "Items/Items.bin").read_bytes()
    version, _, type_count = struct.unpack_from("<iqi", index)
    if version != 5 or not 0 < type_count <= 65535:
        raise ValueError("Unsupported native ModernUO item index")
    cursor = 16
    types = []
    for _ in range(type_count):
        length = 0
        for shift in range(0, 35, 7):
            octet = index[cursor]
            cursor += 1
            length |= (octet & 127) << shift
            if octet < 128:
                break
        else:
            raise ValueError("Invalid type-name size in ModernUO index")
        types.append(index[cursor:cursor + length].decode("utf-8"))
        cursor += length
    count, = struct.unpack_from("<i", index, cursor)
    records = index[cursor + 4:]
    layout = struct.Struct("<HIqqi")
    if len(records) != count * layout.size:
        raise ValueError("Truncated native ModernUO item index")
    tail = source_id.encode() + struct.pack("<" + "i"*len(fields), *fields)
    payload_size = 0
    if source_payload is not None:
        raw = source_payload.encode("ascii")
        # Regional records have 6 or 12 source bytes written as hex. Their
        # length (and ModernUO's worst-case UTF-8 size) fits a one-byte prefix.
        if len(raw) not in (12, 24) or bytes.fromhex(source_payload).hex() != source_payload:
            raise ValueError("Invalid saved regional payload")
        payload_size = 2 + len(raw)
        expected_payload = bytes((1, len(raw))) + raw
    matches = []
    for t, serial, _, pos, size in layout.iter_unpack(records):
        if t >= len(types) or pos < 0 or size < 0 or pos + size > len(data):
            raise ValueError("Invalid native ModernUO item index entry")
        if types[t] == item_type:
            payload = data[pos:pos + size]
            identity = payload[:-payload_size] if payload_size else payload
            if identity.endswith(tail):
                if payload_size and payload[-payload_size:] != expected_payload:
                    raise ValueError(f"Saved regional payload differs for {source_id}")
                matches.append({"serial":serial, "item_type":types[t], "offset":pos, "size":size,
                                "payload_sha256":hashlib.sha256(payload).hexdigest()})
    if len(matches) != 1:
        raise ValueError(f"Expected one saved {item_type} carrying {source_id}, found {len(matches)}")
    return matches[0]


def capture(world, seed, key):
    state, digest = read_registry(world / "UltimaOfflineDialogue/UltimaOfflineDialogue.bin")
    return {"flags":{str(i):state["Changes"].get(str(i), seed["flags"][i]) for i in (60,72,90)},
            "hatched":state.get("Hatched", {}), "registry_sha256":digest, "saved_key":saved_key(world, key)}


def bag_contents(conn):
    if conn.serial not in conn.backpacks:
        raise ValueError("The player equipment packet did not advertise a backpack")
    bag = conn.backpacks[conn.serial]
    conn.game.sendall(struct.pack(">BI", 0x06, bag))
    conn.expect({0x24}, predicate=lambda f:struct.unpack_from(">I", f, 1)[0] == bag)
    frame = conn.expect({0x3C})
    length, count = struct.unpack_from(">HH", frame, 1)
    if length != len(frame) or length != 5+count*20:
        raise ValueError("Unexpected ClassicUO container contents framing")
    children = {}
    for serial, art, _, amount, _, _, _, parent, _ in struct.iter_unpack(">IHBHHHBIH",frame[5:]):
        if serial in children or parent != bag:
            raise ValueError("Duplicate or wrong-parent item in opened backpack")
        children[serial] = (art, amount, parent)
    return bag, children


def lift_to_backpack(conn, serial, art):
    bag, before = bag_contents(conn)
    if serial in before:
        raise ValueError("Ground item also appeared inside the player backpack")
    # A normal double-click starts the pinned AOS shard's 1,000 ms action delay.
    time.sleep(1.15)
    conn.game.sendall(struct.pack(">BIH", 0x07, serial, 1))
    conn.game.sendall(b"\x73\x46")
    reply = conn.expect({0x73, 0x27}, predicate=lambda f:f[0] == 0x27 or f == b"\x73\x46")
    if reply[0] == 0x27:
        raise ValueError(f"Server refused ordinary lift of item {serial} (reason {reply[1]})")
    conn.game.sendall(struct.pack(">BIHHbBI", 0x08, serial, 40, 50, 0, 0, bag))
    reply = conn.expect({0x25, 0x27}, predicate=lambda f:f[0] == 0x27 or struct.unpack_from(">I",f,1)[0] == serial)
    if (reply[0] != 0x25 or len(reply) != 21 or struct.unpack_from(">I",reply,15)[0] != bag or
            struct.unpack_from(">H",reply,5)[0] != art):
        raise ValueError(f"Ordinary backpack drop did not confirm item {serial} and parent: {reply.hex()}")
    time.sleep(1.15)
    _, contents = bag_contents(conn)
    if contents.get(serial) != (art, 1, bag) or serial in conn.ground_items:
        raise ValueError(f"Dropped item {serial} not uniquely present in the opened backpack")
    return bag, contents


def play_stables(conn, sample, campaign, world, snapshot):
    seed = json.loads((campaign / "story-seed.json").read_bytes())
    key, = [r for r in seed["investigation_items"] if r["shape"] == 641 and r["quality_byte"] == 253]
    egg, = [r for r in seed["eggs"] if r["offset"] == 2489 and r["function_id"] == 0x06A4]
    if (key["frame"], key["offset"], key["edge"], key["world_xy"], key["movable"]) != (0,2571,"world",[1068,2197],True):
        raise ValueError("The staged investigation key differs from the original Trinsic key")
    snapshot()
    accepted = capture(world, seed, key)
    if accepted["flags"] != {"60":0,"72":0,"90":1} or accepted["hatched"]:
        raise ValueError(f"Unexpected pre-entry investigation state: {accepted}")
    ex, ey, _ = egg["position"]
    radius = egg["distance"]
    targets = {(x,y) for x in range(ex-radius, ex+radius+1) for y in range(ey-radius, ey+radius+1)}
    entrance = path_to(sample, conn.position[:2], targets)
    conn.walk(entrance)
    conn.resync()
    snapshot()
    entered = capture(world, seed, key)
    receipt = entered["hatched"].get(egg["id"], {})
    if (entered["flags"] != {"60":1,"72":0,"90":1} or len(entered["hatched"]) != 1 or
            [receipt.get(k) for k in ("Player","Before","After","Flag","Function","Event","MemberOffset","ArchiveOffset")] !=
            [conn.serial,0,1,60,0x06A4,3,egg["offset"],egg["archive_offset"]] or
            [receipt["X"],receipt["Y"]] != list(entrance[-1]) or
            [receipt["BeforeX"],receipt["BeforeY"]] != list(entrance[-2])):
        raise ValueError(f"Source egg and committed entrance movement differ: {entered}")
    serial = accepted["saved_key"]["serial"]
    position = (key["uo_art"], *key["world_xy"], key["lift"])
    if entered["saved_key"]["serial"] != serial or conn.ground_items.get(serial) != position:
        raise ValueError(f"Entered stable without seeing the saved original key on the ground: {conn.ground_items.get(serial)}")
    x, y = key["world_xy"]
    route = path_to(sample, conn.position[:2], {(x+dx,y+dy) for dx,dy in DIRECTIONS.values()})
    conn.walk(route)
    conn.resync()
    if conn.ground_items.get(serial) != position:
        raise ValueError("Ground key disappeared while walking to it")
    bag, contents = lift_to_backpack(conn, serial, key["uo_art"])
    snapshot()
    carried = capture(world, seed, key)
    if carried["hatched"] != entered["hatched"] or carried["flags"] != entered["flags"] or carried["saved_key"]["serial"] != serial:
        raise ValueError("The source key or stables state changed after the inventory transfer")
    return {"status":"pending_restart","source":key,"player_serial":conn.serial,"backpack_serial":bag,
            "key_serial":serial,"entrance_path":entrance,"key_approach_path":route,"saved_position":list(conn.position),
            "ground_packet":{"art":position[0],"position":list(position[1:]),"serial":serial},
            "inventory_packet":{"art":contents[serial][0],"amount":contents[serial][1],"parent":bag,"serial":serial},
            "accepted":accepted,"entered":entered,"carried":carried}


def restore_stables(conn, result, world, seed):
    serial = result["key_serial"]
    key = result["source"]
    if list(conn.position) != result["saved_position"] or conn.serial != result["player_serial"]:
        raise ValueError("Restored stables player differs from the saved position or serial")
    bag, contents = bag_contents(conn)
    restored = capture(world, seed, key)
    if (restored["flags"] != result["carried"]["flags"] or restored["hatched"] != result["carried"]["hatched"] or
            restored["saved_key"]["serial"] != serial or serial in conn.ground_items or
            bag != result["backpack_serial"] or contents.get(serial) != (key["uo_art"], 1, bag)):
        raise ValueError("Reloaded backpack, original key identity, or stables trigger differs from the native save")
    result.update(status="passed", restored=restored, reopened_backpack={"serial":bag,"owner":conn.serial,
                  "child":serial,"art":contents[serial][0],"amount":contents[serial][1]})


def check_investigation_triggers(carried, after, seed, trail, serial):
    prior = carried["hatched"]
    if any(after.get(key) != record for key,record in prior.items()):
        raise ValueError("A previously hatched investigation egg changed")
    expected = set(prior)
    for egg in seed["eggs"]:
        if egg["id"] in prior or egg.get("function_id") != 0x06A4:
            continue
        x,y = egg["world_xy"]
        radius = egg["distance"]
        for previous, step in zip(trail,trail[1:]):
            if previous == step or max(abs(step[0]-x),abs(step[1]-y)) > radius:
                continue
            rec = after.get(egg["id"], {})
            fields = ("Player","BeforeX","BeforeY","X","Y","Flag","Before","After","Function",
                      "Event","Radius","MemberOffset","ArchiveOffset")
            if [rec.get(k) for k in fields] != [
                    serial,*previous,*step,60,1,1,egg["function_id"],egg["event"],radius,
                    egg["offset"],egg["archive_offset"]]:
                raise ValueError(f"Player route and original investigation egg disagree at {egg['id']}")
            expected.add(egg["id"])
            break
    if set(after) != expected:
        raise ValueError("Unexpected investigation egg outside the player's route")


def report_key(conn, movement, investigation, campaign, world, snapshot, *, return_path=None, travelled=()):
    # Return along the route just walked, including the already-hatched stable
    # entrance. A saved key must remain in the backpack during the conversation.
    back = return_path if return_path is not None else [
        *investigation["key_approach_path"][::-1], *investigation["entrance_path"][-2::-1]]
    conn.walk(back)
    if list(conn.resync()) != movement["approach"]:
        raise ValueError("The return to the Mayor did not reach the saved approach position")
    serial = conn.actor(movement["actor"]["position"],"Finnigan")
    if "serial" in movement["actor"] and serial != movement["actor"]["serial"]:
        raise ValueError("The returning player could not identify the original Mayor")
    doc = json.loads((campaign / "dialogue.json").read_bytes())
    function, = [f for f in doc["program"]["functions"] if f["id"] == 0x040C]
    rows = {pc:(op,args) for pc,op,args,_ in function["rows"]}
    def literal(pc, opcode):
        op, args = rows[pc]
        if op != opcode:
            raise ValueError(f"Source no longer references a literal at 040C:{pc:04X}")
        return function["strings"][str(args[0])]
    pages = []
    def say(page, pc):
        h = check_say(page,literal(pc,0x1C),f"0x040C:0x{pc:X}")
        pages.append({"append_pc":pc,"text_sha256":h,"gump_sha256":page["digest"]})
        send_reply(conn,page,next(iter(page["buttons"])))
        return compressed_gump(conn.expect({0xDD}))
    def choose(page, options, wanted):
        if list(page["buttons"].values()) != options:
            raise ValueError(f"Unexpected ordered original report topics: {list(page['buttons'].values())}")
        pages.append({"options":options,"selected":wanted,"gump_sha256":page["digest"]})
        send_reply(conn,page,next(k for k,v in page["buttons"].items() if v==wanted))
    page = say(open_actor(conn,serial),0x3C)
    choose(page,["Yes","No"],"Yes")
    page = say(compressed_gump(conn.expect({0xDD})),0x46)
    choose(page,[literal(pc,0x1D) for pc in (0x54,0x51,0x4E,0x66)],"a key")
    page = say(compressed_gump(conn.expect({0xDD})),0x87)
    for _ in range(16):
        if list(page["buttons"].values()) != ["Continue"]:
            break
        pages.append({"supplementary_say":page["digest"]})
        send_reply(conn,page,next(iter(page["buttons"])))
        page=compressed_gump(conn.expect({0xDD}))
    current,_=read_registry(world / "UltimaOfflineDialogue/UltimaOfflineDialogue.bin")
    seed = json.loads((campaign / "story-seed.json").read_bytes())
    topics=["name","job","murder","bye"]
    # Retail 040C:0259 tests whether the guard has already referred the player
    # to the Mayor. This adds a real topic on the gate-first route.
    if current["Changes"].get("66",seed["flags"][66]) and not current["Changes"].get("61",seed["flags"][61]):
        topics.append("password")
    choose(page,topics,"bye")
    conn.game.sendall(b"\x73\x64")
    for _ in range(16):
        response = conn.expect({0x73,0xDD})
        if response == b"\x73\x64":
            break
        page = compressed_gump(response)
        if list(page["buttons"].values()) != ["Continue"]:
            raise ValueError("Unexpected topic after leaving the Mayor")
        send_reply(conn,page,next(iter(page["buttons"])))
        conn.game.sendall(b"\x73\x64")
    snapshot()
    after = capture(world,seed,investigation["source"])
    registry,_ = read_registry(world / "UltimaOfflineDialogue/UltimaOfflineDialogue.bin")
    flag61 = registry["Changes"].get("61",seed["flags"][61])
    check_investigation_triggers(investigation["carried"],after["hatched"],seed,[*travelled,*back],conn.serial)
    if (after["flags"]!={"60":1,"72":1,"90":1} or flag61!=0 or
            str(conn.serial) in registry["Active"] or after["saved_key"]["serial"]!=investigation["key_serial"]):
        raise ValueError(f"Post-report native quest state differs from the original: {after}, flag61={flag61}")
    bag, contents = bag_contents(conn)
    if bag != investigation["backpack_serial"] or contents.get(investigation["key_serial"]) != (investigation["source"]["uo_art"],1,bag):
        raise ValueError("Reported key no longer belongs to the player's backpack")
    return {"status":"passed","npc_position":movement["actor"]["position"],"direct_interaction":True,
            "path":back,"pages":pages,"state":after,"flag61":flag61,"source_flag72_write_pc":0x93,
            "retained_key":investigation["key_serial"],"backpack":bag,"npc_serial":serial,
            "source_usecode_sha256":doc["source_sha256"]}


def compare_original(installation, session, replay):
    """Requalify the original game-native saves, then compare equivalent state in both engines."""
    from tools.oracle.investigation import qualify_stable
    original = qualify_stable(session, installation)
    key = replay["source"]
    if replay["status"] != "passed" or original["ground_key_shape_frame_quality"] != [
            key["shape"], key["frame"], key["quality_byte"]]:
        raise ValueError("Investigation key differs from the one in the original native saves")
    stages = {}
    for i, name in enumerate(("accepted","entered","carried")):
        dos = original["checkpoints"][i]
        modern = replay[name]
        if any(dos["flags"][flag] != value for flag,value in modern["flags"].items()):
            raise ValueError(f"Investigative flags differ from DOS at {name}")
        location = dos["key"]["location"]
        if name == "carried":
            if (location != "inventory" or dos["key"]["actor_slot"] != 0 or
                    replay["reopened_backpack"]["child"] != modern["saved_key"]["serial"] or
                    replay["reopened_backpack"]["owner"] != replay["player_serial"]):
                raise ValueError("Restored inventory ownership differs from the original game")
        elif location != "world" or dos["key"]["world_xy"] != replay["ground_packet"]["position"][:2]:
            raise ValueError("Original ground key position differs from the ordinary player's view")
        stages[name] = {"dos_save":dos["save_file"],"dos_sha256":dos["save_sha256"],
                        "modern_registry_sha256":modern["registry_sha256"],"flags":modern["flags"],
                        "key_location":location}
    if "mayor_report" in replay:
        mayor = replay["mayor_report"]
        dos = original["checkpoints"][3]
        native = mayor["state"]
        frames = original["mayor_report"]["source_frames"]
        seen = {page["append_pc"]:page["text_sha256"] for page in mayor["pages"] if "append_pc" in page}
        if (mayor["status"]!="passed" or dos["flags"]["61"]!=mayor["flag61"] or
                any(dos["flags"][k]!=v for k,v in native["flags"].items()) or
                dos["key"]["location"]!="inventory" or dos["key"]["actor_slot"]!=0 or
                mayor["source_flag72_write_pc"]!=original["mayor_report"]["flag_write"]["pc"] or
                any(seen.get(f["source_strings"][0]["pc"])!=f["source_strings"][0]["source_string_sha256"]
                    for f in (frames[0],frames[2],frames[4]))):
            raise ValueError("The reported key, original Mayor's lines or resulting flags disagree with the DOS save")
        stages["mayor_report"] = {"dos_save":dos["save_file"],"dos_sha256":dos["save_sha256"],
                                  "modern_registry_sha256":native["registry_sha256"],
                                  "flags":{**native["flags"],"61":mayor["flag61"]},"key_location":"inventory",
                                  "matching_original_say":seen,"npc_position_original":dos["actors"]["12"]["world_xy"],
                                  "npc_position_modern":mayor["npc_position"]}
    return {"status":"passed","edition":original["edition"],"source_sha256":original["edition_source_sha256"],
            "dos_session":str(session),"shape_frame_quality":original["ground_key_shape_frame_quality"],
            "checkpoints":stages}


if __name__ == "__main__":
    import argparse
    from pathlib import Path
    parser = argparse.ArgumentParser(description="Compare completed private stables replay against original native DOS checkpoints")
    parser.add_argument("verification", type=Path)
    parser.add_argument("dos_session", type=Path)
    parser.add_argument("--installation", type=Path, required=True)
    args = parser.parse_args()
    raw = args.verification.read_bytes()
    verified = json.loads(raw)
    report = compare_original(args.installation, args.dos_session, verified["player_replay"]["stables"])
    report.update(build_id=verified["build_id"], verification_sha256=hashlib.sha256(raw).hexdigest())
    print(json.dumps(report, indent=2))
