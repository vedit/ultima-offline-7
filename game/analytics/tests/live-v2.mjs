// Synthetic data is permitted only at the explicitly approved disposable Worker.
import assert from 'node:assert/strict';
import {PlayerSession} from '../session-v2.js';
import {validate} from '../worker.js';
const endpoint=process.argv[2];
assert.equal(endpoint,'https://uo7-playtime-smoke.artifactsystems.workers.dev/collect');
const started=Math.floor(Date.now()/1000)-60,player=crypto.randomUUID();
const make=(id=player,returning=false)=>new PlayerSession({id:crypto.randomUUID(),player:id,returning,build:'0000000000000002',started,now:0});
const s=make();s.event('context',{mode:'new'},0);s.event('stage','client',0);s.event('draw',null,1000);
s.event('action',{op:'USE',result:'ok'},1000);s.event('saved',{kind:'auto',ms:90},1000);
const early=s.snapshot(5000);s.event('end',null,9000);const ended=s.snapshot(9000);
const returning=make(player,true);returning.event('draw',null,500);returning.event('end',null,2500);
const failed=make(crypto.randomUUID());failed.event('stage','native',0);failed.event('fail',null,2500);
const legacy={v:1,id:crypto.randomUUID(),build:'0000000000000002',started,seq:1,state:'ended',stage:'render',wallMs:1000,activeMs:500,loadMs:500,ready:true,trinsic:false,evidence:false,reported:false,gate:false};
for(const data of [early,ended,ended,early,returning.snapshot(2500),failed.snapshot(2500),legacy]){
 assert(validate(data));
 const response=await fetch(endpoint,{method:'POST',headers:{Origin:'https://ultimaoffline7.com','Content-Type':'text/plain'},body:JSON.stringify(data),signal:AbortSignal.timeout(20000)});
 assert.equal(response.status,204,await response.text());
}
console.log(JSON.stringify({started,sent:7,expectedSessions:4,expectedUniqueBrowsers:2,expectedReturningBrowsers:1,expectedActiveMs:10500,expectedLoadingFailures:1,expectedAutoSaves:1}));
