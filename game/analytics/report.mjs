// Consume the authenticated Analytics Engine query response; no account secret
// or individual session IDs are embedded in the resulting report.
import {readFile,writeFile} from 'node:fs/promises';
import {pathToFileURL} from 'node:url';
export function query(days=7,now=Date.now()) {
  if(!Number.isInteger(days)||days<1||days>89)throw Error('Choose 1–89 days');
  const since=Math.floor(now/1000)-days*86400;
  return `SELECT max(double1) AS started, max(double3) AS wallMs, max(double4) AS activeMs,
max(double5) AS loadMs, max(double6) AS ready, max(double7) AS trinsic,
max(double8) AS evidence, max(double9) AS reported, max(double10) AS gate,
argMax(blob2, double2) AS state, argMax(blob3, double2) AS stage,
max(_sample_interval) AS weight
FROM uo7_dataset WHERE timestamp >= toDateTime(${since}) AND double1 >= ${since}
GROUP BY index1 LIMIT 10001 FORMAT JSON`;
}
export function summarize(rows) {
  if(!Array.isArray(rows) || rows.length>=10001)throw Error('Query missing or truncated; use a shorter reporting period');
  const data=rows.map(r=>Object.fromEntries(Object.entries(r).map(([k,v])=>[k,['state','stage'].includes(k)?v:Number(v)])));
  // SQL already collapses every session's cumulative heartbeats into one row.
  // _sample_interval describes sampled heartbeat rows, not extra sessions;
  // multiplying per-session maxima by it would inflate counts and playtime.
  const sum=(a,key)=>a.reduce((n,r)=>n+(key?r[key]:1),0);
  if(data.some(r=>!Number.isFinite(r.activeMs)||!Number.isFinite(r.wallMs)||!Number.isFinite(r.weight)||r.weight<1))throw Error('Invalid report rows');
  const playable=data.filter(r=>r.ready), failed=data.filter(r=>!r.ready&&r.state==='failed');
  const n=sum(playable), ordered=[...playable].sort((a,b)=>a.activeMs-b.activeMs);
  const rankValue=rank=>ordered[rank-1]?.activeMs||0;
  const median=n?(rankValue(Math.floor((n+1)/2))+rankValue(Math.ceil((n+1)/2)))/2:0;
  const stages={};for(const r of failed)stages[r.stage]=(stages[r.stage]||0)+1;
  return {observedSessions:data.length,sampled:data.some(r=>r.weight>1),launches:sum(data),
    successfulLaunches:n,loadingFailures:sum(failed),incompleteLaunches:sum(data.filter(r=>!r.ready&&r.state!=='failed')),
    activeHours:sum(playable,'activeMs')/3600000,meanActiveMinutes:n?sum(playable,'activeMs')/n/60000:0,
    medianActiveMinutes:median/60000,meanSessionMinutes:n?sum(playable,'wallMs')/n/60000:0,
    reachedTrinsic:sum(playable,'trinsic'),foundEvidence:sum(playable,'evidence'),reportedMurder:sum(playable,'reported'),
    crossedEastGate:sum(playable,'gate'),loadingFailuresByStage:stages};
}
export function htmlReport(summary) {
  const esc=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const labels={launches:'Launch attempts',successfulLaunches:'Rendered sessions',loadingFailures:'Loading failures',incompleteLaunches:'Unfinished loading attempts',activeHours:'Total active hours',meanActiveMinutes:'Average active minutes',medianActiveMinutes:'Median active minutes',meanSessionMinutes:'Average elapsed minutes',reachedTrinsic:'Observed in Trinsic',foundEvidence:'Key + chest evidence',reportedMurder:'Reported to Finnigan',crossedEastGate:'Observed east gate crossings'};
  return `<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Ultima Offline 7 · Playtest report</title><style>body{font:17px/1.6 system-ui;background:#151b18;color:#e8e4d7;max-width:900px;margin:50px auto;padding:24px}h1{font:36px Georgia}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:16px}.card{padding:20px;background:#202a23;border:1px solid #465343}.card b{display:block;font:32px Georgia;color:#d9bd7c}p{color:#bfc8bb}</style><h1>Ultima Offline 7 · Playtest report</h1><p>Generated ${esc(new Date().toISOString())}. ${summary.sampled?'Sampling detected: missing snapshots can understate duration and progress.':'No sampling detected in these rows.'} Observed sessions only, without extrapolation. Sessions are not unique players. Loaded saves can already contain progress. Active and incomplete sessions are included through their latest received snapshot.</p><div class="grid">${Object.entries(labels).map(([key,label])=>`<div class="card">${esc(label)}<b>${esc(summary[key].toLocaleString('en',{maximumFractionDigits:2}))}</b></div>`).join('')}</div><p>Loading failures: ${esc(JSON.stringify(summary.loadingFailuresByStage))}</p><p>Turned-off reporting, blocked requests and abrupt closure cause undercounting. Gate crossings are observed movement, not proof of a full fresh-save playthrough.</p></html>`;
}
if(process.argv[1]&&import.meta.url===pathToFileURL(process.argv[1]).href) {
  const [mode,arg,out]=process.argv.slice(2);
  if(mode==='--query')console.log(query(Number(arg||7)));
  else if(mode==='--input') {const result=JSON.parse(await readFile(arg,'utf8'));const s=summarize(result.data);console.log(JSON.stringify(s,null,2));if(out)await writeFile(out,htmlReport(s));}
  else throw Error('Usage: node report.mjs --query 7 | --input query-result.json report.html');
}
