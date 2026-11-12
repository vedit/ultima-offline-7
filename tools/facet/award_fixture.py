"""Set up the measured DOS companion HP in a stopped disposable journey."""

import hashlib
import json

from tools.oracle.reward import reward_state
from .player_replay import read_registry


def apply_health(save, state, seed):
    receipt=json.loads((save.parent/"receipt.json").read_bytes())
    original=reward_state(save)
    if not any(c["file"]==save.name and c["sha256"]==original["save_sha256"]
               for c in receipt.get("checkpoints",[])):
        raise ValueError("Expected a verified original pre-report checkpoint")
    path=state/"world/UltimaOfflineDialogue/UltimaOfflineDialogue.bin"
    registry,before=read_registry(path)
    opening=registry["Opening"]
    if opening["Status"]!="complete" or registry["Gate"]["Progress"] or registry["Active"]:
        raise ValueError("Expected the disposable world after the opening and before the reward")
    if opening["Party"]!=[-356,-1]:
        raise ValueError("The ordinary opening must already have recruited Iolo")
    actor=seed["actors"]["1"]
    sample=original["party_progress"][1]
    if (sample["experience"]!=actor["experience"] or sample["training"]!=actor["training"]
            or sample["hp"]>0 or sample["dead"] or sample["paralyzed"]):
        raise ValueError("Expected the measured living, incapacitated pre-report companion")
    old=opening["HitPoints"].get("-1",actor["hit_points"])
    opening["HitPoints"]["-1"]=sample["hp"]
    # ModernUO serializes this standalone persistence as version, non-null
    # marker, a 7-bit byte count and a UTF-8 JSON string.
    payload=json.dumps(registry,separators=(",",":"),ensure_ascii=False).encode()
    size=len(payload)
    length=bytearray()
    while size>=128:
        length.append((size&127)|128)
        size>>=7
    length.append(size)
    tmp=path.with_suffix(".award-tmp")
    with tmp.open("xb") as stream:
        stream.write(b"\x01\x00\x00\x00\x01"+length+payload)
    if read_registry(tmp)[0]!=registry:
        raise ValueError("Failed to write the disposable companion condition")
    tmp.replace(path)
    return {"source_save":str(save),"source_sha256":original["save_sha256"],"actor_id":actor["id"],
            "source_actor":sample,"previous_hp":old,"imported_hp":sample["hp"],
            "registry_before":before,"registry_after":hashlib.sha256(path.read_bytes()).hexdigest()}
