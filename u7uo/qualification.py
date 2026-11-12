"""Edition-specific release decisions. A skipped check cannot qualify a roadmap gate."""

import json


REQUIRED = (
    ("input_inventory", "clean_worker", "source_comparison"),
    ("loader_proof", "walking_loaders", "standalone_lua", "live_host", "private_start", "live_entities", "reference_branch"),
    ("reference_opening", "source_dialogue", "continuation_restart", "trinsic_departure"),
    ("world_inventory", "full_facet", "world_behaviors", "media", "scripts"),
    ("vanilla_input", "main_route", "both_endings", "side_content", "reachable_operations"),
    ("player_commands", "release_kit", "clean_offline_rehearsal", "backup_restore", "performance"),
)


def gate_decisions(observations):
    allowed = {"passed", "failed", "not_run"}
    gates = []
    for index, required in enumerate(REQUIRED):
        cases = {name: observations.get(name, "not_run") for name in required}
        if any(value not in allowed for value in cases.values()):
            raise ValueError(f"Invalid qualification result for gate {index}")
        if "failed" in cases.values():
            decision = "failed"
        elif "not_run" in cases.values():
            decision = "incomplete"
        else:
            decision = "passed"
        gates.append({"gate": index, "decision": decision, "checks": cases})
    return gates


def proof_report(directory, identifier, manifest, checks):
    def read(name):
        return json.loads((directory / name).read_bytes())

    def status(key):
        result = checks.get(key, "not_run")
        return result["status"] if isinstance(result, dict) else result

    coverage = read("coverage.json")
    observations = {"input_inventory": "passed", "loader_proof": status("uo_loaders"),
                    "walking_loaders": status("walking_area_loaders"), "standalone_lua": status("lua_execution")}
    counts = {"proof": coverage, "functions_inventoried": coverage["original_functions_inventoried"],
              "functions_generated": coverage["functions_generated"],
              "functions_executed_in_game": None, "calls_observed_in_game": None,
              "standalone_scenarios_passed": checks["lua_execution"]["scenarios_passed"]
              if status("lua_execution") == "passed" else None}
    if manifest["kind"] == "trinsic-development":
        source = read("world.json")
        corpus = read("usecode.json")
        walking = read("walking/terrain.json")
        observations["world_inventory"] = "passed" if len(source["regions"]) == 144 else "failed"
        counts.update({"land_occurrences_in_source": source["land_tile_occurrences"],
                       "region_object_counts": source["totals"], "source_object_families": source["object_shape_frame_pairs"],
                       "emitted_route_components": len(walking["statics"]), "route_source_placements": walking["fixed"],
                       "usecode": {k: corpus[k] for k in ("functions_decoded", "instructions", "distinct_opcodes",
                                                          "script_call_sites", "distinct_intrinsics", "intrinsic_call_sites")}})
    if "script-library" in manifest.get("features", []):
        library = read("script-library.json")
        invoked = checks.get("script_library_execution", "not_run")
        counts["functions_with_compiler_diagnostics"] = library["functions_with_diagnostics"]
        counts["library_scenarios_passed"] = invoked["scenarios_passed"] if isinstance(invoked, dict) else None
        counts["library_distinct_functions_exercised"] = len(invoked["function_ids_observed"]) if isinstance(invoked, dict) else None
    if "world-land" in manifest.get("features", []):
        land = read("world-land.json")
        counts["world_land"] = {key:land[key] for key in
                                ("source_cells","cells_with_land_rule","total_blocks","emitted_blocks","distinct_native_blocks")}
        if land.get("schema")==3:
            counts["world_land"].update(fully_mapped_blocks=land["fully_mapped_blocks"],mixed_blocks=land["mixed_blocks"],
                                        padding_cells=land["source_cells"]-land["cells_with_land_rule"])
    if "world-statics" in manifest.get("features", []):
        statics = read("world-statics/summary.json")
        counts["world_statics"] = {key:statics[key] for key in
                                    ("source_counts","dispositions","native_records","occupied_native_blocks",
                                     "sample_region","sample_native_records")}
    if "dialogue" in manifest.get("features", []):
        dialogue = read("dialogue.json")
        ids = {f["id"] for f in dialogue["program"]["functions"]}
        library_ids = set(read("script-library.json")["function_ids"]) if "script-library" in manifest["features"] else set()
        counts["dialogue_functions_generated"] = len(ids)
        counts["dialogue_instructions_emitted"] = dialogue["instructions"]
        counts["distinct_functions_generated_across_emitters"] = len(ids | library_ids | {0x6A4})
        case = checks.get("dialogue_fixture_execution", "not_run")
        counts["dialogue_fixture_scenarios_passed"] = case["scenarios_passed"] if isinstance(case, dict) else None
        seed = read("story-seed.json")
        counts["starting_flags"] = len(seed["flags"])
        counts["placed_actor_records"] = len(seed["actors"])
    if "campaign-usecode" in manifest.get("features", []):
        campaign = read("campaign-usecode.json")
        counts["closed_library_functions_with_diagnostics"] = counts["functions_with_compiler_diagnostics"]
        counts["functions_with_compiler_diagnostics"] = sum(bool(f["diagnostics"]) for f in campaign["functions"].values())
        counts["distinct_functions_generated_across_emitters"] = len(campaign["functions"])
        run = checks.get("campaign_usecode_execution")
        counts["campaign_lua_fixture_functions_observed"] = len(run["function_ids_observed"]) if isinstance(run,dict) else None
        counts["campaign_lua_first_effects_observed"] = run["entry_effects_observed"] if isinstance(run,dict) else None
    return {"build_id": identifier, "edition": manifest["source_edition"], "source_profile": manifest["source_profile"],
            "counts": counts, "gates": gate_decisions(observations)}
