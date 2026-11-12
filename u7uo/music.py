"""Bind the original opening score to its private ClassicUO digital music entry."""

import hashlib
import json
import re
import shutil
import subprocess
from pathlib import Path

from .u7 import flex_directory


SCORE = "17c7cee4b9443d529931104ea6e1939348ae1d7175ae9d1488df342fba232cb9"
RECORDING = "f816257ce8650d4f228bf0a43ff18571632855772dc52ae6605f6c41f848e038"
CONFIG = "Music/Digital/Config.txt"
TRACK = "Music/Digital/u7bg035.mp3"


def produce_opening_music(u7, installation, output):
    records = []
    for bank in ("ADLIBMUS.DAT", "MT32MUS.DAT"):
        data = (u7 / "STATIC" / bank).read_bytes()
        offset, length = flex_directory(data)[35]
        digest = hashlib.sha256(data[offset:offset + length]).hexdigest()
        if digest != SCORE:
            raise ValueError(f"No qualified digital recording for {bank} score 35")
        records.append({"file": "STATIC/" + bank, "record": 35, "offset": offset, "size": length, "sha256": digest})
    recording = installation / "Tools/Exult/data/music/35bg.ogg"
    if hashlib.sha256(recording.read_bytes()).hexdigest() != RECORDING:
        raise ValueError("Exult digital Black Gate track 35 differs from the qualified recording")
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise ValueError("The opening music needs FFmpeg with libmp3lame on PATH")
    output.mkdir(parents=True, exist_ok=True)
    target = output / Path(TRACK).name
    subprocess.run([ffmpeg, "-nostdin", "-v", "error", "-i", str(recording), "-map_metadata", "-1",
                    "-fflags", "+bitexact", "-flags:a", "+bitexact", "-c:a", "libmp3lame", "-b:a", "128k",
                    "-y", str(target)], check=True, timeout=90)
    pcm = subprocess.run([ffmpeg, "-nostdin", "-v", "error", "-i", str(target), "-f", "s16le", "-ac", "2",
                          "-ar", "22050", "pipe:1"], capture_output=True, check=True, timeout=90).stdout
    if not any(pcm) or len(pcm) % 4:
        raise ValueError("Opening music yielded no valid stereo samples")
    cue = {"source_records": records, "client_slot": 200, "repeat": False, "path": TRACK,
           "recording": "Exult digital music / 35bg.ogg", "recording_sha256": RECORDING,
           "sha256": hashlib.sha256(target.read_bytes()).hexdigest(), "pcm_samples_per_channel": len(pcm) // 4,
           "pcm_sha256": hashlib.sha256(pcm).hexdigest(), "sample_rate": 22050, "channels": 2,
           "encoder": subprocess.check_output([ffmpeg, "-version"], text=True).splitlines()[0]}
    manifest = {"schema": 1, "tracks": {"35": cue}}
    (output / "music.json").write_bytes((json.dumps(manifest, sort_keys=True) + "\n").encode())
    return manifest


def stage_music(proof_music, assets):
    manifest = json.loads((proof_music / "music.json").read_bytes())
    cue = manifest["tracks"]["35"]
    if (cue["path"], cue["client_slot"], cue["repeat"]) != (TRACK, 200, False):
        raise ValueError("Unrecognized opening music profile")
    encoded = (proof_music / Path(TRACK).name).read_bytes()
    if hashlib.sha256(encoded).hexdigest() != cue["sha256"]:
        raise ValueError("Opening music digest changed")
    config = assets / CONFIG
    stock = config.read_bytes()
    if re.search(rb"(?m)^\s*200(?:,|\s|$)", stock):
        raise ValueError("Private music slot 200 is occupied")
    filename = Path(TRACK).name
    if any(p.name.casefold() == filename.casefold() for p in (assets / "Music").rglob("*.mp3")):
        raise ValueError("Private music filename collides with an existing track")
    (assets / TRACK).write_bytes(encoded)
    separator = b"" if stock.endswith(b"\n") else b"\r\n"
    config.write_bytes(stock + separator + b"200 u7bg035.mp3\r\n")
    return manifest
