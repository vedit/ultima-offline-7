# U7 spell presentation in ClassicUO

The original Black Gate engine owns casting eligibility, reagents, mana, targeting,
randomness, damage, resistance, status, fields, summons and duration. ClassicUO
renders stock UO effects from observations of those native operations. No spell is
implemented by calling UO gameplay or by treating a book click as a successful cast.

## Event sources

- Native Usecode calls establish spell provenance, including posted spell routines.
  Intrinsic observers compare before/after state. Healing, cure, protection,
  invisibility and similar bursts require an actual mutation.
- Native missile trackers export current position and lifetime. Client effects
  follow those coordinates; they do not predict collisions or apply hits.
- Native combat hits and explosions supply impact cues. Explosive weapons use
  the explosion event, avoiding a second burst from the initial hit.
- Successfully placed fields and summoned actors retain native identities. Fields
  remain selectable native objects and disappear when the original engine removes them.
- Flame Strike uses UO graphic `0x3709` once at each successfully placed native
  fire field. U7's enemy list and placement success determine the affected locations.
  This adds neither UO damage nor another target-selection pass.
- Original weather and earthquake state drive rain/snow and a small camera shake.
  Light spells receive an activation cue; this change does not replace the town's
  global lighting system. Thunder retains the original sound-only behaviour.

Observers do not call gameplay, advance random numbers or modify weapon-record
caches. The native engine's original scripts and spell-resource checks are unchanged.

## Mapping

| U7 spell family | UO presentation |
|---|---|
| Heal, Great Heal, Restoration | Healing particles `0x376A` when HP increases; separate cleansing cue when applicable |
| Cure, Mass Cure, Awaken, Awaken All | Cleansing particles `0x373A` when the condition is removed |
| Protection, Protect All | Protection `0x375A` |
| Curse, Mass Curse, Poison | Curse/poison `0x374A` when the status takes effect |
| Paralyze | Paralyze `0x376A` on successful status application |
| Invisibility, Invisible All, Reveal | Stock vanish/reveal cue and native invisible state |
| Fire Blast | Fireball `0x36D4` following native flight; fire impact |
| Lightning, Magic Storm | Native UO lightning effect at the native strike location |
| Explosion, Delayed Blast | Explosion `0x36CB` at native detonation |
| Flame Strike | One stock Flame Strike `0x3709` at every accepted native placement |
| Fire Field, Fire Ring | Fire-field `0x398C` on each native field object |
| Poison Field, Energy Field | Stock field graphics `0x3915`, `0x3946` |
| Dispel Field, Destroy Trap | Dispel cue after successful native removal/disarm |
| Mark, Recall, Help | Mark/travel `0x3728` where the native operation occurs |
| Unlock Magic, Telekinesis | Unlock/remote-use cue from the native change or callback |
| Create Food, Create Gold, Enchant | Sparkles on actual creation/transformation |
| Ignite, Great Ignite, Douse, Great Douse | Flame/extinguish cue when the native item's light-bearing shape changes |
| Glimmer, Light, Great Light | Light activation particles |
| Swarm, Conjure, Clone, Summon | Summoning cue on successfully placed native creatures; existing creature art |
| Resurrect | Resurrection cue after native resurrection succeeds |
| Death Bolt | Energy-bolt `0x379F` following native flight; native death cue on success |
| Armageddon, Mass Death | Death cues on actual native deaths; original exemptions remain |
| Weather, Tremor | Native weather state and earthquake-driven camera shake |
| Locate, Peer, Wizard Eye | Existing native display/camera path, without an invented impact effect |
| Thunder | Original sound; no invented lightning hit |

## Ambiguous visual equivalents

These are provisional stock-art reuses, not claims that the UO spell has the same rules.

| U7 spells | Provisional treatment |
|---|---|
| Sleep, Mass Sleep, Sleep Field | Pale sleep particles and tinted UO paralyze-field art. U7 still applies sleep. |
| Charm, Mass Charm, Dance, Cause Fear, Mass Might | Tinted buff/debuff particles; U7 decides affected actors and outcomes. |
| Energy Mist | Pale energy animation on the native moving effect. |
| Death Vortex | Dark energy animation on the native vortex, not an independently spawned UO creature. |
| Swordstrike | Stock `0x37EB` candidate on the native flight/impact; appearance needs visual review. |
| Seance | Pale spirit-like particles from the native sprite event. |
| Time Stop | Activation cue only; the native clock hold remains authoritative. |
| Fireworks, Detect Trap | Coloured stock sparkles from the original sprite events. |

Summoned species without an existing ClassicUO body mapping still need an art
review. This change does not invent replacements for those creatures. Native field
footprints and collision are preserved; the UO field sprites are visual proxies,
not a qualification of exact coverage for every original 3-by-3 field shape.

## Transport and qualification

`FX` carries the event watermark, `F` carries a sequenced native event, `FM` carries
the complete current magical-projectile set, and `FV` carries environment state.
Events retain native coordinates and lifetime-qualified object IDs. Repeated
snapshots/reconnects cannot replay an already consumed sequence. Loading clears
transients; absent missiles are removed immediately. The queue is bounded to 512
events and 1.8 seconds, so a client disconnected longer than that does not replay
old combat. Older native hosts without `FX` remain supported.

Run the existing qualification entry points with `TRINSIC_HOST_EXECUTABLE` and
`TRINSIC_CLIENT_BIN` pointing to the candidate:

```powershell
py -3 -B game/qualification/spell-effects.py --all
py -3 -B game/qualification/spell-effects.py --client
py -3 -B game/qualification/spell-effects.py --parity
py -3 -B game/qualification/interaction-suite.py spellbook creatures-combat world-effects audit-boundaries world-targets
```

The 72-spell run is a dispatch/modal smoke test, not proof that all 72 spells
successfully affect the generic target. Focused checks qualify actual mutations,
cancellation, sequence stability, load clearing and Flame Strike placement.
Observer-on/off checks compare native healing, cure, protection and invisibility
outcomes. Client replay checks stock-art availability, healing, Flame Strike,
reconnect deduplication and movement. `AUDITCAST` bypasses book resources only in
the explicitly enabled disposable `interaction-audit` fixture; normal player
casting still uses the native spellbook's checks.

Primary stock-art references: [ServUO Flame Strike](https://github.com/ServUO/ServUO/blob/pub57/Scripts/Spells/Seventh/FlameStrike.cs),
[Heal](https://github.com/ServUO/ServUO/blob/pub57/Scripts/Spells/First/Heal.cs),
[Cure](https://github.com/ServUO/ServUO/blob/pub57/Scripts/Spells/Second/Cure.cs),
[Fireball](https://github.com/ServUO/ServUO/blob/pub57/Scripts/Spells/Third/Fireball.cs).
Only their presentation assets are reused.
