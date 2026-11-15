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
11. Explore the haunted smithy by the west wall. Watch its chairs and door, and
    let any party sickness/fear finish before moving on. These depend on original
    saving throws; every party is not guaranteed to become sick. Save/reload there.
12. Return to the murder scene after completing the investigation and opening a
    gate. Its original cleanup trigger should remove the victims and evidence.
    Buying a ship/cart title is covered below; campaign vehicle travel is separate.

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
| Haunted smithy | All eleven original script eggs consumed during a UO traversal: seven chair triggers, two door triggers, nausea and fear. Observed changed furniture, temporary blood, overhead reactions and bend/kneel animation; Iolo returns to native Follow Avatar work. Save/load and movement recover. |
| Healer | Paid healing (30), poison cure (50) and real companion resurrection (400); possessions and living state survive load. Healthy targets, absent corpses, price refusal, cancellation and insufficient funds are covered. |
| Shops, training and titles | Quantity-based food/arrows, drink and provisions, room key, original combat training, ship deed and carriage title. Insufficient funds, business hours, full inventory, missing training points, capped combat and repeat ship purchase are checked. |
| Inn and world objects | Rented key unlocks the room; double-clicking the visible bed blanket reaches original rest controls. Bucket/well and bellows/fire checks exercise UO targeting and world picking. |
| After the investigation | Resume the earned gate-exit save, return to the stables and observe original cleanup removing the victims, blood and bucket. No quest flags are supplied. |

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
| Murder cleanup | 1 | Completed investigation → return to stables → native deletions disappear from UO. The script uses gate flag 87 and area activation; it does not enforce a separate 24-hour timer. |
| Party remarks | 4 | Original speaker selection → native bark → UO mobile text. Shared channel passed; not all four probabilistic remarks were individually forced. |
| Haunted-house scripts | 11 | All eleven original one-time eggs consumed. Furniture changes, nausea poses/blood/barks, fear recovery, save/load and subsequent movement passed. Low native attributes are a logged stress-test precondition; random rolls and scripts are unchanged. |
| Music | 7 | These placements select three original tracks (19, 27, 35). Regional trigger observations and music-only PCM output are checked; this does not certify every approach to all seven placements or local Exult recordings. |
| Speech | 2 | Both area-triggered Guardian lines (31 and 24) passed with original audio enabled, and separately with the original text fallback. Speech-only PCM output was non-silent. |
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

- **Well east of the pub:** UO accepts the bucket target, but the original script
  requests standing at native `(1071, 2235, 0)`, in the neighboring wall. Current
  native collision/pathfinding rejects that point. Refusal is displayed and
  movement recovers. The other three Trinsic wells complete their original walk,
  fill and drink sequence. This is a native path/data issue, not a lost UO target;
  no coordinate exception or collision bypass was added. A retail DOS comparison
  is still needed before deciding whether to change that original behavior.
  The earlier native-only well test positioned the observer on this blocked cell;
  it proved the animation/contents changes but overstated walking access.
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
- **Remaining campaign coverage:** every spell, every path through all dialogue,
  every probabilistic party remark, creature-spawn timetable and special weather
  outcome still need campaign tests. The optional Trinsic service/haunting matrix
  below covers the previously listed local activities, with the well exception
  above; it does not certify the rest of Britannia or all possible random outcomes.

Original rules to expect: shop services depend on NPC work schedules; several
Fellowship members refuse conversation at their evening meeting. Spark joins
after the Hook account even if the Avatar answers No. Wrong report answers and
an unsuccessful geography quiz can be retried. These are original Usecode rules.
Apollonia works overnight and sleeps from 03:00 to 06:00. Gargan's original
sextant script checks for 80 gold but omits charging it; that original script behavior is
preserved rather than replaced with a frontend transaction.

## Side-activity fixes and evidence

`receipts/trinsic-side-activities.json` records the additional disposable-save
cases, screenshots, binary hashes and regressions. Setup may supply money or
set native attributes/time/observer position before the client connects. The
client then owns the pipe, and actions under test use its normal widgets,
targeting and movement. Bed/forge checks additionally use visible pixel picking.
No original quest flags, scripts, schedules or saving throws are replaced.

Three shared connections were corrected. Developer's Wand HP editing/refill/copy and
the avatar stat snapshot now read/write live native item HP, matching combat,
healing and resurrection, instead of the separate NPC cache. Original bend/kneel
poses for humans now invoke stock UO's living bow animation; native posted actions still
control their timing and recovery. Native time advancement now serves read-only
bridge observations while waiting for original speech; resting no longer causes
a false disconnect warning. Gameplay commands remain refused during that wait,
and the existing connection timeout still detects an unresponsive engine. These
fixes add no item-specific gameplay rules.

## Repeating the qualification

`interaction-suite.py` now also includes `trigger-census`,
`frontend-murder-to-gate`, `trigger-branches`, `report-retries` and `trinsic-sides`, after the
pre-existing cases. Running the full suite provides their prerequisite saves.
The longer frontend journey takes roughly nine minutes on the tested machine.

For only the optional matrix, run:

```powershell
py -3 -B game/qualification/trinsic-side-activities.py --all --checkpoint <completed-native-save>
```

The checkpoint must come from an
earned murder-to-gate run; it is used only for carriage/cleanup prerequisites.
Other cases start from their own fresh investigation saves. Use `--case haunted`
(or another case name) for a focused repeat. Haunted nausea/fear and the inn's
random sleep speech allow at most four independent native attempts per invocation,
never a forced result. If the required random outcome is absent, qualification
reports it rather than silently counting that branch as covered; repeat the case
with a fresh run name.

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
