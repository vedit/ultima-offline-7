# Build locally on Windows

Build the desktop Trinsic slice from source using your own game installations. No ModernUO server, private reference saves, maintainer release folder, Exult executable or Codex subscription is required.

Commands below are PowerShell, run from the repository root. Stop on failures. Prefer a short checkout path such as C:\src\ultima-offline-7.

## 1. Prerequisites

| Requirement | Tested baseline / official source |
| --- | --- |
| Windows x64 | Desktop client and native named-pipe bridge; other platforms are not qualified |
| Git | [Git for Windows](https://git-scm.com/downloads/win), including submodules |
| Python | 3.13 x64 tested; [python.org](https://www.python.org/downloads/windows/); requirements-dev.txt pins packages |
| .NET **SDK** | 10.0; [Microsoft guide](https://learn.microsoft.com/en-us/dotnet/core/install/windows). The runtime alone cannot build |
| Visual Studio Build Tools | Desktop development with C++, x64 MSVC tools and Windows SDK. VS 2019 tested; vswhere discovers installed versions |
| LLVM clang-cl | 18.1.8 tested; [LLVM](https://github.com/llvm/llvm-project/releases/tag/llvmorg-18.1.8) or VS [C++ Clang tools](https://learn.microsoft.com/en-us/cpp/build/clang-support-msbuild?view=msvc-170). MSVC cl is not a substitute |
| CMake / Ninja | CMake 3.20+ and Ninja available in the build environment; VS CMake tools can supply them |
| U7 data | English Black Gate **with Forge of Virtue**, Steam edition tested |
| UO data | Fully patched **Classic** client, 7.0.118.46 tested; Enhanced Client is unsupported |

Other editions/tool versions are not yet qualified. Do not silently substitute Serpent Isle, fan-patched usecode or another engine. Allow several GB for private data, checkouts and generated output, plus room for builds and repeated run folders.

Inventory first:

~~~powershell
git --version
py -0p
dotnet --list-sdks
# In an x64 Visual Studio developer prompt:
where.exe clang-cl
clang-cl --version
cmake --version
ninja --version
~~~

If clang-cl is installed but absent from PATH, add its actual bin directory to this shell. Do not rename cl.exe. Build scripts discover Visual Studio but cannot install missing components.

## 2. Private installation and Python

Clone once, then choose a private root outside both this checkout and your original game folders.

~~~powershell
git clone https://github.com/vedit/ultima-offline-7.git
Set-Location ultima-offline-7

$env:ULTIMA_OFFLINE_HOME = Join-Path $env:LOCALAPPDATA 'UltimaOffline7'
$installRoot = $env:ULTIMA_OFFLINE_HOME
$runtime = Join-Path $installRoot 'PoCs\ClassicUO-U7-Local'
New-Item -ItemType Directory -Force "$installRoot\Assets", "$installRoot\Tools", $runtime | Out-Null

py -3.13 -m venv "$installRoot\venv"
$python = "$installRoot\venv\Scripts\python.exe"
& $python -m pip install -r requirements-dev.txt
if ($LASTEXITCODE -ne 0) { throw 'Python dependency installation failed' }
~~~

The launcher uses that virtual environment automatically. No activation/global pip install is needed. For a custom root, set ULTIMA_OFFLINE_HOME in every new shell; optionally persist it for your user:

~~~powershell
[Environment]::SetEnvironmentVariable('ULTIMA_OFFLINE_HOME', $installRoot, 'User')
~~~

## 3. Copy your own game data

Use your Steam/GOG U7 installation and the official [UO Classic client](https://uo.com/client-download/). Let the official UO patcher finish before copying. See [agent discovery guidance](agent-install.md) for unknown installation paths.

Replace these paths with inspected folders. The U7 folder must directly contain STATIC and U7.CFG; a collection's outer folder is often one level too high.

~~~powershell
$u7Source = 'D:\YourGames\Ultima VII\ULTIMA7' # replace
$uoSource = 'D:\YourGames\Ultima Online Classic' # replace

foreach ($name in @('STATIC\INITGAME.DAT','STATIC\SHAPES.VGA','STATIC\USECODE',
                    'STATIC\INTROSND.DAT','STATIC\MAINSHP.FLX','STATIC\ENDSHAPE.FLX',
                    'STATIC\INTROPAL.DAT','U7.CFG')) {
    if (!(Test-Path -LiteralPath (Join-Path $u7Source $name))) { throw "Missing U7 input: $name" }
}
foreach ($name in @('artLegacyMUL.uop','tiledata.mul','hues.mul','radarcol.mul')) {
    if (!(Test-Path -LiteralPath (Join-Path $uoSource $name))) { throw "Missing UO input: $name" }
}
$u7Private = "$installRoot\Assets\UltimaVII-Steam"
$uoPrivate = "$installRoot\Assets\UO-Classic"
if ((Test-Path $u7Private) -or (Test-Path $uoPrivate)) {
    throw 'Private data already exists. Verify and reuse it; do not overwrite blindly.'
}
New-Item -ItemType Directory -Path $u7Private | Out-Null
Copy-Item -LiteralPath "$u7Source\STATIC" -Destination $u7Private -Recurse
Copy-Item -LiteralPath "$u7Source\U7.CFG" -Destination $u7Private
robocopy $uoSource $uoPrivate /E /COPY:DAT /R:1 /W:1 /NFL /NDL /NJH /NJS
if ($LASTEXITCODE -ge 8) { throw 'UO data copy failed' }
~~~

These checks identify required files, not full edition/content compatibility. Keep the entire UO data directory, including animations, gumps, fonts and sound. The legacy name UltimaVII-Steam is a path contract; it does not mean other editions were tested.

Never modify the originals. Saves go in separate run folders. Atlas readers require modern UOP art and tiledata. Missing map0.mul is normal: this build generates its own bounded U7 facet, without converting a retail UO map.

## 4. Pinned sources and overlays

[game/dependencies.json](../game/dependencies.json) records the source pins. Clone once into new directories. For later builds, verify revisions and reuse checkouts; do not reset another task's work.

~~~powershell
git clone --no-checkout https://github.com/ClassicUO/ClassicUO.git "$runtime\client"
if ($LASTEXITCODE -ne 0) { throw 'ClassicUO clone failed' }
git -C "$runtime\client" checkout --detach ee79d7ebc1cc0e53ff84fe6cae17d389e2737f93
if ($LASTEXITCODE -ne 0) { throw 'ClassicUO revision unavailable' }
git -C "$runtime\client" submodule update --init --recursive
if ($LASTEXITCODE -ne 0) { throw 'ClassicUO submodules failed' }

$nativeCheckout = "$installRoot\Tools\Ultima7_Decomp"
git clone --no-checkout https://github.com/Kitrinx/Ultima7_Decomp.git $nativeCheckout
if ($LASTEXITCODE -ne 0) { throw 'Native clone failed' }
git -C $nativeCheckout checkout --detach 872a613c718abf3a40cf94533887171bec8cfb24
if ($LASTEXITCODE -ne 0) { throw 'Native revision unavailable' }

git clone --branch v1.12.1 --depth 1 https://github.com/exult/exult.git "$installRoot\Tools\Exult-Source-v1.12.1"
if ($LASTEXITCODE -ne 0) { throw 'Exult metadata checkout failed' }

New-Item -ItemType Directory -Force "$runtime\native" | Out-Null
foreach ($part in @('Black Gate','third_party','assets')) {
    Copy-Item -LiteralPath "$nativeCheckout\ultima7-portable\$part" -Destination "$runtime\native" -Recurse
}
robocopy 'game\client\src' "$runtime\client\src" /E /COPY:DAT /R:1 /W:1 /NFL /NDL /NJH /NJS
if ($LASTEXITCODE -ge 8) { throw 'Client overlay failed' }
robocopy 'game\native\Black Gate' "$runtime\native\Black Gate" /E /COPY:DAT /R:1 /W:1 /NFL /NDL /NJH /NJS
if ($LASTEXITCODE -ge 8) { throw 'Native overlay failed' }
~~~

Use **ultima7-portable**, not ultima7-modern. Keep upstream and dependency notices. The client overlay needs the pinned upstream project files, FNA/SDL2-CS and other recursive dependencies. Exult supplies metadata only.

## 5. Build and generate

The native script discovers Visual Studio with vswhere or uses an existing **x64** developer prompt. Ensure clang-cl, CMake and Ninja are available there.

~~~powershell
& .\game\qualification\build-native.cmd matoya
if ($LASTEXITCODE -ne 0) { throw 'libmatoya build failed' }
& .\game\qualification\build-native.cmd
if ($LASTEXITCODE -ne 0) { throw 'Native game build failed' }
& .\game\qualification\build-client.ps1
if ($LASTEXITCODE -ne 0) { throw 'ClassicUO build failed' }

& $python -B game/atlas/complete-town/generate.py
if ($LASTEXITCODE -ne 0) { throw 'Atlas generation failed' }
& $python -B game/qualification/town_atlas.py
if ($LASTEXITCODE -ne 0) { throw 'Town generation failed' }
& $python -B game/intro/prepare.py
if ($LASTEXITCODE -ne 0) { throw 'Intro preparation failed' }
~~~

Use your normal PowerShell policy. If policy blocks the script, review it and use a permitted process-scoped invocation, not a machine-wide policy change.

Expected outputs under the private runtime:

| Path | Result |
| --- | --- |
| client/bin/Release-Trinsic-Avatar-Sheet/net10.0/cuo.dll | Client, accompanying libraries and native FNA dependencies |
| build-host/playtest-avatar-inventory/Ultima7.exe | Native U7 authority |
| reviewed-atlas/index.html | Local review atlas, mappings and source manifests |
| town-battlement-data | Map/statics, graphics.tsv, art and placement metadata |
| intro-assets | intro.json, Guardian sprites, blue static and local voice extraction |

Generation can take minutes. Outputs contain retail-derived material and must stay private. Original speech and blue static come from your game; authored head sources are tracked.

New games read your STATIC/INITGAME.DAT. **Do not run reference.py for installation:** its default command reconstructs maintainer-only DOS fixtures.

## 6. Launch

~~~powershell
& '.\Play Ultima Offline 7.cmd'
# Independent playthrough:
& '.\Play Ultima Offline 7.cmd' --run first-playtest
~~~

Enter the Avatar's name and appearance. Escape wakes you from the dream; walk into the red portal yourself. Finnigan's original greeting should open at the stables. F2/F3/F4 open paperdoll/backpack/map; F5 saves. See [controls and saves](../game/README.md).

Optional Exult digital music can be selected from a local folder in audio options. Music recordings and MT-32 ROMs are not downloaded or required for first launch.

## Verify the installation

Data-free tests:

~~~powershell
& $python -B -m unittest discover -s tests -q
& $python -B game/qualification/verify_test_copy.py
~~~

With binaries and generated data, run the real-client checks:

~~~powershell
& $python -B game/intro/verify.py creation
& $python -B game/intro/verify.py world
~~~

They open ClassicUO, exercise creation/dream/portal controls, and write logs/screenshots under private runs/dream-*-proof folders. Repeating a check resets its own named test run. Do not use those names for your playthrough.

Manually reach Trinsic, move, open the backpack, use an object, save with F5, close the client, and relaunch the same run. Confirm name, position and inventory persist. Compilation alone is insufficient.

Older qualification scripts may require private DOS saves, review atlases or frozen builds. Missing private fixtures are not an instruction to download saves or fabricate evidence.

## Troubleshooting

| Symptom | Check |
| --- | --- |
| Missing FNA/SDL2-CS or renderer libraries | Recursive submodules at the pinned revision; retain upstream external native libraries |
| Cannot build net10.0 | .NET 10 **SDK**, PATH, or DOTNET set to the full dotnet.exe path |
| CMake rejects MSVC / missing matoya.lib | clang-cl, x64 C++ environment; build matoya first |
| U7 data not found | Private Assets/UltimaVII-Steam/STATIC and U7.CFG |
| UOP key / tiledata error | Fully patched UO Classic and tested data format |
| Missing graphics.tsv / intro.json | Complete generators with the same private root as the launcher |
| Missing private release/fixture | Use this guide's opening launcher, not archived scripts |
| Client closes immediately | Read runs/<name>/client.log and host.log; retain actual command/tool versions |
| Run locked | Close that run normally or use another run; do not kill all game/Python processes |
| Broken staged checkout | Compare pins and reapply overlays in a new directory; preserve saves |

Advanced overrides: TRINSIC_CLIENT_BIN (directory with cuo.dll), TRINSIC_HOST_EXECUTABLE (full executable path), TRINSIC_INTRO_ASSETS (generated intro directory), TRINSIC_UO_ASSETS (runtime UO directory), and DOTNET. Atlas readers still use the private Assets layout; a runtime override does not import assets. The documented layout needs no overrides.

Historical E:\UltimaOffline paths in receipts and archived notes describe a maintainer machine, not prerequisites. Play Trinsic Playtest.cmd launches a private frozen package and is not the public source launcher.
