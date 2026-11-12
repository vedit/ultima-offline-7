"""Command-line front door. JSON results go to stdout; unsuccessful checks exit nonzero."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

from .build import active_release, build_proof, inspect_inputs, run_checks


def installation_default():
    value = os.environ.get("U7UO_INSTALLATION")
    if value:
        return Path(value)
    provisioned = Path("E:/UltimaOffline")
    return provisioned if os.name == "nt" and provisioned.is_dir() else None


def explain(directory, diagnostic_id):
    # Reward item IDs persisted by CampaignRewardCoins bind the generating Lua
    # module and world seed to a precise instruction in the owner's USECODE.
    grant = re.fullmatch(r"([0-9a-f]{64}):([0-9a-f]{64}):([0-9a-fA-F]{4}):([0-9a-fA-F]{4}):(\d+)", diagnostic_id)
    if grant:
        module_hash, seed_hash, function, pc, offset = grant.groups()
        module = json.loads((directory/"dialogue.json").read_bytes())
        seed_bytes = (directory/"story-seed.json").read_bytes()
        if (module_hash != module["lua_sha256"] or
                hashlib.sha256((directory/"dialogue.lua").read_bytes()).hexdigest() != module_hash or
                hashlib.sha256(seed_bytes).hexdigest() != seed_hash):
            raise ValueError("Reward belongs to a different campaign module or seed")
        fn = next((f for f in module["program"]["functions"] if f["id"] == int(function,16)), None)
        row = next((r for r in fn["rows"] if r[0] == int(pc,16)), None) if fn else None
        if (not row or int(function,16)!=0x884 or row[1:3]!=[0x38,[0x2C,5]]
                or fn["base"]+row[0]!=int(offset)):
            raise ValueError("Reward ID does not point to its original grant instruction")
        return {"id":diagnostic_id, "source":"STATIC/USECODE", "source_sha256":module["source_sha256"],
                "function":fn["id"], "pc":row[0], "source_offset":int(offset), "intrinsic":0x2C,
                "operation":"add party items", "lua_sha256":module_hash, "seed_sha256":seed_hash,
                "asset":json.loads(seed_bytes)["runtime_shapes"]["644"]}
    if (directory/"world-statics").is_dir():
        if diagnostic_id=="world-statics":
            return json.loads((directory/"world-statics/summary.json").read_bytes())
        if diagnostic_id.startswith(("ifix:","terrain:")):
            from .world_statics import explain_static
            match = explain_static(directory,diagnostic_id)
            if match:
                return match
    if diagnostic_id == "world-land" and (directory/"world-land.json").is_file():
        return json.loads((directory/"world-land.json").read_bytes())
    if diagnostic_id.startswith("tile:"):
        x, y = map(int, diagnostic_id.removeprefix("tile:").split(","))
        for source in (directory / "walking/terrain.json", directory / "terrain.json"):
            if not source.is_file():
                continue
            terrain = json.loads(source.read_bytes())
            left, top = terrain["source_origin"]
            dx, dy = x - left, y - top
            if 0 <= dx < terrain["width"] and 0 <= dy < terrain["height"]:
                cell = terrain["cells"][dy * terrain["width"] + dx]
                rules = terrain.get("rules", terrain.get("land_rules", {}))
                return {"id": diagnostic_id, "source_position": [x, y], "tile": cell,
                        "rule": rules.get(str(cell["shape"])) or terrain.get("static_rules", {}).get(str(cell["shape"]))}
        if (directory/"world-land.source").is_file():
            from .world_land import explain_world_cell
            return explain_world_cell(directory,x,y,json.loads((directory/"world-land.json").read_bytes()))
    elif diagnostic_id.startswith("ifix:"):
        walking = directory / "walking/fixed.json"
        if walking.is_file():
            for obj in json.loads(walking.read_bytes()):
                if obj["id"] == diagnostic_id and obj["family"] == "IFIX":
                    return {"id": diagnostic_id, "object": obj, "source": "STATIC/" + obj.get("file", "U7IFIX64")}
        fixed = json.loads((directory / "fixed.json").read_bytes())
        for obj in fixed["objects"]:
            if obj["id"] == diagnostic_id:
                return {"id": diagnostic_id, "object": obj, "source": "STATIC/" + fixed["source_file"]}
    elif diagnostic_id.startswith("ireg:"):
        catalog_record = {}
        if (directory/"world-ireg").is_dir():
            from .world import explain_movable
            catalog_record = explain_movable(directory,diagnostic_id)
        witness = json.loads((directory / "container.json").read_bytes())
        for obj in witness["objects"]:
            if obj["id"] == diagnostic_id:
                return {**catalog_record,"id": diagnostic_id, "object": obj, "source": witness["source_file"], "member": witness["member"]}
        if (directory / "story-seed.json").is_file():
            seed = json.loads((directory / "story-seed.json").read_bytes())
            for tree in seed.get("investigation_chests", []):
                for obj in tree["objects"]:
                    if obj["id"] == diagnostic_id:
                        anchor = tree["objects"][0]
                        return {**catalog_record,"id": diagnostic_id, "object": obj, "source": "STATIC/INITGAME.DAT",
                                "member": tree["member"], "initial_world_position":[*anchor["world_xy"],anchor["lift"]]}
            for collection in ("eggs", "investigation_items", "gate_objects"):
                for obj in seed.get(collection, []):
                    if obj["id"] == diagnostic_id:
                        return {**catalog_record,"id": diagnostic_id, "object": obj, "source": "STATIC/INITGAME.DAT",
                                "member": obj["id"].split(":")[2], "initial_world_position": [*obj["world_xy"], obj["lift"]]}
        if catalog_record:
            return catalog_record
    elif diagnostic_id.startswith("npc-item:") and (directory / "story-seed.json").is_file():
        rows = json.loads((directory / "story-seed.json").read_bytes())["actors"].values()
        for row in rows:
            for item in row.get("inventory", []):
                if item["id"] == diagnostic_id:
                    return {"source": "STATIC/INITGAME.DAT", "member": "npc.dat", "item": item,
                            "initial_world_position": row["source_position"]}
    elif diagnostic_id.startswith("npc:"):
        actor = json.loads((directory / "actor.json").read_bytes())
        if actor["id"] == diagnostic_id:
            return actor
        if (directory / "story-seed.json").is_file():
            for row in json.loads((directory / "story-seed.json").read_bytes())["actors"].values():
                if row["id"] == diagnostic_id:
                    return row
    elif diagnostic_id in ("actor", "container", "coverage", "world", "usecode"):
        return json.loads((directory / (diagnostic_id + ".json")).read_bytes())
    elif diagnostic_id == "portrait":
        return json.loads((directory / "portrait" / "portrait.json").read_bytes())
    elif diagnostic_id.startswith("music:") and (directory / "music/music.json").is_file():
        tracks = json.loads((directory / "music/music.json").read_bytes())["tracks"]
        if diagnostic_id[6:] in tracks:
            return tracks[diagnostic_id[6:]]
    elif diagnostic_id.startswith("function:"):
        function = int(diagnostic_id.removeprefix("function:"), 16)
        inputs = json.loads((directory / "inputs.json").read_bytes())
        for record in inputs["u7"]["usecode"]["records"]:
            if record["id"] == function:
                result = {"id": diagnostic_id, "source": "STATIC/USECODE", "record": record,
                          "generated": function == 0x06A4}
                if result["generated"]:
                    result["translation"] = json.loads((directory / "script.json").read_bytes())
                ir = directory / "usecode-ir.json"
                if ir.is_file():
                    decoded = next(f for f in json.loads(ir.read_bytes())["functions"] if f["id"] == function)
                    result["disassembly"] = decoded
                library = directory / "script-library.json"
                if library.is_file():
                    metadata = json.loads(library.read_bytes())
                    result["generated"] = function in metadata["function_ids"]
                    result["compiler_diagnostics"] = metadata["diagnostics"].get(str(function), [])
                dialogue = directory / "dialogue.json"
                corpus = directory / "campaign-usecode.json"
                if corpus.is_file():
                    result["campaign_lua"] = json.loads(corpus.read_bytes())["functions"][str(function)]
                    result["generated"] = True
                    if library.is_file():
                        result["closed_library_diagnostics"] = result["compiler_diagnostics"]
                    result["compiler_diagnostics"] = result["campaign_lua"]["diagnostics"]
                if dialogue.is_file():
                    metadata = json.loads(dialogue.read_bytes())
                    fn = next((f for f in metadata["program"]["functions"] if f["id"] == function), None)
                    if fn:
                        result["generated"] = True
                        result["resumable_dialogue"] = {"source_offset": fn["base"], "code_sha256": fn["code_sha256"],
                                                        "reachable_instructions": len(fn["rows"]),
                                                        "module_sha256": metadata["lua_sha256"]}
                return result
    raise ValueError(f"No matching source record for {diagnostic_id}")


def main(argv=None):
    parser = argparse.ArgumentParser(prog="u7uo")
    actions = parser.add_subparsers(dest="command", required=True)
    for name in ("inspect", "build", "verify", "explain", "play", "stage"):
        action = actions.add_parser(name)
        if name in ("inspect", "build"):
            action.add_argument("--u7", required=True, type=Path)
            action.add_argument("--uo", required=True, type=Path)
        if name in ("inspect", "build", "verify", "play", "stage", "explain"):
            action.add_argument("--installation", type=Path, default=installation_default(),
                                help="Provisioned root for checking the pinned tools")
        if name == "inspect":
            action.add_argument("--full", action="store_true", help="Include hashes and offsets for all inspected source records")
            group = action.add_mutually_exclusive_group()
            group.add_argument("--world", action="store_true", help="Inventory terrain, fixed and movable objects, actors and schedules across all 144 regions")
            group.add_argument("--region", type=lambda value: int(value, 16), metavar="HEX",
                               help="Decode one source superchunk, including object identities and schedule destinations")
        if name == "build":
            action.add_argument("--stage", choices=("campaign", "proof", "trinsic"), default="campaign")
        if name in ("stage", "build"):
            action.add_argument("--out", required=True, type=Path)
        if name == "stage":
            action.add_argument("--port", type=int, default=2594)
            action.add_argument("--opening", action="store_true", help="Activate the source opening egg on a development facet")
        if name in ("verify", "explain", "play", "stage"):
            action.add_argument("--campaign", required=True, type=Path)
        if name == "verify":
            action.add_argument("--scenario", choices=("auto","journey","estate","swamp","void"),default="auto",
                                help="Select ordinary player gameplay verification on a staged private facet")
            action.add_argument("--structural-only", action="store_true",
                                help="Check the manifest and files; explicitly skip engine execution")
        if name == "explain":
            action.add_argument("--id", required=True, help="tile:<source x>,<source y>, function:<hex>, actor, portrait, container, coverage or a source object ID")
    args = parser.parse_args(argv)
    try:
        if args.command == "inspect":
            result = inspect_inputs(args.u7, args.uo, args.installation)
            success = result["u7"]["ready"] and result["uo"]["ready"] and result["tool_lock"]["status"] != "failed"
            if (args.world or args.region is not None) and result["u7"]["ready"]:
                from .world import world_census
                result["source_world"] = world_census(args.u7, args.region)
            if not args.full:
                source = result["u7"]
                for name in ("static_files", "seed_members"):
                    source[name + "_count"] = len(source.pop(name))
                if source["usecode"]:
                    source["usecode"].pop("records")
        elif args.command == "build":
            if args.stage == "campaign":
                raise ValueError("Full campaign compilation is unfinished. Use --stage trinsic for the development build.")
            result = build_proof(args.u7, args.uo, args.out, args.installation, trinsic=args.stage == "trinsic")
            success = True
        elif args.command == "stage":
            from .facet import stage_facet
            _, directory, manifest = active_release(args.campaign)
            if manifest["kind"] != "trinsic-development":
                raise ValueError("The private facet requires a build from --stage trinsic.")
            if not args.installation:
                raise ValueError("Private facet staging requires --installation.")
            result = stage_facet(args.installation, directory, args.out, port=args.port, opening=args.opening)
            success = True
        else:
            pointer = args.campaign / "current.json"
            metadata = json.loads(pointer.read_bytes()) if pointer.is_file() else {}
            if not isinstance(metadata, dict):
                raise ValueError("Invalid active build pointer")
            if metadata.get("kind") == "private-slot-zero-development":
                if not args.installation:
                    raise ValueError("The staged private facet requires --installation.")
                if args.command == "explain":
                    from .facet import facet_source
                    facet_id, source = facet_source(args.installation, args.campaign)
                    result = explain(source, args.id)
                    print(json.dumps({**result, "facet_build_id": facet_id, "compiler_build_id": source.name},
                                     indent=2, ensure_ascii=True))
                    return 0
                from .facet import play_facet, verify_facet
                result = (play_facet(args.installation, args.campaign) if args.command == "play" else
                          verify_facet(args.installation, args.campaign, structural_only=args.structural_only,
                                       scenario=args.scenario))
                print(json.dumps(result, indent=2, ensure_ascii=True))
                return 0 if result.get("status") != "failed" else 1
            if args.command=="verify" and args.scenario!="auto":
                raise ValueError("Player scenarios require a staged private facet.")
            identifier, directory, manifest = active_release(args.campaign)
            if args.command == "play":
                raise ValueError("This build contains compiler proof assets. The playable campaign is unfinished.")
            if args.command == "explain":
                result = explain(directory, args.id)
            else:
                checks = ({"uo_loaders": "not_run", "walking_area_loaders": "not_run", "lua_execution": "not_run", "converted_gameplay": "not_run",
                           "original_dos_runtime": "not_run", "vanilla_campaign": "not_run"}
                          if args.structural_only else run_checks(directory, args.installation))
                result = {"build_id": identifier, "kind": manifest["kind"], "integrity": "passed", "checks": checks}
                from .qualification import proof_report
                result["qualification"] = proof_report(directory, identifier, manifest, checks)
            success = True
    except (KeyError, OSError, ValueError, subprocess.SubprocessError) as exc:
        result, success = {"status": "failed", "diagnostic": str(exc)}, False
    print(json.dumps(result, indent=2, ensure_ascii=True))
    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(main())
