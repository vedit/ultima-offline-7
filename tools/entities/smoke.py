"""Exercise source IDs on two isolated ModernUO boots against a staged private facet."""

import argparse
import hashlib
import json
import os
import shutil
import socket
import subprocess
import tempfile
import time
from pathlib import Path


def load(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def run(installation, facet, report_path):
    receipt = load(facet / "current.json")
    release = (facet / "releases" / receipt["build_id"]).resolve()
    if not release.is_relative_to((facet / "releases").resolve()):
        raise ValueError("Invalid facet release path")
    src = release / "server"
    if not (src / "Campaign/container.json").is_file():
        raise ValueError("Stage a facet with entity witnesses before running the replay")
    cache = installation / "Cache/EntitiesHost"
    dll = cache / "replay/EntityReplay.dll"
    if not dll.is_file():
        raise ValueError("Build replay/EntityReplay.csproj via build.ps1 -WithReplay")
    env = dict(os.environ, DOTNET_ROOT=str(installation / "Tools/dotnet"),
               DOTNET_ROOT_X64=str(installation / "Tools/dotnet"))
    with tempfile.TemporaryDirectory(prefix="restart-", dir=cache) as tmp:
        work = Path(tmp)
        server, state = work / "server", work / "state"
        shutil.copytree(src, server, ignore=shutil.ignore_patterns("Logs", "Backups", "Archives", "temp",
                                                                 "Saves", "before.json", "after.json", "replay-error.txt"))
        shutil.copyfile(dll, server / "Assemblies/EntityReplay.dll")
        assembly_list = server / "Data/assemblies.json"
        modules = load(assembly_list)
        if "U7EntitiesHost.dll" not in modules or "EntityReplay.dll" in modules:
            raise ValueError("Unexpected private server assembly list")
        write(assembly_list, [*modules, "EntityReplay.dll"])
        config_file = server / "Configuration/modernuo.json"
        config = load(config_file)
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            config["listeners"] = [f"127.0.0.1:{listener.getsockname()[1]}"]
        config["settings"].update({"world.savePath": str(state / "world"), "autosave.enabled": "False",
                                   "autoArchive.archivePath": str(state / "archives"),
                                   "autoArchive.backupPath": str(state / "backups")})
        write(config_file, config)
        for phase in ("save", "reload"):
            log = work / (phase + ".log")
            with log.open("w", encoding="utf-8") as stream:
                process = subprocess.Popen([str(server / "ModernUO.exe")], cwd=server, env=env,
                                           stdin=subprocess.DEVNULL, stdout=stream, stderr=subprocess.STDOUT,
                                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                try:
                    deadline = time.monotonic() + 90
                    while time.monotonic() < deadline:
                        fail = server / "replay-error.txt"
                        if fail.exists():
                            raise ValueError(fail.read_text())
                        if phase == "reload" and (server / "after.json").exists():
                            break
                        registry = state / "world/UltimaOfflineEntities/UltimaOfflineEntities.bin"
                        if phase == "save" and registry.is_file() and (server / "before.json").is_file():
                            if "Writing world save snapshot done" in log.read_text(errors="replace"):
                                break
                        if process.poll() is not None:
                            raise ValueError(f"Server exited during {phase}: " + log.read_text(errors="replace")[-2600:])
                        time.sleep(0.15)
                    else:
                        raise ValueError(f"Timed out during {phase}: " + log.read_text(errors="replace")[-2600:])
                finally:
                    if process.poll() is None:
                        process.terminate()
                    process.wait(timeout=15)
        before, after = load(server / "before.json"), load(server / "after.json")
        if before != after:
            raise ValueError("Restart did not preserve the first boot's observation")
        report = {"schema": 1, "status": "passed", "restarted": True, "scope": "server-side entity replay",
                  "client_gameplay": "not_run", "facet_build": receipt["build_id"],
                  "host_sha256": hashlib.sha256((server / "Assemblies/U7EntitiesHost.dll").read_bytes()).hexdigest(),
                  "before": before, "after": after}
        write(report_path, report)
        return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--installation", type=Path, required=True)
    parser.add_argument("--facet", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    result = run(args.installation.resolve(), args.facet.resolve(), args.report)
    print(f"Two boots verified {result['after']['liveCount']} active campaign entities.")
