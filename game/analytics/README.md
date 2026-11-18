# Browser playtest reporting

Version 2 adds a persistent random browser-profile ID after explicit opt-in.
It is pseudonymous, not a cross-device person/account identifier. Each launch
still has its own session ID. Returning means this profile previously reached a
rendered frame. Unique counts exclude legacy sessions and sessions where an ID
could not be persisted. Clearing storage, resetting the ID or another browser
can count as a new profile; shared profiles can combine different people.

The v2 preference is independent of the old session-only preference. It defaults
off, honors DNT/GPC, stops immediately on opt-out, removes the local ID, and
synchronizes opt-out/reset across tabs. Reset does not delete historical rows.
Settings never touch game saves. This remains browser-only instrumentation.

This optional layer observes the existing browser launcher and native `Q`/`E`
snapshot rows. U7 logic, inputs, randomness and saves are unchanged. The native
Cloudflare connector handles deployment and queries; there is no agent service,
custom orchestration server, or browser-held API token.

## Build and publish

Requires Python 3 and Node 22+ for installation/tests; no npm dependencies.

```
node --test game/analytics/tests/*.test.mjs
python game/analytics/install.py /path/to/prepared/pages/play
```

Run the installer **before exact-bundle parity verification and publication**.
For the editable launcher, use `install.py <web/public> --launcher client.html`;
for its prepared export use `install.py <prepared-client>`. Run the existing
full parity replay and release gate after installation, including opt-in/off
browser checks. Never patch an already-qualified game bundle and reuse its old
acceptance receipt. It fails on changed integration anchors and is idempotent. The active
browser source/export tools are developed independently; this adapter preserves
their current output and does not replace or rebuild the WebAssembly binaries.
Do not publish the browser hooks until the collector and query access are verified.

Deploy `worker.js`, `core.js` and `schema.js` as module files with `worker.js` as main module.
The standard Wrangler configuration is also provided. With the Cloudflare
connector, upload multipart metadata using these bindings:

```json
[
  {"type":"analytics_engine","name":"PLAYTIME","dataset":"uo7_dataset"},
  {"type":"ratelimit","name":"INGEST_LIMIT","namespace_id":"7001","simple":{"limit":60,"period":60}}
]
```

Use compatibility date `2026-11-17`, disable observability/logging, and attach
only `telemetry.ultimaoffline7.com` as a Worker custom domain. The homepage and
game remain on GitHub Pages. A staging Worker must use its **own dataset** so
smoke tests cannot pollute player statistics. Keep authentication in Cloudflare's
connector or the operator's environment, never in site files or git.

The POST endpoint is public, not authenticated gameplay evidence. Explicit origin
checks, an 8 KB streamed body cap, schema validation, bounded numeric fields and
an edge IP rate limit reduce accidents/abuse, but determined clients can forge
data. This is a playtest indicator, not billing, anti-cheat, or an exact census.

## Definitions

- One session is one launch attempt. A retry/reload starts a new in-memory UUID.
  A restored back-forward cached page keeps its session. V2 links sessions only
  through the opted-in browser ID; no IP-based identity or fingerprinting.
- Rendered session: the first actual ClassicUO `draw-heartbeat`, not a Play click.
- Active time: rendered, visible, focused, non-failed time with a recent drawing
  heartbeat. Native dialogue/inventory holds still count. Explicit client
  `paused`/`resumed` signals are supported; the current browser slice has no
  separate pause control. Focus/visibility loss is wired today. Computer sleep
  gaps over 15 seconds are discarded; rendering stalls can overcount up to 15s.
- Elapsed time includes loading/background time, capped at 24 hours per launch.
  An unattended visible game can count as active time. No input history is sent.
- Evidence means native flags 60 and 62 (key found and chest searched).
  Reported means flag 61 (Finnigan awards the password). These may already be set
  in a resumed save. See `game/qualification/investigation.py`.
- Reached Trinsic means an on-map Avatar within the town envelope. Gate exit
  requires a nearby observed east-gate crossing at y=2210–2218, x=1103→1104,
  flag 61, and the native portcullis raised. Loaded outside and long teleports do
  not qualify. It does not prove the entire investigation happened this session.
- Loading failures use fixed stages, never error text, stack traces or paths.
  Abrupt loading-tab closure without a failure callback is an unfinished attempt.
- Cumulative snapshots every 30s plus lifecycle transitions. Use maxima grouped
  by session, **never sum the heartbeat rows**. Missing final network deliveries
  undercount the tail; closed/crashed sessions remain usable through last snapshot.

## Read a report

The report now includes observed unique/active/returning browser profiles,
daily active profiles grouped by session start date (UTC), new/resumed journeys,
browser/OS families, viewport buckets, save destination and music selection.
V2 details also contain exclusive hidden/unfocused/paused/stalled/suspended
duration counters, render-heartbeat gaps (not FPS), supported main-thread long
tasks, native action attempts and rejections by category, completed saves/loads
with timing and failures, and first-observed milestone times. Resumed progress
present in the initial world snapshot is a baseline, not a newly earned milestone.
Native action categories use the existing bridge opcodes, without their arguments.
The first ten numeric columns and three blob columns remain compatible with v1.

V2 column layout: blob4 browser ID; blob5–10 browser, OS, viewport, journey,
save mode, music; blob11 the bounded details object. Double11 schema version,
double12 returning, double13–16 hidden/unfocused/paused/stalled milliseconds,
double17–20 automatic saves, manual saves, loads and errors. Session remains the
single index. New queries group by session and select details with `argMax` by
sequence. Never sum cumulative snapshots or multiply session rows by event
sampling weights. Browser IDs exist only in private query results; the report
aggregates them and does not embed them in HTML. Old reports cannot acquire IDs
retroactively. Use the same report generator for mixed-version datasets.

The dataset is private to the Cloudflare account, separate from Web Analytics.
The operator or an authorized agent can query it with Account Analytics Read:

```
node game/analytics/report.mjs --query 7
```

POST the printed SQL (text/plain) to Cloudflare's official endpoint
`/accounts/{account_id}/analytics_engine/sql` using the connected plugin. Save
the returned JSON locally, then:

```
node game/analytics/report.mjs --input query-result.json playtest-report.html
```

The HTML contains aggregates only and needs no network connection. No raw session
IDs are selected or included. Results cover sessions started in the last N days,
including still-open sessions, not just completed sessions. The report refuses a
truncated 10,001-row result; narrow the period instead. Each returned session is
counted once. The sampling interval describes heartbeat events, so it must not
multiply grouped session counts, cumulative maxima or session medians. Reports
flag sampling: missing snapshots can understate duration, progress and session
coverage. These are observed sessions, not an extrapolated population estimate.
Engine retention is three months. Small/empty datasets are expected initially.

For an explicitly approved temporary staging endpoint, `tests/live.mjs` sends
two synthetic sessions as six deliveries (including repeats and an older
snapshot). Query the separate smoke dataset and verify two sessions, one
successful launch, one loading failure and exactly 8,000 active milliseconds.
Remove the smoke Worker after verification. Synthetic data must never be sent
to the production dataset.

`tests/live-v2.mjs` covers mixed v1/v2 ingestion, two browser IDs, a returning
profile, and repeated/out-of-order snapshots. Its separate smoke dataset must
report four sessions, two unique profiles, one returning profile, one loading
failure, one automatic save and 10,500 active milliseconds from seven deliveries.
The script refuses the production URL. Remove the smoke Worker afterward.

## November 18 rollout status

The backward-compatible v2 collector is deployed and its isolated Cloudflare
ingestion/query test passed. The browser installer, controls and reports are
implemented and tested separately. **The browser hooks are not published yet.**
The parallel game build changed after its acceptance run, so the shared release
gate blocks publication pending a fresh full replay. Install this version in
the final candidate before that replay; do not copy the old parity receipt.
The current eight legacy reports contain no persistent browser IDs and cannot
be converted into unique-player counts. See `receipts/2026-11-18-v2.json`.

Browser controls expose opt-out, honor DNT/GPC, and keep the preference local.
Application request logging is disabled. Cloudflare still processes network
metadata. See the shipped privacy page for the exact user-facing description.

References: [Analytics Engine](https://developers.cloudflare.com/analytics/analytics-engine/),
[SQL API](https://developers.cloudflare.com/analytics/analytics-engine/sql-api/),
[limits](https://developers.cloudflare.com/analytics/analytics-engine/limits/).
