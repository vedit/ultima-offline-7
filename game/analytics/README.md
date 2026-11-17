# Browser playtest reporting

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

Run the installer **after every browser export**, before committing the Pages
update. It fails on changed integration anchors and is idempotent. The active
browser source/export tools are developed independently; this adapter preserves
their current output and does not replace or rebuild the WebAssembly binaries.
Do not publish the browser hooks until the collector and query access are verified.

Deploy `worker.js` and `core.js` as module files with `worker.js` as main module.
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
checks, a 2 KB streamed body cap, schema validation, bounded numeric fields and
an edge IP rate limit reduce accidents/abuse, but determined clients can forge
data. This is a playtest indicator, not billing, anti-cheat, or an exact census.

## Definitions

- One session is one launch attempt. A retry/reload starts a new in-memory UUID;
  no persistent user ID. A restored back-forward cached page keeps its session.
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
truncated 10,001-row result; narrow the period instead. Sample weights are applied
and sampled reports marked estimates; medians are calculated over those weights.
Engine retention is three months. Small/empty datasets are expected initially.

Browser controls expose opt-out, honor DNT/GPC, and keep the preference local.
Application request logging is disabled. Cloudflare still processes network
metadata. See the shipped privacy page for the exact user-facing description.

References: [Analytics Engine](https://developers.cloudflare.com/analytics/analytics-engine/),
[SQL API](https://developers.cloudflare.com/analytics/analytics-engine/sql-api/),
[limits](https://developers.cloudflare.com/analytics/analytics-engine/limits/).
