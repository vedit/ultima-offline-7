"""Inspect the mayor's original reward in saved DOS NPC and item tables."""

import hashlib
import struct

from .investigation import inspect_save
from u7uo.u7 import seed_directory


def reward_state(save):
    data = save.read_bytes()
    index = seed_directory(data)
    def member(name):
        _,at,length = index[name]
        return data[at:at+length]

    party = member("party")
    actors = member("u7nbuf.dat")
    items = member("u7ibuf.dat")
    # NpcSaver writes all 105-byte NPCs, two free-list words, then twelve
    # 16-bit equipment handles per NPC in the same order.
    count, remainder = divmod(len(actors)-4, 105+24)
    if remainder or count < 3:
        raise ValueError("Invalid original NPC/equipment table length")
    avatar_slots = struct.unpack_from("<12H", actors, count*105+4)
    if len(party)!=191 or party[16]>8 or party[190]>16:
        raise ValueError("Unexpected original PARTY roster layout")
    active = list(struct.unpack_from("<8H",party)[:party[16]])
    down = list(struct.unpack_from("<16H",party,158)[:party[190]])
    progress = {}
    for slot in (0,1,2):
        base = 105*slot
        handle,status = struct.unpack_from("<HH",actors,base+2)
        if not handle or handle%8 or handle+8>len(items):
            raise ValueError("Invalid original reward NPC item handle")
        extension, = struct.unpack_from("<H",items,handle+6)
        if not extension or extension%8 or extension+8>len(items):
            raise ValueError("Invalid original reward NPC item extension")
        # Item_getHitPoints reads the live ItemExtra for a CLASS_RECORDS NPC.
        hp, = struct.unpack_from("<b",items,extension+6)
        xp,training = struct.unpack_from("<iB",actors,base+20)
        progress[slot] = {"handle":handle,"experience":xp,"training":training,
                          "asleep":bool(status&0x80),"in_active_roster":handle in active,
                          "in_downed_roster":handle in down,"hp":hp,"paralyzed":bool(status&0x1000),
                          "dead":bool(status&0x8000),
                          "unconscious_at_checkpoint":bool(status&(0x80|0x1000|0x8000)) or hp<=0}
    summary = inspect_save(save)
    key = summary["key"]
    if key["actor_slot"]!=0 or len(key["parents"])!=2 or key["parents"][1]!=progress[0]["handle"]:
        raise ValueError("Original reward checkpoint has no investigation key in the Avatar's backpack")
    coins = {}
    for parent,edge in zip(key["parents"],("backpack","avatar")):
        extension, = struct.unpack_from("<H",items,parent+6)
        current, = struct.unpack_from("<H",items,extension)
        seen = set()
        while current:
            if current%8 or current+8>len(items) or current in seen:
                raise ValueError("Invalid DOS reward inventory linkage")
            seen.add(current)
            nxt,owner,word,kind,attr = struct.unpack_from("<HHHBB",items,current)
            if owner!=parent:
                raise ValueError("DOS reward inventory parent disagreement")
            if word&1023==644:
                slots = [slot for slot,handle in enumerate(avatar_slots) if handle==current]
                if len(slots)>1 or (slots and edge!="avatar"):
                    raise ValueError("Original currency equipment disagrees with its owner")
                coins[current] = {"quantity":(attr&127) or 1,"parent":parent,"edge":edge,"frame":word>>10,
                                  "source_slot":slots[0] if slots else None}
            current = nxt
    return {"save_sha256":hashlib.sha256(data).hexdigest(),"party_progress":progress,
            "gold":coins,"active_roster":active,"downed_roster":down}


def compare_reward(before,after,target):
    first,last = reward_state(before),reward_state(after)
    party = {}
    for slot in first["party_progress"]:
        pre,post = first["party_progress"][slot],last["party_progress"][slot]
        matches = [p for k,p in target["party_progress"].items() if k.endswith(f":npc.dat:{slot}")]
        if len(matches)!=1 or pre["handle"]!=post["handle"]:
            raise ValueError("Reward participant cannot be matched across engines")
        modern = matches[0]
        original = [pre["experience"],post["experience"],pre["training"],post["training"]]
        converted = [modern["initial_experience"],modern["Experience"],modern["initial_training"],modern["Training"]]
        party[str(slot)] = {"matched":original==converted,"dos_xp_then_training_before_after":original,
                            "uo_xp_then_training_before_after":converted,"dos_before":pre,"dos_after":post}
    before_total = sum(c["quantity"] for c in first["gold"].values())
    after_total = sum(c["quantity"] for c in last["gold"].values())
    new_stacks = [c for n,c in last["gold"].items() if n not in first["gold"]]
    if len(new_stacks)!=1 or after_total-before_total!=new_stacks[0]["quantity"]:
        raise ValueError("Unqualified DOS reward stack merge or quantity change")
    modern_coins=target["coins"]
    parent=modern_coins.get("parent")
    if parent is None and modern_coins.get("bag"):
        parent="backpack"  # Earlier receipts verified the serial in the opened backpack.
    if parent not in ("avatar","backpack") or (parent=="avatar" and modern_coins.get("source_slot") not in (1,2)):
        raise ValueError("Missing or invalid converted reward ownership evidence")
    gold = {"quantity_matches":after_total-before_total==modern_coins["amount"],
            "dos_before":before_total,"dos_after":after_total,"uo_award":target["coins"]["amount"],
            "dos_parent":new_stacks[0]["edge"],"uo_parent":parent,"owner":"Avatar",
            "dos_slot":new_stacks[0]["source_slot"],"uo_slot":modern_coins.get("source_slot")}
    return {"status":"passed" if all(p["matched"] for p in party.values()) and gold["quantity_matches"]
            and gold["dos_parent"]==gold["uo_parent"] and gold["dos_slot"]==gold["uo_slot"] else "differences",
            "before_sha256":first["save_sha256"],"after_sha256":last["save_sha256"],
            "party":party,"gold":gold,"award_time_roster":"not_observed"}
