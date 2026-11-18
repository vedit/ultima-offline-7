import test from 'node:test';
import assert from 'node:assert/strict';
import {PlayerSession} from '../session-v2.js';
import worker,{validate} from '../worker.js';
import {summarize,htmlReport} from '../report.mjs';
const player='aaaaaaaa-aaaa-4aaa-aaaa-aaaaaaaaaaaa';
const make=()=>new PlayerSession({id:crypto.randomUUID(),player,build:'abcdef1234567',started:Math.floor(Date.now()/1000),now:0});
const frame=flags=>`S 1 1 1 1 ok\nQ ${flags}\nE 1 721 0 1076 2214 0 0 0 0 1 0\nN private name\nT private dialogue`;

test('suspension and the 24-hour cap never create overlapping or invalid durations',()=>{
 const s=make();s.event('draw',null,0);s.tick(1000);s.tick(60000);
 assert.equal(s.data.metrics.suspendedMs,59000);assert.equal(s.data.activeMs,1000);
 s.tick(86400000);s.event('visible',false,86400010);s.event('draw',null,86401000);
 const d=s.snapshot(86402000);assert.equal(d.wallMs,86400000);
 assert(validate(d,(d.started+86402)*1000));
 assert.equal(d.activeMs+Object.entries(d.metrics).filter(([k])=>['hiddenMs','unfocusedMs','pausedMs','stalledMs','suspendedMs'].includes(k)).reduce((n,[k,v])=>n+v,0),d.wallMs);
});
test('v2 timing, native action categories, completed saves and failure counters',()=>{
 const s=make();s.event('context',{mode:'new'},0);s.event('stage','native',0);s.event('draw',null,1000);
 s.event('visible',false,3000);s.event('visible',true,5000);s.event('focused',false,5000);s.event('focused',true,6000);
 s.event('paused',true,6000);s.event('paused',false,7000);s.event('draw',null,7000);
 s.event('action',{op:'MOVE',result:'ok'},7000);s.event('action',{op:'STEP',result:'blocked'},7000);s.event('action',{op:'BOOKCAST',result:'using'},7000);
 s.event('saved',{kind:'auto',ms:40},7000);s.event('saved',{kind:'manual',ms:50},7000);s.event('saved',{kind:'load',ms:60},7000);s.event('save-fail',null,7000);
 s.event('longtask',100,7000);s.event('frame',frame('0 0 0 0 0 0 0 0'),7000);s.event('frame',frame('1 1 1 0 0 0 0 0'),8000);
 const d=s.snapshot(8000);assert(validate(d));assert.equal(d.activeMs,3000);assert.equal(d.metrics.hiddenMs,2000);assert.equal(d.metrics.unfocusedMs,1000);assert.equal(d.metrics.pausedMs,1000);
 assert.equal(d.metrics.inventory,1);assert.equal(d.metrics.movement,1);assert.equal(d.metrics.spells,1);assert.equal(d.metrics.rejectedActions,1);
 assert.equal(d.metrics.autoSaves,1);assert.equal(d.metrics.manualSaves,1);assert.equal(d.metrics.loads,1);assert.equal(d.metrics.saveMs,150);
 assert.equal(d.milestones.evidence,8000);assert.deepEqual(d.baseline,[]);assert(!JSON.stringify(d).includes('private'));
 s.event('end',null,8000);s.event('saved',{kind:'manual',ms:20},9000);assert.equal(s.snapshot(10000).metrics.manualSaves,1);
});
test('resumed progress is a baseline; unknown fields and impossible metric payloads are rejected',()=>{
 const s=make();s.event('context',{mode:'resume'},0);s.event('frame',frame('1 1 1 0 0 0 0 0'),0);const d=s.snapshot(0);assert(validate(d));assert.deepEqual(d.baseline,['trinsic','evidence','reported']);
 for(const bad of [{...d,name:'private'},{...d,player:'email@example.com'},{...d,context:{...d.context,userAgent:'private'}},{...d,metrics:{...d.metrics,coordinates:1}},
  {...d,metrics:{...d.metrics,activeMs:1}},{...d,metrics:{...d.metrics,hiddenMs:1}},{...d,metrics:{...d.metrics,actions:1}},{...d,baseline:['gate']},{...d,milestones:{...d.milestones,gate:0}}])assert(!validate(bad));
});
test('expanded rows retain old columns and fit Analytics Engine limits',async()=>{
 const d=make().snapshot(0),points=[];
 const r=await worker.fetch(new Request('https://telemetry.ultimaoffline7.com/collect',{method:'POST',headers:{Origin:'https://ultimaoffline7.com'},body:JSON.stringify(d)}),{INGEST_LIMIT:{limit:async()=>({success:true})},PLAYTIME:{writeDataPoint:p=>points.push(p)}});
 assert.equal(r.status,204);assert.equal(points[0].blobs[3],player);assert.equal(points[0].doubles.length,20);assert(points[0].blobs.length<=20);assert(JSON.stringify(d).length<8192);
});
test('unique/returning profiles are deduplicated; legacy and unknown IDs are not invented',()=>{
 const s=make();s.event('draw',null,0);const d=s.snapshot(1000);
 const row={started:d.started,wallMs:d.wallMs,activeMs:d.activeMs,loadMs:0,ready:1,trinsic:0,evidence:0,reported:0,gate:0,state:'ended',stage:'render',weight:1,schemaVersion:2,returning:0,player,browser:'chrome',os:'windows',viewport:'large',mode:'new',storage:'browser',music:'native',details:JSON.stringify({metrics:d.metrics,stages:d.stages,milestones:d.milestones,baseline:[]})};
 const summary=summarize([row,{...row,returning:1},{...row,player:''},{...row,schemaVersion:0,player:''}]);
 assert.equal(summary.uniqueBrowsers,1);assert.equal(summary.activeBrowsers,1);assert.equal(summary.returningBrowsers,1);assert.equal(summary.sessionsWithoutIdentity,2);assert.equal(summary.launches,4);
 assert.equal(Object.values(summary.dailyActiveBrowsers)[0],1);assert(!htmlReport(summary).includes(player));
});
