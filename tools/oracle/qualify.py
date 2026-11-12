"""Check the visible Finnigan refusal and any exported original save in an owned DOS run."""

import argparse
import hashlib
import json
from pathlib import Path
import struct
import zlib

from u7uo.u7 import STEAM_FORGE_USECODE, seed_directory, usecode_inventory


# Visually identified from the original DOS frame sequence, then frozen as hashes of
# foreground glyph masks. Animated world pixels and the shape of the mouse cursor
# are deliberately omitted. The frame itself is always independently hashed.
TEXT = (55, 0, 287, 42)
MENU = (98, 64, 178, 82)
REFERENCES = [
    ("mayor_description", TEXT, "ee4ccad9082f6331f28ed878db3e19cc35d0bbdc43fe9cb66514af7c8c468505", 0x40C, 0x139),
    ("offer_page_1", TEXT, "1d6ee1138a64773139432295b2a1ed88d546f15f2ef9b8ee9529def7e2eb9e0d", 0x40C, 0x1B9),
    ("offer_page_2", TEXT, "2b656ccb10568638f3f2741ce650a8eb3d306e2a9e9a835330be284a063ef8a8", 0x40C, 0x1B9),
    ("offer_page_3", TEXT, "41547eaa98896f0e814bc77bf2cdc43dc875470a70a24f4c6cb918f3ba5d6b9c", 0x40C, 0x1B9),
    ("yes_then_no", MENU, "7ad573b4746bfe80593ee7f85e7bc80e75e49cfc6783e1c0af8fa0aaa188eccf", 0x90A, 0x11),
    ("refusal", TEXT, "a2194c6c7207efb23c05f10628b9581fe8fdc5ee2ab4cdc397970b969f314aa5", 0x40C, 0x216),
]
RECONSIDERATION = [
    ("reconsideration", TEXT, "58c58dd2551ec0d885aeaca969f172139dc4c9a68a1082d7409a38e1e41a7141", 0x40C, 0xD4),
    ("yes_then_no_again", MENU, REFERENCES[-2][2], 0x90A, 0x11),
    ("accept_after_refusing", TEXT, "75f307122320e45f8545abc98e19aa66369d0cd85d8f2c4aff4ed88cc4f1b1c1", 0x40C, 0xDE),
]


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def capture_pixels(png):
    """Read the checked, filter-zero RGBA PNG form produced by capture.cjs."""
    if png[:8]!=b"\x89PNG\r\n\x1a\n":
        raise ValueError("invalid captured PNG")
    pos,compressed=8,bytearray()
    header=None
    while pos<len(png):
        n,kind=struct.unpack_from(">I4s",png,pos)
        data=png[pos+8:pos+8+n]
        if len(data)!=n or zlib.crc32(kind+data)!=struct.unpack_from(">I",png,pos+8+n)[0]:
            raise ValueError("damaged capture PNG")
        if kind==b"IHDR":
            header=struct.unpack(">IIBBBBB",data)
        if kind==b"IDAT":
            compressed.extend(data)
        pos+=n+12
    if header!=(320,200,8,6,0,0,0):
        raise ValueError("reference needs the native 320x200 RGBA framebuffer")
    pixels=zlib.decompress(compressed)
    stride=320*4+1
    if len(pixels)!=200*stride or any(pixels[i] for i in range(0,len(pixels),stride)):
        raise ValueError("unexpected screen capture scanline format")
    return pixels


def mask(png, box, foreground=b"\xdf\xdf\x00"):
    pixels = capture_pixels(png)
    stride = 320*4+1
    left,top,right,bottom=box
    return sha(bytes(pixels[i:i+3]==foreground for y in range(top,bottom)
                     for i in range(y*stride+1+left*4,y*stride+1+right*4,4)))


def qualify(session, installation):
    session=session.resolve()
    receipt=json.loads((session/"receipt.json").read_bytes())
    source=installation/"Assets/UltimaVII-Steam"
    originals=receipt["inputs"]
    required={"ULTIMA7.COM","U7.EXE","MAINMENU.EXE","INTRO.EXE","ENDGAME.EXE","U7.CFG"}
    if (not receipt["fresh_filesystem"] or set(n for n in originals if not n.startswith("STATIC/"))!=required
            or sha((source/"STATIC/USECODE").read_bytes())!=STEAM_FORGE_USECODE):
        raise ValueError("unexpected original campaign or input selection")
    for name,record in originals.items():
        path=(source/name).resolve()
        if not path.is_relative_to(source.resolve()) or sha(path.read_bytes())!=record["sha256"]:
            raise ValueError(f"original DOS input changed: {name}")
    config=(session/"dosbox.conf").read_bytes()
    if sha(config)!=receipt["config_sha256"] or b"mount c .\r\nc:\r\nultima7.com" not in config:
        raise ValueError("unexpected original DOS launch configuration")
    usecode=(source/"STATIC/USECODE").read_bytes()
    records={r["id"]:r for r in usecode_inventory(usecode)["records"]}
    observations=[]
    references=REFERENCES+RECONSIDERATION
    for record in receipt["frames"]:
        file=(session/record["file"]).resolve()
        if file.parent!=session or not file.is_file():
            raise ValueError("invalid capture path")
        png=file.read_bytes()
        if sha(png)!=record["sha256"]:
            raise ValueError("frame hash differs from the capture receipt")
        if len(observations)==len(references) or (record["width"],record["height"])!=(320,200):
            continue
        role,box,digest,fid,pc=references[len(observations)]
        if mask(png,box)!=digest:
            continue
        fn=records[fid]
        offset=fn["code_offset"]+pc
        observed={**record,"observation":role,"mask_sha256":digest,"rect":box,"function_id":fid,"pc":pc,
                  "usecode_file_offset":offset}
        if box!=MENU:
            if usecode[offset]!=0x1C:
                raise ValueError("expected original append-string opcode")
            start=fn["offset"]+6+struct.unpack_from("<H",usecode,offset+1)[0]
            end=usecode.index(0,start,fn["offset"]+6+fn["data_length"])
            observed.update(source_string_offset=start,source_string_sha256=sha(usecode[start:end]))
        else:
            if usecode[offset]!=0x04:
                raise ValueError("expected original conversation opcode")
            hashes=[]
            for push in (7,4):
                ip=fn["code_offset"]+push
                if usecode[ip]!=0x1D:
                    raise ValueError("unexpected original yes/no menu construction")
                start=fn["offset"]+6+struct.unpack_from("<H",usecode,ip+1)[0]
                end=usecode.index(0,start,fn["offset"]+6+fn["data_length"])
                hashes.append(sha(usecode[start:end]))
            observed["ordered_source_string_sha256"]=hashes
        observations.append(observed)
    if len(observations)<len(REFERENCES):
        raise ValueError(f"only {len(observations)} of {len(REFERENCES)} ordered DOS reference screens matched")
    menu,end=observations[len(REFERENCES)-2:len(REFERENCES)]
    clicks=[a for a in receipt["actions"] if a["type"]=="click" and
            menu["elapsed_ms"]<=a["elapsed_ms"]<=end["elapsed_ms"]]
    if len(clicks)!=1 or clicks[0].get("button",0)!=0 or not (
            149<=320*clicks[0]["x"]<=174 and 65<=200*clicks[0]["y"]<=80):
        raise ValueError("expected one recorded left click on the original No answer")
    result={"schema":1,"game":"Steam Black Gate with Forge of Virtue","status":"passed",
            "edition_source_sha256":STEAM_FORGE_USECODE,"backend":receipt["backend"],"backend_version":receipt["backend_version"],
            "wasm_sha256":receipt["wasm_sha256"],"fresh_campaign":True,"inputs_checked":len(originals),
            "observations":observations[:len(REFERENCES)],"choice_input":clicks[0],"visible_outcome":"refusal",
            "original_save_state":"not_checked","qualification":"Ordered rendered glyph masks and recorded choice input"}
    extra=observations[len(REFERENCES):]
    if extra:
        result["same_session_reentry"]={"observations":extra,"status":"reconsideration_prompt_observed"}
    if len(extra)==len(RECONSIDERATION):
        menu,accepted=extra[-2:]
        answers=[a for a in receipt["actions"] if a["type"]=="click" and
                 menu["elapsed_ms"]<=a["elapsed_ms"]<=accepted["elapsed_ms"]]
        if len(answers)!=1 or answers[0].get("button",0)!=0 or not (
                102<=320*answers[0]["x"]<=136 and 65<=200*answers[0]["y"]<=80):
            raise ValueError("expected one left click on the original reconsideration Yes answer")
        result["same_session_reentry"].update(status="passed",choice_input=answers[0],visible_outcome="acceptance")
    if "original_save" in receipt:
        save=(session/"GAME00.U7").read_bytes()
        if sha(save)!=receipt["original_save"]["sha256"]:
            raise ValueError("original save archive digest mismatch")
        _,start,size=seed_directory(save)["flaginit"]
        flags=save[start:start+size]
        seed=(source/"STATIC/INITGAME.DAT").read_bytes()
        _,offset,seed_size=seed_directory(seed)["flaginit"]
        original=seed[offset:offset+seed_size]
        if len(flags)!=len(original) or [(original[n],flags[n]) for n in (76,89)]!=[(0,1),(0,1)]:
            raise ValueError("unexpected original steady-state flags after refusal")
        result.update(original_save_state="passed",save_sha256=sha(save),save_flags_offset=start,
                      flags_checked={str(i):{"seed":original[i],"save":flags[i]} for i in (20,59,60,72,76,89,90,92)})
    return result


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("session",type=Path)
    p.add_argument("--installation",type=Path,required=True)
    args=p.parse_args()
    report=qualify(args.session,args.installation)
    (args.session/"refusal-check.json").write_text(json.dumps(report,sort_keys=True,indent=2)+"\n",encoding="utf-8")
    print(report["status"],report["visible_outcome"],report["original_save_state"])
