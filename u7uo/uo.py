"""Identify the client's installed data profile and both engines' base-map choices."""

import hashlib
import json
from pathlib import Path


PROFILES = json.loads(Path(__file__).with_name("profiles.json").read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def inspect_uo(root: Path) -> dict:
    files = {}
    diagnostics = []
    if root.is_dir():
        for entry in root.iterdir():
            if entry.is_file():
                key = entry.name.casefold()
                if key in files:
                    diagnostics.append(f"Ambiguous resource name: {files[key].name}, {entry.name}")
                files[key] = entry
    pins = PROFILES["uo_files"]
    observed = {}
    missing = []
    different = []
    for name, digest in pins.items():
        path = files.get(name.casefold())
        if path is None:
            missing.append(name)
            continue
        observed[name] = {"bytes": path.stat().st_size, "sha256": sha256(path)}
        if observed[name]["sha256"] != digest:
            different.append(name)

    def present(name):
        path = files.get(name.casefold())
        return path.name if path else None

    mul = present("map0.mul")
    uop = present("map0LegacyMUL.uop")
    # These are the unpatched base-map choices for the pinned version.
    client = uop if present("MainMisc.uop") and uop else mul
    server = mul or uop
    if server != client:
        diagnostics.append(f"Conflicting base map: ClassicUO selects {client}, ModernUO selects {server}")
    if missing:
        diagnostics.append("Missing pinned UO resources: " + ", ".join(missing))
    if different:
        diagnostics.append("Unqualified resource fingerprints: " + ", ".join(different))
    version = PROFILES["uo_version"] if observed.get("client.exe", {}).get("sha256") == pins["client.exe"] else None
    return {
        "ready": not diagnostics,
        "status": "missing" if not files else "unqualified" if diagnostics else "recognized",
        "client_version": version,
        "resources": observed,
        "missing": missing,
        "different": different,
        "base_map": {"ClassicUO": client, "ModernUO": server},
        "installed_map_overrides": sorted(p.name for k, p in files.items() if
                                           k.startswith(("mapdif", "stadif", "map0x", "statics0x", "staidx0x"))),
        "diagnostics": diagnostics,
    }


def inspect_tools(installation: Path | None) -> dict:
    if installation is None:
        return {"status": "not_run", "tools": {}, "reason": "No --installation directory supplied"}
    results = {}
    for name, pin in PROFILES["tools"].items():
        path = installation / pin["file"]
        actual = sha256(path) if path.is_file() else None
        results[name] = {"status": "passed" if actual == pin["sha256"] else "failed",
                         "sha256": actual, "expected_sha256": pin["sha256"],
                         "version": pin.get("version"), "revision": pin.get("revision")}
    passed = all(result["status"] == "passed" for result in results.values())
    return {"status": "passed" if passed else "failed", "tools": results}
