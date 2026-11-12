"""Compare the observed Forge DOS refusal against the local UO protocol transcript."""
import hashlib
import json
from pathlib import Path
from tools.oracle.qualify import qualify


def compare(directory, trace, installation):
    directory = Path(directory)
    reference = json.loads((directory / "receipt.json").read_bytes())
    if (reference["fresh_filesystem"] is not True or
            reference["inputs"]["STATIC/USECODE"]["sha256"] != trace["usecode_sha256"]):
        raise ValueError("DOS refusal evidence has different source data or initial conditions")
    checked = qualify(directory, installation)
    observations = checked["observations"]
    if (checked["status"] != "passed" or checked["visible_outcome"] != "refusal" or
            observations[0]["source_string_sha256"] != trace["ordered_source_say"]["0x040C:0x13C"] or
            observations[1]["source_string_sha256"] != trace["ordered_source_say"]["0x040C:0x1BC"]):
        raise ValueError("DOS glyph witness and the first original UO dialogue or offer do not match")
    frames = reference["frames"][34:41]
    digests = []
    for frame in frames:
        name = frame["file"]
        if Path(name).name != name:
            raise ValueError("Unexpected DOS frame filename")
        actual = hashlib.sha256((directory / name).read_bytes()).digest()
        if actual.hex() != frame["sha256"]:
            raise ValueError("Original-game frame no longer matches its recorded digest")
        digests.append(actual)
    # This is the ordered set of seven manually read native frames showing the
    # stern remark, offer across three pages, Yes / No, refusal, and return to the world.
    digest = hashlib.sha256(b"".join(digests)).hexdigest()
    reviewed_close = digest == "1db9749e691f4938e62a98ae5dd0b317d50c1d649a569474654de85efb9e33bc"
    expected = {
        "0x040C:0x1B8":"581efe5b1adcbb602a1320a6b41438e2fc24a0ad3cf4a91e5dcb3ae50c0a14f4",
        "0x040C:0x1BC":"44b4de8caa7042dd839ad1db1284dc39a03d8c5203ae4373c78bb4abd54e4b39",
        "0x040C:0x219":"46f7eb6c0afaa535e1dc2f3cc5ccf336a13026bb4405bbb19c7043b8d2c729db",
    }
    if (any(trace["ordered_source_say"][pc] != text for pc,text in expected.items()) or
            trace["displayed_choices"] != ["Yes","No"] or trace["selected"] != "No" or not trace["closed_after_refusal"]):
        raise ValueError("The converted offer, choices or refusal differs from the observed DOS sequence")
    return {"edition":"English Steam Forge", "reference_directory":str(directory.resolve()),
            "receipt":str(directory.resolve()/"receipt.json"), "glyph_witness":checked,
            "reviewed_close_frames":frames if reviewed_close else [],
            "ordered_text_and_choices":"passed", "post_refusal_close":"passed" if reviewed_close else "not_compared",
            "literal_refusal_display":"differs_by_terminal_asterisk" if trace["terminal_asterisk_visible"] else "passed",
            "pagination":"DOS spans three offer pages; the UO Gump offers a larger text region",
            "activation":"DOS opening brings Finnigan to the player; this test walks to Finnigan",
            "dos_internal_flags":checked["original_save_state"], "dos_reconsideration":"not_compared"}


def compare_reentry(directory, trace, installation):
    checked = qualify(Path(directory), installation)
    retry = checked["same_session_reentry"]
    question, menu, _ = retry["observations"]
    hashes = [hashlib.sha256(label.encode()).hexdigest() for label in trace["retry_choices"]]
    if (checked["edition_source_sha256"] != trace["usecode_sha256"] or retry["status"] != "passed"
            or question["source_string_sha256"] != trace["reconsideration_text_sha256"]
            or menu["ordered_source_string_sha256"] != hashes):
        raise ValueError("Original DOS reconsideration or choice order differs from the UO restart")
    return {"status":"passed", "dos_reentry":"same_session", "uo_reentry":"after_server_restart",
            "dos_directory":str(Path(directory).resolve()), "question":question, "menu":menu,
            "uo_restored_flags":{n: trace["after_retry"][f"flag_{n}"] for n in (76,89,90)},
            "uo_subsequent_acceptance":"not_run"}
