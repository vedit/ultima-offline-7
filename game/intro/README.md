# Dream opening

**Art status — rejected on 2026-11-15.** The current generated head, all four
mouth variants and both eyelid variants fail the facial perspective and tone
review. All 15 packed combinations inherit the same faulty master. Functional
intro verification is not visual approval. Keep these files as rejected
development references until the master is rebuilt; see `art/review.json`.

This development-only presentation precedes the original Black Gate Trinsic
arrival. The bare Guardian relief uses a fixed head with four alternate
mouth patches and two eyelid patches. Original speech, subtitles and facial
cues are read from the player's local U7 installation; retail audio and data
are not checked in.

The dream has no native objects or quest flags. Native time stays behind the
existing `TRINSIC_READY` / `BEGIN` boundary until portal entry or skipping.
An existing save bypasses the intro.

Art in `art/` is generated with the built-in image generation tool from the
selected relief concept. There is no trophy plate, mounting hardware, teeth
or tongue. Mouth openings are real alpha cutouts exposing the stock wall.
Production variants remain registered to
the master; import crops and layer masks are recorded by the asset recipe.
These are separate development candidates, not replacements for town art.
The older eye sources contribute only the two cropped eyelid regions; their
surrounding material is never imported. `art/relief-prompts.json` records the
prompts and the user's revisions.

Before generating replacement animation, review one master against the original
U7 Guardian's identity and stock UO stone faces (including 0x110F) for projection.
The skull, brow, nose bridge/tip, mouth centre and chin must describe one head
orientation. Check the nose's depth and occlusion, the far side's foreshortening,
and the mouth wrapping around the muzzle. Keep the expression stern, with
restrained lips and angular facial planes. Check enlarged and at 104 x 140 before
making mouth/eyelid patches. Preserve the requested transparent mouth apertures
and absence of teeth, tongue, trophy plate and hardware.

## Play

After preparing and building, run **Play Ultima Offline 7 Intro.cmd** at the
repository root. Its `player-dream-intro` run is independent of the normal
development save. `--run another-name` selects another private run. `--reset`
starts again and retains the previous checkpoint using the existing launcher.

Space pauses/resumes the scene and voice. Esc skips to the original arrival.
After waking, hold right mouse or use arrow keys to enter the red moongate.
Mouse distance selects walking/running. Speech uses the existing U7 speech
enable/volume preferences; captions remain available when muted or when audio
cannot be opened. The scene also pauses when the client loses focus.

## Prepare and build

Use the existing private ClassicUO source checkout as the dependency baseline.
All generated retail data, binaries and intermediate files remain under the
ignored `bin/` directory. In PowerShell at the repository root:

```powershell
py -3.13 game/intro/prepare.py
robocopy E:/UltimaOffline/PoCs/ClassicUO-U7-Local/client game/intro/bin/source /E /XD .git bin obj .vs /NFL /NDL /NJH /NJS /NP /R:0 /W:0
robocopy game/client/src game/intro/bin/source/src /E /NFL /NDL /NJH /NJS /NP /R:0 /W:0
$env:DOTNET_CLI_HOME = Join-Path $PWD 'game/intro/bin/cache/dotnet'
$env:NUGET_PACKAGES = Join-Path $PWD 'game/intro/bin/cache/packages'
$output = Join-Path $PWD 'game/intro/bin/client/'
& E:/UltimaOffline/Tools/dotnet/dotnet.exe build game/intro/bin/source/src/ClassicUO.Client/ClassicUO.Client.csproj -c Release -p:PublishAot=false -p:UseSharedCompilation=false -p:NuGetAudit=false '-p:RestoreFallbackFolders=E:/UltimaOffline/Cache/NuGet' --source E:/UltimaOffline/Cache/NuGet --disable-build-servers "-p:OutputPath=$output"
```

The asset importer accepts `--static` for another local U7 STATIC directory.
It imports the original VOC as PCM, the original 297 facial cues in file order,
and the original subtitle strings. Five mouth shapes and three eye states form
15 packed cells from seven authored images; it does not generate 15 separate
heads. Native randomness, inventory and quest state are untouched.

## Verification

```powershell
& E:/UltimaOffline/Tools/dotnet/dotnet.exe run --project game/intro/tests/TimelineTests.csproj -- game/intro/bin/assets/intro.json
py -3.13 game/intro/verify.py full
py -3.13 game/intro/verify.py skip
py -3.13 game/intro/verify.py resume
py -3.13 game/intro/verify.py muted
py -3.13 game/intro/verify.py silent
```

The integration checks use the existing `TrinsicReplay` and `client-proof.py`
driver. `full` checks audio playback, pausing, every native snapshot byte staying
unchanged during the dream, portal movement and the native handoff. The native
host runs in private `dream-*-proof` runs. Captures and result receipts stay in
those runs and in `bin/`; original retail speech and subtitles are not committed.

The sleeping figure uses a held stock UO prone animation, rather than custom
sleeping art. Waking switches to the stock standing/walking animations. This
is a deliberately small dream scene, not a reconstruction of the original
Earth bedroom cinematic.
