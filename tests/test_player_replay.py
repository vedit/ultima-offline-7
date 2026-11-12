import struct
import json
from pathlib import Path
import tempfile
import unittest
import zlib

from tools.facet.player_replay import compressed_gump, dialogue_save, check_say
from tools.facet.opening_replay import check_opening
from tools.facet.journey_replay import interview, saved_regional_tool
from tools.facet.stables_replay import check_investigation_triggers, saved_key


def frame(layout, lines):
    def pack(data):
        block = zlib.compress(data)
        return struct.pack(">II", 4 + len(block), len(data)) + block
    strings = b"".join(struct.pack(">H", len(s)) + s.encode("utf-16-be") for s in lines)
    payload = (struct.pack(">IIII", 101, 1001, 32, 40) + pack(layout.encode() + b"\0")
               + struct.pack(">I", len(lines)) + pack(strings))
    return struct.pack(">BH", 0xDD, len(payload) + 3) + payload


class OriginalDialogueGump(unittest.TestCase):
    def test_geography_uses_the_advertised_entry_and_stock_text_response(self):
        from unittest.mock import Mock
        page = {"buttons":{1:"Answer"}, "entries":[0], "body":['"Example?"'], "images":[64012],
                "digest":"example","sender":80,"kind":99}
        conn=Mock()
        farewell=frame("{ text 80 90 1 0 }{ button 48 90 1 2 1 0 1 }",["Continue"])
        conn.expect.side_effect=[farewell,b"\x73\x01"]
        result=interview(conn,page,[],geography=({"Example?":120},"fixture"))
        packet=conn.game.sendall.call_args_list[0].args[0]
        self.assertEqual(struct.unpack_from(">BHIIIIIHH",packet),(0xB1,33,80,99,1,0,1,0,3))
        self.assertEqual(packet[27:].decode("utf-16-be"),"120")
        self.assertEqual(result[0]["numeric_player_response"],120)
        page["entries"]=[4]
        with self.assertRaisesRegex(ValueError,"numeric control"):
            interview(conn,page,[],geography=({"Example?":120},"fixture"))

    def test_original_say_omits_terminal_page_marker_and_preserves_other_glyphs(self):
        page = {"body":["End."],"buttons":{1:"Continue"}}
        self.assertEqual(check_say(page, "End.*", "unit"), check_say(page, "End.", "unit"))
        with self.assertRaises(ValueError):
            check_say(page, "End!*", "unit")

    def test_source_key_is_bound_to_only_one_correct_persisted_entity(self):
        key = {"id":"seed:2571","shape":641,"frame":0,"quality_byte":253}
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            folder = root / "Items"
            folder.mkdir()
            name = b"UltimaOffline.Entities.CampaignInvestigationItem"
            pref = struct.pack("<iqi",5,0,1) + bytes((len(name) | 128, 0)) + name
            one = b"prefix" + key["id"].encode() + struct.pack("<iii",641,0,253)
            (folder / "Items.bin").write_bytes(one * 2)
            row = struct.pack("<HIqqi",0,112,0,0,len(one))
            path = folder / "Items.idx"
            path.write_bytes(pref + struct.pack("<i",1) + row)
            self.assertEqual(saved_key(root,key)["serial"], 112)
            path.write_bytes(pref + struct.pack("<i",2) + row + struct.pack("<HIqqi",0,113,0,len(one),len(one)))
            with self.assertRaisesRegex(ValueError, "found 2"):
                saved_key(root,key)

    def test_regional_save_keeps_the_exact_payload_and_rejects_duplicate_instances(self):
        tool = {"id":"ireg:fixture:u7ireg00:44", "payload":"1234567890ab"}
        name = b"UltimaOffline.Entities.RegionalItem"
        item = b"\1" + bytes([len(tool["id"])]) + tool["id"].encode() + b"\1\x0c" + tool["payload"].encode()
        with tempfile.TemporaryDirectory() as tmp:
            world = Path(tmp)
            folder = world / "Items"
            folder.mkdir()
            header = struct.pack("<iqi",5,0,1) + bytes([len(name)]) + name
            def save(records):
                (folder / "Items.bin").write_bytes(b"".join(records))
                rows = [struct.pack("<HIqqi",0,100+i,0,i*len(item),len(record))
                        for i,record in enumerate(records)]
                (folder / "Items.idx").write_bytes(header + struct.pack("<i",len(rows)) + b"".join(rows))
            save([item])
            self.assertEqual(saved_regional_tool(world,tool)["serial"],100)
            save([item,item])
            with self.assertRaisesRegex(ValueError,"found 2"):
                saved_regional_tool(world,tool)
            save([item,item[:-1]+b"9"])
            with self.assertRaisesRegex(ValueError,"payload differs"):
                saved_regional_tool(world,tool)

    def test_investigation_detour_requires_the_egg_at_the_first_committed_step_in_range(self):
        prior = {"stable":{"Player":8}}
        egg = {"id":"smithy","function_id":0x6A4,"world_xy":[7,3],"distance":2,
               "event":3,"offset":12,"archive_offset":140}
        seed = {"eggs":[{"id":"non-usecode-egg"},egg]}
        route = [(4,3),(4,3),(5,4),(6,4)]
        fire = {"Player":8,"BeforeX":4,"BeforeY":3,"X":5,"Y":4,"Flag":60,"Before":1,"After":1,
                "Function":0x6A4,"Event":3,"Radius":2,"MemberOffset":12,"ArchiveOffset":140}
        carried = {"hatched":prior}
        check_investigation_triggers(carried,{**prior,"smithy":fire},seed,route,8)
        for wrong in (prior,{**prior,"smithy":{**fire,"X":6}},
                      {**prior,"smithy":fire,"unseen":fire},{"smithy":fire}):
            with self.subTest(receipt=wrong), self.assertRaises(ValueError):
                check_investigation_triggers(carried,wrong,seed,route,8)

    def test_visible_reply_labels_are_matched_by_layout_not_text_table_order(self):
        raw = frame("{ gumppic 5 5 64012 }{ text 80 90 99 0 }{ button 45 90 1 2 1 0 3 }"
                    "{ htmlgump 80 50 150 20 1 0 0 }{ button 45 50 1 2 1 0 5 }", ["No", "<b>Yes</b>"])
        page = compressed_gump(raw)
        self.assertEqual(page["buttons"], {3:"No", 5:"Yes"})
        self.assertEqual(page["images"], [64012])
        self.assertEqual(page["kind"], 1001)

    def test_truncated_zlib_payload_is_rejected(self):
        raw = bytearray(frame("{ text 1 1 1 0 }", ["Test"]))
        raw[23:27] = struct.pack(">I", 1)
        with self.assertRaises(ValueError):
            compressed_gump(bytes(raw))

    def test_stock_gump_renderer_displays_entity_spellings_literally(self):
        layout = "{ htmlgump 20 20 250 60 0 0 1 }"
        for line in ('"Who is this stranger?"', '&quot;Who is this stranger?&quot;', "Iolo's bow & arrows"):
            with self.subTest(line=line):
                self.assertEqual(compressed_gump(frame(layout,[line]))["body"], [line])

    def test_dialogue_save_reads_only_framed_state_and_preserves_untouched_seed_flags(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "UltimaOfflineDialogue").mkdir()
            (root / "story-seed.json").write_text(json.dumps({"flags":[0]*837}))
            original = {"Build":"a:b", "Changes":{"76":1}, "Work":{"npc:12":{"Kind":11,"State":1}},
                        "Active":{"9":{"Actor":"npc:12","Function":0x40c,"History":[1,2]}}}
            body = json.dumps(original).encode()
            data = b"\x01\0\0\0\x01" + bytes((128 | len(body) & 127,len(body) >> 7)) + body
            path = root / "UltimaOfflineDialogue/UltimaOfflineDialogue.bin"
            path.write_bytes(data)
            state = dialogue_save(root, root, 9)
            self.assertEqual((state["flag_76"],state["flag_90"],state["history_length"]), (1,0,2))
            path.write_bytes(data + b"\0")
            with self.assertRaises(ValueError):
                dialogue_save(root, root, 9)

    def test_completed_status_alone_cannot_certify_the_opening(self):
        capture = {"saved_opening":{"Trace":[],"Owner":9,"Status":"complete","Locked":False},
                   "events":[],"pages":[],"music_slot":200,"requested_moves":0,
                   "server_position":[1076,2214,0], "player_serial":9,"diagnostic":None}
        checks = check_opening(capture)
        self.assertTrue(checks["completed"])
        for required in ("cached_egg","nine_source_barks","summoned_gate","source_steps","opening_faces"):
            self.assertFalse(checks[required])
