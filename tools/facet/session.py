"""Create an ordinary player on a disposable loopback copy and optionally open ClassicUO there."""
import argparse
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import socket
import struct
import subprocess
import tempfile
import time

from u7uo.facet import _active, _graceful_stop, _paths, _read, _start, _write


def receive(stream, count):
    data = bytearray()
    while len(data) < count:
        packet = stream.recv(count - len(data))
        if not packet:
            raise ValueError("Disposable game server closed the login connection")
        data.extend(packet)
    return bytes(data)


def wait_log(log, prompt, proc, timeout=15):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline and proc.poll() is None:
        text = log.read_text(errors="replace")
        if prompt in text:
            return text
        time.sleep(0.1)
    raise ValueError(f"Missing stage {prompt!r} in disposable shard log {log}")


def character_packet(name):
    # ClassicUO Send_CreateCharacter (protocol 7.0.118.46), first advertised city, slot zero.
    fields = [b"\xf8", struct.pack(">IIB", 0xedededed, 0xffffffff, 0),
              name.encode("ascii").ljust(30, b"\0"), bytes(2),
              struct.pack(">IIIB", 0, 1, 0, 1), bytes(15), bytes((2, 45, 30, 15)),
              bytes((27, 35, 40, 35, 17, 25, 1, 25)), struct.pack(">HHHHH", 1002, 0, 0, 0, 0),
              struct.pack(">HHHIHH", 0, 0, 0, 0x7f000001, 2, 3)]
    packet = b"".join(fields)
    if len(packet) != 106:
        raise ValueError("Character-creation packet layout changed")
    return packet


@contextmanager
def game_login(port, log, proc, account, password):
    # Only the ephemeral listener started in this method's caller is reachable.
    address = ("127.0.0.1", port)
    user = account.encode("ascii").ljust(30, b"\0")
    key = password.encode("ascii").ljust(30, b"\0")
    with socket.create_connection(address, timeout=10) as login:
        login.sendall(struct.pack(">BIIIII", 0xef, 0x7f000001, 7, 0, 118, 46))
        login.sendall(b"\x80" + user + key + b"\xff")
        if receive(login, 1) != b"\xa8":
            raise ValueError("Disposable shard did not return the advertised server list")
        length, = struct.unpack(">H", receive(login, 2))
        listing = receive(login, length - 3)
        if len(listing) < 5 or struct.unpack_from(">H", listing, 1)[0] != 1:
            raise ValueError("Expected one local shard")
        login.sendall(b"\xa0" + listing[3:5])
        ack = receive(login, 11)
        if ack[0] != 0x8c or struct.unpack_from(">H", ack, 5)[0] != port:
            raise ValueError("Game server handoff did not point at the disposable listener")
        ticket = ack[7:11]
    with socket.create_connection(address, timeout=10) as game:
        game.sendall(ticket)
        game.sendall(b"\x91" + ticket + user + key)
        wait_log(log, "at character list", proc)
        yield game


def create_player(port, log, proc, account, password, character, position, in_world=None):
    with game_login(port, log, proc, account, password) as game:
        game.sendall(character_packet(character))
        expected = "started.location=(" + ", ".join(str(n) for n in position) + ")"
        text = wait_log(log, expected, proc)
        line = next((s for s in text.splitlines() if expected in s and "New character being created" in s), "")
        if f"character={character}," not in line or "started.city=Trinsic" not in line or "started.map=Felucca" not in line:
            raise ValueError("Normal player placement did not match the configured source start")
        if in_world:
            return in_world(game)


def select_player(game, character):
    name = character.encode("ascii").ljust(30, b"\0")
    game.sendall(struct.pack(">BI30s2xI24xII", 0x5D, 0xedededed, name, 0, 0, 0x7f000001))


def snapshot_count(log):
    text = log.read_text(errors="replace")
    return text.rsplit("New character being created", 1)[-1].count("Writing world save snapshot done")


def saved_after_creation(log, proc, state, character, prior_snapshots=0):
    deadline = time.monotonic() + 65
    while time.monotonic() < deadline and proc.poll() is None:
        data = state / "world/Mobiles/Mobiles.bin"
        if snapshot_count(log) > prior_snapshots and data.is_file() and character.encode("ascii") in data.read_bytes():
            return
        time.sleep(0.25)
    raise ValueError("No completed world save containing the disposable character")


def launch_client(root, release, sandbox, state, result, account, password, visual, login_screen=False):
    # Isolate executable-relative profiles, plugins and renderer screenshots.
    client = sandbox / "client"
    shutil.copytree(release / "client", client, ignore=shutil.ignore_patterns("Data"))
    settings = _read(client / "settings.json")
    machine = os.environ["COMPUTERNAME"].encode("ascii")
    encoded = bytes(c ^ machine[i % len(machine)] for i,c in enumerate(password.encode("ascii")))
    settings.update(port=result["port"], username=account, password="1-"+encoded.hex().upper(),
                    autologin=not login_screen, saveaccount=True, profilespath=str(state/"profiles"))
    cfg = state / "client-settings.json"
    client_env = os.environ.copy()
    if visual:
        from .visual import install
        plugin = install(root, client, state)
        settings["plugins"] = [plugin.name]
        client_env["U7UO_VISUAL_TEST"] = "1"
        result["visual_plugin_sha256"] = hashlib.sha256(plugin.read_bytes()).hexdigest()
    _write(cfg, settings)
    args = [client/"ClassicUO.exe", "-settings", cfg, "-profilespath", state/"profiles"]
    if not login_screen:
        args.append("-skiploginscreen")
    process = subprocess.Popen(args, cwd=client, env=client_env)
    result.update(client_pid=process.pid, rendered_client="launched_pending_observation")


def run(installation, output, launch, *, walk=False, dialogue=False, refusal=False, dos_reference=None, opening=False,
        stables=False, journey=False, estate=False, visual=False, shore=False, swamp=False, void=False,
        award_checkpoint=None, login_screen=False, witnesses_first=False, appointment=None, appointment_restart=False,
        office_observer=None,chair_restart=False,occupy_chair=False):
    if occupy_chair and not chair_restart:
        raise ValueError("The occupied-chair control starts from the interrupted chair route")
    if chair_restart and office_observer is None:
        raise ValueError("The active chair walk needs the office observer")
    if office_observer is not None and (appointment is None or appointment_restart):
        raise ValueError("The office observer requires its distant morning appointment")
    if appointment_restart and appointment is None:
        raise ValueError("The mid-walk restart needs a resident appointment fixture")
    if appointment is not None and any((launch and office_observer is None, walk, dialogue, refusal, opening, stables, journey, estate, shore, swamp, void)):
        raise ValueError("The matched appointment uses a separate disposable player")
    if witnesses_first and not journey:
        raise ValueError("The witness-first route requires the full journey")
    if login_screen and (not launch or any((walk, dialogue, refusal, opening, stables, journey, estate, shore, swamp, void))):
        raise ValueError("Start the login screen with --open-client and no preplayed scenario")
    if award_checkpoint is not None and not journey:
        raise ValueError("A pre-report health checkpoint requires the disposable journey")
    expected_downed=(-1,) if award_checkpoint is not None else ()
    terrain_scenarios = sum((shore, swamp, void))
    if terrain_scenarios > 1 or (terrain_scenarios and any((opening,walk,dialogue,refusal,stables,journey,estate))):
        raise ValueError("Choose one player scenario for the disposable starting position")
    if visual and not launch:
        raise ValueError("The visual controller requires a rendered client")
    if estate:
        stables = True
    if journey:
        opening = True
    if refusal and stables:
        raise ValueError("The stables investigation requires an accepted offer")
    if refusal or stables:
        dialogue = True
    if dos_reference is not None and not refusal:
        raise ValueError("The captured DOS comparison exercises the refusal branch")
    if opening and (walk or dialogue or launch):
        raise ValueError("The automatic opening uses a fresh isolated player without route or desktop actions")
    root, out = _paths(installation, output)
    release, record = _active(root, out)
    start = record["start"]
    if void:
        source = Path(record["source_release"])
        catalog = _read(source/"world-statics/summary.json")
        mountains = "frame_layers" in catalog["mapped_materials"].get("395",{})
        start = [497,2315,0] if mountains else [121,2544,0]
    if swamp:
        if not (release/"server/Campaign/swamp.json").is_file():
            raise ValueError("The selected facet has no field contact index")
        start=[1299,961,0]
    if shore:
        if not record.get("shore_art"):
            raise ValueError("The selected facet has no compiled shoreline")
        start = [1022,2424,0]
    if journey or estate:
        staged_seed=_read(release/"server/Campaign/story-seed.json")
        if journey and not staged_seed.get("gate_objects"):
            raise ValueError("The selected journey facet has no source dock guard or gate objects")
        if estate and not staged_seed.get("investigation_chests"):
            raise ValueError("The selected estate facet has no source investigation chest")
    sandbox = Path(tempfile.mkdtemp(prefix="playtest-", dir=root / "Cache/FacetHost"))
    # Never copy a live player account, client settings or save. Use the isolated release and new scratch state.
    shutil.copytree(release / "server", sandbox / "server",
                    ignore=shutil.ignore_patterns("Backups", "Archives", "Logs", "temp", "host-probe.json"))
    state = sandbox / "state"
    config_path = sandbox / "server/Configuration/modernuo.json"
    config = _read(config_path)
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    config["listeners"] = [f"127.0.0.1:{port}"]
    if appointment is not None:
        from .appointment_replay import prepare
        start, fixture = prepare(root, appointment, release, record, sandbox/"server/Campaign")
        if office_observer is not None:
            from tools.oracle.mayor_schedule import qualify_office_observer
            native=qualify_office_observer(root,office_observer)
            if native["source_trial"]!=appointment.name or fixture["resident"]:
                raise ValueError("Office observer and selected distant appointment differ")
            fixture["office_observer"]=native
        if appointment_restart and not fixture["resident"]:
            raise ValueError("The distant appointment has no walk to interrupt")
    if terrain_scenarios or appointment is not None:
        for axis,value in zip("XYZ",start):
            config["settings"]["ultimaOffline.start"+axis] = str(value)
        config["settings"]["ultimaOffline.openingEgg"] = "false"
    for key, folder in (("world.savePath", "world"), ("autoArchive.backupPath", "backups"), ("autoArchive.archivePath", "archives")):
        config["settings"][key] = str(state / folder)
    config["settings"]["autosave.saveDelay"] = "00:00:02" if appointment_restart or office_observer else "00:00:15"
    config["settings"]["autosave.warningDelay"] = "00:00:00"
    _write(config_path, config)
    proc, log = _start(root, sandbox, {**record, "state": str(state), "port": port})
    keep = False
    try:
        account = "Proof" + secrets.token_hex(4)
        password = secrets.token_hex(10)
        character = "Alden"
        if appointment is not None:
            from .appointment_replay import play
            from .player_replay import PlayerConnection, read_registry
            if office_observer is not None:
                from .appointment_replay import play_office, seated_mayor
                seed=_read(sandbox/"server/Campaign/story-seed.json")
                result=create_player(port,log,proc,account,password,character,start,
                    lambda game:play_office(game,root,state,start,seed,_read(release/"sample.json"),native["office"],
                                            interrupt=chair_restart))
                saved_after_creation(log,proc,state,character,snapshot_count(log))
                if chair_restart:
                    partial=result
                    registry=state/"world/UltimaOfflineDialogue/UltimaOfflineDialogue.bin"
                    before,_=read_registry(registry)
                    child=before["Gate"]["OfficeSeat"]
                    routes=[s.split() for s in before["Gate"]["Trace"] if " chair-route " in s]
                    if (not child or child["State"]!=5 or len(routes)!=1 or
                            not 0<len(child["Path"])<int(routes[0][-1])):
                        raise ValueError(f"No partially consumed chair route at disconnect: {child}, {routes}")
                    old_pid=proc.pid
                    _graceful_stop(proc,sandbox/"server/ModernUO.exe")
                    if occupy_chair:
                        blocker_account="Proof"+secrets.token_hex(4)
                        blocker_password=secrets.token_hex(10)
                        occupied=[child["Target"][axis] for axis in "XYZ"]
                        config["settings"]["accountHandler.maxAccountsPerIP"]="2"
                        for axis,value in zip("XYZ",occupied):
                            config["settings"]["ultimaOffline.start"+axis]=str(value)
                        _write(config_path,config)
                    proc,log=_start(root,sandbox,{"state":str(state),"port":port})
                    restored_state,_=read_registry(registry)
                    if restored_state["Gate"]!=before["Gate"] or restored_state["Work"]!=before["Work"]:
                        raise ValueError("Saved NPC activity or route changed before player reentry")
                    def resume_observer():
                        with game_login(port,log,proc,account,password) as game:
                            select_player(game,character)
                            return play_office(game,root,state,partial["observer_position"],seed,
                                               _read(release/"sample.json"),native["office"],resumed=partial,
                                               blocked_child=child if occupy_chair else None)
                    if occupy_chair:
                        def hold_chair(game):
                            blocker=PlayerConnection(game,root)
                            if list(blocker.enter())!=occupied: raise ValueError("Blocker entered away from selected chair")
                            observation=resume_observer()
                            if list(blocker.resync())!=occupied: raise ValueError("Blocker moved during observation")
                            observation["blocked_actor_serial"]=blocker.actor(observation["blocked_position"],"Finnigan")
                            observation["blocker"]={"serial":blocker.serial,"position":occupied}
                            return observation
                        result=create_player(port,log,proc,blocker_account,blocker_password,
                                             "Bran",occupied,hold_chair)
                    else:
                        result=resume_observer()
                    final_routes=[s for s in result["trace"] if " chair-route " in s]
                    if not occupy_chair and (len(final_routes)!=1 or result["seat"]["source"]["id"]!=child["SeatId"]):
                        raise ValueError("Reopened chair walk discarded its saved selection")
                    result["chair_restart"]={"child":child,"tick":before["Gate"]["Steps"],"route_length":int(routes[0][-1]),
                        "old_pid":old_pid,"new_pid":proc.pid,"saved_rng":before["Gate"]["SeatRandomSeed"],
                        "approach_before_restart":partial["approach"]}
                    saved_after_creation(log,proc,state,character,snapshot_count(log))
                _graceful_stop(proc,sandbox/"server/ModernUO.exe")
                proc,log=_start(root,sandbox,{**record,"state":str(state),"port":port})
                with game_login(port,log,proc,account,password) as game:
                    select_player(game,character)
                    conn=PlayerConnection(game,root)
                    reopened_position=list(conn.enter())
                    if reopened_position!=result["observer_position"] or conn.serial!=result["player_serial"]:
                        raise ValueError(f"Office observer expected {result['observer_position']} and serial {result['player_serial']}, "
                                         f"reopened at {reopened_position} with serial {conn.serial}")
                    stored,_=read_registry(state/"world/UltimaOfflineDialogue/UltimaOfflineDialogue.bin")
                    if occupy_chair:
                        work=stored["Work"][seed["actors"]["12"]["id"]]
                        if (stored["Gate"]["OfficeSeat"] is not None or work!=result["saved_work"] or
                                stored["Gate"]["Trace"]!=result["trace"]):
                            raise ValueError("The failed chair route or actor changed across restart")
                        result["restored_work"]=work
                        with game_login(port,log,proc,blocker_account,blocker_password) as second:
                            select_player(second,"Bran")
                            blocker=PlayerConnection(second,root)
                            if list(blocker.enter())!=occupied or blocker.serial!=result["blocker"]["serial"]:
                                raise ValueError("A different blocker resumed the appointment")
                            deadline=time.monotonic()+65
                            while time.monotonic()<deadline:
                                blocker.resync()
                                later,_=read_registry(registry)
                                events=later["Gate"]["Trace"]
                                if later["Gate"]["Error"]: raise ValueError(later["Gate"]["Error"])
                                if any(" seated " in event for event in events):
                                    next_seat=seated_mayor(blocker,state/"world",seed,later["Gate"])
                                    appointments=[s.split() for s in events if " appointment " in s]
                                    if (len(appointments)!=2 or int(appointments[1][0])-int(appointments[0][0])!=375 or
                                            next_seat["source"]["id"]==child["SeatId"] or next_seat["position"]==occupied or
                                            next_seat["actor_serial"]!=result["blocked_actor_serial"]):
                                        raise ValueError("Following appointment reused the obstruction or changed the mayor")
                                    result["next_appointment"]={"ticks":fixture["start_tick"]+int(appointments[-1][0]),
                                                              "seat":next_seat,"trace":events}
                                    break
                                time.sleep(.25)
                            else: raise ValueError("No new seated outcome at the following occupied appointment")
                    else:
                        restored=seated_mayor(conn,state/"world",seed,stored["Gate"])
                        if restored!=result["seat"] or stored["Gate"]["OfficeSeat"]!=result["saved_child"]:
                            raise ValueError("Selected chair or seated actor changed across restart")
                        result["restored_seat"]=restored
                result.update(status="passed",build_id=record["build_id"],scratch=str(sandbox),port=port,server_pid=proc.pid,
                              fixture=fixture,saved_and_restarted=True)
                if launch:
                    launch_client(root,release,sandbox,state,result,account,password,visual)
                    keep=True
                _write(sandbox/"entry.json",result)
                return result
            result = create_player(port, log, proc, account, password, character, start,
                                   lambda game: play(game,root,state,start,fixture,interrupt=appointment_restart))
            if appointment_restart:
                partial = result
                first_pid=proc.pid
                _graceful_stop(proc,sandbox/"server/ModernUO.exe")
                proc,log=_start(root,sandbox,{**record,"state":str(state),"port":port})
                stored,_=read_registry(state/"world/UltimaOfflineDialogue/UltimaOfflineDialogue.bin")
                if stored["Gate"]!=partial["gate"] or stored["Work"]!=partial["work"]:
                    raise ValueError("The stopped appointment snapshot changed before reconnect")
                with game_login(port,log,proc,account,password) as game:
                    select_player(game,character)
                    result=play(game,root,state,start,fixture,previous=partial)
                result["mid_walk_restart"]={"saved_tick":fixture["start_tick"]+partial["gate"]["Steps"],
                    "walked_steps":partial["gate"]["OfficeSteps"],"pending_directions":partial["gate"]["OfficePath"],
                    "actor_serial":partial["actor_serial"],"stopped_pid":first_pid,"resumed_pid":proc.pid}
            _graceful_stop(proc,sandbox/"server/ModernUO.exe")
            proc,log = _start(root,sandbox,{**record,"state":str(state),"port":port})
            with game_login(port,log,proc,account,password) as game:
                select_player(game,character)
                conn = PlayerConnection(game,root)
                pos = conn.enter()
                stored,_ = read_registry(state/"world/UltimaOfflineDialogue/UltimaOfflineDialogue.bin")
                if (list(pos)!=start or conn.serial!=result["player_serial"] or
                        stored["Gate"]["Trace"]!=result["trace"] or stored["Work"]!=result["saved_work"] or
                        not stored["Gate"]["OfficeArrived"] or not stored["Gate"]["OfficeWokeFromSleep"]):
                    raise ValueError("Appointment or observing player changed after restart")
                if fixture["exterior_fence_cells"]:
                    from .appointment_replay import reopen_fence
                    result["reopened_fence"]=reopen_fence(conn,fixture,result["visible_fence"])
            result.update(status="passed", build_id=record["build_id"], scratch=str(sandbox),
                          fixture=fixture, saved_and_restarted=True)
            _write(sandbox/"entry.json",result)
            return result
        if login_screen:
            result = {"status":"passed","build_id":record["build_id"],"scratch":str(sandbox),
                      "server_pid":proc.pid,"log":str(log),"port":port,"saved_and_restarted":False}
            launch_client(root, release, sandbox, state, result, account, password, visual, login_screen=True)
            keep = True
            _write(sandbox / "entry.json", result)
            return result
        if opening:
            from .opening_replay import check_opening, observe_opening, walk_to_mayor
            from .player_replay import PlayerConnection, read_registry
            if not record["inputs"].get("opening_egg"):
                raise ValueError("The automatic opening requires its opt-in campaign facet")
            campaign = sandbox / "server/Campaign"
            gate_profile = bool(_read(campaign / "story-seed.json").get("gate_objects"))
            capture = create_player(port,log,proc,account,password,character,record["start"],
                                    lambda game: observe_opening(game,root,campaign,
                                        automatic_mayor="accept" if journey else gate_profile))
            saved_after_creation(log,proc,state,character,snapshot_count(log))
            registry, digest = read_registry(state / "world/UltimaOfflineDialogue/UltimaOfflineDialogue.bin")
            capture["saved_opening"] = registry["Opening"]
            capture["saved_flags"] = registry["Changes"]
            capture["save_sha256"] = digest
            if (capture["diagnostic"] or "").startswith("Timed out waiting for [221]") and registry["Opening"]["Status"]=="complete":
                # A completed original script emits no further Gump; confirm the idle interval with the real save.
                capture["end_of_dialogue"]="no further Gump; completed source queue"
                capture["diagnostic"]=None
            capture["checks"] = check_opening(capture)
            binding = _read(campaign/"dialogue.json").get("campaign_binding")
            if binding:
                module_hash = hashlib.sha256((campaign/"dialogue.lua").read_bytes()).hexdigest()
                seed_hash = hashlib.sha256((campaign/"story-seed.json").read_bytes()).hexdigest()
                capture["campaign_binding"] = {**binding,"loaded_module_sha256":module_hash,
                                               "saved_build":registry["Build"]}
                capture["checks"]["loaded_campaign_module"] = registry["Build"] == module_hash+":"+seed_hash
            middle_log = None
            if gate_profile:
                gate_state = registry["Gate"]
                capture["approach_state"] = gate_state
                capture["checks"]["automatic_mayor"] = bool(capture["automatic_mayor"] and
                    not capture["automatic_mayor"]["actor_double_click"] and gate_state["MayorStartedTalk"] and
                    gate_state["TalkSteps"] > 0 and any(" talk " in s for s in gate_state["Trace"]) and
                    registry["Changes"].get("90" if journey else "89")==1 and registry["Changes"].get("76")==1)
            initial_log = None
            if all(capture["checks"].values()):
                initial_log = log
                _graceful_stop(proc,sandbox / "server/ModernUO.exe")
                if award_checkpoint is not None:
                    from .award_fixture import apply_health
                    capture["award_condition"]=apply_health(award_checkpoint,state,_read(campaign/"story-seed.json"))
                proc,log = _start(root,sandbox,{**record,"state":str(state),"port":port})
                with game_login(port,log,proc,account,password) as game:
                    select_player(game,character)
                    reopened = PlayerConnection(game,root)
                    pos = reopened.enter()
                    time.sleep(0.8)
                    reopened.game.sendall(b"\x73\x56")
                    reopened.expect({0x73},predicate=lambda f:f==b"\x73\x56")
                    try:
                        if journey:
                            from .journey_replay import journey as play_journey
                            capture["journey"]={}
                            sample = _read(release/"sample.json")
                            if "world_geometry" in record:
                                sample["world_geometry"] = record["world_geometry"]
                            play_journey(reopened,sample,campaign,state/"world",
                                lambda: saved_after_creation(log,proc,state,character,snapshot_count(log)),capture["journey"],root,
                                expected_downed=expected_downed,witnesses_first=witnesses_first)
                        elif gate_profile:
                            from .gate_replay import refuse_passage
                            capture["dock_guard"] = refuse_passage(reopened,_read(release/"sample.json"),campaign)
                        else:
                            capture["mayor_after_opening"] = walk_to_mayor(
                                reopened,_read(release/"sample.json"),campaign,registry["Opening"]["Egg"])
                    except ValueError as exc:
                        capture["diagnostic"] = str(exc)
                saved_after_creation(log,proc,state,character,snapshot_count(log))
                updated, _ = read_registry(state / "world/UltimaOfflineDialogue/UltimaOfflineDialogue.bin")
                # Later legitimate party joins and random draws belong to the
                # same RPG state. The completed opening itself must not rerun.
                opening_persisted = (all(updated["Opening"][k]==registry["Opening"][k] for k in
                    ("Egg","Owner","Status","Tick","Trace","GateCreated","GateId","Actions"))
                    if journey else updated["Opening"]==registry["Opening"])
                capture["checks"]["one_shot_after_restart"] = (
                    list(pos)==capture["server_position"] and reopened.serial==capture["player_serial"]
                    and opening_persisted)
                capture["post_visit_flags"] = updated["Changes"]
                if journey:
                    capture["saved_gate"]=updated["Gate"]
                    capture["checks"]["legitimate_gate_journey"] = capture["journey"].get("passed_gate_reclose") is True
                    if capture["checks"]["legitimate_gate_journey"]:
                        from .journey_replay import verify_award
                        middle_log = log
                        _graceful_stop(proc,sandbox/"server/ModernUO.exe")
                        proc,log=_start(root,sandbox,{**record,"state":str(state),"port":port})
                        with game_login(port,log,proc,account,password) as game:
                            select_player(game,character)
                            again=PlayerConnection(game,root)
                            saved_pos=again.enter()
                            last=capture["journey"]["closed"]["physical_crossing_test"]["position"]
                            if list(saved_pos)!=last or again.serial!=capture["player_serial"]:
                                raise ValueError("The restored end-of-journey position or player differs")
                            direction=capture["journey"]["closed"]["physical_crossing_test"].get("requested_direction",2)
                            blocked=again.move(direction,block=True)
                            again.resync()
                            persisted,_=read_registry(state/"world/UltimaOfflineDialogue/UltimaOfflineDialogue.bin")
                            from .stables_replay import bag_contents
                            inventory = bag_contents(again)
                            reward=verify_award(again,persisted,_read(campaign/"story-seed.json"),inventory=inventory,
                                                program=_read(campaign/"dialogue.json")["program"],expected_downed=expected_downed)
                            capture["checks"]["final_gate_and_reward_after_restart"]=(
                                reward==capture["journey"]["reward"] and persisted["Changes"]==updated["Changes"] and
                                persisted["Gate"]["Trace"]==updated["Gate"]["Trace"] and not persisted["Gate"]["Actions"])
                            capture["journey"]["restored"]={"blocked_walk":blocked,"reward":reward,
                                "position":list(saved_pos),"flags":persisted["Changes"]}
                            if (campaign/"world-live.json").is_file():
                                from .journey_replay import restore_smithy_tongs
                                item = restore_smithy_tongs(again,capture["journey"]["regional_item"],state/"world",inventory)
                                capture["journey"]["restored"]["regional_item"] = item
                                capture["checks"]["regional_item_after_restart"] = item["status"] == "passed"
                elif gate_profile:
                    capture["saved_gate"] = updated["Gate"]
                    capture["checks"]["ordinary_dock_refusal_and_collision"] = (
                        "dock_guard" in capture and updated["Changes"].get("78")==1 and
                        updated["Changes"].get("66")==1 and updated["Changes"].get("61",0)==0 and
                        str(reopened.serial) not in updated["Active"] and
                        not updated["Gate"]["Actions"] and not updated["Gate"]["Error"] and
                        not any(" lift " in s for s in updated["Gate"]["Trace"]))
                else:
                    capture["checks"]["restored_player_control_and_refusal"] = (
                        "mayor_after_opening" in capture and updated["Changes"].get("89")==1
                        and updated["Changes"].get("76")==1 and updated["Changes"].get("90",0)==0)
            result = {"status":"passed" if all(capture["checks"].values()) else "incomplete",
                      "build_id":record["build_id"],"scratch":str(sandbox),"log":str(log),"opening":capture,
                      "port":port, "server_pid":proc.pid, "rendered_client":"not_run"}
            if initial_log:
                result["initial_log"]=str(initial_log)
            if middle_log:
                result["middle_log"]=str(middle_log)
            _write(sandbox/"opening.json",result)
            return result
        movement = None
        if walk or dialogue or terrain_scenarios:
            from .player_replay import PlayerConnection, walk_replay
            sample = _read(release / "sample.json")
            if dialogue:
                from .player_replay import (dialogue_save, reopen_refusal, replay_dialogue, replay_refusal,
                                            resume_dialogue, source_pages)
                campaign = sandbox / "server/Campaign"
                sources = source_pages(campaign)

            def play(game):
                connection = PlayerConnection(game, root)
                connection.enter()
                if void:
                    from u7uo.world_land import explain_world_cell
                    source = Path(record["source_release"])
                    report = _read(source/"world-land.json")
                    path = [(497,2315),(496,2315)] if mountains else [(121,2544),(120,2544)]
                    obstacle = (496,2316) if mountains else (119,2544)
                    cells = [explain_world_cell(source,x,y,report) for x,y in [*path,obstacle]]
                    for cell in cells[:2]:
                        if (cell["source"]["shape"] != 12 or cell.get("underlay_donor")
                                or cell.get("shore_graphic",{}).get("palette_index") != 226):
                            raise ValueError("Expected directly placed original void ground on the player path")
                    if mountains:
                        from u7uo.world_statics import explain_static
                        fixture_id = f"terrain:{catalog['source_seed_sha256']}:499:2319"
                        fixture = explain_static(source,fixture_id)["object"]
                        if ((fixture["shape"],fixture["frame"])!=(395,2) or len(fixture["native_records"])!=32
                                or cells[2].get("shore_graphic",{}).get("shape")!=12):
                            raise ValueError("Missing source mountain footprint above the void")
                    elif cells[2]["native"]["land_id"] not in range(168,172):
                        raise ValueError("Expected deep water west of the void")
                    connection.walk(path)
                    denied = connection.move(4 if mountains else 6,block=True)
                    collision = ({"rejected_mountain_step":denied,"mountain_fixture":fixture}
                                 if mountains else {"rejected_water_step":denied})
                    return {"approach":list(connection.resync()),**collision,
                            "source_cells":cells,"movement":connection.acknowledged}
                if swamp:
                    from .swamp_replay import replay as run_swamp
                    return run_swamp(connection,sandbox/"server/Campaign",state,
                        lambda: saved_after_creation(log,proc,state,character,snapshot_count(log)))
                if shore:
                    from u7uo.world_land import explain_world_cell
                    source = Path(record["source_release"])
                    report = _read(source/"world-land.json")
                    path = [(1022,2424)]+[(1023,y) for y in range(2424,2430)]
                    cells = [explain_world_cell(source,x,y,report) for x,y in [*path,(1024,2429)]]
                    first = record["shore_art"]["first_slot"]
                    limit = first+record["shore_art"]["frames"]
                    if (not all(first<=c["native"]["land_id"]<limit for c in cells[1:-1]) or
                            not 168<=cells[-1]["native"]["land_id"]<=171):
                        raise ValueError("Shore route does not cross the source bank and reach deep water")
                    connection.walk(path)
                    denied = connection.move(2,block=True)
                    return {"approach":list(connection.resync()),"rejected_water_step":denied,
                            "source_cells":cells,"movement":connection.acknowledged}
                replay = walk_replay(connection, sample)
                if dialogue:
                    scenario = replay_refusal if refusal else replay_dialogue
                    replay["dialogue"] = scenario(connection, replay["actor"]["serial"], sources)
                    if dos_reference is not None:
                        from .dos_refusal import compare
                        replay["dialogue"]["dos_reference"] = compare(dos_reference, replay["dialogue"], root)
                return replay

            movement = create_player(port, log, proc, account, password, character, start, play)
        else:
            create_player(port, log, proc, account, password, character, record["start"])
        prior = snapshot_count(log)
        saved_after_creation(log, proc, state, character, prior if movement is not None else 0)
        if dialogue:
            conversation = movement["dialogue"]
            saved = dialogue_save(state / "world", campaign, conversation["player_serial"], closed=refusal)
            if (saved["flag_76"], saved["flag_90"]) != (1,0):
                raise ValueError("Unexpected saved first-encounter or investigation flag")
            if refusal and saved["flag_89"] != 1:
                raise ValueError("The original refusal flag was not committed to the saved world")
            conversation["before_restart"] = saved
        original_pid, original_log = proc.pid, log
        _graceful_stop(proc, sandbox / "server/ModernUO.exe")
        proc, log = _start(root, sandbox, {**record, "state": str(state), "port": port})
        wait_log(log, "Loading world done", proc)
        result = {"status":"passed","character":character,"account_access":"normal new player","port":port,
                  "start":start,"slot":0,"server_pid":proc.pid,"build_id":record["build_id"],
                  "initial_server_pid":original_pid,"initial_log":str(original_log),"saved_and_restarted":True,
                  "rendered_client":"not_run","scratch":str(sandbox),"log":str(log)}
        if movement is not None:
            with game_login(port, log, proc, account, password) as game:
                select_player(game,character)
                reopened = PlayerConnection(game, root)
                actual = reopened.enter()
                if list(actual) != movement["approach"]:
                    raise ValueError(f"Reopened player stands at {actual}, expected {movement['approach']}")
                movement["saved_position_after_restart"] = list(actual)
                if swamp:
                    from .swamp_replay import reopen
                    reopen(reopened,movement,state,lambda: saved_after_creation(log,proc,state,character,snapshot_count(log)))
                if dialogue:
                    scenario = reopen_refusal if refusal else resume_dialogue
                    scenario(reopened, movement, sources)
                if stables:
                    from .stables_replay import play_stables
                    result["stables"] = play_stables(
                        reopened, sample, campaign, state / "world",
                        lambda: saved_after_creation(log, proc, state, character, snapshot_count(log)))
            if dialogue:
                saved_after_creation(log, proc, state, character, snapshot_count(log))
                saved = dialogue_save(state / "world", campaign, conversation["player_serial"])
                before = conversation["before_restart"]
                if (saved["flag_76"],saved["flag_90"]) != (1,0 if refusal else 1) or any(
                    saved[key] != before[key] for key in ("actor","program_and_seed")):
                    raise ValueError("Persisted post-choice investigation state or identity does not match")
                if refusal and saved["flag_89"] != 1:
                    raise ValueError("Restored reconsideration did not preserve the original refusal flag")
                if refusal and dos_reference is not None:
                    witness = conversation["dos_reference"]["glyph_witness"]
                    if witness["original_save_state"] == "passed":
                        flags = witness["flags_checked"]
                        for n in ("76","89","90"):
                            if before[f"flag_{n}"] != flags[n]["save"] or saved[f"flag_{n}"] != flags[n]["save"]:
                                raise ValueError(f"Restored flag {n} differs from the original DOS save")
                        conversation["dos_reference"]["matching_saved_flags"] = [76,89,90]
                conversation["after_retry" if refusal else "after_continue"] = saved
            result["walking"] = movement
        if stables:
            from .stables_replay import report_key, restore_stables
            result["middle_log"] = str(log)
            _graceful_stop(proc, sandbox / "server/ModernUO.exe")
            proc, log = _start(root, sandbox, {**record,"state":str(state),"port":port})
            with game_login(port, log, proc, account, password) as game:
                select_player(game, character)
                restored = PlayerConnection(game, root)
                restored.enter()
                restore_stables(restored, result["stables"], state / "world", _read(campaign / "story-seed.json"))
                result["stables"]["mayor_report"] = report_key(
                    restored, movement, result["stables"], campaign, state / "world",
                    lambda: saved_after_creation(log, proc, state, character, snapshot_count(log)))
                if estate:
                    from .estate_replay import play_estate
                    try:
                        result["estate"] = play_estate(restored,sample,campaign,state/"world",result["stables"],
                            lambda: saved_after_creation(log,proc,state,character,snapshot_count(log)))
                    except ValueError as exc:
                        result.update(status="incomplete",estate={"status":"incomplete","diagnostic":str(exc)})
            if estate and result["estate"]["status"] == "passed":
                from .estate_replay import reopen_estate
                _graceful_stop(proc, sandbox / "server/ModernUO.exe")
                proc, log = _start(root, sandbox, {**record,"state":str(state),"port":port})
                with game_login(port,log,proc,account,password) as game:
                    select_player(game,character)
                    restored = PlayerConnection(game,root)
                    restored.enter()
                    try:
                        result["estate"]["reopened"] = reopen_estate(restored,result["estate"])
                    except ValueError as exc:
                        result["estate"].update(status="incomplete",diagnostic=str(exc))
                        result["status"]="incomplete"
            result.update(server_pid=proc.pid, log=str(log))
        if launch:
            launch_client(root, release, sandbox, state, result, account, password, visual)
            keep = True
        _write(sandbox / "entry.json", result)
        return result
    finally:
        if not keep and proc.poll() is None:
            _graceful_stop(proc, sandbox / "server/ModernUO.exe")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--installation", type=Path, required=True)
    parser.add_argument("--facet", type=Path, required=True)
    parser.add_argument("--open-client", action="store_true")
    parser.add_argument("--login-screen", action="store_true", help="Open the login screen with a new disposable account and no precreated character")
    parser.add_argument("--visual", action="store_true", help="Enable renderer capture and movement in the disposable client")
    parser.add_argument("--shore", action="store_true", help="Cross the source muddy bank, attempt deep water and reopen the player")
    parser.add_argument("--void", action="store_true", help="Walk on exposed original void ground, attempt the adjacent obstruction and reopen")
    parser.add_argument("--swamp", action="store_true", help="Wear placed swamp boots, cross a poison field, remove the boots and reopen the poisoned player")
    parser.add_argument("--walk", action="store_true", help="Walk the source route and exercise server collision")
    parser.add_argument("--dialogue", action="store_true", help="Walk to Finnigan and exercise the staged dialogue Gump")
    parser.add_argument("--refusal", action="store_true", help="Decline Finnigan's offer and verify reconsideration after restart")
    parser.add_argument("--dos-reference", type=Path, help="Compare refusal with an observed original DOS capture")
    parser.add_argument("--opening", action="store_true", help="Observe the opt-in introduction beginning with an ordinary login")
    parser.add_argument("--stables", action="store_true", help="Accept the investigation, enter the stables and carry the key through a restart")
    parser.add_argument("--estate", action="store_true", help="Take the carried key upstairs and open the source investigation chest")
    parser.add_argument("--journey", action="store_true", help="Accept the automatic interview and follow the investigation to the town gate")
    parser.add_argument("--witnesses-first", action="store_true", help="Follow the witness investigation before asking the dock guard for passage")
    parser.add_argument("--award-checkpoint", type=Path, help="Reproduce Iolo's measured pre-report DOS hit points in this disposable journey")
    parser.add_argument("--appointment",type=Path,help="Replay a qualified DOS morning appointment in a disposable world")
    parser.add_argument("--appointment-restart",action="store_true",help="Restart with an active saved NPC route, then complete the appointment")
    parser.add_argument("--office-observer",type=Path,help="Observe Finnigan sitting and reopen, using the verified DOS office continuation")
    parser.add_argument("--chair-restart",action="store_true",help="Disconnect during Finnigan's chair walk and resume the persisted route")
    parser.add_argument("--occupy-chair",action="store_true",help="Resume with a second ordinary player occupying the selected seat")
    args = parser.parse_args()
    report = run(args.installation, args.facet, args.open_client, walk=args.walk, dialogue=args.dialogue,
                 refusal=args.refusal, dos_reference=args.dos_reference, opening=args.opening, stables=args.stables, estate=args.estate,
                 journey=args.journey,visual=args.visual,shore=args.shore,swamp=args.swamp,void=args.void,
                 award_checkpoint=args.award_checkpoint,login_screen=args.login_screen,witnesses_first=args.witnesses_first,appointment=args.appointment,
                 appointment_restart=args.appointment_restart,office_observer=args.office_observer,chair_restart=args.chair_restart,
                 occupy_chair=args.occupy_chair)
    print(json.dumps(report, indent=2))
    raise SystemExit(0 if report["status"] == "passed" else 1)
