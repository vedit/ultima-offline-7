# Ultima Offline 7 development build

Run `Play Ultima Offline 7.cmd` at the repository root. It resumes `runs/player-investigation/GAME00.U7` in the existing private installation, or starts with Finnigan's commission at the stables. Use the arrow keys or right mouse button to move, double-click objects and people to use them, and drag items between the world, containers and paperdoll. F2 opens the paperdoll, F3 the backpack, F4 the map and F5 saves. Close the client window to end that session.

The default installation is `E:\UltimaOffline`. Set `ULTIMA_OFFLINE_HOME` to use another installation with the same layout. The historical folder name `PoCs\ClassicUO-U7-Local` identifies the private runtime and its save slots. Use a separate slot to try a new investigation.

```powershell
& '.\Play Ultima Offline 7.cmd' --run my-investigation
```

## Source and private inputs

| Repository files | Origin and use |
|---|---|
| `game/client/src` | Editable source overlay for ClassicUO at `ee79d7ebc1cc0e53ff84fe6cae17d389e2737f93`. The first checkpoint includes 21 changed tracked files and three new files. The base commit pins FNA, FileEmbed and MP3Sharp. Keep the upstream source tree, its recursive submodules and notices. [ClassicUO license](client/LICENSE.md) |
| `game/native/Black Gate` | Eight changed files and two new local-session files relative to the portable Black Gate engine in Kitrinx/Ultima7_Decomp at `872a613c718abf3a40cf94533887171bec8cfb24`. The local `Downloads/Kitrinx-872a613c.zip` has SHA-256 `f0ce7336158e7a3ca86390576f4f63599495849b785b37c0264590e46321bcb4`. [Upstream notice](native/LICENSE) |
| `game/atlas` | Source readers, reviewed mappings and stock-art recipes. The review covers 18 revised matches and all ten rake frames. The source census and generated file hashes are in the [atlas receipt](receipts/trinsic-atlas.json). |
| `game/qualification` | Windows build scripts, launcher, atlas-to-ClassicUO conversion, renderer checks and input replays. The [investigation receipt](receipts/trinsic-investigation.json) records the original town playthrough. The [facing receipt](receipts/trinsic-facing.json) describes an earlier facing pass at its recorded revision. |

The private build reads `Assets/UltimaVII-Steam`, `Assets/UO-Classic`, and the assets, settings and sample from `Builds/BritanniaChairRouteFacet/releases/50f99d0c53594314f443902201e3a2312aa43764c7d35fede5f252da601ec4f1`. The atlas also uses the installed Exult 1.12.1 shape metadata and the ModernUO decoration reference. Git contains the recipes and source changes. Generated retail art, game data, compiled executables, evidence images and player saves live in the private installation.

The local Git tag `archive/forge-conversion` points to the preceding ModernUO checkpoint. Three superseded native binaries and their manifests are under `PoCs/ClassicUO-U7-Local/archive/pre-uo7-hosts`. To restore one, return its directory to `build-host` and verify its files against the [archive manifest](receipts/archived-hosts.json). The older `build-host/playtest` is still used for reference checks.

## Rebuild on a provisioned machine

Begin with a private installation containing the pinned toolchains, packages, input data and DOS evidence. Its `PoCs/ClassicUO-U7-Local/client` must contain a checkout of the pinned ClassicUO revision and its submodules. Under `native`, extract the pinned archive's `ultima7-portable/Black Gate`, `third_party` and `assets` trees. Apply the tracked overlay to those two source trees, preserving relative paths. For example, starting from the repository root in PowerShell with a separate provisioned development installation:

```powershell
$installation = if ($env:ULTIMA_OFFLINE_HOME) { $env:ULTIMA_OFFLINE_HOME } else { 'E:\UltimaOffline' }
$runtime = Join-Path $installation 'PoCs\ClassicUO-U7-Local'
Copy-Item -LiteralPath 'game\client\src' -Destination "$runtime\client" -Recurse -Force
Copy-Item -LiteralPath 'game\native\Black Gate' -Destination "$runtime\native" -Recurse -Force
& .\game\qualification\build-native.cmd matoya
& .\game\qualification\build-native.cmd
& .\game\qualification\build-client.ps1
```

The native script uses VS 2019 Build Tools, clang-cl 18.1.8, CMake and Ninja. The client uses the private .NET SDK and NuGet mirror. `reference.py` can recreate the investigation starter from `Evidence/dos-reference/session-jrKbjq/accepted-GAME00.U7` and its staging fixture from the pinned chair-route evidence. The installed investigation save and that original DOS checkpoint have the same SHA-256.

```powershell
py -3 -B game/qualification/reference.py
py -3 -B game/atlas/complete-town/generate.py
py -3 -B game/qualification/town_atlas.py
```

Use Python 3.11 or later with Pillow. The generators default to `reviewed-atlas` and `town-battlement-data` inside the private runtime. For a comparison build use `--out <directory>` on either generator. The town generator reads the runtime's reviewed atlas. This keeps the parallel asset-mapping project's newer candidates available for separate review. The town validator also reads the retained `town-data` and `town-stables-data` comparison builds. The atlas validator uses the earlier review's `Trinsic-Asset-Mapping/atlas/mapping.csv`.

## Verify

```powershell
py -3 -B game/atlas/complete-town/verify_town.py
py -3 -B game/atlas/complete-town/verify_town.py --world-terrain
py -3 -B game/qualification/verify_town_facings.py
py -3 -B game/qualification/investigation.py --run verify-investigation
py -3 -B -m unittest discover -s tests -q
```

The first check compares the atlas with source records and reviewed output hashes. The second compares exact atlas keys with terrain placements across the original world. The third reads the installed map, statics, art and tile flags. The fourth starts a separate native host, sends actions through the local input protocol and saves at each investigation milestone. It starts the named verification slot from the original checkpoint. For player-facing visual or mouse interaction changes, also exercise the ClassicUO client. The last command runs the repository's existing compiler and source-reader tests.
