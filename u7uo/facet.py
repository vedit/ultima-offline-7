"""Stage and start a private slot-zero development facet on the provisioned Windows host."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import socket
import struct
import subprocess
import sys
import tempfile
import time
import zipfile


from .terrain import UNRESOLVED_LAND as VOID
from . import fences

WIDTH, HEIGHT = 7168, 4096
BLOCKS = WIDTH // 8 * (HEIGHT // 8)
EMPTY_INDEX = struct.pack("<iii", -1, 0, 0)
CLASSIC_ZIP_HASH = "cb556a076ba7dfa6a200255e36f57a236813801cdec5e106226117dcde536473"
LAYOUTS = "7168,4096;7168,4096;2304,1600;2560,2048;1448,1448;1280,4096"
SHADOW = re.compile(r"(?:map0x?(?:legacymul\.uop|\.mul)|(?:staidx|statics)0x?\.mul|(?:mapdifl?|stadif[il]?)0\.mul|verdata\.mul)$", re.I)


def _read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _write(path, data):
    path.write_text(json.dumps(data, sort_keys=True, indent=2) + "\n", encoding="utf-8", newline="\n")


def _hash(path):
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def _safe_child(root, relative):
    path = (root / relative).resolve()
    if Path(relative).is_absolute() or not path.is_relative_to(root.resolve()):
        raise ValueError(f"Invalid relative path: {relative}")
    return path


def stamp_blocks(sample, target, meta, width=WIDTH, height=HEIGHT):
    """Place source-aligned 8×8 blocks into a column-major padded UO facet."""
    sw, sh = meta["width"], meta["height"]
    sx, sy = meta["source_origin"]
    if min(width, height, sw, sh) <= 0 or any(v % 8 for v in (width, height, sw, sh, sx, sy)):
        raise ValueError("Facet dimensions and origin must be block aligned")
    if sx < 0 or sy < 0 or sx + sw > min(width, 3072) or sy + sh > min(height, 3072):
        raise ValueError("Sample is outside Black Gate or the facet")
    map_data = (sample / "map0.mul").read_bytes()
    index = (sample / "staidx0.mul").read_bytes()
    statics = (sample / "statics0.mul").read_bytes()
    sample_blocks = sw * sh // 64
    if len(map_data) != 196 * sample_blocks or len(index) != 12 * sample_blocks:
        raise ValueError("Sample block count disagrees with its resources")
    for offset, size, _ in struct.iter_unpack("<III", index):
        if offset == 0xffffffff and size in (0, 0xffffffff):
            continue
        if size % 7 or size // 7 > 1024 or offset + size > len(statics):
            raise ValueError("Invalid or overfull sample static block")
        for _, x, y, _, _ in struct.iter_unpack("<HBBbH", statics[offset:offset + size]):
            if max(x, y) > 7:
                raise ValueError("Static coordinate outside its block")
    bh, sbh = height // 8, sh // 8
    void_block = bytes(4) + struct.pack("<Hb", VOID, 0) * 64
    pad_map, pad_index = void_block * bh, EMPTY_INDEX * bh
    ox, oy = sx // 8, sy // 8
    with (target / "map0.mul").open("wb") as maps, (target / "staidx0.mul").open("wb") as idx:
        for x in range(width // 8):
            if not ox <= x < ox + sw // 8:
                maps.write(pad_map)
                idx.write(pad_index)
                continue
            a = (x - ox) * sbh
            maps.write(pad_map[:oy * 196] + map_data[a * 196:(a + sbh) * 196] + pad_map[(oy + sbh) * 196:])
            idx.write(pad_index[:oy * 12] + index[a * 12:(a + sbh) * 12] + pad_index[(oy + sbh) * 12:])
    (target / "statics0.mul").write_bytes(statics)


def _stamp_extras(sample, target, meta, main):
    """Stamp a disjoint second patch and rebase its optional static record offsets."""
    ox, oy = meta["source_origin"]
    w, h = meta["width"], meta["height"]
    bx, by = main["source_origin"]
    if not (ox + w <= bx or bx + main["width"] <= ox or oy + h <= by or by + main["height"] <= oy):
        raise ValueError("Converted terrain patches overlap")
    if min(w,h) <= 0 or min(ox,oy) < 0 or max(ox+w,oy+h) > 3072 or any(n % 8 for n in (ox,oy,w,h)):
        raise ValueError("Additional terrain patch is outside the aligned Black Gate world")
    land = (sample / "map0.mul").read_bytes()
    idx = (sample / "staidx0.mul").read_bytes()
    static = (sample / "statics0.mul").read_bytes()
    blocks = w*h//64
    if len(land) != blocks*196 or len(idx) != blocks*12:
        raise ValueError("Additional terrain resources disagree with source dimensions")
    with (target/"statics0.mul").open("ab") as sf:
        base = sf.tell()
        fixed = bytearray()
        for offset, size, extra in struct.iter_unpack("<III", idx):
            if offset == 0xffffffff and size in (0, 0xffffffff):
                fixed.extend(EMPTY_INDEX)
            else:
                if size%7 or size//7 > 1024 or offset+size > len(static):
                    raise ValueError("Invalid or overfull additional static block")
                if any(max(x, y) > 7 for _,x,y,_,_ in struct.iter_unpack("<HBBbH", static[offset:offset+size])):
                    raise ValueError("Static coordinate outside its block")
                fixed.extend(struct.pack("<III", offset+base, size, extra))
        sf.write(static)
    with (target/"map0.mul").open("r+b") as maps, (target/"staidx0.mul").open("r+b") as indices:
        column = h//8
        for x in range(w//8):
            block = (ox//8+x)*(HEIGHT//8)+oy//8
            maps.seek(block*196)
            maps.write(land[x*column*196:(x+1)*column*196])
            indices.seek(block*12)
            indices.write(fixed[x*column*12:(x+1)*column*12])


def stamp_world(proof, target, patches):
    """Fill every qualified source block outside the fully interactive quest patches."""
    from .world_statics import read_native_blocks
    reference = target.parent/"world-reference"
    reference.mkdir()
    for src,dst in (("world-land.idx","land.idx"),("world-land.mul","land.mul"),
                    ("world-statics/staidx0.mul","staidx0.mul"),("world-statics/statics0.mul","statics0.mul")):
        shutil.copyfile(proof/src,reference/dst)
    index = (reference/"land.idx").read_bytes()
    pool = (reference/"land.mul").read_bytes()
    if len(index)!=4*384**2 or len(pool)%196:
        raise ValueError("Invalid world land pool or index")
    data,blocks = read_native_blocks(reference)
    protected = set()
    for patch in patches:
        ox,oy = patch["source_origin"]
        protected.update((x,y) for x in range(ox//8,(ox+patch["width"])//8)
                         for y in range(oy//8,(oy+patch["height"])//8))
    native_index = bytearray((target/"staidx0.mul").read_bytes())
    land_file = target/"map0.mul"
    native_land = bytearray(land_file.read_bytes())
    padded_cells = {}
    for offset in range(0,len(pool),196):
        cells = struct.iter_unpack("<Hb",pool[offset+4:offset+196])
        padding = {i for i,(land,_) in enumerate(cells) if land==VOID}
        if padding:
            padded_cells[offset//196] = padding
    stamped = components = omitted = mixed = mixed_padding = 0
    with (target/"statics0.mul").open("ab") as statics:
        for i,(entry,) in enumerate(struct.iter_unpack("<i",index)):
            bx,by = divmod(i,384)
            if (bx,by) in protected:
                continue
            if entry == -1:
                omitted += 1
                continue
            if not 0<=entry<len(pool)//196:
                raise ValueError(f"Invalid source land index at {bx},{by}")
            slot = bx*(HEIGHT//8)+by
            native_land[slot*196:(slot+1)*196] = pool[entry*196:(entry+1)*196]
            padding = padded_cells.get(entry)
            if padding:
                mixed += 1
                mixed_padding += len(padding)
            if i in blocks:
                start,count = blocks[i]
                records = data[start:start+count*7]
                if padding:
                    records = b"".join(records[p:p+7] for p in range(0,len(records),7)
                                       if records[p+3]*8+records[p+2] not in padding)
                if records:
                    struct.pack_into("<iii",native_index,slot*12,statics.tell(),len(records),0)
                    statics.write(records)
                    components += len(records)//7
            stamped += 1
    land_file.write_bytes(native_land)
    (target/"staidx0.mul").write_bytes(native_index)
    return {"additional_land_blocks":stamped,"additional_static_components":components,
            "additional_land_cells":stamped*64-mixed_padding,"mixed_blocks":mixed,
            "mixed_block_padding_cells":mixed_padding,
            "quest_patch_blocks":len(protected),"unresolved_blocks":omitted}


def _combined_sample(main, extra):
    if not extra:
        return main
    result = dict(main)
    dx = extra["source_origin"][0] - main["source_origin"][0]
    dy = extra["source_origin"][1] - main["source_origin"][1]
    for key in ("cells", "statics"):
        result[key] = list(main.get(key, []))
        result[key].extend({**item, "x": item["x"] + dx, "y": item["y"] + dy} for item in extra.get(key, []))
    return result


def _copy_assets(root, target, receipt):
    source = root / "Assets/UO-Classic"
    for entry in receipt["installed_files"]:
        rel = entry["path"]
        leaf = Path(rel).name
        if SHADOW.fullmatch(leaf) or (leaf.lower().endswith(".exe") and leaf.lower() != "client.exe"):
            continue
        src, dst = _safe_child(source, rel), _safe_child(target, rel)
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dst)
        if _hash(dst) != entry["local_sha256"].lower():
            raise ValueError(f"Official asset changed since installation: {rel}")
    data = (target / "tiledata.mul").read_bytes()
    at = (VOID // 32) * 964 + 4 + (VOID % 32) * 30
    flags, _, name = struct.unpack_from("<QH20s", data, at)
    if not flags & 0x40 or name.rstrip(b"\0").lower() != b"void":
        raise ValueError("Target tiledata disagrees with the impassable void padding rule")


def _server(root, target, final, state, position, port, host, plugin, entities, proof, dialogue, portraits,
            music, opening):
    source = root / "Tools/ModernUO/Distribution"
    target.mkdir()
    for binary in source.iterdir():
        if binary.is_file() and binary.suffix.lower() in (".dll", ".exe", ".config", ".json"):
            shutil.copyfile(binary, target / binary.name)
    shutil.copytree(source / "Assemblies", target / "Assemblies")
    shutil.copyfile(host, target / "Assemblies/UOContent.dll")
    shutil.copytree(source / "Data", target / "Data",
                    ignore=shutil.ignore_patterns("Spawns", "Decoration", "Pathfinding", "regions.json", "teleporters.json"))
    for name in ("Spawns", "Decoration"):
        (target / "Data" / name).mkdir(exist_ok=True)
    for name in ("regions.json", "teleporters.json"):
        _write(target / "Data" / name, [])
    # Several stock systems need Internal and the named map definitions at boot.
    # Expansion selection, advertised starts, regions and the fresh world govern access.
    maps = _read(source / "Data/map-definitions.json")
    slot = next(m for m in maps if m["index"] == 0)
    if (slot["id"], slot["fileIndex"], slot["width"], slot["height"]) != (0, 0, WIDTH, HEIGHT):
        raise ValueError("Upstream slot zero definition changed")
    slot.update(season=0, rules="TrammelRules")
    _write(target / "Data/map-definitions.json", maps)
    (target / "Configuration").mkdir()
    expansion = _read(source / "Configuration/expansion.json")
    expansion["MapSelectionFlags"] = {k: k == "Felucca" for k in expansion["MapSelectionFlags"]}
    _write(target / "Configuration/expansion.json", expansion)
    settings = {
        "ultimaOffline.openingEgg": str(opening).lower(),
        "ultimaOffline.privateFacet": "true", "ultimaOffline.startX": str(position[0]),
        "ultimaOffline.startY": str(position[1]), "ultimaOffline.startZ": str(position[2]),
        "serverListing.address": "127.0.0.1", "serverListing.autoDetect": "false",
        # The pinned PingServer.Shutdown assumes its listener list was initialized.
        # Port zero reserves a separate ephemeral loopback socket without colliding with Hexen.
        "serverListing.serverName": "Black Gate Trinsic", "pingServer.enabled": "true", "pingServer.port": "0",
        "world.savePath": str(state / "world"), "autoArchive.backupPath": str(state / "backups"),
        "autoArchive.archivePath": str(state / "archives"), "pathfinding.prebakeMaps": "false",
        "accountHandler.enableAutoAccountCreation": "true", "uogateway.enabled": "false",
    }
    _write(target / "Configuration/modernuo.json", {"assemblyDirectories": ["./Assemblies"],
           "dataDirectories": [str(final / "assets")], "listeners": [f"127.0.0.1:{port}"], "settings": settings})
    modules = ["UOContent.dll"]
    game_files = []
    if plugin:
        for name, dst in [("U7UsecodeHost.dll", "Assemblies"), ("U7LuaHost.dll", "")]:
            shutil.copyfile(plugin / name, target / dst / name)
        modules.append("U7UsecodeHost.dll")
        game_files.extend(["script.json", "function.lua"])
    if entities:
        shutil.copyfile(entities, target / "Assemblies/U7EntitiesHost.dll")
        modules.append("U7EntitiesHost.dll")
        game_files.extend(["actor.json", "container.json"])
        if (proof/"world-live.json").is_file():
            game_files.append("world-live.json")
    if dialogue:
        shutil.copyfile(dialogue / "U7DialogueHost.dll", target / "Assemblies/U7DialogueHost.dll")
        shutil.copyfile(dialogue / "U7DialogueNative.dll", target / "U7DialogueNative.dll")
        modules.append("U7DialogueHost.dll")
        game_files.extend(["story-seed.json", "dialogue.lua", "dialogue.json"])
        if (proof/"swamp.json").is_file():
            game_files.extend(["swamp.json","swamp-fields.bin"])
    if game_files:
        _write(target / "Data/assemblies.json", modules)
        data = target / "Campaign"
        data.mkdir()
        for name in game_files:
            shutil.copyfile(proof / name, data / name)
        if dialogue:
            seed_path = data / "story-seed.json"
            seed = _read(seed_path)
            if "gate_query_bounds" in seed and (proof / "world-ireg").is_dir():
                fences.town_fixtures(proof, target.parent/"assets", root/"Assets/UltimaVII-Steam/STATIC", seed)
                _write(seed_path, seed)
            if (proof/"campaign-usecode.json").is_file():
                from .campaign_usecode import bind_world_functions
                bind_world_functions(proof,data)
            frames = {f"{p['shape']}:{p['frame']}": p["gump_id"] for p in [portraits, *portraits["companions"]]}
            _write(data / "portraits.json", {"schema": 1, "frames": frames})
        if music:
            shutil.copyfile(proof / "music/music.json", data / "music.json")
        (data / "edition.txt").write_text(_read(proof / "manifest.json")["source_edition"], encoding="utf-8")


def _client(root, target, assets, state, port):
    archive = root / "Downloads/ClassicUO-win-x64-release.zip"
    if _hash(archive) != CLASSIC_ZIP_HASH:
        raise ValueError("ClassicUO release archive has changed")
    target.mkdir()
    with zipfile.ZipFile(archive) as zipfile_:
        for item in zipfile_.infolist():
            if item.is_dir() or item.filename.lower().endswith(".pdb"):
                continue
            dest = _safe_child(target, item.filename)
            dest.parent.mkdir(parents=True, exist_ok=True)
            with zipfile_.open(item) as src, dest.open("wb") as dst:
                shutil.copyfileobj(src, dst)
    _write(target / "settings.json", {"ip": "127.0.0.1", "port": port, "clientversion": "7.0.118.46",
           "ultimaonlinedirectory": str(assets), "profilespath": str(state / "profiles"),
           "maps_layouts": LAYOUTS, "use_verdata": False, "saveaccount": False, "autologin": False, "plugins": []})


def _paths(installation, output_dir):
    root, out = Path(installation).resolve(), Path(output_dir).resolve()
    if not out.is_relative_to(root / "Builds") or out in (root / "Builds", root / "Builds/ModernUO"):
        raise ValueError("Choose a dedicated facet directory inside the installation Builds directory")
    if out.is_relative_to(root / "Builds/ModernUO"):
        raise ValueError("Facet may not be staged within the stock server")
    return root, out


def stage_facet(installation, proof_dir, output_dir, *, port=2594, opening=False):
    root, out = _paths(installation, output_dir)
    proof = Path(proof_dir).resolve()
    if out.is_relative_to(proof) or proof.is_relative_to(out):
        raise ValueError("Facet output and proof directories overlap")
    if not 1024 <= port <= 65535 or port in (2593, 12000):
        raise ValueError("Choose a separate unprivileged loopback game port")
    out.mkdir(parents=True, exist_ok=True)
    if any(p.name not in ("current.json", "releases") and not p.name.startswith((".stage-", ".pointer-")) for p in out.iterdir()):
        raise ValueError("Facet staging requires an empty or existing dedicated output")
    receipt = root / "Evidence/uo-asset-check.json"
    from .build import check_release
    from . import gump_overlay,shore
    from .uo import inspect_uo
    manifest = check_release(proof, proof.name)
    features = manifest.get("features", [])
    if opening and not {"opening-music", "opening-portraits", "dialogue"}.issubset(features):
        raise ValueError("The opening needs a compiler build with the original score, portraits and dialogue")
    if inspect_uo(root / "Assets/UO-Classic") != _read(proof / "inputs.json")["uo"]:
        raise ValueError("The installed UO source selection differs from the verified proof's input resources")
    host = root / "Cache/FacetHost/ModernUO/Distribution/Assemblies/UOContent.dll"
    if not host.is_file():
        raise ValueError("Missing private UOContent.dll. Build it with tools/facet/build_host.py --installation <root>.")
    plugin = root / "Cache/UsecodeHost"
    if not (plugin / "U7UsecodeHost.dll").exists() and not (plugin / "U7LuaHost.dll").exists():
        plugin = None
    entities = root / "Cache/EntitiesHost/U7EntitiesHost.dll"
    if not entities.is_file():
        entities = None
    if "regional-live-items" in features and entities is None:
        raise ValueError("Regional item conversion requires the private entity host.")
    dialogue = root / "Cache/DialogueHost" if "dialogue" in features else None
    dialogue_dlls = ("U7DialogueHost.dll", "U7DialogueNative.dll")
    if dialogue and (not entities or not all((dialogue / name).is_file() for name in dialogue_dlls)):
        raise ValueError("Dialogue requires the entity and dialogue hosts. Run tools/entities/build.ps1 and tools/dialoguehost/build.ps1.")
    chosen = proof / "walking" if (proof / "walking/terrain.json").is_file() else proof
    terrain = _read(chosen / "terrain.json")
    extra = _read(proof / "water/terrain.json") if (proof / "water/terrain.json").is_file() else None
    position = _read(proof / "terrain.json")["avatar"]["position"]
    ox, oy = terrain["source_origin"]
    if not (ox <= position[0] < ox + terrain["width"] and oy <= position[1] < oy + terrain["height"]):
        raise ValueError("Selected terrain excludes the source Avatar")
    identity = {"schema": 1, "tool": _hash(Path(__file__)), "gump_tool": _hash(Path(gump_overlay.__file__)),
                "port": port, "opening_egg": opening, "proof": _hash(proof / "manifest.json"),
                "sample": _hash(chosen / "terrain.json"), "water": _hash(proof / "water/terrain.json") if extra else None,
                "input_assets": _hash(receipt), "host": _hash(host),
                "entities": _hash(entities) if entities else None,
                "dialogue": {name: _hash(dialogue / name) for name in dialogue_dlls} if dialogue else None,
                "plugin": {p: _hash(plugin / p) for p in ("U7UsecodeHost.dll", "U7LuaHost.dll")} if plugin else None}
    if "campaign-usecode" in features:
        from . import campaign_usecode
        identity["campaign_linker"] = _hash(Path(campaign_usecode.__file__))
    if dialogue and (proof/"world-ireg").is_dir():
        identity["town_fixtures"] = _hash(Path(fences.__file__))
    if "shore-art" in features:
        identity["shore_tool"] = _hash(Path(shore.__file__))
    build_id = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
    release = out / "releases" / build_id
    if release.resolve() != release or (out / "current.json").resolve() != out / "current.json":
        raise ValueError("Facet storage must not redirect its release or current pointer")
    state_key = hashlib.sha256(str(out).casefold().encode()).hexdigest()[:16]
    state = root / "Saves/BlackGateFacet" / state_key / build_id
    (out / "releases").mkdir(exist_ok=True)
    if not release.exists():
        with tempfile.TemporaryDirectory(dir=out, prefix=".stage-") as scratch:
            staged = Path(scratch) / "payload"
            assets = staged / "assets"
            assets.mkdir(parents=True)
            inventory = _read(receipt)
            _copy_assets(root, assets, inventory)
            companions = [(n, proof / "portraits" / str(n)) for n in (1, 11)] if "opening-portraits" in features else []
            if "east-gate" in features:
                companions.append((14, proof / "portraits/14"))
            if "investigation-witnesses" in features:
                companions.extend((slot, proof / "portraits" / str(slot)) for slot in (2, 13))
            for face, frame in _read(proof / "manifest.json").get("additional_portrait_frames", []):
                companions.append((face, proof / "portraits" / str(face) / f"frame{frame}"))
            portrait = gump_overlay.stage_gump_overlay(root / "Assets/UO-Classic", assets, proof / "portrait", companions)
            from .music import CONFIG, TRACK, stage_music
            music = stage_music(proof / "music", assets) if "opening-music" in features else None
            stamp_blocks(chosen, assets, terrain)
            if extra:
                _stamp_extras(proof / "water", assets, extra, terrain)
            world = stamp_world(proof,assets,[m for m in (terrain,extra) if m]) if "world-statics" in features else None
            shores = None
            if "shore-art" in features:
                shores = shore.stage_shores(proof,assets)
                shutil.copyfile(proof/"shore-art.json",staged/"world-reference/shore-art.json")
            _server(root, staged / "server", release, state, position, port, host, plugin, entities, proof, dialogue,
                    portrait, music, opening)
            _client(root, staged / "client", release / "assets", state, port)
            _write(staged / "sample.json", _combined_sample(terrain, extra))
            tracks = ["assets/map0.mul", "assets/staidx0.mul", "assets/statics0.mul", "sample.json",
                      "client/ClassicUO.exe", "client/cuo.dll", "client/settings.json", "assets/gumpartLegacyMUL.uop",
                      "server/ModernUO.exe", "server/Server.dll", "server/Configuration/expansion.json",
                      "server/Assemblies/UOContent.dll", "server/Data/map-definitions.json",
                      "server/Data/regions.json", "server/Data/teleporters.json", "server/Data/assemblies.json"]
            if plugin:
                tracks.extend(["server/Assemblies/U7UsecodeHost.dll", "server/U7LuaHost.dll",
                               "server/Campaign/function.lua", "server/Campaign/script.json", "server/Campaign/edition.txt"])
            if entities:
                tracks.extend(["server/Assemblies/U7EntitiesHost.dll","server/Campaign/actor.json","server/Campaign/container.json"])
                if "regional-live-items" in features:
                    tracks.append("server/Campaign/world-live.json")
            if dialogue:
                if "town_fixtures" in identity:
                    tracks.extend(["assets/artLegacyMUL.uop","assets/tiledata.mul"])
                tracks.extend(["server/Assemblies/U7DialogueHost.dll", "server/U7DialogueNative.dll",
                               "server/Campaign/story-seed.json", "server/Campaign/dialogue.lua", "server/Campaign/dialogue.json",
                               "server/Campaign/portraits.json", "server/Campaign/edition.txt"])
                if "swamp" in features:
                    tracks.extend(["server/Campaign/swamp.json","server/Campaign/swamp-fields.bin"])
            if music:
                tracks.extend(["server/Campaign/music.json", "assets/" + CONFIG, "assets/" + TRACK])
            if shores:
                tracks.extend(["assets/"+name for name in (shore.ARCHIVE,"tiledata.mul","radarcol.mul")])
            copied_hashes = {"assets/" + item["path"]:item["local_sha256"].lower() for item in inventory["installed_files"]
                             if (assets / item["path"]).is_file() and not SHADOW.fullmatch(Path(item["path"]).name)}
            report = {"build_id": build_id, "kind": "private-slot-zero-development", "state": str(state),
                      "port": port, "slot": 0, "width": WIDTH, "height": HEIGHT, "season": 0, "rules": "TrammelRules",
                      "start": position, "source_origin": [ox, oy], "sample_size": [terrain["width"], terrain["height"]],
                      "areas": [{"origin": m["source_origin"], "size": [m["width"], m["height"]]} for m in (terrain,extra) if m],
                      "generated_ground_cells": sum(m["width"] * m["height"] for m in (terrain,extra) if m), "pad_land_id": VOID,
                      "files": {**copied_hashes, **{name: _hash(staged / name) for name in tracks}},
                      "portrait": portrait, "music": music, "inputs": identity,
                      "source_release": str(proof)}
            if world:
                report["world_geometry"] = world
                report["generated_ground_cells"] += world["additional_land_cells"]
                for file in sorted((staged/"world-reference").iterdir()):
                    report["files"]["world-reference/"+file.name] = _hash(file)
            if shores:
                report["shore_art"] = shores
            _write(staged / "facet.json", report)
            try:
                staged.rename(release)
            except FileExistsError:
                pass
    report = _read(release / "facet.json")
    _verify(root, release, report)
    loaders = _readback(root, release)
    with tempfile.NamedTemporaryFile(mode="w", dir=out, prefix=".pointer-", delete=False) as temp:
        json.dump({"kind": "private-slot-zero-development", "build_id": build_id,
                   "facet_sha256": _hash(release / "facet.json")}, temp)
    os.replace(temp.name, out / "current.json")
    return {**report, "release": str(release), "loaders": loaders}


def _verify(root, release, report):
    for name, digest in report["files"].items():
        if _hash(_safe_child(release, name)) != digest:
            raise ValueError(f"Private facet file changed: {name}")
    server = _read(release / "server/Configuration/modernuo.json")
    client = _read(release / "client/settings.json")
    if (server["listeners"] != [f"127.0.0.1:{report['port']}"] or
            server["dataDirectories"] != [str(release / "assets")] or
            server["settings"]["world.savePath"] != str(Path(report["state"]) / "world") or
            client["ip"] != "127.0.0.1" or client["port"] != report["port"] or
            client["ultimaonlinedirectory"] != str(release / "assets")):
        raise ValueError("Private facet configuration changed")
    if any(SHADOW.fullmatch(p.name) and p.name.lower() not in ("map0.mul", "staidx0.mul", "statics0.mul")
           for p in (release / "assets").iterdir()):
        raise ValueError("Private slot zero contains a shadow or patch file")


def _active(root, out):
    current = _read(out / "current.json")
    key = current["build_id"]
    if current.get("kind") != "private-slot-zero-development" or not re.fullmatch(r"[0-9a-f]{64}", key):
        raise ValueError("Expected a private facet current pointer")
    r = _safe_child(out / "releases", key)
    if _hash(r / "facet.json") != current["facet_sha256"]:
        raise ValueError("Facet manifest differs from the active pointer")
    rep = _read(r / "facet.json")
    if rep["build_id"] != key or not Path(rep["state"]).resolve().is_relative_to(root / "Saves/BlackGateFacet"):
        raise ValueError("Invalid save path or release identity in facet manifest")
    _verify(root, r, rep)
    return r, rep


def facet_source(installation, campaign):
    """Resolve the exact compiler build used for the selected playable shard."""
    from .build import check_release
    root, out = _paths(installation, campaign)
    _, facet = _active(root, out)
    digest = facet["inputs"]["proof"]
    if not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise ValueError("Invalid compiler manifest fingerprint in the private facet")
    candidates = [Path(facet["source_release"])] if "source_release" in facet else []
    # Older facets record only the hash. Look in the provisioned and sibling
    # campaign directories, even if their active build has advanced.
    for parent in dict.fromkeys((out.parent, root / "Builds")):
        if parent.is_dir():
            candidates.extend(sorted(parent.glob(f"*/releases/{digest}")))
    for source in candidates:
        if source.name == digest and (source / "manifest.json").is_file():
            check_release(source, digest)
            return facet["build_id"], source
    raise ValueError(f"Original compiler release {digest} is missing. Restore its releases directory to explain this facet.")


def _readback(root, release):
    verifier = root / "Cache/FacetHost/readback/FacetVerify.dll"
    if not verifier.is_file():
        raise ValueError("Build the pinned facet host and FacetVerify.dll via tools/facet/build_host.py")
    probe = subprocess.run([root / "Tools/dotnet/dotnet.exe", verifier, release], text=True,
                           capture_output=True, timeout=90)
    if probe.returncode:
        raise ValueError("Full-size facet loader verification failed: " + (probe.stdout or probe.stderr)[-1800:])
    result = json.loads(probe.stdout)
    if result.get("status") != "passed":
        raise ValueError("Incomplete full-facet loader result")
    shores = _read(release/"facet.json").get("shore_art")
    if shores:
        observed = result.get("shore_art") or {}
        if observed.get("status")!="passed" or observed.get("frames")!=shores["frames"]:
            raise ValueError("Rebuild FacetVerify.dll to verify the private shore art")
    seed_file = release/"server/Campaign/story-seed.json"
    donors = _read(seed_file).get("fence_art",{}) if seed_file.is_file() else {}
    if donors and {k:v["donor"] for k,v in (result.get("fence_art") or {}).items()} != donors:
        raise ValueError("ClassicUO did not verify all private fence graphics")
    return result


def _port_owner(port):
    """Return the PID of the Windows TCP listener on this exact loopback address."""
    if os.name != "nt":
        raise ValueError("Private shard startup currently supports Windows")
    lines = subprocess.check_output(["netstat", "-ano", "-p", "TCP"], text=True).splitlines()
    for line in lines:
        fields = line.split()
        if len(fields) == 5 and fields[0] == "TCP" and fields[1] == f"127.0.0.1:{port}" and fields[2] == "0.0.0.0:0":
            return int(fields[4])
    return None


def _graceful_stop(process, executable):
    """Send Ctrl+C solely to the owned server's isolated console and wait for its teardown."""
    signal = Path(__file__).resolve().parents[1] / "tools/facet/stop_console.py"
    if process.poll() is not None:
        return
    try:
        subprocess.run([sys.executable, "-B", signal, str(process.pid), executable], check=True, timeout=12)
        if process.wait(timeout=15) != 0:
            raise ValueError("Private server returned an error during graceful shutdown")
    finally:
        if process.poll() is None:
            process.terminate()
            process.wait(timeout=15)


def _start(root, release, rep):
    state = Path(rep["state"])
    state.mkdir(parents=True, exist_ok=True)
    if _port_owner(rep["port"]) is not None:
        raise ValueError(f"Facet port {rep['port']} is already listening")
    env = dict(os.environ, DOTNET_ROOT=str(root / "Tools/dotnet"), DOTNET_ROOT_X64=str(root / "Tools/dotnet"))
    server = release / "server/ModernUO.exe"
    log = state / f"server-{time.time_ns()}.log"
    with log.open("wb") as stream:
        process = subprocess.Popen([server], cwd=server.parent, env=env, stdin=subprocess.DEVNULL,
                                   stdout=stream, stderr=subprocess.STDOUT, creationflags=subprocess.CREATE_NO_WINDOW)
    try:
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise ValueError("Facet server exited during startup: " + log.read_text(errors="replace")[-1600:])
            if _port_owner(rep["port"]) == process.pid:
                return process, log
            time.sleep(0.25)
        raise ValueError(f"Private facet readiness timed out. See {log}")
    except BaseException:
        if process.poll() is None:
            process.terminate()
            process.wait(timeout=15)
        raise


def probe_facet(installation, output_dir):
    root, out = _paths(installation, output_dir)
    release, rep = _active(root, out)
    loaders = _readback(root, release)
    # Probe a new copy of the server's disposable writable files with a distinct save root.
    # This must never start or terminate the player's running server or open their save.
    cache = root / "Cache/FacetHost"
    with tempfile.TemporaryDirectory(dir=cache, prefix="probe-") as tmp:
        sandbox = Path(tmp)
        shutil.copytree(release / "server", sandbox / "server",
                        ignore=shutil.ignore_patterns("Backups", "Archives", "Logs", "temp", "host-probe.json"))
        temp_state = sandbox / "state"
        config_file = sandbox / "server/Configuration/modernuo.json"
        config = _read(config_file)
        with socket.socket() as reservation:
            reservation.bind(("127.0.0.1", 0))
            port = reservation.getsockname()[1]
        config["listeners"] = [f"127.0.0.1:{port}"]
        for key, folder in (("world.savePath", "world"), ("autoArchive.backupPath", "backups"),
                            ("autoArchive.archivePath", "archives")):
            config["settings"][key] = str(temp_state / folder)
        _write(config_file, config)
        proc, log = _start(root, sandbox, {**rep, "state": str(temp_state), "port": port})
        try:
            text = log.read_text(errors="replace")
            if "Loading regions done (0 regions)" not in text or f"127.0.0.1:{port}" not in text:
                raise ValueError("Boot logs did not confirm zero stock regions and the private listener: " + text[-1000:])
            result = {"build_id": rep["build_id"], "loaders": loaders, "server_boot": "passed",
                      "map_slot": 0, "regions": 0, "configured_start": rep["start"],
                      "client_world_entry": "not_run", "probe_port": port}
            if rep["inputs"]["plugin"]:
                result["lua_host"] = _read(sandbox / "server/Campaign/host-probe.json")
                if result["lua_host"].get("status") != "passed":
                    raise ValueError("In-process Lua check did not pass")
            if rep["inputs"].get("entities") and (sandbox / "server/Campaign/entities-probe.json").is_file():
                result["entities_host"] = _read(sandbox / "server/Campaign/entities-probe.json")
        finally:
            _graceful_stop(proc, sandbox / "server/ModernUO.exe")
        text = log.read_text(errors="replace")
        if "Unhandled exception" in text or "Generating crash report" in text or "Shutting down" not in text:
            raise ValueError("Private server reported a shutdown error: " + text[-1600:])
        result["server_shutdown"] = "passed"
        return result


def verify_facet(installation, output_dir, *, structural_only=False, scenario="auto"):
    root, out = _paths(installation, output_dir)
    pointer = out / "current.json"
    initial_stat = pointer.stat()
    current = _read(pointer)
    release, report = _active(root, out)
    key = current["build_id"]
    if report["build_id"] != key:
        raise ValueError("Private facet selection changed before verification")
    result = {"build_id": key, "integrity": "passed", "player_replay": "not_run"}
    if scenario not in ("auto","journey","estate","swamp","void"):
        raise ValueError("Unknown private player scenario")
    if scenario != "auto":
        enabled=report["inputs"].get("opening_egg",False)
        if not report["inputs"].get("dialogue") or (scenario=="journey" and not enabled) or (scenario=="estate" and enabled):
            raise ValueError("The journey requires an opening-enabled dialogue facet; the estate scenario uses its direct-start facet.")
        result["scenario"]=scenario
    if structural_only:
        result.update(loaders="not_run", server_boot="not_run", server_shutdown="not_run",
                      client_world_entry="not_run")
    elif report["inputs"].get("dialogue"):
        from tools.facet.session import run
        result["loaders"] = _readback(root, release)
        opening = report["inputs"].get("opening_egg", False)
        seed_path = release / "server/Campaign/story-seed.json"
        stables = not opening and seed_path.is_file() and bool(_read(seed_path).get("investigation_items"))
        if scenario=="void":
            replay=run(root,out,False,void=True)
        elif scenario=="swamp":
            replay=run(root,out,False,swamp=True)
        elif scenario=="journey":
            replay = run(root,out,False,journey=True)
        elif scenario=="estate":
            replay = run(root,out,False,estate=True)
        elif opening:
            replay = run(root, out, False, opening=True)
        elif stables:
            replay = run(root, out, False, stables=True)
        else:
            replay = run(root, out, False, dialogue=True)
        if replay["build_id"] != key:
            raise ValueError("Player replay did not use the selected private facet")
        if scenario=="void":
            route = replay["walking"]
            mountain = "rejected_mountain_step" in route
            end = [496,2315,0] if mountain else [120,2544,0]
            denied = route["rejected_mountain_step" if mountain else "rejected_water_step"]
            if (replay["status"] != "passed" or route["saved_position_after_restart"] != end
                    or denied["packet"] != "0x21" or denied["position"] != end):
                raise ValueError("Original void movement, boundary collision or restart check failed")
        elif scenario=="swamp":
            if replay["status"]!="passed" or not replay["walking"]["reopened_poisoned"]:
                raise ValueError("Required swamp equipment, exposure and restart checks did not pass")
        elif opening:
            observed = replay["opening"]
            if replay["status"] != "passed" or not all(observed["checks"].values()):
                result.update(status="failed", diagnostic=observed["diagnostic"] or observed["saved_opening"]["Error"]
                              or "Incomplete original opening: " + ", ".join(k for k,v in observed["checks"].items() if not v))
        else:
            dialogue = replay["walking"]["dialogue"]
            if dialogue["status"] != "passed" or not dialogue["same_page_after_restart"]:
                raise ValueError("Required fresh-game dialogue and restart did not pass")
            if scenario=="estate" and replay["estate"]["status"]!="passed":
                result.update(status="failed",diagnostic=replay["estate"]["diagnostic"])
            elif replay["status"] != "passed":
                raise ValueError("Required ordinary player scenario did not pass")
            if stables and replay["stables"]["status"] != "passed":
                raise ValueError("Required stables investigation and key restoration did not pass")
        # Inspect the same disposable processes that exercised this scenario.
        for field in ("initial_log", "middle_log", "log"):
            if field not in replay:
                continue
            log = Path(replay[field]).read_text(errors="replace")
            if ("Loading regions done (0 regions)" not in log or f"127.0.0.1:{replay['port']}" not in log
                    or "Shutting down" not in log or "Unhandled exception" in log or "Generating crash report" in log):
                raise ValueError(f"Private player replay server boot/shutdown failed. See {replay[field]}")
        campaign = Path(replay["scratch"]) / "server/Campaign"
        if report["inputs"].get("plugin"):
            lua = _read(campaign / "host-probe.json")
            if lua.get("status") != "passed" or lua.get("process") != replay["server_pid"]:
                raise ValueError("In-process Lua check did not pass on the restarted server")
            result["lua_host"] = lua
        if report["inputs"].get("entities") and (campaign / "entities-probe.json").is_file():
            result["entities_host"] = _read(campaign / "entities-probe.json")
        result.update(player_replay=replay, server_boot="passed", server_shutdown="passed",
                      regions=0, map_slot=report["slot"], configured_start=report["start"],
                      probe_port=replay["port"], client_world_entry="not_run")
        edition = release / "server/Campaign/edition.txt"
        if edition.is_file():
            result["source_edition"] = edition.read_text(encoding="utf-8").strip()
    else:
        result.update(probe_facet(root, out))
    final_stat = pointer.stat()
    if (result["build_id"] != key or not os.path.samestat(initial_stat, final_stat)
            or initial_stat.st_mtime_ns != final_stat.st_mtime_ns or _read(pointer) != current):
        raise ValueError("Private facet selection changed during verification")
    return result


def play_facet(installation, output_dir, *, launch_client=True):
    root, out = _paths(installation, output_dir)
    release, rep = _active(root, out)
    state = Path(rep["state"])
    state.mkdir(parents=True, exist_ok=True)
    owner = state / "running.json"
    current = _port_owner(rep["port"])
    if current is not None:
        if not owner.exists() or _read(owner) != {"build_id": rep["build_id"], "server_pid": current}:
            raise ValueError("A different process owns the intended private facet port")
        server_pid = current
    else:
        proc, log = _start(root, release, rep)
        server_pid = proc.pid
        _write(owner, {"build_id": rep["build_id"], "server_pid": proc.pid})
    result = {"build_id": rep["build_id"], "server_pid": server_pid, "port": rep["port"], "state": str(state)}
    if launch_client:
        # The stock ClassicUO program rewrites settings on exit. Keep mutable settings with saves.
        settings_file = state / "client-settings.json"
        settings = _read(settings_file) if settings_file.is_file() else {}
        settings.update(_read(release / "client/settings.json"))
        _write(settings_file, settings)
        exe = release / "client/ClassicUO.exe"
        result["client_pid"] = subprocess.Popen([exe, "-settings", settings_file, "-profilespath", state / "profiles"],
                                                cwd=exe.parent).pid
    return result
