# Ultima Offline 7 roadmap

Ultima Offline 7 uses the portable Black Gate engine as the single authority for simulation, original Usecode and native saves. ClassicUO presents that state and sends player actions back to it. The first campaign release still targets owner-supplied English DOS Black Gate on Windows. Current playable evidence is from Steam Forge. [Play and rebuild](../game/README.md)

## Current milestones

| Milestone | Where we are | Evidence still needed |
|---|---|---|
| Inputs and first playable build (G0â€“G1) | The provisioned installation boots a native host and ClassicUO, uses original DOS fixtures, and rebuilds the reviewed atlas and compact Trinsic overlay from source. | Reproduce the install and fixtures on another machine. Remove the dependency on a historical staged facet for client assets/settings. Qualify the base edition separately (ED-01). |
| Trinsic investigation (G2) | The frozen Steam Forge playtest runs from the original moongate arrival through Finnigan's commission, the investigation and the east gate. The restarted exit save matches the DOS Avatar position, gate lift, key ownership and 19 recorded flags. ClassicUO replays cover the stable, estate, report and crossing. [Playtest receipt](../game/receipts/trinsic-playtest-01.json) | Player sign-off on feel, readability and occlusion. Full ordered-topic comparison with DOS, audible music and the base edition remain open. |
| World renderer (G3) | Source inventory exists for 144 regions. Trinsic has 52,224 source terrain cells, 54,427 terrain/fixed/world placements checked and 28 approved art treatments preserved. | Run the same rules on an unseen town, a wilderness/shore seam and a multi-level interior. Record exact matches, inferred graphics, unknowns, and exceptions by occurrence. Verify seams from both sides with neighboring regions loaded. |
| Campaign and player release (G4â€“G5) | The gated town slice and previous compiler experiments provide fixtures and comparisons. | Play the campaign and both endings from legitimate states, qualify unsupported systems and the base edition, and demonstrate private installation, offline launch, save migration and recovery on a clean machine. |

### Next development milestone

Render a second settlement and the journey there from original records, with the current rules frozen for the first pass. Compare source footprints and lifts, door openings, wall turns, moving objects and region seams. Make a correction at the narrowest level the data justifies, then rerun Trinsic and the second settlement. A passing Trinsic regression alone establishes behavior in Trinsic. [Rule-by-rule rendering audit](rendering-audit.md)

Alongside that route, use the Developer's Wand to prepare isolated scenarios for ordinary combat, death and spellcasting. Tool-assisted setup must not substitute for the player action being qualified. Add missing controls and presentation adapters around the original native operations; retain native gameplay rules.

## U7 systems coverage — 15 November 2026

The native engine supplies the underlying systems. **Partial** below means some player-facing behavior has evidence; **unqualified** means the full scenario has not been demonstrated through ClassicUO, rather than that its native logic is absent. Existing passing cases remain in the [interaction inventory](../game/INTERACTIONS.md) and [21-group qualification receipt](../game/receipts/full-interactions.json).

| System | Current baseline | Remaining work and completion evidence |
|---|---|---|
| World travel and vehicles | Walking and Trinsic gate departure are qualified. | Qualify travel across region boundaries, boats/barges, flying carpet, boarding, passengers and cargo. Present moving structures from native state and verify their positions and contents after restart. |
| Party and combat | Following, feeding, inventories, equipment, native attacks and war/peace have passing cases. | Expose original combat-strategy controls. Qualify recruitment/dismissal, larger parties, ranged attacks and ammunition, fleeing and sustained encounters with native outcomes and restart checks. |
| Death and recovery | Native combat death and wand resurrection with possessions are tested. | Qualify ordinary spell-based resurrection, companion death, Avatar defeat/rescue and equipment recovery. Debug resurrection alone does not close these gameplay cases. |
| Magic | All 72 U7 spells appear in the native spellbook; resource checks and selected effects have focused tests. | Exercise every spell with suitable targets, including duration, resistance/refusal, cancellation and persistence. Review provisional visual equivalents, unmapped summons and field coverage. [Spell presentation and limits](../game/spell-effects.md) |
| Lighting and weather | Native time/schedule updates and weather controls work; rain/snow presentation exists. | Connect coherent day/night brightness, darkness, carried lights and lighting spells to native state. Complete or explicitly mark unsupported advanced weather presentation. |
| Production and everyday activities | Buckets, selected potions, resting, purchases, training and forge heating have effect assertions. | Qualify complete baking, weaving and forging chains, remaining potion effects and multi-step tool/object transformations. Baking and weaving are outside the Trinsic census. |
| Crime and NPC reactions | Ownership, theft reporting and witness objections are qualified. | Exercise escalation, guards, repeated offences and multiple witnesses; compare consequences and persistence with native behavior. |
| NPC schedules | Original schedules run; time changes invoke native schedule updates. | Observe full-day work/sleep routines, interrupted actions, blocked routes and behavior after leaving and returning to a region. |
| Audio | Some UO impact sounds are connected. The headless launcher suppresses native music/sound. | Integrate and listening-test music, speech, ambient and action sounds, avoiding duplicate playback between native and client effects. |
| Saves and player menus | Native save/load, generated-object persistence and independent test copies are qualified. | Provide a player-facing slot browser and naming; rehearse backups, recovery and upgrade compatibility with progressed saves. |
| World and campaign coverage | Trinsic's original investigation is playable through departure. | Qualify other settlements, wilderness seams, dungeons, multi-level interiors, special displays, alternate quest paths and the full campaign under G3–G5. Keep base Black Gate and Forge evidence separate. |

The [Developer's Wand](../game/developer-wand.md) is implemented and installed for desktop development, with supplies, catalogs/spawning, duplication, inspection, stat/condition editing, world controls and session cleanup. Its [verification receipt](../game/receipts/developer-wand.json) records bounds, allocation exhaustion, native resurrection, independent save copies and regression results. This completes testing support, not campaign qualification.

Close each remaining system with a legitimate or explicitly prepared starting state, ordinary player inputs, expected native outcomes, UO presentation evidence, cancellation/movement recovery where applicable, and save/reload checks. Record unsupported and unrun cases explicitly.

Reuse the original compiler's source readers, record identities, DOS comparisons and staged client assets where applicable. Counts of Lua functions compiled or statics accepted by ModernUO belong to that earlier implementation. The previous gate decisions and task IDs remain available. [Historical roadmap](modernuo-roadmap.md) · [Task backlog](tasks.md)
