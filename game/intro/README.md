# Dream opening

**Interim art — accepted for now on 2026-11-15.** The user considers the clay
animation imperfect but usable for this demo. The selected first grey clay
master and three original-frame mouth studies now have a crimson/yellow colour
pass installed in the isolated
intro. Small, medium and wide openings come from original U7 frames 6, 5 and 3.
Rounded cues reuse medium, and eyelid rows repeat the open-eye heads. This is
still four full-head poses, not a final animation set. The rejected red head,
second clay pass and the old colour pass are not used. The new paint pass is in
`art/painted-clay`; its prompt and source-image provenance are recorded there.

The background uses the original blue monitor pattern from `ENDSHAPE.FLX` member 19
and `INTROPAL.DAT` member 2. The importer exports the full 320-by-200 bitmap in
all 78 palette phases for entries 16 through 93, rotating in
the original speech-loop direction. The client advances at 20 phases/second.
The texture and colours are original; viewport scaling and presentation cadence
are adaptations for this scene. No new random noise is generated.

One background is drawn behind the complete head in the world render target,
covering its full width and height. Mouth apertures are true alpha holes, so
they expose the same background coordinates and animation phase. There is no
separate texture inside the mouth. The pattern pauses with the scene and stays
behind the red portal after the head fades. The stone wall is removed.
Original retail pixels and audio are prepared from the local installation into
ignored `bin/` files; they are not checked in.

This development-only scene precedes the original Black Gate Trinsic arrival.
Original speech, subtitle strings and facial cues remain unchanged. Native time
stays behind the existing `TRINSIC_READY` / `BEGIN` boundary until the player walks onto the portal tile. An existing save bypasses the intro. The dream allocates no native
objects or quest flags.

`art/clay-original-frames/prompts.json` records the image-generation provenance.
Its review record preserves the known landmark drift and the user's interim
acceptance. The old red set remains rejected in `art/review.json`.

## Play

After preparing and building, run **Play Ultima Offline 7 Intro.cmd** at the
repository root. Its `player-dream-intro` run is independent of the normal
development save. `--run another-name` selects another private run. `--reset`
starts again and retains the previous checkpoint using the existing launcher.

Space pauses/resumes the scene and voice. Esc skips the speech and wakes the Avatar; it never skips the walk to the portal.
New games first show a native UO-style name and gender panel. Enter a name of
1–14 characters and select male or female, then click Begin or press Enter.
The name uses the original game's CP437 character set; unsupported characters
produce a message. Typing and arrow keys do not move the Avatar or advance
native time on this screen. Quit leaves without creating a world save.

The native `CREATEAVATAR` command is available only at the fresh, off-map
opening boundary. It uses the same NPC name buffer and sex operations as
`LoadGameArgs`, retaining sequence/generation checks and rejecting later
renames. The chosen identity supplies the dream, dialogue, paperdoll and
native saves. Existing saved worlds bypass both setup and the dream.

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
$output = Join-Path $PWD 'game/intro/bin/creation-client/'
& E:/UltimaOffline/Tools/dotnet/dotnet.exe build game/intro/bin/source/src/ClassicUO.Client/ClassicUO.Client.csproj -c Release -p:PublishAot=false -p:UseSharedCompilation=false -p:NuGetAudit=false '-p:RestoreFallbackFolders=E:/UltimaOffline/Cache/NuGet' --source E:/UltimaOffline/Cache/NuGet --disable-build-servers "-p:OutputPath=$output"
```

The asset importer accepts `--static` for another local U7 STATIC directory.
It imports the original VOC as PCM, the original 297 facial cues in file order,
and the original subtitle strings. Four complete clay heads fill the existing five-column, three-row atlas;
medium is reused for rounded cues and open eyes for all eyelid rows. The
original blue pattern is exported as a separate 78-frame palette-cycle atlas. Native randomness, inventory and quest state are untouched.

## Verification

```powershell
& E:/UltimaOffline/Tools/dotnet/dotnet.exe run --project game/intro/tests/TimelineTests.csproj -- game/intro/bin/painted-assets/intro.json
py -3.13 game/intro/verify.py world
py -3.13 game/intro/verify.py full
py -3.13 game/intro/verify.py skip
py -3.13 game/intro/verify.py resume
py -3.13 game/intro/verify.py muted
py -3.13 game/intro/verify.py silent
py -3.13 game/intro/verify_character.py
py -3.13 game/intro/verify.py creation
py -3.13 game/intro/verify.py creation-male
py -3.13 game/intro/verify.py creation-cancel
py -3.13 game/intro/verify.py creation-resume
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

## World-rendered first slice

The opening now uses `U7DreamIntroScene : GameScene` with a separate client
`World`. Floor, bed and moongate are ordinary UO world objects;
the Guardian is a world item drawn through the normal render list and depth
buffer. Only captions and control hints use the UI layer. No video is played.

The room uses normal ClassicUO tile collision, movement interpolation, turning,
and mouse-distance running. Local walk acknowledgements apply only to this
client world; Trinsic still uses the original U7 engine. The Avatar wakes beside
the bed, then waits indefinitely for player input. Crossing the moongate tile
releases native BEGIN exactly once and restores the original Trinsic world.
Escape wakes the Avatar without entering the portal. Closing the client does
not change a save or allocate native U7 objects. Existing saves skip the room.

The `world` replay checks actual arrow-key motion, world rendering, collision,
and mouse-driven movement around the bed into the portal. Automated navigation
exists only in the opt-in replay and never runs in a player session.

## Stable-door arrival revision

The bed resolves original shape 696/frame 0 through the current town mapping,
so it uses the approved widened bed sprite rather than separate stock pieces.
It uses the same live-sleeper alignment as the game's beds: a held final prone
frame registered to the mattress. Waking clears that registration. The floor
is 10×10 UO tiles; the stone wall is absent.

The dream copies the native Avatar's body, skin, gender, hair and beard. Only
plain shirt and trousers are added locally; no armour or weapons are copied.
The native Avatar's equipment is untouched and returns at Trinsic. The client
dependency baseline must include the existing `Mobile.NativeLyingDown` and
bed-registration support used by ordinary Trinsic sleepers.

Dream handoff sends `BEGIN 1`; ordinary `BEGIN` retains the retail placement.
The native adapter moves the off-map arrival anchor to (1074,2210,0), then
restores its off-map state. Original Usecode still spawns the moongate, moves
three steps west, and runs Iolo/Petre/Finnigan's opening. This ends at
(1071,2210,0), directly south of the stable door (1071,2207,0). A one-shot
observer emits the existing travel effect when the Avatar actually appears.
No inventory, spell costs, quest flags, dialogue or Usecode is replaced.

The launcher now uses the separate native build at `bin/native-creation/Ultima7.exe`.
To reproduce it, copy the private `native` dependency tree into `bin/native-source`,
then overlay `game/native`. From a Visual Studio x64 developer command prompt:

```bat
set "PATH=E:\UltimaOffline\PoCs\ClassicUO-U7-Local\toolchain\bin;%PATH%"
cmake -S "game/intro/bin/native-source/Black Gate" -B "game/intro/bin/native-build" -G Ninja -DCMAKE_BUILD_TYPE=Release -DCMAKE_C_COMPILER=clang-cl -DCMAKE_CXX_COMPILER=clang-cl -DCMAKE_RUNTIME_OUTPUT_DIRECTORY="%CD%/game/intro/bin/native-creation"
cmake --build "game/intro/bin/native-build" --target u7 --parallel 4
```

`py -3.13 game/intro/verify.py arrival` checks the complete original commission,
repeated command handling and unchanged ordinary arrival. `world` additionally
asserts the stable-door coordinates and exactly one rendered travel effect.
