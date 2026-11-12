"""Exercise original placed swamp boots and field contacts with normal player requests."""
import json
import struct
import time

from .player_replay import read_registry
from .stables_replay import bag_contents, lift_to_backpack


def replay(conn,campaign,state,snapshot):
    live=json.loads((campaign/"world-live.json").read_bytes())["objects"]
    source,=[r for r in live if r["shape"]==588 and r["xy"]==[1300,961] and r["parent"] is None]
    conn.resync()
    serial,=[s for s,v in conn.ground_items.items() if v==(source["art"],1300,961,4)]
    for worn,(art,layer) in list(conn.equipment.get(conn.serial,{}).items()):
        if layer==3:
            lift_to_backpack(conn,worn,art)
    time.sleep(1.15)
    conn.game.sendall(struct.pack(">BIH",7,serial,1))
    conn.game.sendall(b"\x73\x47")
    lifted=conn.expect({0x73,0x27},predicate=lambda f:f[0]==0x27 or f==b"\x73\x47")
    if lifted[0]==0x27:
        raise ValueError(f"Server refused the original boots lift, reason {lifted[1]}")
    conn.game.sendall(struct.pack(">BIBI",0x13,serial,3,conn.serial))
    reply=conn.expect({0x2e,0x27},predicate=lambda f:f[0]==0x27 or struct.unpack_from(">I",f,1)[0]==serial)
    if reply[0]!=0x2e or conn.equipment[conn.serial].get(serial)!=(source["art"],3):
        raise ValueError(f"Original boots equip reply {reply.hex()}, equipment {conn.equipment.get(conn.serial)}")
    conn.walk([(1299,961),(1298,961),(1297,961),(1296,961)])
    def steps(n):
        for _ in range(n):
            conn.move(4 if conn.position[1]==961 else 0)
        conn.resync()
    def saved(expected,roll,boots,poisoned):
        snapshot()
        record,digest=read_registry(state/"world/UltimaOfflineDialogue/UltimaOfflineDialogue.bin")
        swamp=record["Swamp"]
        last=swamp["Last"]
        if (swamp["Contacts"]!=expected or last["Roll"]!=roll or last["Serial"]!=conn.serial or
                last["Boots"]!=boots or last["Poisoned"]!=poisoned or last["Shape"]!=22 or
                [last["FieldX"],last["FieldY"]]!=list(conn.position[:2]) or
                swamp["Poisoned"].get(f"player:{conn.serial}",False)!=poisoned):
            raise ValueError(f"Unexpected swamp contact or immunity: {swamp}")
        return {"contacts":expected,"contact":last,"registry_sha256":digest}
    steps(17)
    protected=saved(18,2,True,False)
    bag,_=lift_to_backpack(conn,serial,source["art"])
    steps(5)
    exposed=saved(23,1,False,True)
    return {"source_boots":source["id"],"boots_serial":serial,"backpack":bag,"player_serial":conn.serial,
            "protected":protected,"exposed":exposed,"approach":list(conn.position)}


def reopen(conn,result,state,snapshot):
    bag,contents=bag_contents(conn)
    if bag!=result["backpack"] or result["boots_serial"] not in contents:
        raise ValueError("Source boots changed owner across restart")
    snapshot()
    registry,digest=read_registry(state/"world/UltimaOfflineDialogue/UltimaOfflineDialogue.bin")
    swamp=registry["Swamp"]
    if swamp["Contacts"]!=23 or not swamp["Poisoned"].get(f"player:{conn.serial}"):
        raise ValueError("Source poison flag failed to survive shard restart")
    result["reopened_poisoned"]=True
    result["reopened_registry_sha256"]=digest
