"""Stage, qualify and publish the first private compiler proof."""

import hashlib
import json
import os
import re
import subprocess
import tempfile
from pathlib import Path

from .u7 import inspect_u7
from .uo import PROFILES, inspect_tools, inspect_uo, sha256


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":")) + "\n").encode()


def inspect_inputs(u7, uo, installation=None):
    return {"schema": 1, "u7": inspect_u7(u7), "uo": inspect_uo(uo), "tool_lock": inspect_tools(installation)}


def release_files(directory):
    result = {}
    for file in sorted(directory.rglob("*")):
        relative = file.relative_to(directory).as_posix()
        if relative == "manifest.json":
            continue
        if file.is_symlink() or file.resolve() != directory.resolve() / relative:
            raise ValueError(f"Redirected proof resource: {relative}")
        if file.is_dir():
            continue
        if not file.is_file():
            raise ValueError(f"Unexpected resource in proof: {relative}")
        result[relative] = sha256(file)
    return result


def check_release(directory, identifier):
    manifest = directory / "manifest.json"
    if manifest.is_symlink() or sha256(manifest) != identifier:
        raise ValueError("The active manifest does not match its build ID")
    contents = json.loads(manifest.read_bytes())
    if contents.get("schema") != 1 or contents.get("kind") not in {"trinsic-compiler-proof", "trinsic-development"}:
        raise ValueError("Unrecognized proof manifest")
    actual = release_files(directory)
    recorded = contents["files"]
    required = {"inputs.json", "terrain.json", "fixed.json", "map0.mul", "statics0.mul", "staidx0.mul",
                "function.lua", "script.json", "container.json", "actor.json", "coverage.json",
                "portrait/portrait.json", "portrait/gumpidx.mul", "portrait/gumpart.mul"}
    if contents["kind"] == "trinsic-development":
        required.update({"walking/terrain.json", "walking/fixed.json", "walking/map0.mul",
                         "walking/statics0.mul", "walking/staidx0.mul", "world.json", "usecode.json", "usecode-ir.json"})
        if "script-library" in contents.get("features", []):
            required.update({"script-library.lua", "script-library.json"})
        if "dialogue" in contents.get("features", []):
            required.update({"dialogue.lua", "dialogue.json", "story-seed.json"})
        if "opening-portraits" in contents.get("features", []):
            required.update(f"portraits/{slot}/{name}" for slot in (1, 11)
                            for name in ("portrait.json", "gumpidx.mul", "gumpart.mul"))
        if "opening-music" in contents.get("features", []):
            required.update({"music/music.json", "music/u7bg035.mp3"})
        if "east-gate" in contents.get("features", []):
            required.update("portraits/14/" + name for name in ("portrait.json", "gumpidx.mul", "gumpart.mul"))
        if "investigation-witnesses" in contents.get("features", []):
            required.update(f"portraits/{slot}/{name}" for slot in (2, 13)
                            for name in ("portrait.json", "gumpidx.mul", "gumpart.mul"))
        for face, frame in contents.get("additional_portrait_frames", []):
            required.update(f"portraits/{face}/frame{frame}/{name}" for name in ("portrait.json","gumpidx.mul","gumpart.mul"))
        if "barge-water" in contents.get("features", []):
            required.update({"water/terrain.json", "water/map0.mul", "water/staidx0.mul", "water/statics0.mul"})
        if "world-land" in contents.get("features", []):
            required.update({"world-land.json","world-land.idx","world-land.mul"})
            if "shore-art" in contents["features"]:
                required.update({"shore-art.json","shore-art.mul"})
            if "swamp" in contents["features"]:
                required.update({"swamp-fields.bin","swamp.json"})
            if "world-land-provenance" in contents.get("features", []):
                required.add("world-land.source")
            if "world-land-sample" in contents.get("features", []):
                required.update("world-land-sample/"+n for n in ("terrain.json","map0.mul","staidx0.mul","statics0.mul"))
        if "world-statics" in contents.get("features", []):
            required.update("world-statics/"+n for n in ("summary.json","staidx0.mul","statics0.mul","tfa.dat"))
            required.update(f"world-statics/region-{i:02x}.json" for i in range(144))
            if "ifix-provenance" in contents.get("features", []):
                required.add("world-statics/ifix.source")
        if "ireg-provenance" in contents.get("features", []):
            required.add("world-ireg/initgame.source")
            required.update(f"world-ireg/u7ireg{i:02x}.json" for i in range(144))
        if "regional-live-items" in contents.get("features", []):
            required.update(("world-live.json","world-live-coverage.json"))
        if "campaign-usecode" in contents.get("features", []):
            required.update(("campaign-usecode.source","campaign-usecode.lua","campaign-usecode.json"))
    if not required.issubset(recorded):
        raise ValueError("Incomplete proof manifest")
    if recorded != actual:
        differences = sorted(name for name in actual.keys() | recorded.keys() if actual.get(name) != recorded.get(name))
        raise ValueError("Proof file mismatch: " + ", ".join(differences))
    return contents


def active_release(campaign):
    try:
        pointer = json.loads((campaign / "current.json").read_bytes())
        identifier = pointer["build_id"]
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise ValueError(f"No valid active proof in {campaign}") from exc
    if not isinstance(identifier, str) or not re.fullmatch("[0-9a-f]{64}", identifier):
        raise ValueError("Invalid active build ID")
    directory = campaign / "releases" / identifier
    if directory.resolve() != campaign.resolve() / "releases" / identifier:
        raise ValueError("Active proof must reside inside the campaign directory")
    return identifier, directory, check_release(directory, identifier)


def run_checks(directory, installation):
    from .lua import verify_lua

    if not installation:
        raise ValueError("Both loader and Lua execution checks require --installation or U7UO_INSTALLATION")
    lock = inspect_tools(installation)
    if lock["status"] != "passed":
        bad = [name for name, entry in lock["tools"].items() if entry["status"] != "passed"]
        raise ValueError("Tool lock mismatch: " + ", ".join(bad))
    scratch = installation / "Cache" / "Readback"
    reader = scratch / "bin" / "Readback.dll"
    if not reader.is_file():
        raise ValueError(f"Missing {reader}. Build the pinned readback with tools/readback/build.ps1 first.")
    dotnet = installation / "Tools" / "dotnet" / "dotnet.exe"
    def readback(folder):
        execution = subprocess.run([str(dotnet), str(reader), str(folder.resolve())], cwd=scratch,
                                   capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60)
        if execution.returncode:
            raise ValueError("UO loader readback failed: " + (execution.stdout or execution.stderr).strip())
        result = json.loads(execution.stdout)
        if result.get("status") != "passed":
            raise ValueError("UO loaders did not confirm the generated terrain")
        for name, digest in PROFILES["readback_assemblies"].items():
            if result[name]["sha256"] != digest:
                raise ValueError(f"Unexpected production assembly for {name}")
        return result

    loaders = readback(directory)
    if loaders.get("portrait", {}).get("status") != "passed":
        raise ValueError("ClassicUO did not confirm the portrait gump")
    lua = verify_lua(directory, installation / PROFILES["tools"]["Lua"]["file"])
    if lua.get("status") != "passed":
        raise ValueError("Lua branch execution did not pass")
    route = "not_run"
    if (directory / "walking").is_dir():
        route = readback(directory / "walking")
        statics = route.get("statics") or {}
        if statics.get("matched") is not True or statics.get("expected_count", 0) < 1:
            raise ValueError("The loaders did not confirm a source-backed static placement")
    library = "not_run"
    if (directory / "script-library.lua").is_file():
        from .script_library import verify_script_library
        library = verify_script_library(directory, installation / PROFILES["tools"]["Lua"]["file"])
    water = readback(directory / "water") if (directory / "water").is_dir() else "not_run"
    world_land = readback(directory / "world-land-sample") if (directory / "world-land-sample").is_dir() else "not_run"
    world_index = "not_run"
    if (directory/"world-land.source").is_file():
        from .world_land import verify_world_land
        world_index = verify_world_land(directory)
    static_index = "not_run"
    if (directory/"world-statics").is_dir():
        from .world_statics import verify_world_statics
        static_index = verify_world_statics(directory)
    swamp = "not_run"
    if (directory/"swamp.json").is_file():
        from .swamp import verify_swamp
        swamp = verify_swamp(directory)
    movable_index = "not_run"
    if (directory/"world-ireg").is_dir():
        from .world import verify_movable_catalog
        movable_index = verify_movable_catalog(directory)
    regional = "not_run"
    if (directory/"world-live.json").is_file():
        from .regional_items import verify_regional_items
        regional = verify_regional_items(directory)
    dialogue = "not_run"
    if (directory / "dialogue.lua").is_file():
        from .dialogue import verify_dialogue
        dialogue = verify_dialogue(directory, installation / PROFILES["tools"]["Lua"]["file"])
    corpus = "not_run"
    if (directory/"campaign-usecode.lua").is_file():
        from .campaign_usecode import verify_corpus
        corpus = verify_corpus(directory, installation / PROFILES["tools"]["Lua"]["file"])
    return {"uo_loaders": loaders, "walking_area_loaders": route, "water_loaders": water,"world_land_loaders":world_land,
            "world_land_index":world_index,"world_static_index":static_index,"world_movable_index":movable_index,
            "swamp_fields":swamp,
            "regional_import":regional, "campaign_usecode_execution":corpus,
            "script_library_execution": library, "dialogue_fixture_execution": dialogue, "lua_execution": lua,
            "original_dos_runtime": "not_run", "converted_gameplay": "not_run", "vanilla_campaign": "not_run"}


def validate_output(campaign, inputs):
    target = campaign.resolve()
    for path in inputs:
        source = path.resolve()
        if target.is_relative_to(source) or source.is_relative_to(target):
            raise ValueError("Proof storage and game installations must be disjoint directories")
    if target.exists():
        allowed = {"releases", "current.json"}
        # Only our own temporary names may coexist during a concurrent/interrupted build.
        if any(p.name not in allowed and not p.name.startswith((".stage-", ".pointer-")) for p in target.iterdir()):
            raise ValueError("Use an empty or existing proof directory for --out")
    for name in ("releases", "current.json"):
        if (target / name).resolve() != target / name:
            raise ValueError("Proof storage must not redirect its release or pointer path")


def build_proof(u7, uo, campaign, installation, *, trinsic=False):
    from .actor import produce_actor
    from .containers import produce_container
    from .lua import produce_lua
    from .portrait import produce_portrait
    from .terrain import produce_terrain

    campaign = campaign.resolve()
    protected = [u7, uo]
    if installation:
        protected.extend(installation / name for name in ("Assets", "Tools", "Saves", "Builds/ModernUO"))
    validate_output(campaign, protected)
    inspected = inspect_inputs(u7, uo, installation)
    for name in ("u7", "uo"):
        if not inspected[name]["ready"]:
            raise ValueError(f"{name} input: " + "; ".join(inspected[name]["diagnostics"]))
    if not inspected["u7"]["matched_profile"]:
        raise ValueError("The edition was recognized but these source bytes are not qualified for the Trinsic proof")
    if inspected["tool_lock"]["status"] != "passed":
        raise ValueError("Proof requires the installed, matching tool lock. Run inspect with --installation for details.")
    releases = campaign / "releases"
    releases.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=campaign, prefix=".stage-") as temporary:
        staging = Path(temporary)
        payload = staging / "payload"
        terrain = produce_terrain(u7, uo, payload)
        script = produce_lua(u7, payload)
        portrait = produce_portrait(u7, payload / "portrait")
        container = produce_container(u7, payload)
        actor = produce_actor(u7, payload)
        if (actor["function_id"] != portrait["binding"]["function"] or actor["face"] != portrait["shape"]
                or actor["npc_slot"] != -portrait["binding"]["npc_ref"]):
            raise ValueError("The source actor, Usecode speaker, and portrait do not agree")
        coverage = {
            "u7_source_world_tiles": 3072 * 3072, "terrain_tiles_compiled": terrain["cell_count"],
            "uo_land_blocks_emitted": terrain["blocks"], "source_shape_frame_pairs_in_sample": terrain["distinct_source_shape_frames"],
            "fixed_superchunks_inventoried": 1, "fixed_superchunks_in_world": 144, "fixed_objects": terrain["fixed"],
            "movable_superchunks_decoded": 1, "movable_superchunks_in_world": 144,
            "objects_in_selected_containment_tree": len(container["objects"]),
            "movable_records_scanned_in_region": container["scanned_objects"],
            "actors_catalogued_in_proof": 1, "actor_slots_traversed": actor["table"]["records_indexed"],
            "portraits_compiled": 1, "standalone_gump_id": portrait["gump_id"],
            "original_functions_inventoried": inspected["u7"]["usecode"]["count"],
            "functions_generated": 1, "translated_instructions": script["instruction_count"],
            "gameplay_comparison": "not_run",
        }
        if trinsic:
            from .usecode import produce_usecode
            from .script_library import produce_script_library
            from .dialogue import produce_dialogue
            from .story_seed import produce_story_seed
            from .music import produce_opening_music
            from .walking import produce_walking_area
            from .water import produce_water
            from .world import world_census
            from .world_land import produce_world_land
            from .world_statics import produce_world_statics

            walking = produce_walking_area(u7, uo, payload / "walking")
            produce_water(u7, uo, payload / "water")
            census = world_census(u7, movable_output=payload/"world-ireg")
            land = produce_world_land(u7,uo,payload)
            statics = produce_world_statics(u7,uo,payload,census,land)
            coverage["world_statics_emitted"] = statics["native_records"]
            if land["source_cells"] != census["land_tile_occurrences"]:
                raise ValueError("Compiler and source census disagree on world tile coverage")
            coverage["world_land_blocks_emitted"] = land["emitted_blocks"]
            (payload / "world.json").write_bytes(json_bytes(census))
            produce_usecode(u7, payload, installation)
            from .campaign_usecode import produce_corpus
            corpus = produce_corpus(u7,payload)
            library = produce_script_library(payload)
            dialogue = produce_dialogue(u7, payload)
            seed = produce_story_seed(u7, payload, uo)
            from .swamp import produce_swamp
            produce_swamp(u7,payload,seed)
            from .regional_items import produce_regional_items
            coverage["regional_live_records"] = produce_regional_items(payload,u7,uo)
            for slot in (1, 2, 11, 13, 14):
                produce_portrait(u7, payload / "portraits" / str(slot), seed["actors"][str(slot)])
            produce_portrait(u7, payload / "portraits/2/frame1", seed["actors"]["2"], frame=1)
            coverage["portraits_compiled"] = 7
            produce_opening_music(u7, installation, payload / "music")
            coverage.update({"walking_area_cells": walking["cell_count"],
                             "source_flags": len(seed["flags"]), "placed_actor_seeds": len(seed["actors"]),
                             "walking_actor_slots": seed["walking_actor_slots"],
                             "resumable_dialogue_functions": dialogue["functions_compiled"],
                             "resumable_dialogue_instructions": dialogue["instructions"],
                             "functions_generated": corpus["generated_functions"],
                             "closed_library_functions": library["functions_compiled"],
                             "campaign_reachable_instructions": corpus["reachable_instructions"],
                             "campaign_unsupported_instruction_sites": corpus["unsupported_instruction_sites"],
                             "instructions_in_generated_library": library["instructions_emitted"],
                             "closed_library_functions_with_diagnostics": library["functions_with_diagnostics"],
                             "functions_with_diagnostics": corpus["generated_functions"]-corpus["functions_without_local_opcode_diagnostics"],
                             "world_source_inventory": census["totals"],
                             "regions_in_world_census": len(census["regions"])})
        (payload / "coverage.json").write_bytes(json_bytes(coverage))
        # Freeze the inputs actually certified by the inspector across generation.
        if inspect_inputs(u7, uo, installation) != inspected:
            raise ValueError("Input data or tool fingerprints changed during compilation")
        (payload / "inputs.json").write_bytes(json_bytes(inspected))
        manifest = {
            "schema": 1, "kind": "trinsic-development" if trinsic else "trinsic-compiler-proof", "playable": False,
            "source_edition": inspected["u7"]["status"], "source_profile": inspected["u7"]["matched_profile"],
            "tool_profile_sha256": sha256(Path(__file__).with_name("profiles.json")),
            "files": release_files(payload),
        }
        if trinsic:
            manifest["additional_portrait_frames"] = [[2, 1]]
            manifest["features"] = ["barge-water", "script-library", "dialogue", "opening-portraits", "opening-music",
                                    "east-gate", "investigation-witnesses", "world-land", "world-land-provenance",
                                    "world-statics","ifix-provenance","ireg-provenance","regional-live-items","campaign-usecode"]
            if "loader_sample_region" in land:
                manifest["features"].append("world-land-sample")
            manifest["features"].append("shore-art")
            manifest["features"].append("swamp")
        raw = json_bytes(manifest)
        (payload / "manifest.json").write_bytes(raw)
        identifier = hashlib.sha256(raw).hexdigest()
        check_release(payload, identifier)
        checks = run_checks(payload, installation)
        check_release(payload, identifier)
        destination = releases / identifier
        if destination.exists() and destination.resolve() != destination.absolute():
            raise ValueError("Unexpected redirected release directory")
        try:
            payload.rename(destination)
        except OSError:
            if not destination.is_dir():
                raise
            check_release(destination, identifier)
        # Only the small pointer changes. Each concurrent builder owns its staging tree.
        pointer = staging / "current.json"
        pointer.write_bytes(json_bytes({"build_id": identifier}))
        os.replace(pointer, campaign / "current.json")
    return {"status": "passed", "scope": manifest["kind"], "playable": False, "build_id": identifier,
            "release": str(destination.resolve()), "tiles": terrain["cell_count"], "checks": checks}
