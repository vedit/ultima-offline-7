import test from 'node:test';
import assert from 'node:assert/strict';
import {createDashboard,liveReport} from '../dashboard-worker.js';
import {summarize} from '../report-data.js';
const env={ACCOUNT_ID:'a'.repeat(32),ACCESS_AUD:'test-aud',ACCESS_EMAIL:'owner@example.test',ANALYTICS_READ_TOKEN:'test-secret'};
const ctx={access:{aud:'test-aud',getIdentity:async()=>({email:'owner@example.test'})}};
const row={started:1,wallMs:120000,activeMs:60000,loadMs:1000,ready:1,trinsic:1,evidence:0,reported:0,gate:0,state:'ended',stage:'render',weight:1};
const request=(path='/',init)=>new Request('https://analytics.example.test'+path,init);

test('dashboard refuses missing/forged Access and wrong audience/owner before querying',async()=>{
 let calls=0;const worker=createDashboard(async()=>{calls++;throw Error('must not query');});
 for(const context of [{},{access:{...ctx.access,aud:'other'}},{access:{...ctx.access,getIdentity:async()=>({email:'other@example.test'})}},{access:{...ctx.access,getIdentity:async()=>{throw Error('identity unavailable');}}}]){
   const r=await worker.fetch(request('/',{headers:{'Cf-Access-Jwt-Assertion':'forged','Cf-Access-Authenticated-User-Email':env.ACCESS_EMAIL}}),env,context);
   assert.equal(r.status,403);
 }
 assert.equal((await worker.fetch(request(),{...env,ACCESS_AUD:''},ctx)).status,403);assert.equal(calls,0);
});
test('dashboard uses fixed bounded SQL and exports only aggregates with private headers',async()=>{
 const worker=createDashboard(async(url,init)=>{
   assert.equal(url,`https://api.cloudflare.com/client/v4/accounts/${env.ACCOUNT_ID}/analytics_engine/sql`);
   assert.equal(init.headers.Authorization,'Bearer test-secret');assert.equal(init.redirect,'error');
   assert.match(init.body,/GROUP BY index1 LIMIT 10001/);assert.match(init.body,/FROM uo7_dataset/);
   return Response.json({data:[row,row]});
 });
 const r=await worker.fetch(request('/summary.json?days=30'),env,ctx);
 assert.equal(r.status,200);assert.equal(r.headers.get('Cache-Control'),'private, no-store');assert.equal(r.headers.get('Access-Control-Allow-Origin'),null);
 const text=await r.text(),json=JSON.parse(text);assert.equal(json.days,30);assert.equal(json.summary.successfulLaunches,2);assert.equal(json.summary.activeHours,1/30);
 assert.doesNotMatch(text,/test-secret|test-aud|owner@example|index1/);
});
test('dashboard validates requests, handles rate limits and never substitutes failed queries with zeroes',async()=>{
 let calls=0;const worker=createDashboard(async()=>{calls++;return new Response('private provider error',{status:403});});
 for(const path of ['/?days=0','/?days=31','/?days=NaN','/?sql=SELECT','/?days=7&token=anything'])assert.equal((await worker.fetch(request(path),env,ctx)).status,400);
 assert.equal((await worker.fetch(request('/other'),env,ctx)).status,404);
 assert.equal((await worker.fetch(request('/',{method:'POST'}),env,ctx)).status,405);
 assert.equal(calls,0);
 assert.equal((await worker.fetch(request(),{...env,REPORT_LIMIT:{limit:async()=>({success:false})}},ctx)).status,429);
 const r=await worker.fetch(request(),env,ctx);assert.equal(r.status,503);assert.doesNotMatch(await r.text(),/private provider error/);
 const truncated=createDashboard(async()=>Response.json({data:Array(10001).fill(row)}));
 assert.equal((await truncated.fetch(request(),env,ctx)).status,503);
});
test('live report preserves legacy unknown identity and provides controls without scripts or IDs',()=>{
 const html=liveReport(summarize([row]),7,'2026-11-18T00:00:00.000Z');
 assert.match(html,/Not collected yet/);assert.match(html,/name="days"/);assert.match(html,/<option value="7" selected>/);assert.match(html,/Refresh/);assert.match(html,/Download aggregate JSON/);assert.match(html,/Traffic dashboard/);
 assert.doesNotMatch(html,/<script|test-secret|owner@example/);
});
