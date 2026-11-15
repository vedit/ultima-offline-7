# Trinsic interaction qualification

The native Black Gate engine owns outcomes. ClassicUO supplies gestures and presents the resulting state. There are no replacement bread, key, bucket, merchant, training or combat rules in the client.

Run `py -3 -B game/qualification/interaction-suite.py` from the repository root. To target an already-built candidate without replacing the development binaries, set `TRINSIC_HOST_EXECUTABLE` to its `Ultima7.exe` and `TRINSIC_CLIENT_BIN` to its client directory. For the qualified candidate:

```powershell
$env:TRINSIC_HOST_EXECUTABLE = 'E:/UltimaOffline/PoCs/ClassicUO-U7-Local/build-side-20261115/bin/Ultima7.exe'
$env:TRINSIC_CLIENT_BIN = 'E:/UltimaOffline/PoCs/ClassicUO-U7-Local/client/bin/Trinsic-Sides-20261115'
py -3 -B game/qualification/interaction-suite.py
```

Each case uses a private save and owned host/client processes. Results and per-case logs are in `runs/full-interaction-suite` under the local game installation. Supplying case names runs only those cases and writes a separate results file. The November 14 baseline is recorded in `receipts/full-interactions.json`; the November 15 side-activity candidate and deployment are recorded in `receipts/trinsic-side-activities.json`.

| Interaction | Authority and current evidence |
| --- | --- |
| Item use across town | Original `Use` / `RunUsable`; 26 inventory items and 65 reachable town families checked for dispatch, prompt completion/cancellation and restored movement. This checks one instance per family, not every outcome. |
| Object and ground targeting | Original target callback; invalid coordinates, cancellation, ground selection and feeding have separate assertions. |
| Food and companions | Native consumption; companion dialogue and paperdoll together; inventory transfer, equipment rejection and save/restart. |
| Keys and doors | Original murder-scene key unlocks Christopher's chest; investigation opens doors and earns the gate password. |
| Spellbook | Native ClassicUO SpellbookGump, stock art/circle tabs/page corners/minimization; all 72 U7 spell entries including cantrips, original learned bits, reagent requirements/counts, save/load bookmark, resource refusal and Awaken invocation. Mouse selection/double-click casting, right-click/Escape closing and movement recovery are exercised. Other spell effects are not all qualified. |
| Theft and placement | Native ownership reconciliation, `ReportCrime`, egg triggers and settling after successful placement. Rejected drops retain ownership and location. Petre and the gate guard also emit their original witness objections. Escalated guard combat and every witness outcome are not exhaustively qualified. |
| Creatures and combat | Nearby extra creature records exported; matching stock UO bodies, original health and combat state, attack/casting poses. All mapped bodies have walk/attack frames in five stored directions. An original attack damages a spawned rat; peace restores movement. U7-specific unmatched creatures and all projectile/death effects still need visual coverage. |
| Buckets | Original blood-drinking refusal, ground blood creation, well filling, drinking and saved frame/ownership. Three wells have complete UO walk/fill/drink coverage. The pub-side well's scripted standing point is blocked by native collision; its refusal and movement recovery are covered, with no frontend bypass. The earlier observer-positioned native test did not prove access to that well. The blood bucket can pour repeatedly according to its original quality value. |
| Commerce and training | Dell takes 2 gold and supplies a bucket. Markus takes 20 gold and increases combat skill through the original student-selection dialogue. |
| Potions | Original consumption, full-health cap, poison status and cure. Other potion varieties have dispatch coverage where present, not exhaustive effects. |
| Rest | Original numeric hours choice, one-hour time advance, wake-up and recovered movement. Tests approach the bed from its free side; native reach checks remain authoritative. |
| Forge | Original bellows frames, fire heating and cooldown. The Trinsic blank's original frame is preserved; tests do not manufacture a different forging scenario. |
| Containers and equipment | ClassicUO mouse pickup, transfer, equip/unequip, refusal, icon repositioning, close/reopen and process restart. Gold split/merge and failed-drop rollback conserve quantities. |
| Feedback and controls | Single-click names, NPC overhead reactions, stack sliders, status load, Tab and paperdoll war/peace controls. |
| Map and signs | Original displays surfaced in ClassicUO, close/Escape, movement after dismissal. |
| Murder to gate | Existing original investigation walkthrough, dialogue choices, evidence and gate exit; no quest flags granted by the adapter. |
| Audit setup isolation | Book creation, ownership setup and creature spawning are rejected without the explicit private audit environment. |

Baking and weaving are original engine routines, but the Trinsic source census has no baking hearth or loom. Their complete production chains are outside this town qualification. Vehicles, other towns, all spells and alternate quest outcomes also need their own campaign tests. Passing this suite is not a claim that every Black Gate interaction or visual effect has been exhaustively tested.

The broad town matrix positions an observer near source objects, then uses original interactions. It does not certify a walkable path to every item. The murder-to-gate case separately exercises normal movement and quest progression. No check forcibly clears native movement holds to turn a failure into a pass.

The spellbook uses a structured mode-6 prompt instead of the U7 raster view. `K` identifies the book and bookmark; `L` carries the 72 original learned flags, reagent cast counts, masks and source-routine display names; `J` supplies original reagent names. `BOOKSELECT` and `BOOKCAST` require the current prompt token and a learned spell index. Original `CanCastSpell` / `TryToCastSpell` retain level, mana, reagent consumption, targeting and Usecode effects. The client only arranges the stock UO book pages; it cannot grant or cast an unlearned spell. Existing mode-5 map and sign displays remain separate.

The native UO spellbook requalification on November 15 is recorded in `receipts/spellbook-controls.json`. It supersedes the raster-book entry in the November 14 full-suite receipt. World targeting, map/sign presentation and audit isolation also passed focused regression runs.

The November 15 [Trinsic playtest audit](TRINSIC-PLAYTEST.md) adds a continuous
original-arrival-to-east-gate ClassicUO journey, all-town-speaker and gate branch
checks, report/quiz recovery with an exactly-once reward, and a source census of
48 area triggers. See `receipts/trinsic-trigger-audit.json` for input hashes,
evidence and explicit coverage limits. The full suite now includes these cases;
passing shared dispatch does not imply every optional trigger has been replayed.

The subsequent side-activity pass is recorded in
`receipts/trinsic-side-activities.json`. It exercises all eleven haunted-smithy
script triggers, paid healing/cure/resurrection, inn food/drink/rental/rest,
training, provisions/ammunition, ship/cart titles, native sextant use, refusal
branches, post-investigation cleanup, Guardian speech and regional music through
the UO frontend. Original bed/forge sprites also receive pixel-picked double-clicks.
Run `trinsic-side-activities.py --all --checkpoint <earned-gate-exit-save>` to
repeat the matrix independently; the full interaction suite includes it as
`trinsic-sides` after producing its prerequisite investigation save.

This pass corrects shared presentation/debug connections: live native HP
now supplies stat inspection/edit/refill/duplication and the avatar snapshot;
native human bend/kneel poses invoke stock UO bow animation; read-only bridge
observations continue during native rest/speech waits, preventing a false
disconnect while preserving mutation gating. Original item
scripts, costs, saving throws, actor schedules and quest progression remain the
authority. The health regression compares inspection with live combat/status
records so a matching but stale debug cache cannot pass unnoticed.
