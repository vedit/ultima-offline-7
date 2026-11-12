"""Observe normal player movement and Gump replies on an owned disposable ModernUO shard."""
from collections import deque
import hashlib
import json
import re
import struct
import time
import zlib


class BlockedStep(ValueError):
    """A normal walk was refused at the player's last acknowledged position."""


def huffman_tree(root):
    # Reuse the exact ClassicUO wire alphabet from its pinned checkout.
    source = (root / "Cache/Readback/ClassicUO/src/ClassicUO.Client/Network/Huffman.cs").read_bytes().replace(b"\r\n", b"\n")
    if hashlib.sha256(source).hexdigest() != "c1736af3b210c0472fc295120d467830aeca2d80b431acff38fec4f275ea7d40":
        raise ValueError("Unrecognized ClassicUO Huffman table")
    rows = re.findall(rb"/\*\s*(\d+)\*/\s*(-?\d+),\s*(-?\d+),", source)
    if [int(i) for i, _, _ in rows] != list(range(256)):
        raise ValueError("Incomplete ClassicUO wire alphabet")
    return [(int(right), int(left)) for _, left, right in rows]


class PlayerConnection:
    """Each NetState.Send is one byte-aligned Huffman frame, independently of TCP reads."""
    def __init__(self, game, root, observe=None):
        self.game = game
        self.observe = observe
        self.tree = huffman_tree(root)
        self.node = 0
        self.partial = bytearray()
        self.frames = deque()
        self.mobiles = {}
        self.ground_items = {}
        self.backpacks = {}
        self.equipment = {}
        self.acknowledged = []
        self.sequence = 0

    def feed(self, block):
        for octet in block:
            for shift in range(7, -1, -1):
                self.node = self.tree[self.node][(octet >> shift) & 1]
                if self.node == -256:
                    if not self.partial:
                        raise ValueError("Empty ModernUO game frame")
                    self.frames.append(bytes(self.partial))
                    self.partial.clear()
                    self.node = 0
                    break
                if self.node <= 0:
                    self.partial.append(-self.node)
                    self.node = 0
            if len(self.partial) > 65535:
                raise ValueError("Oversized ModernUO game frame")

    def expect(self, ids, *, predicate=None, timeout=10):
        end = time.monotonic() + timeout
        seen = []
        while time.monotonic() < end:
            if not self.frames:
                self.game.settimeout(max(0.01, end - time.monotonic()))
                try:
                    block = self.game.recv(16384)
                except TimeoutError:
                    break
                if not block:
                    raise ValueError("Owned game server closed the in-world player connection")
                self.feed(block)
                continue
            frame = self.frames.popleft()
            kind = frame[0]
            seen.append(kind)
            if self.observe is not None:
                self.observe(frame)
            if kind == 0xBD:
                version = b"7.0.118.46\0"
                self.game.sendall(struct.pack(">BH", kind, 3 + len(version)) + version)
            if kind == 0x78:
                serial, _, x, y, z = struct.unpack_from(">IHHHb", frame, 3)
                self.mobiles[serial] = (x, y, z)
                worn = {}
                at = 19
                while at + 4 <= len(frame):
                    item, = struct.unpack_from(">I", frame, at)
                    if item == 0:
                        break
                    if at + 9 > len(frame):
                        raise ValueError("Truncated mobile equipment list")
                    if frame[at + 6] == 0x15:
                        self.backpacks[serial] = item
                    worn[item] = (struct.unpack_from(">H", frame, at + 4)[0], frame[at + 6])
                    at += 9
                self.equipment[serial] = worn
            elif kind == 0x2E:
                item, art, layer, owner = struct.unpack_from(">IHHI", frame, 1)
                self.equipment.setdefault(owner, {})[item] = (art, layer)
            elif kind == 0xF3 and frame[3] == 0:
                serial, art = struct.unpack_from(">IH", frame, 4)
                self.ground_items[serial] = (art, *struct.unpack_from(">HHb", frame, 15))
            elif kind == 0x1D:
                removed, = struct.unpack_from(">I", frame, 1)
                self.ground_items.pop(removed, None)
                self.mobiles.pop(removed, None)
                for worn in self.equipment.values():
                    worn.pop(removed, None)
            elif kind == 0x77:
                mobile, _, x, y, z = struct.unpack_from(">IHHHb",frame,1)
                self.mobiles[mobile] = (x,y,z)
            if kind in (0x1C, 0xAE):
                text = (frame[44:].decode("latin1") if kind == 0x1C else frame[48:].decode("utf-16-be")).rstrip("\0")
                if text.startswith(("Conversation paused at ", "Opening paused", "East gate world step ", "Stables trigger ")):
                    raise ValueError(text)
            if kind in ids and (predicate is None or predicate(frame)):
                return frame
        raise ValueError(f"Timed out waiting for {sorted(ids)}. Recent frame types: {seen[-32:]}")

    def enter(self):
        confirm = self.expect({0x1B})
        self.serial, = struct.unpack_from(">I", confirm, 1)
        x, y, z, facing = struct.unpack_from(">HHhB", confirm, 11)
        self.position = (x, y, z)
        self.facing = facing & 7
        self.expect({0x55})
        return self.position

    def resync(self):
        self.game.sendall(b"\x22\0\0")
        frame = self.expect({0x20}, predicate=lambda f: struct.unpack_from(">I", f, 1)[0] == self.serial)
        x, y, _, facing, z = struct.unpack_from(">HHHBb", frame, 11)
        if (x, y, z) != self.position:
            raise ValueError(f"Server position {(x,y,z)} differs from acknowledged route {self.position}")
        self.sequence, self.facing = 0, facing & 7
        return self.position

    def move(self, direction, *, block=False):
        # UO uses a successful movement request to turn in place if facing differs.
        if self.facing != direction:
            self._step(direction, False, turning=True)
        return self._step(direction, block, turning=False)

    def _step(self, direction, blocked, *, turning):
        # Space each request at ordinary unmounted walking speed.
        time.sleep(0.45)
        seq = self.sequence
        self.game.sendall(struct.pack(">BBBI", 0x02, direction, seq, 0))
        reply = self.expect({0x21, 0x22})
        if reply[1] != seq:
            raise ValueError(f"Movement reply sequence {reply[1]} differs from request {seq}")
        if reply[0] == 0x21:
            x, y, facing, z = struct.unpack_from(">HHBb", reply, 2)
            if (x,y,z) != self.position:
                raise ValueError(f"Unexpected server movement rejection at {(x,y,z)} direction {direction}, expected {self.position}")
            self.sequence, self.facing = 0, facing & 7
            if not blocked:
                raise BlockedStep(f"Server refused ordinary movement at {self.position} direction {direction}")
            return {"packet": "0x21", "sequence": seq, "position": [x,y,z], "direction": facing & 7}
        if blocked or len(reply) != 3:
            raise ValueError(f"Expected a collision at {self.position}, received {reply.hex()}")
        self.sequence = (seq + 1) & 255 or 1
        self.facing = direction
        if not turning:
            dx, dy = DIRECTIONS[direction]
            self.position = (self.position[0] + dx, self.position[1] + dy, self.position[2])
        self.acknowledged.append({"sequence": seq, "direction": direction, "turn": turning, "position": list(self.position)})

    def walk(self, start_inclusive):
        if tuple(start_inclusive[0]) != self.position[:2]:
            raise ValueError("Replay path does not begin at the observed position")
        for x,y in start_inclusive[1:]:
            delta = x - self.position[0], y - self.position[1]
            self.move(next(d for d, vector in DIRECTIONS.items() if vector == delta))

    def actor(self, position, name):
        matching = [serial for serial, pos in self.mobiles.items() if pos == tuple(position) and serial != self.serial]
        if len(matching) != 1:
            raise ValueError(f"Expected one visible NPC at {position}")
        serial, = matching
        self.game.sendall(struct.pack(">BIBI", 0x34, 0xedededed, 4, serial))
        status = self.expect({0x11}, predicate=lambda f: struct.unpack_from(">I", f, 3)[0] == serial)
        if status[7:37].rstrip(b"\0").decode("ascii") != name:
            raise ValueError("NPC name in the server status reply differs from the source")
        return serial


DIRECTIONS = {0: (0,-1), 2: (1,0), 4: (0,1), 6: (-1,0)}


def pillar_detour(sample, start):
    ox, oy = sample["source_origin"]
    tiles = {(c["x"] + ox, c["y"] + oy) for c in sample["cells"]
             if 0 <= c["x"] < sample["width"] and 0 <= c["y"] < sample["height"]}
    solid_ids = {r["id"] for r in sample["static_rules"].values() if r["flags"] & 0x40}
    solids = {(s["x"] + ox, s["y"] + oy) for s in sample["statics"] if s["z"] == 0 and s["id"] in solid_ids}
    pillars = {(s["x"] + ox, s["y"] + oy): s for s in sample["statics"]
               if s["source_id"] in sample["landmark_ids"] and s["z"] == 0 and s["id"] in solid_ids}
    obstacles = solids | {tuple(o["world_xy"]) for o in sample["ireg_objects_deferred"]} | {tuple(sample["finnigan"]["source"][:2])}
    previous = {start: None}
    todo = deque([start])
    while todo:
        pos = todo.popleft()
        for d, (dx,dy) in DIRECTIONS.items():
            step = pos[0] + dx, pos[1] + dy
            if step in pillars:
                path = [pos]
                while previous[path[-1]] is not None:
                    path.append(previous[path[-1]])
                return path[::-1], d, step, pillars[step]["source_id"]
            if step in tiles and step not in obstacles and step not in previous:
                previous[step] = pos
                todo.append(step)
    raise ValueError("No source pillar is reachable from the route")


def walk_replay(conn, sample):
    ox, oy = sample["source_origin"]
    route = [(x + ox, y + oy) for x, y in sample["route"]]
    if conn.position != tuple(sample["avatar"]["source"]) or route[-1] != tuple(sample["finnigan"]["source"][:2]):
        raise ValueError("Source route endpoint differs from the actual game start or NPC")
    conn.walk(route[:-1])
    approach = conn.resync()
    path, direction, pillar, source_id = pillar_detour(sample, route[-2])
    conn.walk(path)
    rejection = conn.move(direction, block=True)
    conn.walk(path[::-1])
    if conn.resync() != approach:
        raise ValueError("Return from source pillar failed")
    serial = conn.actor(sample["finnigan"]["source"], "Finnigan")
    return {"start": list(route[0]) + [0], "approach": list(approach), "actor": {"name":"Finnigan", "serial":serial,
            "position":sample["finnigan"]["source"]}, "route_steps": len(route)-2, "detour_steps": 2*(len(path)-1),
            "movement_acks": conn.acknowledged, "pillar": {"position":list(pillar),"source_id":source_id,"rejection":rejection}}


def compressed_gump(frame):
    if len(frame) < 31 or frame[0] != 0xDD or struct.unpack_from(">H", frame, 1)[0] != len(frame):
        raise ValueError("Invalid ClassicUO compressed Gump frame")
    sender, kind = struct.unpack_from(">II", frame, 3)

    def unpack(at):
        length, size = struct.unpack_from(">II", frame, at)
        end = at + 4 + length
        if length < 4 or end > len(frame) or size > 4 * 1024 * 1024:
            raise ValueError("Invalid compressed Gump block")
        decoder = zlib.decompressobj()
        plain = decoder.decompress(frame[at+8:end], size + 1)
        if len(plain) != size or not decoder.eof or decoder.unused_data:
            raise ValueError("Compressed Gump did not decode to its declared length")
        return plain, end

    layout, at = unpack(19)
    count, = struct.unpack_from(">I", frame, at)
    at += 4
    if count > 65535:
        raise ValueError("Excessive Gump text rows")
    text, cursor = b"", 0
    if count:
        text, at = unpack(at)
    labels = []
    for _ in range(count):
        n, = struct.unpack_from(">H", text, cursor)
        cursor += 2
        raw = text[cursor:cursor + 2*n]
        if len(raw) != 2*n:
            raise ValueError("Truncated Gump text")
        labels.append(raw.decode("utf-16-be"))
        cursor += 2*n
    if at != len(frame) or cursor != len(text):
        raise ValueError("Unconsumed Gump wire data")
    layout = layout.rstrip(b"\0").decode("utf-8")
    commands = [c.strip().split() for c in re.findall(r"\{([^{}]+)\}", layout)]
    # ModernUO labels use a text-table index. Associate each reply button with
    # the label alongside it, so the replay follows the options presented.
    fields = []
    images = []
    body = []
    controls = {}
    entries = []
    page = 0
    for c in commands:
        if c[0] == "page":
            page = int(c[1])
        elif c[0] in ("text", "croppedtext", "htmlgump"):
            col = {"text":4, "croppedtext":6, "htmlgump":5}[c[0]]
            if not 0 <= int(c[col]) < len(labels):
                raise ValueError("Gump label references a missing string")
            raw_label = labels[int(c[col])]
            label = (re.sub("<[^>]*>", "", raw_label) if c[0]=="htmlgump" else raw_label).strip()
            if c[0] == "htmlgump":
                body.append(label)
            fields.append((page, int(c[1]), int(c[2]), label))
        elif c[0] == "gumppic":
            images.append(int(c[3]))
        elif c[0] in ("textentry","textentrylimited"):
            entries.append(int(c[6]))
        elif c[0] == "button" and int(c[5]) == 1:
            number = int(c[7])
            if number in controls:
                raise ValueError("Ambiguous duplicate Gump reply control")
            controls[number] = (page, int(c[1]), int(c[2]))
    buttons = {}
    for number,(page,x,y) in controls.items():
        nearby = [(abs(v-y), u-x, label) for index,u,v,label in fields if index in (0,page) and u >= x and abs(v-y) <= 12]
        if not nearby:
            raise ValueError("Reply button has no associated visible Gump label")
        buttons[number] = min(nearby)[2]
    digest = hashlib.sha256(json.dumps([layout, labels], ensure_ascii=True, separators=(",",":")).encode()).hexdigest()
    return {"sender":sender, "kind":kind, "digest":digest, "buttons":buttons, "images":images, "text_rows":len(labels),
            "body":body,"entries":entries}


def send_reply(conn, gump, button):
    if button and button not in gump["buttons"]:
        raise ValueError("Reply does not match any displayed button")
    conn.game.sendall(struct.pack(">BHIIIII",0xB1,23,gump["sender"],gump["kind"],button,0,0))


def open_actor(conn, serial):
    conn.game.sendall(struct.pack(">BI",0x06,serial))
    return compressed_gump(conn.expect({0xDD}))


def source_pages(campaign):
    doc = json.loads((campaign / "dialogue.json").read_bytes())
    functions = {f["id"]: f for f in doc["program"]["functions"]}
    def literal(function, append_pc, say_pc):
        f = functions[function]
        rows = {pc: (op, operands) for pc,op,operands,_ in f["rows"]}
        opcode, operands = rows[append_pc]
        if opcode != 0x1C or rows[say_pc] != (0x33, []):
            raise ValueError("Expected retail APPEND_DATA/SAY sequence has changed")
        return f["strings"][str(operands[0])].split("~", 1)[0].strip()
    return {"first":literal(0x40C,0x139,0x13C), "last":literal(0x885,0x84,0x87),
            "reopen":literal(0x40C,0x3C,0x3F), "stern":literal(0x40C,0x1B5,0x1B8),
            "offer":literal(0x40C,0x1B9,0x1BC), "refusal":literal(0x40C,0x216,0x219),
            "reconsider":literal(0x40C,0xD4,0xD7), "usecode_sha256":doc["source_sha256"]}


def check_say(page, expected, source):
    # The original FarString parser consumes a final page marker. Retained
    # historical private hosts displayed it literally, which their receipts expose.
    if (len(page["body"]) != 1 or page["body"][0] not in {expected, expected.removesuffix("*")} or
            list(page["buttons"].values()) != ["Continue"]):
        raise ValueError(f"Visible dialogue differs from source SAY at {source}")
    return hashlib.sha256(page["body"][0].encode()).hexdigest()


def replay_dialogue(conn, serial, source, *, first_page=None, suspend=True):
    page = open_actor(conn, serial) if first_page is None else first_page
    kind = page["kind"]
    first = check_say(page, source["first"], "0x040C:0x13C")
    log, choices = [], []
    for _ in range(64):
        if page["kind"] != kind:
            raise ValueError("Unexpected Gump kind after player input")
        buttons = page["buttons"]
        log.append({"sha256":page["digest"], "portrait_64012":64012 in page["images"],
                    "portraits":page["images"], "text_rows":page["text_rows"], "controls":buttons})
        if len(choices) == 2:
            last = check_say(page, source["last"], "0x0885:0x87")
            if not any(item["portrait_64012"] for item in log):
                raise ValueError("Finnigan's source portrait never appeared in the Gump layout")
            send_reply(conn, page, 0 if suspend else next(iter(buttons)))
            return {"status":"passed", "actor_double_click":first_page is None, "gump_type":kind, "pages":log,
                    "player_serial":conn.serial, "selected":choices, "suspended_sha256":page["digest"],
                    "usecode_sha256":source["usecode_sha256"], "say_text_sha256":{"0x040C:0x13C":first,"0x0885:0x87":last}}
        offered = {v.strip().casefold(): k for k,v in buttons.items()}
        if set(offered) == {"yes","no"}:
            answer = ("yes","no")[len(choices)]
            button = offered[answer]
            choices.append({"button":button,"label":buttons[button], "page":len(log)})
        else:
            if set(offered) != {"continue"}:
                raise ValueError(f"No expected displayed conversation choice: {list(offered)}")
            button = offered["continue"]
        send_reply(conn, page, button)
        page = compressed_gump(conn.expect({0xDD}))
    raise ValueError("Original dialogue did not offer a choice within 64 displayed pages")


def resume_dialogue(conn, movement, source):
    serial = conn.actor(movement["actor"]["position"], movement["actor"]["name"])
    if serial != movement["actor"]["serial"]:
        raise ValueError("Restarted actor has a different server serial")
    page = open_actor(conn, serial)
    original = movement["dialogue"]
    if page["kind"] != original["gump_type"] or page["digest"] != original["suspended_sha256"]:
        raise ValueError("Restarted player received a different conversation continuation")
    original["resumed_sha256"] = page["digest"]
    original["same_page_after_restart"] = True
    send_reply(conn, page, next(n for n,s in page["buttons"].items() if s == "Continue"))
    # The final original SAY commits the investigation flag when acknowledged.
    # A normal ping synchronizes processed packets before the next NPC interaction.
    conn.game.sendall(b"\x73\x59")
    conn.expect({0x73}, predicate=lambda f: f == b"\x73\x59")
    time.sleep(1)
    followup = open_actor(conn, serial)
    original["say_text_sha256"]["0x040C:0x3F"] = check_say(followup, source["reopen"], "0x040C:0x3F")
    original["reopened_investigation_page"] = followup["digest"]
    send_reply(conn, followup, 0)


def read_registry(f):
    raw = f.read_bytes()
    # ModernUO writes an int version, a non-null marker, then a 7-bit UTF-8 byte count.
    if len(raw) < 7 or struct.unpack_from("<i", raw)[0] != 1 or raw[4] != 1:
        raise ValueError("Unsupported ModernUO conversation registry framing")
    length = 0
    for i in range(5,10):
        value = raw[i]
        length |= (value & 127) << (7*(i-5))
        if value < 128:
            break
    else:
        raise ValueError("Invalid ModernUO conversation string length")
    if len(raw) != i+1+length:
        raise ValueError("Truncated ModernUO conversation registry")
    return json.loads(raw[i+1:]), hashlib.sha256(raw).hexdigest()


def dialogue_save(world, campaign, player_serial, *, closed=False):
    f = world / "UltimaOfflineDialogue/UltimaOfflineDialogue.bin"
    state, digest = read_registry(f)
    changes = state["Changes"]
    seed = json.loads((campaign / "story-seed.json").read_bytes())["flags"]
    conversation = state["Active"].get(str(player_serial))
    if closed:
        if conversation is not None:
            raise ValueError("Refused conversation did not close")
        actor = json.loads((campaign / "actor.json").read_bytes())["id"]
    elif not conversation or conversation["Function"] != 0x40C or not conversation["Actor"]:
        raise ValueError("Saved conversation belongs to an unexpected actor")
    else:
        actor = conversation["Actor"]
    work = state["Work"][actor]
    if (work["Kind"],work["State"]) != (11,1):
        raise ValueError("Expected the persisted Finnigan opening activity")
    return {"file_sha256":digest, "actor":actor,
            "program_and_seed":state["Build"], "history_length":len(conversation["History"]) if conversation else 0,
            "conversation_active":bool(conversation), "flag_89":changes.get("89",seed[89]),
            "actor_work":{"kind":work["Kind"],"state":work["State"]},
            "flag_76":changes.get("76",seed[76]), "flag_90":changes.get("90",seed[90])}


def replay_refusal(conn, serial, source, first_page=None):
    page = open_actor(conn, serial) if first_page is None else first_page
    first = check_say(page, source["first"], "0x040C:0x13C")
    seen, ordered = [], []
    for _ in range(40):
        if list(page["buttons"].values()) != ["Continue"]:
            break
        seen.append(page["digest"])
        if page["body"] == [source["stern"]]:
            ordered.append("0x040C:0x1B8")
        if page["body"] == [source["offer"]]:
            ordered.append("0x040C:0x1BC")
        send_reply(conn,page,next(iter(page["buttons"])))
        page = compressed_gump(conn.expect({0xDD}))
    options = list(page["buttons"].values())
    if ordered != ["0x040C:0x1B8","0x040C:0x1BC"] or options != ["Yes","No"]:
        raise ValueError("Fresh-game offer and ordered Yes/No choices differ from the source")
    send_reply(conn,page,next(k for k,v in page["buttons"].items() if v=="No"))
    page = compressed_gump(conn.expect({0xDD}))
    if len(page["body"]) != 1 or list(page["buttons"].values()) != ["Continue"]:
        raise ValueError("Unexpected post-refusal SAY")
    displayed = page["body"][0]
    if displayed.removesuffix("*") != source["refusal"].removesuffix("*"):
        raise ValueError("Post-refusal dialogue differs from the original 0x040C:0x219")
    send_reply(conn,page,next(iter(page["buttons"])))
    conn.game.sendall(b"\x73\x58")
    if conn.expect({0x73,0xDD}) != b"\x73\x58":
        raise ValueError("Refusal acknowledgement unexpectedly displayed another Gump")
    digest = lambda s: hashlib.sha256(s.encode()).hexdigest()
    return {"status":"passed","gump_type":page["kind"],"player_serial":conn.serial,
            "actor_double_click":first_page is None, "intro_page_hashes":seen, "displayed_choices":options,
            "selected":"No", "closed_after_refusal":True, "usecode_sha256":source["usecode_sha256"],
            "ordered_source_say":{ "0x040C:0x13C":first, "0x040C:0x1B8":digest(source["stern"]),
                "0x040C:0x1BC":digest(source["offer"]), "0x040C:0x219":digest(displayed.removesuffix("*"))},
            "refusal_display_sha256":digest(displayed), "terminal_asterisk_visible":displayed.endswith("*")}


def reopen_refusal(conn, movement, source):
    serial = conn.actor(movement["actor"]["position"],movement["actor"]["name"])
    if serial != movement["actor"]["serial"]:
        raise ValueError("Restarted NPC has a different server serial")
    page = open_actor(conn,serial)
    trace = movement["dialogue"]
    if page["kind"] != trace["gump_type"]:
        raise ValueError("Refusal retry changed Gump type")
    trace["reconsideration_text_sha256"] = check_say(page,source["reconsider"],"0x040C:0xD7")
    send_reply(conn,page,next(iter(page["buttons"])))
    options = compressed_gump(conn.expect({0xDD}))
    trace["retry_choices"] = list(options["buttons"].values())
    if trace["retry_choices"] != trace["displayed_choices"]:
        raise ValueError("Reconsideration did not offer the expected original choices")
    send_reply(conn,options,0)
