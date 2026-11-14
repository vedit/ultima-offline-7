"""Verify original food/key use and companion inventory through the host and ClassicUO."""
import json
import runpy
import time
from pathlib import Path
from investigation import Walkthrough, DOORS, distance
from play import Pipe, ROOT, session


def wait_mode(pipe, mode):
    deadline = time.monotonic() + 6
    while time.monotonic() < deadline:
        pipe.sync()
        if int(pipe.head[9]) == mode:
            return
        time.sleep(.025)
    raise AssertionError(("prompt", mode, pipe.head))


def native():
    with session("companion-item-native", "Investigation", True) as (folder, env, host):
        pipe = Pipe(env["TRINSIC_PIPE"], host)
        row = lambda handle: next(r for r in pipe.rows if r[0] == handle)
        assert row(184)[11] & 16 and row(200)[6] == 184
        assert row(168)[11] & 4 and row(264)[6] == 200
        assert pipe.send("USE", 168) == "using"
        wait_mode(pipe, 4)
        assert pipe.send("TARGET", int(pipe.head[10]), 0) == "ok"
        wait_mode(pipe, 0)
        assert row(168)[6] == 88
        assert pipe.send("USE", 168) == "using"
        wait_mode(pipe, 4)
        assert pipe.send("TARGET", int(pipe.head[10]), 184) == "ok"
        wait_mode(pipe, 0)
        assert not any(r[0] == 168 for r in pipe.rows)
        assert pipe.send("MOVE", 264, 88) == "ok" and row(264)[6] == 88
        assert pipe.send("MOVE", 264, 200) == "ok" and row(264)[6] == 200
        assert pipe.send("EQUIP", 128, 184) == "occupied" and row(128)[6] == 88
        assert pipe.send("MOVE", 232, 200) == "ok"
        assert pipe.send("EQUIP", 128, 184) == "ok" and row(128)[10] == 2
        assert pipe.send("MOVE", 128, 88) == "ok"
        assert pipe.send("EQUIP", 232, 184) == "ok" and row(232)[10] == 1
        assert pipe.send("USE", 88) == "using"
        pipe.sync()
        assert int(pipe.head[8]) == 88
        assert pipe.send("USE", 160) == "ok"
        wait_mode(pipe, 4)
        assert pipe.send("TARGET", int(pipe.head[10]), 0) == "ok"
        wait_mode(pipe, 0)
        assert row(160)[6] == 88
        assert pipe.send("SAVE") == "ok"
        assert pipe.send("LOAD") == "ok"
        assert row(264)[6] == 200 and row(232)[6] == 184 and row(232)[10] == 1
        print("Food consumption, cancellation, open-container use, party transfers and equipment passed.", flush=True)

        walk = Walkthrough(pipe, folder)
        walk.go((1070, 2208))
        door = next(r for r in pipe.rows if r[1] in DOORS and r[3:5] == [1071, 2207])
        if door[2] % 4 != 1:
            pipe.send("USE", door[0])
            pipe.sync()
        walk.go((1070, 2207))
        walk.go((1069, 2197))
        key = next(r for r in pipe.rows if r[1] == 641 and r[3:5] == [1068, 2197])
        assert pipe.send("MOVE", key[0], 88) == "ok"
        walk.go((977, 2137))
        door = next(r for r in pipe.rows if r[1] in DOORS and distance(r[3:5], (975, 2137)) <= 1)
        if door[2] % 4 != 1:
            pipe.send("USE", door[0])
            pipe.sync()
        walk.go((974, 2136))
        walk.estate_floor(6)
        walk.go((971, 2133))
        chest = next(r for r in pipe.rows if r[1] == 522 and r[3:5] == [972, 2132])
        key = next(r for r in pipe.rows if r[1] == 641 and r[6] == 88)
        assert pipe.send("SAVE") == "ok"
        assert pipe.send("USE", key[0]) == "using"
        wait_mode(pipe, 4)
        assert pipe.send("TARGET", int(pipe.head[10]), chest[0]) == "ok"
        wait_mode(pipe, 0)
        assert row(chest[0])[1] == 800 and walk.flags()[62]
        (folder / "item-use.json").write_text(json.dumps(
            {"food_consumed": 168, "companion": 184, "key": key[0], "chest": chest[0],
             "checks": ["cancel", "feed", "party transfer", "occupied hand", "equip", "restart", "unlock"]},
            indent=2))
        pipe.close()
        print("Original murder-scene key unlocked Christopher's chest.", flush=True)


def client():
    run = runpy.run_path(str(Path(__file__).with_name("client-proof.py")))["run"]
    name = "companion-item-client"
    commands = [
        "WAIT 900", "PAPERDOLL 184", "WAIT 250", "USE 200", "WAIT 250", "PARTYPANELS 184", "CAPTURE",
        "USE 168", "WAIT 400", "TARGETING 1", "TARGET 0", "WAIT 350", "TARGETING 0", "PACKCHECK 168",
        "USE 168", "WAIT 350", "TARGETING 1", "TARGET 184", "WAIT 400", "TARGETING 0", "ABSENT 168",
        "DRAGICON 264 pack:184 pack 90 70", "PACKCHECK 264",
        "DRAGICON 264 pack pack:184 90 70", "OWNER 264 200",
        "DRAGICON 232 sheet:184 pack:184 85 80", "OWNER 232 200",
        "DRAGICON 128 pack sheet:184 110 120", "WORN 128 TwoHanded 184", "CAPTURE",
        "DRAGICON 128 sheet:184 pack 90 80", "PACKCHECK 128",
        "DRAGICON 232 pack:184 sheet:184 110 120", "WORN 232 OneHanded 184",
        "SAVE", "EXIT",
    ]
    run(name, "Investigation", commands, True, scenario="items")
    run(name, "Investigation", [
        "WAIT 900", "PAPERDOLL 184", "WAIT 200", "USE 200", "WAIT 200", "PARTYPANELS 184",
        "WORN 232 OneHanded 184", "OWNER 264 200", "SHAPECOUNT 377 88 1", "CAPTURE", "USE 184",
        "WAIT 500", "PARTYTALK 184", "CAPTURE", "EXIT",
    ], False, scenario="restart")


if __name__ == "__main__":
    native()
    client()
