import {UUID,METRICS,MILESTONES} from './schema.js';
export function query(days=7,now=Date.now()) {
  if(!Number.isInteger(days)||days<1||days>89)throw Error('Choose 1–89 days');
  const since=Math.floor(now/1000)-days*86400;
  return `SELECT max(double1) AS started, max(double3) AS wallMs, max(double4) AS activeMs,
max(double5) AS loadMs, max(double6) AS ready, max(double7) AS trinsic,
max(double8) AS evidence, max(double9) AS reported, max(double10) AS gate,
argMax(blob2, double2) AS state, argMax(blob3, double2) AS stage,
max(_sample_interval) AS weight, max(double11) AS schemaVersion, max(double12) AS returning,
argMax(blob4, double2) AS player, argMax(blob5, double2) AS browser,
argMax(blob6, double2) AS os, argMax(blob7, double2) AS viewport,
argMax(blob8, double2) AS mode, argMax(blob9, double2) AS storage,
argMax(blob10, double2) AS music, argMax(blob11, double2) AS details
FROM uo7_dataset WHERE timestamp >= toDateTime(${since}) AND double1 >= ${since}
GROUP BY index1 LIMIT 10001 FORMAT JSON`;
}
export function summarize(rows) {
  if(!Array.isArray(rows) || rows.length>=10001)throw Error('Query missing or truncated; use a shorter reporting period');
  const strings=['state','stage','player','browser','os','viewport','mode','storage','music','details'];
  const data=rows.map(r=>Object.fromEntries(Object.entries(r).map(([k,v])=>[k,strings.includes(k)?v:Number(v)])));
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
  const v2=data.filter(r=>r.schemaVersion===2),identifiable=v2.filter(r=>UUID.test(r.player));
  const unique=a=>new Set(a.map(r=>r.player)).size;
  const breakdown=key=>{const counts={};for(const r of v2){const name=r[key]||'unknown';counts[name]=(counts[name]||0)+1;}return counts;};
  const metrics=Object.fromEntries(METRICS.map(k=>[k,0])),achieved=Object.fromEntries(MILESTONES.map(k=>[k,0])),stageMs={};
  const daily={},playersByDay=new Map();
  for(const r of identifiable.filter(r=>r.ready)){
    const day=new Date(r.started*1000).toISOString().slice(0,10);
    if(!playersByDay.has(day))playersByDay.set(day,new Set());playersByDay.get(day).add(r.player);
  }
  for(const [day,players]of [...playersByDay].sort())daily[day]=players.size;
  for(const r of v2){
    const d=JSON.parse(r.details||'{}');
    for(const key of METRICS){const n=d.metrics?.[key]||0;if(!Number.isFinite(n)||n<0)throw Error('Invalid detail metric');metrics[key]=key.startsWith('max')?Math.max(metrics[key],n):metrics[key]+n;}
    for(const [key,n]of Object.entries(d.stages||{})){if(!Number.isFinite(n)||n<0)throw Error('Invalid stage duration');stageMs[key]=(stageMs[key]||0)+n;}
    for(const key of MILESTONES)if(d.milestones?.[key]>=0&&!d.baseline?.includes(key))achieved[key]++;
  }
  return {observedSessions:data.length,sampled:data.some(r=>r.weight>1),launches:sum(data),
    uniqueBrowsers:unique(identifiable),activeBrowsers:unique(identifiable.filter(r=>r.ready)),returningBrowsers:unique(identifiable.filter(r=>r.returning)),
    sessionsWithoutIdentity:data.length-identifiable.length,expandedSessions:v2.length,dailyActiveBrowsers:daily,
    metrics,achieved,stageMs,breakdowns:Object.fromEntries(['browser','os','viewport','mode','storage','music'].map(k=>[k,breakdown(k)])),
    successfulLaunches:n,loadingFailures:sum(failed),incompleteLaunches:sum(data.filter(r=>!r.ready&&r.state!=='failed')),
    activeHours:sum(playable,'activeMs')/3600000,meanActiveMinutes:n?sum(playable,'activeMs')/n/60000:0,
    medianActiveMinutes:median/60000,meanSessionMinutes:n?sum(playable,'wallMs')/n/60000:0,
    reachedTrinsic:sum(playable,'trinsic'),foundEvidence:sum(playable,'evidence'),reportedMurder:sum(playable,'reported'),
    crossedEastGate:sum(playable,'gate'),loadingFailuresByStage:stages};
}
function detailsHtml(s){
  const esc=x=>String(x).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const table=(title,rows)=>`<h2>${esc(title)}</h2><table style="width:100%;border-collapse:collapse">${rows.map(([label,value])=>`<tr><td style="padding:8px;border-bottom:1px solid #465343">${esc(label)}</td><td style="text-align:right">${esc(value)}</td></tr>`).join('')}</table>`;
  if(!s.expandedSessions)return '<p>Expanded player/session reporting has no records in this period yet.</p>';
  return `<p>Expanded fields cover ${s.expandedSessions} sessions. Action counts are native command attempts, not proof that an action succeeded. Render gaps are heartbeat measurements, not FPS. Long-task measurements depend on browser support.</p>`+
    table('Daily active browser profiles (session start date, UTC)',Object.entries(s.dailyActiveBrowsers))+
    table('Session activity',Object.entries(s.metrics).map(([k,v])=>[k,k.endsWith('Ms')?(v/1000).toFixed(2)+' seconds':v]))+
    table('Loading stages',Object.entries(s.stageMs).map(([k,v])=>[k,(v/1000).toFixed(2)+' seconds']))+
    table('Milestones newly observed during a session',Object.entries(s.achieved))+
    Object.entries(s.breakdowns).map(([key,counts])=>table(key,Object.entries(counts))).join('');
}
export function htmlReport(summary) {
  const esc=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const labels={uniqueBrowsers:'Unique browser profiles',activeBrowsers:'Profiles reaching gameplay',returningBrowsers:'Returning profiles',sessionsWithoutIdentity:'Sessions without player identity',launches:'Launch attempts',successfulLaunches:'Rendered sessions',loadingFailures:'Loading failures',incompleteLaunches:'Unfinished loading attempts',activeHours:'Total active hours',meanActiveMinutes:'Average active minutes',medianActiveMinutes:'Median active minutes',meanSessionMinutes:'Average elapsed minutes',reachedTrinsic:'Observed in Trinsic',foundEvidence:'Key + chest evidence',reportedMurder:'Reported to Finnigan',crossedEastGate:'Observed east gate crossings'};
  return `<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Ultima Offline 7 · Playtest report</title><style>body{font:17px/1.6 system-ui;background:#151b18;color:#e8e4d7;max-width:900px;margin:50px auto;padding:24px}h1{font:36px Georgia}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:16px}.card{padding:20px;background:#202a23;border:1px solid #465343}.card b{display:block;font:32px Georgia;color:#d9bd7c}p{color:#bfc8bb}</style><h1>Ultima Offline 7 · Playtest report</h1><p>Generated ${esc(new Date().toISOString())}. ${summary.sampled?'Sampling detected: missing snapshots can understate duration and progress.':'No sampling detected in these rows.'} Observed sessions only, without extrapolation. Unique users means opted-in browser profiles, not people; clearing storage or changing browsers creates a new profile. Legacy sessions cannot be linked retrospectively. Sessions are not unique players. Loaded saves can already contain progress. Active and incomplete sessions are included through their latest received snapshot.</p><div class="grid">${Object.entries(labels).map(([key,label])=>`<div class="card">${esc(label)}<b>${esc(['uniqueBrowsers','activeBrowsers','returningBrowsers'].includes(key)&&!summary.expandedSessions?'Not collected yet':summary[key].toLocaleString('en',{maximumFractionDigits:2}))}</b></div>`).join('')}</div><p>Loading failures: ${esc(JSON.stringify(summary.loadingFailuresByStage))}</p><p>Turned-off reporting, blocked requests and abrupt closure cause undercounting. Gate crossings are observed movement, not proof of a full fresh-save playthrough.</p>${detailsHtml(summary)}</html>`;
}
