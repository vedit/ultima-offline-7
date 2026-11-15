# Trinsic playtest audit — 15 November 2026

The main investigation is completable through the ClassicUO frontend. A fresh
original moongate arrival reached the east-gate exterior through ordinary UO
actions, dialogue widgets and targeting, then saved and reloaded there. No debug
commands, observer teleports, quest-flag edits or supplied quest objects were
used in that continuous run. It took 508 seconds and retained nine screenshots.

This is **core quest readiness**, not a claim that every optional event and visual
effect is finished. The remaining gaps are listed below. This change adds audit
and regression coverage; it does not change any U7 gameplay or quest script.

## Starting tomorrow's playtest

Run **`Play Trinsic Playtest.cmd`** in the repository root. It uses the regular
installed game and a separate `trinsic-playtest-20261116` run. Its first launch
starts the original arrival; later launches resume its saved checkpoint. It does
not reset or overwrite the ordinary development save. The Developer's Wand
remains available under the development launcher's usual rules.

Equivalent command:

```powershell
py -3 -B game/qualification/play.py investigation --from-opening --run trinsic-playtest-20261116
```

Add `--no-debug` for a playtest without the wand. Do not use `--reset` to resume.
Use Options → Saved games for named slots; F5 saves and F9 loads the active slot.
F2 opens the Avatar paperdoll, F3 opens the backpack, and the paperdoll's Party
button exposes actual companions. Right mouse moves; point farther away to run.
Escape cancels a target or closes a native view. Dialogue must be finished through
its offered choices.

## Player checklist

1. Let the arrival finish and accept Finnigan's investigation. Check that Iolo and
   Petre's overhead reactions identify the correct speakers.
2. Enter the stables from either entrance. Look at both victims, the blood bucket,
   footprints and key. Single-click, pick up and reopen the backpack to check that
   evidence remains visible and usable.
3. Report the discovered key to Finnigan. Ask Spark about Christopher and the key.
4. Reach Christopher's upstairs chest by the stairs. Use the key, target the
   chest, inspect its three contents and read the scroll. Move items between the
   chest and backpack, close/reopen, and save/load before leaving.
5. Follow Spark's testimony. Check that joining updates Party, and open his
   paperdoll and backpack there. Feeding, equipping and transferring items should
   use the same controls as Iolo's.
6. Question Gilberto and Johnson. Follow the ship lead, and optionally question
   Gargan, Klog, Ellen, Caroline and Petre about the evidence.
7. Give Finnigan the report. Try one incorrect answer and return to correct it.
   Verify the reward, geography questions and eventual password.
8. At a gate, try an incorrect password before the earned answer. Check the
   portcullis animation, collision and party following as you cross.
9. Save outside, quit, relaunch this same playtest, and confirm the party, evidence,
   reward and quest progress survived. Stop the campaign test after the town exit.
10. For optional town checks, buy food/provisions, rent a room, visit the healer,
    train, use a bed, fill a bucket, try the forge and test witnessed theft. Record
    the NPC's work hours and the exact refusal text when an action is unavailable.

For a bug report, retain the run name, active slot, screenshot, object/NPC name,
last action and whether Escape restores movement. The run's `host.log`,
`client.log` and native save make a reproducible report. Do not replace a stuck
state by granting flags or forcibly clearing a native movement hold.

## What was verified

| Path | Evidence and boundary |
| --- | --- |
| Original arrival and commission | Native new-game run and continuous UO run; original Iolo/Petre/Finnigan sequence, acceptance and stable-search question. Existing overhead regression also passed. |
| Stable entry and key | Original area trigger, real pickup and native backpack ownership; no supplied key. |
| Key report and estate | Finnigan unlocks the relevant topic; native stair ascent, targeted key use, locked-to-unlocked chest change, original scroll text and movement afterward. |
| Witnesses and ship lead | Spark's Hook testimony and Gilberto's Crown Jewel lead through UO dialogue controls. |
| Fellowship clues | Native Spark/Fellowship/Klog branch checked separately, including flags 63 and 65. |
| Party | Spark actually joins under native rules; separate leave, wait and rejoin checks. UO Party buttons opened his real paperdoll and backpack. |
| Incorrect report and saved progress | Wrong occupation rejected. Correct occupation/key followed by a wrong chest answer retains partial progress across load. |
| Reward and quiz recovery | Wrong valid numeric answers withhold the password; returning to the password topic succeeds. Exactly 100 gold awarded, with no second payment on quiz retry. |
| Gate security | Wrong passwords leave east, north and south gates closed. Earned password raises north/south gates in isolated native checks. Continuous UO run crosses the east gate. |
| Save/reload | Native world saved through F5 and restored through F9 outside the east gate; earned password and exterior position retained. |
| All town speakers | All 16 non-player placed/scheduled speakers responded and returned control. This is initial-topic coverage, not exhaustive traversal of their dialogue graphs. |
| Item dispatch | 26 starting inventory items and all 65 placed scripted/container families dispatched native use and recovered control; no unreachable family in this run. |
| Other interaction regressions | All 21 pre-existing suites passed: targeting, spellbook, theft/witnesses, creatures/combat, bucket effects, commerce/training, rest/potions, forge, companions, inventory, labels, panels, stacks, map/sign and audit isolation. |

The continuous UO proof invokes the same client actions, widgets and target manager
as play. It is not OS-level mouse automation for every input. Existing mouse
pickup/drop, hit-testing and single-click regressions provide separate coverage.
The branch matrix uses observer positioning in disposable saves, so it does not
prove walking access to every optional NPC or object.

## Original data census and wiring

The census covers native coordinates **928 ≤ x < 1120, 2080 ≤ y < 2352**. It reads
the owner's original `INITGAME.DAT`, `LINKDEP1`, `TFA.DAT`, town references and
readable original Usecode sources. Input/script hashes and every placement are
retained in `receipts/trinsic-trigger-audit.json`.

There are 17 placed/scheduled actors including the Avatar, 65 scripted/container
item families and 48 placed eggs (area triggers). All frames in that item-family
census have mapping entries. A mapping entry alone does not certify the final
artwork; see Spark's sling below. Weapons and other generic portable objects also
use native transfer/equipment/combat operations without needing a Usecode handler.

| Placed trigger family | Count | UO connection / coverage |
| --- | ---: | --- |
| Iolo arrival | 1 | Native action queue → dialogue/overhead channels; full arrival passed. |
| Stable clue eggs | 2 | Native movement/egg processing → quest state; route through the front entrance passed. Rear entrance is source-audited, not separately walked in this pass. |
| Murder cleanup | 1 | Original cleanup script removes bodies/blood after its native prerequisites. Snapshot removal is shared with other object deletion; the delayed departure/return scenario was not run. |
| Party remarks | 4 | Original speaker selection → native bark → UO mobile text. Shared channel passed; not all four probabilistic remarks were individually forced. |
| Haunted-house scripts | 11 | Seven chair turns, two door actions, nausea and fear; native posted actions, frames, statuses and barks are exported. Full haunted-house traversal and fear recovery remain a manual scenario. |
| Music | 7 | Original music cues and native audio / optional local Exult playback. Prior audio-option qualification applies; this pass did not listen to every regional cue. |
| Speech | 2 | Original speech tracks 31 and 24 use native audio. Listening to both exact area-triggered lines remains a manual check. |
| Weather | 9 | Original weather state reaches `TrinsicEffects`. UO rain/snow exist; special-palette weather and general day/night lighting do not yet have complete UO presentation. |
| Creature spawns | 7 | Native spawn → lifetime-qualified actor snapshot → UO body/costume. Horse/rat and body-animation regressions passed; every placed spawn probability/timetable was not replayed. |
| Teleports | 4 | Native party teleport updates the snapshot. Three destinations are outside the town atlas; those destinations are not part of this playable-town qualification. The fourth is local. |

Interaction routing is shared: native `Use`/`RunUsable` supplies conversations and
item actions, and normal movement processes eggs. Prompt modes 1/2 show text and
offered answers, 3 supplies validated numbers, 4 uses UO targeting, 5 presents the
original map/sign views, and 6 uses the native-style spellbook. Native objects,
party membership, positions, flags and posted actions remain authoritative.

Several historical flag names are misleading: flag 60 comes from entering the
stable clue area, 62 from unlocking the estate chest, 67 from Spark's Hook lead,
and 61 means the password was earned. Tests also assert inventory ownership,
chest shape, scroll text and witness choices, rather than treating one flag as
proof of all those actions. No frontend quest-state replacement was added.

## Remaining issues and boundaries

- **Spark's sling:** the currently installed mapping for shape 474/frame 0 points
  at custom art 49213, which appears as a purple placeholder in his backpack.
  The parallel armory review records an approved replacement, not yet installed
  in this runtime. This is a presentation/install issue, not a missing native
  weapon or party action. See `trigger-spark-panels-20261115/spark-1.png`.
- **Special-palette weather and global lighting:** native state exists, but the
  full UO visual response is unfinished. These do not block the investigation.
- **Teleport destinations and vehicle travel:** the native operations can leave
  the rendered town. Boat/cart travel and the destination areas are not certified
  for this town playtest.
- **Optional outcomes still need direct play:** full haunted-house sequence,
  delayed murder cleanup, every business-hours/insufficient-funds branch,
  Chantu's paid resurrection, pub rentals and vehicle purchases, death/revival,
  every spell, and all routes through the dialogue graph. Shared dispatch is
  wired; these outcomes are not being labelled as exhaustively tested.

Original rules to expect: shop services depend on NPC work schedules; several
Fellowship members refuse conversation at their evening meeting. Spark joins
after the Hook account even if the Avatar answers No. Wrong report answers and
an unsuccessful geography quiz can be retried. These are original Usecode rules.

## Repeating the qualification

`interaction-suite.py` now also includes `trigger-census`,
`frontend-murder-to-gate`, `trigger-branches` and `report-retries`, after the
pre-existing cases. Running the full suite provides their prerequisite saves.
The longer frontend journey takes roughly nine minutes on the tested machine.

The live replay mode is opt-in through `TRINSIC_REPLAY` plus
`TRINSIC_REPLAY_LIVE=1`. Input batches execute existing UO action handlers and
return acknowledged native snapshots. The Python adapter cannot connect to the
native pipe or send arbitrary native mutations; unsupported operations fail.
Movement planning waits for the applied native position, rather than using an
early command acknowledgement. Waits are bounded; only owned test processes and
run files are cleaned up. Ordinary game launches do not enable this mode.

The source census and branch tests keep reusable game-specific assertions while
the session's shell handles process execution. Computer-use capabilities and
current official documentation were checked before extending this existing
domain replay. No separate service, agent orchestrator or WSL workflow was added.
