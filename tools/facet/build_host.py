"""Build opt-in campaign hooks in a private copy of pinned ModernUO."""
import argparse
import hashlib
import os
from pathlib import Path
import subprocess

PIN = "1c63a13b23ef53cab18032d19d870d13b2a85f4a"
CONTENT = "Projects/UOContent/"
STARTS = CONTENT + "Engines/Character Creation/CharacterCreation.cs"
PROMPT = CONTENT + "Misc/AccountPrompt.cs"

HOOKS = {
    STARTS: ("        var pre6000ClientSupport = TileMatrix.Pre6000ClientSupport;",
             """        if (ServerConfiguration.GetSetting("ultimaOffline.privateFacet", false))
        {
            int x = ServerConfiguration.GetSetting("ultimaOffline.startX", -1);
            int y = ServerConfiguration.GetSetting("ultimaOffline.startY", -1);
            int z = ServerConfiguration.GetSetting("ultimaOffline.startZ", 0);
            if (x < 0 || y < 0 || x >= Map.Felucca.Width || y >= Map.Felucca.Height)
                throw new InvalidOperationException("The private campaign start lies outside slot zero.");
            return [new CityInfo("Trinsic", "Black Gate", 1075076, x, y, z, Map.Felucca)];
        }
"""),
    PROMPT: ("        if (Accounts.Count == 0)",
             """        if (ServerConfiguration.GetSetting("ultimaOffline.privateFacet", false))
            return; // Private campaigns create a player through the normal local login.
"""),
    CONTENT + "Items/Weapons/BaseWeapon.cs": (
        "        if (Layer == Layer.OneHanded && layer == Layer.TwoHanded && item is not BaseShield &&",
        """        // Black Gate lets a party member carry currency in a free off hand.
        // Same-layer conflicts and genuinely two-handed weapons were checked above.
        if (Layer == Layer.OneHanded && layer == Layer.TwoHanded && item is Gold &&
            ServerConfiguration.GetSetting("ultimaOffline.privateFacet", false))
        {
            return false;
        }

"""),
}


def build(root):
    root = root.resolve()
    cache = root / "Cache/FacetHost"
    cache.mkdir(parents=True, exist_ok=True)
    src = cache / "ModernUO"
    if not src.exists():
        subprocess.run(["git", "clone", "--quiet", "--no-checkout", "--no-hardlinks",
                        str(root / "Tools/ModernUO"), str(src)], check=True)
        subprocess.run(["git", "-C", str(src), "checkout", "--quiet", "--detach", PIN], check=True)
    git = ["git", "-C", str(src)]
    if subprocess.check_output([*git, "rev-parse", "HEAD"], text=True).strip() != PIN:
        raise ValueError("Unexpected ModernUO revision in the facet build cache")
    # Only the opt-in patch may differ in this private checkout.
    changed = subprocess.check_output([*git, "diff", "--name-only", "HEAD"], text=True).splitlines()
    if set(changed) - HOOKS.keys():
        raise ValueError("Unexpected source changes in the private facet build checkout")
    for name, (anchor, snippet) in HOOKS.items():
        original = subprocess.check_output([*git, "show", f"HEAD:{name}"]).decode("utf-8-sig")
        if original.count(anchor) != 1:
            raise ValueError(f"Missing unique facet hook in {name}")
        patched = original.replace(anchor, snippet + anchor)
        path = src / name
        existing = path.read_text(encoding="utf-8-sig")
        if existing not in (original, patched):
            raise ValueError(f"Unexpected existing edit to {name}")
        if existing != patched:
            path.write_text(patched, encoding="utf-8", newline="\n")
    env = dict(os.environ, DOTNET_ROOT=str(root / "Tools/dotnet"), DOTNET_CLI_HOME=str(root / "Cache/Dotnet"),
               NUGET_PACKAGES=str(root / "Cache/NuGet"), NUGET_HTTP_CACHE_PATH=str(root / "Cache/NuGetHttp"),
               TEMP=str(root / "Cache/Temp"), TMP=str(root / "Cache/Temp"))
    with (cache / "build.log").open("w", encoding="utf-8") as log:
        subprocess.run([str(root / "Tools/dotnet/dotnet.exe"), "build", CONTENT + "UOContent.csproj",
                        "-c", "Release", "--source", env["NUGET_PACKAGES"], "-p:NuGetAudit=false", "-v:q"],
                       cwd=src, env=env, stdout=log, stderr=subprocess.STDOUT, check=True)
    assembly = src / "Distribution/Assemblies/UOContent.dll"
    loader_project = Path(__file__).with_name("FacetVerify.csproj").resolve()
    subprocess.run([str(root / "Tools/dotnet/dotnet.exe"), "build", str(loader_project), "-c", "Release",
                    "-o", str(cache / "readback"), "--source", env["NUGET_PACKAGES"], "-p:NuGetAudit=false",
                    "-p:Libraries=" + str(root / "Cache/Readback/bin"),
                    "-p:BaseIntermediateOutputPath=" + str(cache / "readback-obj") + os.sep, "-v:q"],
                   cwd=cache, env=env, check=True)
    print(f"{assembly} {hashlib.sha256(assembly.read_bytes()).hexdigest()}")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--installation", type=Path, required=True)
    build(p.parse_args().installation)
