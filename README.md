# Ultima Offline

This Windows-first compiler turns part of the original Trinsic into a private ModernUO facet. The current development build uses English Steam Forge and UO Classic 7.0.118.46. The first campaign release targets English DOS Black Gate without Forge. The [task backlog](docs/tasks.md) tracks each acceptance check.

## Run the Trinsic development build

From the directory containing `u7uo.cmd`, run the following on the provisioned machine. The one-time builds in the first block compile the loader checks and shard extensions using the installed SDK, compiler and package cache.

```powershell
$root = 'E:\UltimaOffline'
.\tools\readback\build.ps1 -Root $root
.\tools\usecodehost\build.ps1 -Root $root
.\tools\entities\build.ps1 -Root $root
.\tools\dialoguehost\build.ps1 -Root $root
py -3 -B tools\facet\build_host.py --installation $root
```

```powershell
$u7 = "$root\Assets\UltimaVII-Steam"
$uo = "$root\Assets\UO-Classic"
$dev = "$root\Builds\TrinsicDevelopment"
$facet = "$root\Builds\TrinsicFacet"
.\u7uo.cmd inspect --region 64 --u7 $u7 --uo $uo
.\u7uo.cmd build --stage trinsic --u7 $u7 --uo $uo --out $dev
.\u7uo.cmd verify --campaign $dev
.\u7uo.cmd explain --campaign $dev --id function:040C
.\u7uo.cmd stage --campaign $dev --out $facet
.\u7uo.cmd verify --campaign $facet
.\u7uo.cmd play --campaign $facet
```

The private server uses loopback port 2594. Create a local character, walk west to Finnigan and double-click him from the adjacent tile. His original Usecode supplies the Gump text, speakers and choices. Frame and music generation uses your installed artwork, the provisioned Exult digital recording and FFmpeg on PATH. Saves live under `E:\UltimaOffline\Saves\BlackGateFacet`. On a dialogue-enabled facet, normal verify exercises a disposable player, save, server restart and reopened conversation. `inspect --world` returns the source census for all 144 superchunks. Region arguments are hexadecimal.

The map-triggered opening completes on the private Forge facet. Finnigan approaches the player and opens his conversation. The stables replay checks the original key through pickup, restart and the mayor’s report. The journey scenario follows the witnesses and the gate. Select a scenario explicitly to see which steps passed and the first remaining discrepancy.

```powershell
$opening = "$root\Builds\TrinsicOpeningFacet"
.\u7uo.cmd stage --campaign $dev --out $opening --opening --port 2595
.\u7uo.cmd verify --campaign $opening
```

The provisioned journey facet can also be launched directly. The verification commands use disposable characters and saves.

The world-object compiler build is in `E:\UltimaOffline\Builds\BritanniaObjectDevelopment`. For example, the following command traces an original stack of gold in region `14` to its position and byte range in the new-game archive. For nested items it also reports each owner and the world placement used for the position.

```powershell
.\u7uo.cmd explain --campaign "$root\Builds\BritanniaObjectDevelopment" --id "ireg:c1299e499aa1cd7c6bb9d7f14044ec21dc1f98aa45eaac1f6f1a2c473223491a:u7ireg14:231"
```

```powershell
.\u7uo.cmd play --campaign "$root\Builds\BritanniaCampaignFacet"
.\u7uo.cmd verify --campaign "$root\Builds\BritanniaCampaignFacet" --scenario journey
.\u7uo.cmd verify --campaign "$root\Builds\TrinsicEstateFacet" --scenario estate
.\u7uo.cmd explain --campaign "$root\Builds\BritanniaUsecodeDevelopment" --id function:0501
```

The combined journey picks up the smithy tongs, climbs the source staircase, uses the stables key on Christopher’s chest and reads the original scroll before the witness interviews. After the mayor’s exam, the player receives the reward and crosses the eastern gate. A new server process restores the tongs in the backpack, the equipped reward and the reclosed gate.

To compare the ordered investigation topics and inspect Finnigan’s saved locations, run the following against the Forge evidence. The daylight session restores the original pre-interview save, sets the clock through the DOS debug menu and visits Gilberto on the same saved day. The schedule report records observed positions and leaves movement between saves unqualified.

```powershell
$root = 'E:/UltimaOffline'
$dos = "$root/Evidence/dos-reference/session-5j7GWY"
$daylight = "$root/Evidence/dos-reference/session-J1G7c9"
$replay = "$root/Evidence/post-reboot-witness-first-01.json"
py -3 -B -m tools.oracle.topic_order $root $dos $replay --daylight $daylight
py -3 -B -m tools.oracle.mayor_schedule $root $dos $replay
```

Two private Forge saves bracket Finnigan's 06:00 appointment with the Avatar near his house and by the healer. Each DOS run restores its own save, changes the time to 05:55 and preserves the original day and clock rate. The paired ModernUO fixtures import the clock, player position and relevant NPC state into separate disposable worlds. To check the assignment, walk or relocation, and save/restart on the staged facet, run each fixture:

```powershell
$facet = "$root/Builds/BritanniaTownFacet"
$near = "$root/Evidence/dos-reference/session-jrHX34"
$far = "$root/Evidence/dos-reference/session-JOX539"
py -3 -B -m tools.facet.session --installation $root --facet $facet --appointment $near
py -3 -B -m tools.facet.session --installation $root --facet $facet --appointment $far
```

The DOS verifier accepts repeatable `--trial` arguments. Pair each with a `--player` report from the same facet as the journey replay to compare arrival ticks. On facet `8195f1fd`, the resident and distant arrivals fall within their native save intervals. The resident replay also checks the six visible fence cells after restart, walks into the barrier and around its east end. Add `--appointment-restart` to the resident command to stop and restart a disposable shard with directions still queued.

The DOS report decodes each active route from the original save’s `PATH.DAT` owner table and numbered path files, including its current waypoint and full waypoint list. The target chooses its own route using live ModernUO collision inside the original 80-tile window.

To follow the distant appointment into Finnigan’s office and reopen his seated state, use the chair-enabled facet. The DOS control used the original debug menu to visit NPC 12. The converted player walks from the healer to the office after the 06:00 appointment. The receipt records both positions, the selected source ID, the UO chair art and the actor and item serials before and after restart.

```powershell
$seatFacet = "$root/Builds/BritanniaSeatFacet"
$observer = "$root/Evidence/dos-reference/session-30TQF4"
py -3 -B -m tools.facet.session --installation $root --facet $seatFacet --appointment $far --office-observer $observer
```

Append `--open-client --visual` to inspect the reopened office in ClassicUO. Shape 873 chairs remain movable. Shape 292 seats stay fixed. The target displays the UO chair at its original sitting tile, one tile ahead of the source object's anchor in the direction encoded by its frame. The source anchor remains in the story seed.

The saved-walk comparisons use `BritanniaChairRouteFacet`. The observer disconnects as Finnigan walks, waits for a completed world save, and restarts the shard. The occupied run brings a second ordinary player onto the saved destination. It checks the change to loiter, restarts again, and holds the tile through the next quarter-hour appointment.

```powershell
$routeFacet = "$root/Builds/BritanniaChairRouteFacet"
py -3 -B -m tools.facet.session --installation $root --facet $routeFacet --appointment $far --office-observer $observer --chair-restart
py -3 -B -m tools.facet.session --installation $root --facet $routeFacet --appointment $far --office-observer $observer --chair-restart --occupy-chair
$native = "$root/Evidence/dos-reference"
py -3 -B -m tools.oracle.mayor_schedule $root $dos "$root/Evidence/forge-office-seat-witnesses-ca6ff946.json" --office-observer $observer --chair-restarts "$native/session-18iBnO" "$native/session-POwZ3R" --chair-retry "$native/session-VI2IEY"
```

The paired DOS runs restore the same native slot while Finnigan has an active route. The occupied control changes two coordinate bytes for the Avatar in a private copy of `U7IBUF.DAT`, within the same chunk and lift. The verifier reconstructs the change and checks the source and resulting member hashes. Both controls retain the original clock, route and RNG state.

The private compiler emits `campaign-usecode.lua` and a source index for all 1,012 installed Forge functions. The stager links the 46 functions used by the current event bindings into the playable module. With Iolo downed, the original DOS party-list call and the facet both returned Spark then the Avatar. An active Iolo received 50 XP in each engine.

To recheck the award, run the following against the private evidence. The verifier reconstructs the diagnostic input from the installed game, reads the returned handles and party arrays from DOS memory, then rechecks the uninstrumented saves and converted reward. The diagnostic adds a display loop immediately after the original call stores its result. Each click advances one entry, and the original reward loop resumes after the last page.

```powershell
$root = 'E:/UltimaOffline'
$evidence = "$root/Evidence"
py -3 -B -m tools.oracle.award_return $root "$evidence/forge-conditional-award.json" "$evidence/dos-reference/session-u0v0ZT" "$evidence/dos-reference/session-rGuKHv"
```

To reproduce the structured-regeneration comparison, run `py -3 -B -m tools.oracle.regeneration "$u7\STATIC\USECODE" --installation $root`. The diagnostic exports Kitrinx’s actual generated bytes in a private temporary directory. The command returns status 1 for the current Forge input because three regenerated functions have different ordered control-flow graphs. Each discrepancy includes the original byte offset.

The development compiler emits native land blocks and source-traced statics across all 144 superchunks. Staging keeps the Trinsic quest patches and fills the surrounding world with qualified blocks. Unresolved blocks use impassable padding. Its private `world-land.json` lists material rules, unresolved shapes and per-region block counts. Use `u7uo explain --campaign "$root\Builds\TrinsicEstateDevelopment" --id tile:2048,0` to trace a tile to its original map and chunk offsets. The verifier compares every emitted block with its original position. Both native loaders check the resulting staged world, including all generated statics and unresolved blocks. Use `u7uo explain --campaign "$root\Builds\TrinsicEstateDevelopment" --id world-statics` for the placement counts and dispositions.

### Compare Usecode arithmetic in DOS and the compiled campaign

For a separate Forge arithmetic comparison, run the original DOS interpreter and the published campaign Lua with the same diagnostic caller. The emulator receives a private copy of Iolo's Usecode body, external link and DOS preload slot. The original called routine and the installed files retain their hashes. To recheck an existing capture, append `--session <session-directory>`.

```powershell
py -3 -B -m tools.oracle.numeric_probe E:/UltimaOffline --campaign E:/UltimaOffline/Builds/BritanniaArithmeticDevelopment
```

### Compare Finnigan’s refusal in DOS and Exult

The qualification starts a fresh English Forge campaign, advances Iolo’s introduction, declines Finnigan’s first investigation offer and saves immediately after his response. The DOS player clicked No. The Exult player used the second choice, then Ctrl+S after dismissing the refusal. Both games showed the same refusal and saved flags 20, 59, 76, 89 and 92 set. Flags 60, 72 and 90 remained clear. The default Exult Avatar name and page wrapping differ from the DOS recording.

Read back the saved comparison on Windows. This rechecks the original bytecode, the rendered menu and response in both engines, the trace and both saves.

```powershell
$root = 'E:/UltimaOffline'
$dos = "$root/Evidence/dos-reference/session-vcrOnJ"
$exult = "$root/Evidence/exult-interactive-956b3da9"
py -3 -B -m tools.oracle.exult_refusal $root $exult $dos
```

For a new DOS replay, run `node tools/oracle/capture.cjs $root "$dos/receipt.json"`. The recorder binds the actual game inputs, emulator and configuration before replaying. For Exult, use the debug executable and launch arguments recorded in `$exult/run.json`. Add `$root/Tools/Exult-Build/msys64/ucrt64/bin` to that process’s PATH. Copy `$exult/probe.cfg` into a new session directory, point its Forge gamedat and slot paths to two empty directories there, and pass the new configuration with `-c`. Redirect stdout to the new session. Keep the 1024 × 768 client size for the recorded glyph checks. Advance the dialogue, capture the Yes/No menu, press 2, capture the response, dismiss it, and quicksave.

The Windows debug build uses the installed release’s upstream source revision and logs Usecode instructions and intrinsic results. The installed release initialized the same Forge campaign with both trace settings enabled and produced no intrinsic records. The debug calibration checked the initial Avatar reference and sole party member in Iolo’s event 3, the music request for track 35, and Finnigan’s refusal branch. Exult and its `ucxt` utility share interpreter terminology and opcode tables. The native DOS evidence comes from the Steam executable running in DOSBox and from its own framebuffer and save archive. [Upstream trace implementation](https://github.com/exult/exult/blob/cacb4f584901dab59ff288c750d3622d3378435b/usecode/ucinternal.cc#L1593-L1601)

## Run the compiler

Use PowerShell from the directory containing `u7uo.cmd`. The command uses the Windows Python launcher and Python 3.11 or later. These commands use the provisioned installation on E:.

```powershell
$u7 = 'E:\UltimaOffline\Assets\UltimaVII-Steam'
$uo = 'E:\UltimaOffline\Assets\UO-Classic'
$out = 'E:\UltimaOffline\Builds\TrinsicProof'

.\u7uo.cmd inspect --u7 $u7 --uo $uo
.\u7uo.cmd build --stage proof --u7 $u7 --uo $uo --out $out
.\u7uo.cmd verify --campaign $out
.\u7uo.cmd explain --campaign $out --id tile:1079,2214
.\u7uo.cmd explain --campaign $out --id function:06A4
.\u7uo.cmd explain --campaign $out --id actor
.\u7uo.cmd explain --campaign $out --id container
```

`inspect --full` includes the file hashes, seed member offsets and function index. `build --stage proof` uses the new-game archive inside STATIC. It stages the output, checks both engine loaders and executes the translated Lua before atomically replacing the build pointer. An interrupted build can leave a private staging directory. The active release is selected only by `current.json`. An ordinary rebuild can proceed alongside abandoned staging. Keep retail input directories and generated releases outside the source repository.

`verify` repeats engine and Lua checks offline. `verify --structural-only` checks every published file against its manifest and reports runtime checks as `not_run`. All CLI results are JSON. A failed check produces a nonzero exit code. If the tool installation lives elsewhere, supply `--installation <root>` or set `U7UO_INSTALLATION`.

## What the proof covers

| Component | Observable result |
|---|---|
| Edition | Reads the seed identity, checks the main-menu fingerprint and inventories STATIC. The qualified development corpus is the English Steam Forge copy. Base Black Gate remains the release target. |
| Trinsic terrain | Builds a 16 × 16 tile square from the chunk containing the initial Avatar. Reads the source and target materials before choosing grass and cobblestone art. Stores the shape, frame and source byte offsets for each tile. |
| Engine loaders | ModernUO and ClassicUO read the generated MUL. The checker compares every tile ID and signed elevation, and checks which file each engine opened. Fixtures cover transposed axes, conflicting stock UOPs, and excessive statics. |
| Source objects | Indexes the fixed objects of the surrounding superchunk and recovers an original containment tree from the seed. Each source instance has an identity and record location, including duplicates that share a position. |
| NPC and portrait | Reads Finnigan's actor record from the new-game archive. Checks his slot, portrait and script binding against the Usecode speaker. Compiles his face into an isolated UO gump archive and checks the RGBA image with ClassicUO. |
| Usecode | Translates function `06A4` from the installed bytes, including its conditional jump and flag write. Three real Lua executions check the taken branch, the untaken branch, and an existing flag that must survive the untaken branch. The compiler rejects operations beyond its supported subset. |

The standalone proof uses the unmodified loader libraries in a separate process. Use the development build and staged facet above for server or client execution. The existing Hexen shard has its own installation.

## Development and offline verification

Run the synthetic tests with `py -3 -B -m unittest discover -s tests -v`. Set `U7UO_LUA` to the Lua executable to include its execution test. The tests generate their records locally and require no commercial data. The readback smoke test exercises the actual libraries using generated fixture files.

```powershell
$root = 'E:\UltimaOffline'
$env:U7UO_LUA = "$root\Tools\Lua-5.4.7\lua.exe"
py -3 -B -m unittest discover -s tests -v
.\tools\readback\build.ps1 -Root $root
py -3 -B tools\readback\smoke.py --root $root
```

The loader build uses the ModernUO distribution, pinned ClassicUO sources, local .NET SDK and NuGet cache. On a newly provisioned machine, run `tools/readback/build.ps1 -Provision` once to populate the comparison dependencies. `tools/build-lua.ps1` rebuilds the qualified Lua interpreter from the pinned Revisited source and w64devkit. The expected source revisions, executable fingerprints and target resource fingerprints are in [the tool and input profile](u7uo/profiles.json).

The implementation used native shell execution and Codex subagents to work on separate readers. REA inspected the installed ModernUO assembly and confirmed its SHA-256 and .NET 11 target. The offline CLI owns the source identities, provenance, content hashes and acceptance checks so a later run can reproduce them without an agent. [Codex subagents](https://learn.chatgpt.com/docs/agent-configuration/subagents) · [Codex changelog](https://learn.chatgpt.com/docs/changelog)

### Inspect the rendered Trinsic client

To inspect the full first-run path, start at the login screen with a new disposable local account. Capture a frame, click Login, capture the shard list, double-click the shard, then capture character creation. Read each click position from the latest PNG. Menu receipts have a null player position. Walking becomes available when the client has a player.

```powershell
py -3 -B -m tools.facet.session --installation E:/UltimaOffline --facet E:/UltimaOffline/Builds/TrinsicVisualFacet --open-client --visual --login-screen
py -3 -B -m tools.facet.visual "<scratch>" capture
```

On Windows, launch a disposable Alden session beside Finnigan with the pinned ClassicUO executable and the test plugin. The launcher compiles the plugin using the project-local w64devkit and prints the session directory in its `scratch` field.

```powershell
py -3 -B -m tools.facet.session --installation E:/UltimaOffline --facet E:/UltimaOffline/Builds/TrinsicVisualFacet --walk --open-client --visual
py -3 -B -m tools.facet.visual "<scratch>" capture
py -3 -B -m tools.facet.visual "<scratch>" click <capture-request-id> <x> <y> --button double
py -3 -B -m tools.facet.visual "<scratch>" capture
```

Coordinates are pixels in the full-size PNG. The controller accepts `left`, `right` and `double` clicks from the most recent capture. It moves the pointer within the game window. A `step` command takes a UO direction from 0 (north) clockwise through 7 (northwest). An initial input can turn the character. Capture again to verify the resulting position. Each receipt under `<scratch>/state/visual` records the build, client PID and coordinates. Capture receipts also identify the PNG and its SHA-256.

To inspect the converted shoreline, run the following from the project directory. The disposable player crosses a muddy bank, attempts a step into deep water, and reopens at the last walkable coordinate. The same capture commands work in that session.

```powershell
py -3 -B -m tools.facet.session --installation E:/UltimaOffline --facet E:/UltimaOffline/Builds/BritanniaShoreFacet --shore --open-client --visual
```

To replay swamp exposure, run `.\u7uo.cmd verify --campaign E:/UltimaOffline/Builds/BritanniaSwampFacet --scenario swamp`. The disposable player starts beside original boots at (1300, 961), equips them, and steps onto original swamp fields. The replay saves a protected exposure, moves the boots into the backpack, and checks the resulting poison flag across a server restart.

To verify original void ground beside deep water, run `.\u7uo.cmd verify --campaign E:/UltimaOffline/Builds/BritanniaVoidFacet --scenario void`. For a rendered replay, use `py -3 -B -m tools.facet.session --installation E:/UltimaOffline --facet E:/UltimaOffline/Builds/BritanniaVoidFacet --void --open-client --visual`. A step receipt records the request. Use a subsequent capture after movement settles to verify the new coordinates.

The later `BritanniaMountainFacet` includes the original solid footprint covering that older route. Run `.\u7uo.cmd verify --campaign E:/UltimaOffline/Builds/BritanniaMountainFacet --scenario void` to walk on exposed void and attempt the mountain at (496, 2316). To compare the native DOS saves and player inputs with the converted result, run `py -3 -B -m tools.oracle.mountain E:/UltimaOffline E:/UltimaOffline/Evidence/dos-reference/session-KujFDP E:/UltimaOffline/Evidence/mountain-player.json`.
