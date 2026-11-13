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

Render a second settlement from its original records with the current rules frozen for the first pass. Compare source footprints and lifts, door openings, wall turns and moving objects. Make a correction at the narrowest level the data justifies, then rerun Trinsic and the second settlement. A passing Trinsic regression alone establishes behavior in Trinsic. [Rule-by-rule rendering audit](rendering-audit.md)

Reuse the original compiler's source readers, record identities, DOS comparisons and staged client assets where applicable. Counts of Lua functions compiled or statics accepted by ModernUO belong to that earlier implementation. The previous gate decisions and task IDs remain available. [Historical roadmap](modernuo-roadmap.md) · [Task backlog](tasks.md)
