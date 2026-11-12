"""Capture a rendered frame or take one ordinary walking step in a visual test session."""
import argparse
import hashlib
import json
import msvcrt
import os
from pathlib import Path
import secrets
import struct
import subprocess
import time


def install(root, client, state):
    plugin = client / "Data/Plugins/U7Visual.dll"
    plugin.parent.mkdir(parents=True, exist_ok=True)
    (state / "visual").mkdir()
    subprocess.run([root/"Tools/w64devkit/bin/gcc.exe", "-std=c11", "-m64", "-O2", "-shared",
                    "-Wall", "-Wextra", "-Werror", "-Wl,--no-insert-timestamp", "-o", plugin,
                    Path(__file__).with_name("visual.c")], check=True,
                   env={**os.environ,"TMP":str(root/"Cache/Temp"),"TEMP":str(root/"Cache/Temp")})
    return plugin


def shots(folder):
    return {p:(p.stat().st_mtime_ns,p.stat().st_size) for p in folder.glob("screenshot_*.png")}


def check_pixels(path):
    # Use the Windows image decoder to detect unreadable or uniform captures.
    script = """
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Drawing
$bitmap = [Drawing.Bitmap]::new($env:U7UO_FRAME_FILE)
try {
    $colors = [Collections.Generic.HashSet[int]]::new()
    $dx = [Math]::Max(1, [int]($bitmap.Width / 96))
    $dy = [Math]::Max(1, [int]($bitmap.Height / 96))
    for ($y=0; $y -lt $bitmap.Height; $y+=$dy) {
        for ($x=0; $x -lt $bitmap.Width; $x+=$dx) {
            [void]$colors.Add($bitmap.GetPixel($x,$y).ToArgb())
        }
    }
    Write-Output $colors.Count
} finally { $bitmap.Dispose() }
"""
    count=int(subprocess.check_output(["powershell.exe","-NoProfile","-NonInteractive","-Command",script],
              env={**os.environ,"U7UO_FRAME_FILE":str(path)},text=True,timeout=15).strip())
    if count<2:
        raise ValueError("The game rendered a uniform image")
    return count


def command(session, verb, direction=0, *, frame=None, point=None):
    entry=json.loads((session/"entry.json").read_bytes())
    channel=session/"state/visual"
    if (Path(entry["scratch"]).resolve()!=session.resolve() or not entry.get("visual_plugin_sha256")
            or hashlib.sha256((session/"client/Data/Plugins/U7Visual.dll").read_bytes()).hexdigest()!=entry["visual_plugin_sha256"]):
        raise ValueError("Expected a disposable client with the verified visual plugin")
    folder=session/"client/Data/Client/Screenshots"
    with (channel/"lock").open("a+b") as lock:
        lock.seek(0)
        msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
        request=channel/"request"
        if request.exists() or (channel/"in-progress").exists():
            raise ValueError("A previous visual action is outstanding")
        token=secrets.token_hex(16)
        before=shots(folder) if verb=="capture" else {}
        operands=[direction]
        if verb=="click":
            if frame is None or len(frame)!=32 or any(c not in "0123456789abcdef" for c in frame):
                raise ValueError("A click requires a frame ID from this live client")
            src=json.loads((channel/(frame+".json")).read_bytes())
            if src["client_pid"]!=entry["client_pid"] or src["build_id"]!=entry["build_id"] or src["action"]!="capture":
                raise ValueError("The selected frame belongs to a different client")
            if not (0<=point[0]<src["size"][0] and 0<=point[1]<src["size"][1]):
                raise ValueError("Point outside the rendered PNG")
            if (channel/"reply").read_text(encoding="ascii").split()[0]!=frame:
                raise ValueError("Capture a new frame after the previous action")
            operands.extend([*point,*src["size"]])
        line=" ".join([token,verb,*map(str,operands)])+"\n"
        temp=channel/(token+".tmp")
        temp.write_text(line,encoding="ascii")
        temp.rename(request)
        until=time.monotonic()+12
        while time.monotonic()<until:
            reply=channel/"reply"
            if reply.is_file():
                parts=reply.read_text(encoding="ascii").split()
                if len(parts)==6 and parts[0]==token:
                    _,status,pid,*xyz=parts
                    valid={"capture":("capture-requested","capture-menu"),
                           "step":("move-requested",),"click":("click-requested","click-menu")}
                    if int(pid)!=entry["client_pid"] or status not in valid[verb]:
                        raise ValueError(f"Client action {token} returned {status} from PID {pid}")
                    result={"request":token,"action":verb,"client_pid":int(pid),
                            "position":None if status.endswith("-menu") else list(map(int,xyz)),
                            "build_id":entry["build_id"]}
                    if verb=="step":
                        result["direction"]=direction
                    if verb=="click":
                        result.update(frame=frame,point=point,button_action={1:"left",2:"double",3:"right"}[direction])
                    if verb=="capture":
                        current=shots(folder)
                        changed=[p for p in current if current[p]!=before.get(p)]
                        if len(changed)!=1:
                            raise ValueError("The stock renderer did not write one fresh PNG")
                        png=changed[0].read_bytes()
                        if (png[:16]!=b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR" or png[-8:-4]!=b"IEND"):
                            raise ValueError("Incomplete renderer PNG")
                        dest=channel/(token+".png")
                        dest.write_bytes(png)
                        result.update(image=str(dest),size=struct.unpack_from(">II",png,16),
                                      sha256=hashlib.sha256(png).hexdigest(),sampled_colors=check_pixels(dest))
                    (channel/(token+".json")).write_text(json.dumps(result,indent=2)+"\n",encoding="utf-8")
                    return result
            time.sleep(0.05)
        # A disconnected client must not execute this command at a later login.
        try:
            request.unlink()
        except FileNotFoundError:
            pass
        raise TimeoutError(f"No completion for visual action {token}. Inspect the client before repeating it.")


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("session",type=Path)
    sub=parser.add_subparsers(dest="action",required=True)
    sub.add_parser("capture")
    sub.add_parser("step").add_argument("direction",type=int,choices=range(8))
    click=sub.add_parser("click")
    click.add_argument("frame",help="Request ID of the latest capture")
    click.add_argument("point",type=int,nargs=2,metavar=("X","Y"))
    click.add_argument("--button",choices=("left","double","right"),default="left")
    args=parser.parse_args()
    direction=getattr(args,"direction",0) if args.action!="click" else {"left":1,"double":2,"right":3}[args.button]
    print(json.dumps(command(args.session,args.action,direction,frame=getattr(args,"frame",None),
                             point=getattr(args,"point",None)),indent=2))
