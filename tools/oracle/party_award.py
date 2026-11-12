"""Compare a live Forge award, its native reload and both ModernUO party conditions."""
import argparse
import hashlib
import json
from pathlib import Path
import struct

from .reward import compare_reward, reward_state
from u7uo.u7 import usecode_inventory


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def progress(sample):
    return [(m["handle"], m["xp"], m["training"]) for m in sample["npc_progress"]["members"]
            if m["cached"]]


def verify_snapshot(directory, observation):
    snapshot = observation["cache_snapshot"]
    file = directory / snapshot["file"]
    memory = file.read_bytes()
    if len(memory) != 1048576 or digest(file) != snapshot["sha256"]:
        raise ValueError("Invalid original DOS memory snapshot")
    at = observation["guest_table_offset"]
    for field, start, limit, count in (("active", 0, 8, 48), ("downed", 16, 16, 49)):
        size = memory[at + count]
        if size > limit or list(struct.unpack_from(f"<{size}H", memory, at + start)) != observation[field]:
            raise ValueError("DOS memory and reported roster differ")
    cache = observation["npc_progress"]["cache"]
    for member in observation["npc_progress"]["members"]:
        slot = memory[cache["map"] + member["actor"]]
        if slot >= 32 or slot != member["slot"] or struct.unpack_from("<H", memory, cache["forward"]+2*slot)[0] != member["actor"]:
            raise ValueError("DOS memory and reported actor slot differ")
        record = cache["buffers"] + 105 * slot
        if (struct.unpack_from("<H", memory, record+2)[0] != member["handle"]
                or struct.unpack_from("<iB", memory, record+20) != (member["xp"], member["training"])):
            raise ValueError("DOS memory and reported experience differ")
    return snapshot


def compare(installation, directory, conditional, healthy):
    receipt = json.loads((directory / "receipt.json").read_bytes())
    observed = receipt["party_observations"]
    indices = []
    for filename in ("before-final-answer.bin", "after-original-award.bin", "after-native-load.bin"):
        i, = (i for i, row in enumerate(observed) if row.get("cache_snapshot", {}).get("file") == filename)
        indices.append(i)
    first, last, loaded = indices
    if not first < last < loaded:
        raise ValueError("Unordered original award observations")
    snapshots = [verify_snapshot(directory, observed[i]) for i in indices]
    before = Path(receipt["native_continuation"]["source"])
    after = directory / "conditional-award-GAME05.U7"
    reopened = directory / "reloaded-award-GAME05.U7"
    recorded = {r["file"]: r["sha256"] for r in receipt["checkpoints"]}
    if any(digest(f) != recorded[f.name] for f in (after, reopened)):
        raise ValueError("Original reward checkpoint hash mismatch")
    target = json.loads(conditional.read_bytes())
    control = json.loads(healthy.read_bytes())["player_replay"]
    if (target["status"] != "passed" or control["status"] != "passed" or target["build_id"] != control["build_id"]
            or not all(r["opening"]["checks"]["final_gate_and_reward_after_restart"] for r in (target, control))):
        raise ValueError("Expected two verified journeys on the same converted facet")
    opening = target["opening"]
    setup = opening["award_condition"]
    if digest(before) != setup["source_sha256"] or digest(before) != receipt["native_continuation"]["sha256"]:
        raise ValueError("Original and converted initial conditions refer to different saves")
    source = installation / "Assets/UltimaVII-Steam"
    for name in ("U7.EXE", "STATIC/USECODE", "STATIC/INITGAME.DAT"):
        if digest(source / name) != receipt["inputs"][name]["sha256"]:
            raise ValueError(f"Original input hash mismatch for {name}")
    bytecode = (source / "STATIC/USECODE").read_bytes()
    fn, = (f for f in usecode_inventory(bytecode)["records"] if f["id"] == 0x911)
    offset = fn["code_offset"]
    if bytecode[offset:offset+4] != bytes.fromhex("38230000"):
        raise ValueError("The original award no longer starts with the party-list intrinsic")
    result = opening["journey"]["reward"]
    roster = result["award_roster"]
    original = compare_reward(before, after, result)
    save1, save2 = reward_state(after), reward_state(reopened)
    if (original["status"] != "passed" or save1["gold"] != save2["gold"]
            or result != opening["journey"]["restored"]["reward"]):
        raise ValueError("The award or its ownership differs after reload")
    def values(save):
        return [(v["handle"], v["experience"], v["training"]) for v in save["party_progress"].values()]
    initial = reward_state(before)
    pre, post = values(initial), values(save1)
    if setup["imported_hp"] != initial["party_progress"][1]["hp"] or setup["imported_hp"] != 0:
        raise ValueError("Converted journey did not use Iolo's measured zero HP")
    if pre == post or values(save2) != post or [progress(observed[i]) for i in indices] != [pre, post, post]:
        raise ValueError("Live DOS experience differs from its native saves")
    uo = dict(zip((p[0] for p in pre), (-356, -1, -2), strict=True))
    for row in [*observed[first:last+1], observed[loaded]]:
        if ([uo[h] for h in row["active"]] != roster["Active"] or
                [uo[h] for h in row["downed"]] != roster["Downed"]):
            raise ValueError("The DOS roster changed or differs from the converted intrinsic result")
    if (roster["SourceOffset"] != offset or roster["Downed"] != [-1] or
            roster["Returned"] != roster["Active"][::-1] or roster["xp_recipients"] != roster["Returned"]):
        raise ValueError("Converted award trace disagrees with party eligibility")
    healthy_reward = control["opening"]["journey"]["reward"]
    iolo = healthy_reward["party_progress"][setup["actor_id"]]
    if (healthy_reward["award_roster"]["Downed"] or -1 not in healthy_reward["award_roster"]["xp_recipients"]
            or iolo["Experience"] - iolo["initial_experience"] != 50):
        raise ValueError("Healthy control did not grant Iolo the ordinary award")
    edge, = (i for i in range(first+1, last+1)
             if progress(observed[i-1]) == pre and progress(observed[i]) == post)
    original.update(award_time_roster="live DOS samples bracketing the XP writes",
                    dos_transition_ms=[observed[i]["elapsed_ms"] for i in (edge-1, edge)],
                    active=observed[edge]["active"], downed=observed[edge]["downed"],
                    snapshots=snapshots, converted=roster, healthy_iolo=iolo,
                    reloaded_gold=save2["gold"], reloaded_sha256=save2["save_sha256"],
                    build_id=target["build_id"], source_usecode_sha256=receipt["inputs"]["STATIC/USECODE"]["sha256"],
                    dos_receipt=str(directory/"receipt.json"), conditional=str(conditional), healthy=str(healthy))
    return original


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("installation", "dos_session", "conditional_journey", "healthy_journey"):
        parser.add_argument(name, type=Path)
    args = parser.parse_args()
    print(json.dumps(compare(args.installation, args.dos_session, args.conditional_journey, args.healthy_journey), indent=2))
