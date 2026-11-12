"""Read ordered investigation choices from original DOS font pixels and compare player Gumps."""
import argparse
from functools import lru_cache
import hashlib
import json
from pathlib import Path

from .qualify import capture_pixels
from u7uo.portrait import _member, face_frame
from u7uo.u7 import usecode_inventory


class AnswerFont:
    def __init__(self, fonts):
        shape, _ = _member(fonts, 0, "conversation font")
        self.glyphs = {}
        for c in range(32, 128):
            w,h,p,_,(left,above) = face_frame(shape,c)
            self.glyphs[chr(c)] = (w-2, {(i%w-left, i//w-above+10):v
                                        for i,v in enumerate(p) if v is not None})

    @lru_cache(maxsize=2048)
    def label(self, text):
        result = {}
        x = 0
        for ch in "\x7f"+text:
            advance, pixels = self.glyphs[ch]
            result.update({(x+dx,dy):v for (dx,dy),v in pixels.items()})
            x += advance
        return x, result

    def read(self, png, labels):
        data = capture_pixels(png)
        def rgb(x,y):
            pos = y*1281+1+x*4
            return data[pos:pos+3]
        # DOS draws answer bullet 7F at (99,66) using the current scene palette.
        # Obtain each index from its actual pixels; room lighting changes the RGB.
        advance, raw_bullet = self.label("")
        bullet = {p:v for p,v in raw_bullet.items() if p[0]<advance}
        palette = {}
        for (dx,dy), v in bullet.items():
            c = rgb(99+dx,66+dy)
            if palette.setdefault(v,c) != c:
                raise ValueError("No unobscured DOS answer bullet at the expected origin")
        if len(set(palette.values())) != len(palette):
            raise ValueError("DOS answer palette is ambiguous")
        def matches(x,y,template):
            return all(rgb(x+dx,y+dy)==palette[v] for (dx,dy),v in template.items() if v in palette)
        results = []
        for y in range(66, 131, 13):
            anchors = [x for x in range(99,310) if matches(x,y,bullet)]
            if not anchors:
                break
            if anchors[0] != 99:
                raise ValueError("The first visible answer on a line must start at the pane edge")
            for i,x in enumerate(anchors):
                available = anchors[i+1]-x if i+1 < len(anchors) else 320-x
                hits = []
                for label in labels:
                    width, pixels = self.label(label)
                    if width > available or (i+1<len(anchors) and width+10 != available):
                        continue
                    if matches(x,y,pixels):
                        hits.append((width,label))
                if not hits:
                    raise ValueError(f"Unrecognized DOS label at ({x},{y})")
                width = max(w for w,_ in hits)
                options = [label for w,label in hits if w==width]
                if len(options)!=1:
                    raise ValueError(f"Ambiguous DOS label at ({x},{y})")
                results.append(options[0])
        if not results:
            raise ValueError("No visible answers")
        return results


def vocabulary(raw, fn_ids, extra=()):
    labels = set(extra)
    for fn in usecode_inventory(raw)["records"]:
        if fn["id"] in fn_ids:
            start = fn["offset"]+6
            for s in raw[start:start+fn["data_length"]].split(b"\0"):
                if 0<len(s)<=29 and all(32<=c<127 for c in s):
                    labels.add(s.decode("ascii"))
    return sorted(labels)


# These ordinal groups belong to the verified Forge departure capture.
DEPARTURE_RECEIPT = "22d03c467b0520180f5aae5690d84fcf3f267f7e00a8a54cc82c105eeef3423b"
TOPIC_FRAMES = {
    "Spark": (17, 20, 21, 22, 23, 25, 26, 27),
    "Gilberto": (45, 46, 47, 48, 50),
    "Finnigan": (100, 101, 102, 103, 104, 107, 108, 109, 110, 111, 114),
}


DAYLIGHT_RECEIPT = "1b9ad96e3b5aa5c00d403ee66ff9280aac3949ecc70986b9a00691c280f0db08"
DAYLIGHT_MENUS = ("gilberto-initial", "gilberto-murder", "gilberto-knocked",
                  "gilberto-blow", "gilberto-vessel")


def daylight_reference(session, original, target_ticks):
    from .departure import _frame
    from u7uo.story_seed import forge_clock
    from u7uo.u7 import seed_directory

    session = session.resolve()
    encoded = (session / "receipt.json").read_bytes()
    if hashlib.sha256(encoded).hexdigest() != DAYLIGHT_RECEIPT:
        raise ValueError("Unexpected daylight DOS reference receipt")
    receipt = json.loads(encoded)
    original_receipt = json.loads((original / "receipt.json").read_bytes())
    parent = original / "healer-approach-GAME02.U7"
    continuation = receipt["native_continuation"]
    if (Path(continuation["source"]).resolve() != parent.resolve() or
            receipt["inputs"] != original_receipt["inputs"] or
            receipt["wasm_sha256"] != original_receipt["wasm_sha256"] or
            receipt["scene_setup"]["base_config_sha256"] != original_receipt["config_sha256"] or
            hashlib.sha256((session/"dosbox.conf").read_bytes()).hexdigest() != receipt["config_sha256"]):
        raise ValueError("Daylight donor, interpreter or game data differ from the original route")
    saved, = [s for s in receipt["checkpoints"] if s["file"] == "daylight-interview-GAME02.U7"]
    before = parent.read_bytes()
    after = (session / saved["file"]).read_bytes()
    if (hashlib.sha256(before).hexdigest() != continuation["sha256"] or
            hashlib.sha256(after).hexdigest() != saved["sha256"]):
        raise ValueError("Changed native healer checkpoint")
    clock = forge_clock(after, require_saved=True)
    start = forge_clock(before, require_saved=True)
    def flags(raw):
        _, offset, _ = seed_directory(raw)["flaginit"]
        return {str(n): raw[offset+n] for n in (61, 64, 66, 67, 77)}
    first, last = flags(before), flags(after)
    if (list(first.values()) != [0,0,0,1,0] or list(last.values()) != [0,1,0,1,1] or
            clock["days"] != start["days"] or not isinstance(target_ticks, int) or
            clock["ticks"] // 4500 != (target_ticks % 36000) // 4500 or clock["ticks"] // 4500 != 2):
        raise ValueError("Daylight phase, native day or testimony flags differ")
    setup, _ = _frame(session, receipt, "daylight-clock")
    frames = [_frame(session, receipt, name)[0] for name in DAYLIGHT_MENUS]
    return frames, {"receipt_sha256": DAYLIGHT_RECEIPT, "source_checkpoint_sha256": continuation["sha256"],
                    "final_checkpoint_sha256": saved["sha256"], "initial_clock": start,
                    "clock": clock, "time_slot": 2, "clock_setup_frame": setup["file"],
                    "clock_setup_sha256": setup["sha256"], "initial_flags": first, "final_flags": last,
                    "setup": "Original DOS F2 set time and visit NPC 13, followed by ordinary conversation choices."}


def compare_topics(installation, session, replay, *, daylight=None):
    from .departure import qualify_departure
    from u7uo.story_seed import forge_clock
    from u7uo.u7 import seed_directory

    receipt_bytes = (session / "receipt.json").read_bytes()
    if hashlib.sha256(receipt_bytes).hexdigest() != DEPARTURE_RECEIPT:
        raise ValueError("The frame ordinals require the qualified Forge departure receipt")
    qualification = qualify_departure(session, installation)
    frames = json.loads(receipt_bytes)["frames"]
    data = replay.read_bytes()
    target = json.loads(data)
    target = target.get("player_replay", target)
    opening = target["opening"]
    if target["status"] != "passed" or not all(opening["checks"].values()):
        raise ValueError("Expected a completed ordinary-player journey and restart")
    journey = opening["journey"]
    spark = (session / "spark-hook-GAME00.U7").read_bytes()
    _, npc_offset, _ = seed_directory(spark)["u7nbuf.dat"]
    source_name = spark[npc_offset+89:npc_offset+99].split(b"\0", 1)[0].decode("ascii")
    target_name = "Alden"  # The fixed ordinary-player name in tools.facet.session.
    report_save = (session / "return-to-mayor-GAME05.U7").read_bytes()
    _, flag_offset, _ = seed_directory(report_save)["flaginit"]
    fonts = installation / "Assets/UltimaVII-Steam/STATIC"
    font = AnswerFont((fonts / "FONTS.VGA").read_bytes())
    labels = vocabulary((fonts / "USECODE").read_bytes(),
                        {0x402, 0x40c, 0x40d, 0x884, 0x908, 0x909, 0x90a}, [source_name])
    controlled, control = (None, None) if daylight is None else daylight_reference(
        daylight, session, journey["Gilberto"].get("clock_ticks"))
    rows = []
    for actor, ordinals in TOPIC_FRAMES.items():
        pages = journey["report"] if actor == "Finnigan" else journey[actor]["pages"]
        buttons = [p for p in pages if "choices" in p]
        if len(buttons) != len(ordinals):
            raise ValueError(f"Different number of rendered choice menus for {actor}")
        for index, (ordinal, page) in enumerate(zip(ordinals, buttons)):
            frame = frames[ordinal-1]
            if not frame["file"].startswith(f"{ordinal:03d}-"):
                raise ValueError("Unexpected source frame order")
            source = session
            if actor == "Gilberto" and controlled is not None:
                frame, source = controlled[index], daylight
            png = (source / frame["file"]).read_bytes()
            if hashlib.sha256(png).hexdigest() != frame["sha256"]:
                raise ValueError(f"Changed DOS frame {ordinal}")
            expected = font.read(png, labels)
            shown = page["choices"]
            if [hashlib.sha256(s.encode()).hexdigest() for s in shown] != page["body_hashes"]:
                raise ValueError("Converted buttons differ from on-wire dialogue text")
            compared = list(expected)
            if actor == "Spark" and ordinal == 17:
                if compared.count(source_name) != 1 or shown.count(target_name) != 1:
                    raise ValueError("Missing chosen player name in the introduction")
                compared[compared.index(source_name)] = target_name
            rows.append({"actor": actor, "source_session": source.name, "frame": frame["file"], "png_sha256": frame["sha256"],
                         "gump_sha256": page["gump_sha256"], "dos": expected, "classic_protocol": shown,
                         "match": compared == shown})
    return {"edition": qualification["edition"], "build_id": target["build_id"],
            "source_receipt_sha256": DEPARTURE_RECEIPT, "target_replay_sha256": hashlib.sha256(data).hexdigest(),
            "matched": sum(row["match"] for row in rows), "total": len(rows), "menus": rows,
            "daylight_control": control,
            "gilberto_dos_clock": control["clock"] if control else forge_clock((session/"gilberto-ship-GAME03.U7").read_bytes(), require_saved=True),
            "gilberto_target_ticks": journey["Gilberto"].get("clock_ticks"),
            "before_report_dos_flags": {str(n): report_save[flag_offset+n] for n in (61,66)},
            "before_report_target_flags": journey.get("before_report_flags")}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("installation", "session", "replay"):
        parser.add_argument(name, type=Path)
    parser.add_argument("--daylight", type=Path, help="Compare Gilberto against the day-one DOS control")
    args = parser.parse_args()
    result = compare_topics(args.installation, args.session, args.replay, daylight=args.daylight)
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result["matched"] == result["total"] else 1)
