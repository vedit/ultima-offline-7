# Dream opening

**Interim art — accepted for now on 2026-11-15.** The user considers the clay
animation imperfect but usable for this demo. The selected first grey clay
master and three original-frame mouth studies are now installed in the isolated
intro. Small, medium and wide openings come from original U7 frames 6, 5 and 3.
Rounded cues reuse medium, and eyelid rows repeat the open-eye heads. This is
still four full-head poses, not a final animation set. The rejected red head,
second clay pass and later colour pass are not used.

The wall uses the original blue monitor pattern from `ENDSHAPE.FLX` member 19
and `INTROPAL.DAT` member 2. The importer projects that bitmap onto the UO wall
plane and exports all 78 palette phases for entries 16 through 93, rotating in
the original speech-loop direction. The client advances at 20 phases/second.
The texture and colours are original; the wall projection and presentation
cadence are adaptations for this scene. No new random noise is generated.

One animated wall is drawn behind the complete head. Mouth apertures are true
alpha holes, so they expose the same wall coordinates and animation phase.
There is no separate texture inside the mouth. The wall fades with the face,
pauses with the scene, and gives way to the existing stone wall and red portal.
Original retail pixels and audio are prepared from the local installation into
ignored `bin/` files; they are not checked in.

This development-only scene precedes the original Black Gate Trinsic arrival.
Original speech, subtitle strings and facial cues remain unchanged. Native time
stays behind the existing `TRINSIC_READY` / `BEGIN` boundary until portal entry
or skipping. An existing save bypasses the intro. The dream allocates no native
objects or quest flags.

`art/clay-original-frames/prompts.json` records the image-generation provenance.
Its review record preserves the known landmark drift and the user's interim
acceptance. The old red set remains rejected in `art/review.json`.

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
and the original subtitle strings. Four complete clay heads fill the existing five-column, three-row atlas;
medium is reused for rounded cues and open eyes for all eyelid rows. The
original blue pattern is exported as a separate 78-frame palette-cycle atlas. Native randomness, inventory and quest state are untouched.

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
