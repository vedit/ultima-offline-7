import test from 'node:test';
import assert from 'node:assert/strict';
import {Session} from '../core.js';
import worker,{validate} from '../worker.js';
import {query,summarize,htmlReport} from '../report.mjs';
const make=()=>new Session({id:'12345678-1234-1234-1234-123456789abc',build:'abcdef0123456789',started:Math.floor(Date.now()/1000),now:0});
test('loading, hidden, unfocused and explicit pauses excluded; reading still counts',()=>{
 const s=make();s.event('draw',null,5000);s.tick(7000);assert.equal(s.data.activeMs,2000);
 s.event('visible',false,7000);s.event('draw',null,8000);s.tick(10000);assert.equal(s.data.activeMs,2000);
 s.event('visible',true,10000);s.event('focused',false,11000);s.tick(12000);assert.equal(s.data.activeMs,3000);
 s.event('focused',true,12000);s.event('paused',true,13000);s.tick(14000);assert.equal(s.data.activeMs,4000);
 s.event('paused',false,14000);s.event('draw',null,15000);s.tick(18000);assert.equal(s.data.activeMs,8000);
 assert.equal(s.snapshot(18000).loadMs,5000);
});
test('sleep, render stalls, failure and end cannot inflate playtime',()=>{
 const s=make();s.event('draw',null,0);s.tick(1000);s.tick(100000);assert.equal(s.data.activeMs,1000);
 s.event('draw',null,100000);for(let t=101000;t<=130000;t+=1000)s.tick(t);
 assert.equal(s.data.activeMs,16000);s.event('fail',null,130000);s.event('draw',null,131000);s.tick(132000);
 assert.equal(s.data.activeMs,16000);s.event('end',null,132000);s.tick(140000);assert.equal(s.data.wallMs,132000);
 assert.equal(s.data.state,'failed','Closing the page must preserve a recorded failure');
});
const frame=(x,flags='1 1 1 1 0 1 1 1',gate=true)=>`S 1 1 1 1 ok 0 0 0 1 0 0 0 0 0\nQ ${flags}\nE 1 721 0 ${x} 2214 0 0 0 0 1 0\n${gate?'E 2 271 0 1102 2214 8 0 -1 0 1 0\n':''}N private-name\nT private-dialogue`;
test('native flags and observed gate crossing; loaded outside or teleport is not crossing',()=>{
 const s=make();s.event('frame',frame(1076),0);assert.equal(s.data.trinsic,true);assert.equal(s.data.evidence,true);assert.equal(s.data.reported,true);
 s.event('frame',frame(1107),1);assert.equal(s.data.gate,false);
 s.event('frame',frame(1103),2);s.event('frame',frame(1104),3);assert.equal(s.data.gate,true);
 assert(!JSON.stringify(s.snapshot(3)).includes('private'));
 const a=make();a.event('frame',frame(1107),0);assert.equal(a.data.gate,false);
 const b=make();b.event('frame',frame(1103),0);b.event('frame',frame(1104,'0 0 0 0 0 0 0 0'),1);assert.equal(b.data.gate,false);
 const c=make();c.event('frame',frame(1103),0);c.event('frame',frame(1104,undefined,false),1);assert.equal(c.data.gate,false);
});
test('strict ingestion rejects extra/private data, invalid clocks and incompatible schema',()=>{
 const s=make();s.event('draw',null,1000);const d=s.snapshot(3000);assert(validate(d));
 for(const bad of [{...d,name:'Avatar'},{...d,id:[d.id]},{...d,activeMs:9999},{...d,ready:false},{...d,build:'../../private'},
  {...d,started:0},{...d,seq:-1},{...d,stage:'C:/private/game'}, {...d,wallMs:-1},{...d,v:2}])assert(!validate(bad));
});
test('CORS, rate limit, size bounds, and dataset fields verified',async()=>{
 const points=[];let allow=true;
 const env={INGEST_LIMIT:{limit:async()=>({success:allow})},PLAYTIME:{writeDataPoint:p=>points.push(p)}};
 const req=(body,origin='https://ultimaoffline7.com',method='POST')=>new Request('https://telemetry.ultimaoffline7.com/collect',{method,headers:{Origin:origin},...(method==='OPTIONS'?{}:{body})});
 const body=JSON.stringify(make().snapshot(0));
 let r=await worker.fetch(req(body),env);assert.equal(r.status,204);assert.equal(points.length,1);
 assert.equal(points[0].blobs.length,3);assert.equal(points[0].doubles.length,10);
 assert.equal(r.headers.get('Access-Control-Allow-Origin'),'https://ultimaoffline7.com');
 assert.equal((await worker.fetch(req(body,'https://evil.example'),env)).status,403);
 assert.equal((await worker.fetch(req('',undefined,'OPTIONS'),env)).status,204);
 assert.equal((await worker.fetch(req('x'.repeat(2049)),env)).status,400);
 assert.equal((await worker.fetch(req('{}'),env)).status,400);
 allow=false;assert.equal((await worker.fetch(req(body),env)).status,429);
 assert.equal(points.length,1);
});
test('report queries collapse retries per session and flag sampled data',()=>{
 assert.match(query(7),/GROUP BY index1/);assert.match(query(7),/max\(double4\)/);assert.throws(()=>query(90));
 const row={started:1,wallMs:120000,activeMs:60000,loadMs:1000,ready:1,trinsic:1,evidence:0,reported:0,gate:0,state:'ended',stage:'render',weight:1};
 const s=summarize([row,{...row,ready:0,activeMs:0,state:'failed',stage:'native',weight:2}]);
 assert.equal(s.launches,2);assert.equal(s.successfulLaunches,1);assert.equal(s.loadingFailures,1);assert.equal(s.loadingFailuresByStage.native,1);assert.equal(s.meanActiveMinutes,1);assert.equal(s.sampled,true);
 assert(!htmlReport(s).includes('12345678'));assert.throws(()=>summarize(Array(10001).fill(row)));
 assert.equal(summarize([]).meanActiveMinutes,0);
 const sampled=summarize([row,{...row,activeMs:120000,weight:100}]);
 assert.equal(sampled.launches,2);assert.equal(sampled.successfulLaunches,2);
 assert.equal(sampled.activeHours,3/60);assert.equal(sampled.meanActiveMinutes,1.5);
 assert.equal(sampled.medianActiveMinutes,1.5);assert.equal(sampled.reachedTrinsic,2);
 assert.match(htmlReport(sampled),/Observed sessions only/);
});
