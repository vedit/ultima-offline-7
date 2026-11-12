# Ultima Offline roadmap

**Release target:** a player supplies English DOS *Ultima VII: The Black Gate* and UO Classic data on Windows, builds a private campaign, and plays the original story offline through ClassicUO and ModernUO. Black Gate governs quest outcomes. UO supplies the presentation, controls and combat wherever they preserve those outcomes. Forge of Virtue has a later qualification track. Serpent Isle is outside this release.

**Next milestone.** Compare the ordered dialogue topics across the Forge investigation. The original and converted journeys agree on both witness flags, the earned password, the conditional party reward and passage through the four-cell gate. [Task backlog](tasks.md) · [Master plan](master-plan.md)

## Where the project stands

The working Forge build uses the English Steam data and UO Classic 7.0.118.46. Report filenames below are in `E:\UltimaOffline\Evidence`. The vanilla release needs its own input profile and replays.

| Area | Verified on Forge | Outstanding |
|---|---|---|
| World inventory | All 144 regions, 9,437,184 terrain cells, 37,542 IFIX placements, 33,274 regional IREG objects and 943 schedule entries. All 33,274 regional movable records resolve by ID to original offsets, parents and ordered children. See `forge-world-inventory.json` and `world-movable-verify.json`. | Forge facet `cec66d70` maps 9,437,035 terrain cells and stages 968,164 static components. Both loaders checked the facet, including its quest overrides. The remaining 149 terrain cells and outstanding art, live objects and behaviors are tracked in G3-10. |
| Private facet | Both actual loaders verified 8,776,832 converted cells and 338,229 static components on the expanded facet. The Trinsic quest keeps its seven staged portrait frames. Movement, collision and saved positions have player-protocol receipts. | Rendered landmark, container and additional dialogue layouts, plus full-world geometry. |
| Source identities | Alden carried the original quality-253 key through restart and reported it to Finnigan. Both engines set flags 60 and 72 at the corresponding actions. The original DOS chest also retains its identity on unlock. | The estate unlock, contents, readable scroll and retained key have player and DOS evidence. General inventory mutations and remaining quest objects await qualification. |
| Usecode | All 132,459 Forge instructions matched ucxt. The compiler emits Lua for all 1,012 functions. Standalone fixtures observed 167 distinct functions. The Trinsic facet binds 46 functions to its registered events. DOS and the converted host agree on Finnigan’s XP recipients with Iolo downed. | Qualify the host effects and runtime paths beyond Trinsic, reproduce Iolo recovering and rejoining in a converted journey, and compare three divergent structured regenerations. |

The initial 16 × 16 compiler proof remains available in `Builds\TrinsicProof`. The newer development build and private facet have separate build IDs. Commands are in the [run guide](../README.md).

## Milestones and exit decisions

Gate acceptance is recorded for the edition tested. Development and oracle work can proceed on Forge while the owner-supplied base corpus is outstanding. Vanilla sign-off requires a matching base installation and its own evidence.

| Gate | Current status | Evidence required to close | Tasks |
|---|---|---|---|
| 0. Inputs and fixtures | Partial. Local inspection and fixtures pass. Clean-machine CI evidence is outstanding. | A clean worker distinguishes missing, vanilla, expanded, mixed and unknown inputs, runs data-free fixtures, and reports skipped retail execution explicitly. | [Inputs, fixtures and edition qualification](tasks.md#gate-0-inputs-and-fixtures) |
| 1. Compiler and target proof | Partial. Private character entry and entity persistence pass. Ordinary interactions match several DOS state changes. Alden opened Finnigan’s rendered Gump and advanced it. Landmark elevation, container interaction and fully qualified original traces remain open. | Both actual loaders read the same generated landmark and elevation. A player reaches it, interacts with original imported objects and the NPC, and a translated branch produces the reference outcome. The proof includes a fixed placement, nested container and portrait. | [First playable facet](tasks.md#gate-1-compiler-and-target-proof) |
| 2. Trinsic | Partial. Opening, stables, key report and the closed eastern gate have gameplay evidence. The ordinary Forge gate departure and restart pass. The earned departure, exterior reclosure, blocked reentry and gold placement match DOS on Forge. Iolo’s XP and the base-edition replay remain open. | A normal new game plays the opening, talks to Iolo and Finnigan, investigates the stables, obtains the source-defined progression and leaves town. Topics, inventory, flags and gate behavior survive restart. Then estimate the remaining campaign from measured work. | [Opening and town investigation](tasks.md#gate-2-trinsic) |
| 3. Whole world | Partial. All regions have source and fixed-object inventories. Both engines read the world geometry, and the player can travel beyond the original Trinsic patch. | Reconcile all 144 source regions and every placement, report script and media coverage, and verify representative towns, wilderness, islands, interiors, dungeons, seams and vehicles in both engines. | [World and systems](tasks.md#gate-3-whole-world) |
| 4. Campaign qualification | Open. Vanilla comparison needs the base corpus. | Replay the main route from a new character, exercise both endings from legitimate prior state, check declared side content and systemic interactions, and account for every unresolved reachable operation. | [Vanilla campaign replays](tasks.md#gate-4-campaign-qualification) |
| 5. Player release | Open | From clean staging, build with the two game inputs and provisioned tools, verify, launch offline, resume a compatible save and recover from an interrupted build. Ship the compatibility matrix, exceptions, backup/restore and installation guide. | [Release and later editions](tasks.md#gate-5-player-release) |

## Next work to pick up

1. Compare the ordered topic lists at the remaining witness and mayor checkpoints in the ordinary player replay (**G2-10**). G2-16 has a direct observation of the earned reward’s party-list return.
2. Extend the combined estate and witness replay to cover interactive doors and quest-item decay (**G2-04**, **G2-08**). Compare its identity, lock state, contents, source flag and returned position after restart.
3. Extend the rendered Finnigan check to the source landmark, container and other speakers, and calibrate a known original event in Exult (**G0-04**, **G1-08**, **G2-06**).

**Independent input dependency (ED-01):** supply an original English DOS Black Gate installation without Forge of Virtue. Lock its inputs and use the matching DOS game to settle behavioral disagreements. This gates vanilla qualification. It does not prevent the next Forge development build.

## Player commands at release

| Command | Current implementation | Remaining work |
|---|---|---|
| `u7uo inspect --u7 "<Black Gate>" --uo "<UO Classic data>"` | Reports source identity and inventory, UO fingerprints and base-map selection. `--full` includes record provenance. | Qualify the supported base profile and test ambiguous or missing resources on a clean machine. G0-02, ED-01. |
| `u7uo build --u7 "<Black Gate>" --uo "<UO Classic data>" --out "<private campaign>"` | `--stage trinsic` builds the development assets and `stage` provisions the private facet. The default campaign build reports unfinished work. | Publish the staged client data, initial world, compiled scripts, server configuration, local profile, manifest and exception report. G1-05, G3-10, G5-01. |
| `u7uo verify --campaign "<private campaign>"` | Checks compiler products and both loaders; the private-facet verifier also boots the server. `--structural-only` records skipped execution. | Add player-intention replays and edition-specific outcomes. G0-05, G2-10, G4-04. |
| `u7uo play --campaign "<private campaign>"` | Launches the private development facet; the standalone compiler sample is ineligible. | Start the private loopback server, wait for readiness, launch the client, diagnose failures and stop only owned processes. G1-05, G5-01. |
| `u7uo explain --campaign "<private campaign>" --id "<source or diagnostic ID>"` | Traces proof tiles, source objects, Finnigan, his portrait, functions and coverage. | Follow a live item, composed asset or error through its rule, original record/instruction and test evidence. G3-01, G3-07, G5-01. |

## Evidence to retain at every gate

Record the edition, input hashes, engine/tool revisions, source offsets or capture IDs, build ID, initial state, player action, expected result, observation and any discrepancy. Label structural checks, engine readback and actual gameplay separately. Compare stories by actions and resulting state. Use screenshots for clipping, reachability and presentation.

Report raw counts for source records inventoried, decoded and emitted or assigned to a composite; shape/frame families and placed occurrences covered; functions decoded, generated and executed; opcodes, intrinsics and action commands encountered, implemented and tested; static call sites and observed invocations; and scenarios passed, failed and `not_run`. Identify exact matches, reviewed UO substitutions, unresolved behavior and missing evidence. A reachable unknown or an unpresented ending keeps its gate open.
