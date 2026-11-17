// Explicitly opt-in network qualification against a disposable smoke Worker.
// Never invoke against production: these are synthetic sessions.
import assert from 'node:assert/strict';
import {randomUUID} from 'node:crypto';
const endpoint=process.argv[2];
assert.equal(endpoint,'https://uo7-playtime-smoke.artifactsystems.workers.dev/collect');
const base={v:1,id:randomUUID(),build:'0000000000000000',started:Math.floor(Date.now()/1000)-30,
 seq:1,state:'loading',stage:'native',wallMs:0,activeMs:0,loadMs:0,
 ready:false,trinsic:false,evidence:false,reported:false,gate:false};
const ready={...base,seq:2,state:'playing',stage:'render',wallMs:6000,activeMs:3000,loadMs:2000,ready:true,trinsic:true};
const ended={...ready,seq:3,state:'ended',wallMs:10000,activeMs:8000,evidence:true,reported:true,gate:true};
const failed={...base,id:randomUUID(),seq:2,state:'failed',stage:'client',wallMs:2500};
for(const d of [base,ready,ended,ended,ready,failed]) {
 const response=await fetch(endpoint,{method:'POST',headers:{Origin:'https://ultimaoffline7.com','Content-Type':'text/plain'},body:JSON.stringify(d),signal:AbortSignal.timeout(20000)});
 assert.equal(response.status,204,await response.text());
}
console.log(JSON.stringify({sent:6,expectedSessions:2,expectedActiveMs:8000,expectedLoadingFailures:1,started:base.started}));
