import test from 'node:test';
import assert from 'node:assert/strict';
import {connect,PREFERENCE,IDENTITY,browserContext} from '../browser.js';
import {validate} from '../worker.js';

test('explicit consent, stable identity, returning profiles, reset, cross-tab opt-out and privacy',async()=>{
 const names=['window','document','navigator','localStorage','fetch','setInterval','clearInterval','performance'];
 const original=Object.fromEntries(names.map(k=>[k,Object.getOwnPropertyDescriptor(globalThis,k)]));
 const values=new Map(),posts=[];let time=0,interval,storageFails=false;
 const check=new EventTarget(),reset=new EventTarget(),document=new EventTarget(),window=new EventTarget();
 Object.assign(document,{hidden:false,hasFocus:()=>true,querySelector:q=>q.startsWith('meta')?{content:'https://telemetry.ultimaoffline7.com/collect'}:q==='#usage-reporting'?check:reset});window.innerWidth=1600;
 const storage=(key,oldValue,newValue)=>{const e=new Event('storage');Object.assign(e,{key,oldValue,newValue});window.dispatchEvent(e);};
 try{
  for(const [k,v]of Object.entries({window,document,navigator:{doNotTrack:'0',userAgent:'Windows Chrome/130'},performance:{now:()=>time},
   localStorage:{getItem:k=>values.get(k)||null,setItem:(k,v)=>{if(storageFails)throw Error('blocked');values.set(k,v);},removeItem:k=>{if(storageFails)throw Error('blocked');values.delete(k);}},
   fetch:async(url,options)=>{posts.push({url,...options});throw Error('offline');},setInterval:fn=>{interval=fn;return 1;},clearInterval:()=>{}}))Object.defineProperty(globalThis,k,{configurable:true,writable:true,value:v});
  values.set('uo7-usage-reporting-v1','on');
  let api=connect('abcdef0123456789');api.event('begin');assert.equal(posts.length,0);assert.equal(values.has(IDENTITY),false);
  check.checked=true;check.dispatchEvent(new Event('change'));api.event('begin');assert.equal(posts.length,1);
  const first=JSON.parse(posts[0].body);assert.equal(first.returning,false);assert(first.player);assert(validate(first));
  assert.equal(posts[0].credentials,'omit');assert.equal(posts[0].referrerPolicy,'no-referrer');
  time=1000;api.event('draw');assert.equal(posts.length,2);assert(validate(JSON.parse(posts[1].body)));
  api.dispose();api=connect('abcdef0123456789');api.event('begin');
  const next=JSON.parse(posts.at(-1).body);assert.equal(next.player,first.player);assert.equal(next.returning,true);assert.notEqual(next.id,first.id);
  const old=values.get(IDENTITY);storage(IDENTITY,old,JSON.stringify({...JSON.parse(old),played:true}));
  time=2000;api.event('draw');assert.equal(JSON.parse(posts.at(-1).body).ready,true,'Another tab marking played must not stop this session');
  reset.dispatchEvent(new Event('click'));assert.equal(values.has(IDENTITY),false);const n=posts.length;interval();assert.equal(posts.length,n);
  api.event('begin');assert.notEqual(JSON.parse(posts.at(-1).body).player,first.player);
  storageFails=true;check.checked=false;check.dispatchEvent(new Event('change'));const noStorage=posts.length;
  api.event('draw');interval();assert.equal(posts.length,noStorage,'Opt-out must work even when saving the preference fails');
  check.checked=true;check.dispatchEvent(new Event('change'));api.event('begin');assert.equal(JSON.parse(posts.at(-1).body).player,'','Unpersisted IDs must not count as unique players');
  storageFails=false;
  values.set(PREFERENCE,'off');storage(PREFERENCE,'on','off');const stopped=posts.length;api.event('draw');interval();assert.equal(posts.length,stopped);assert.equal(values.has(IDENTITY),false);
  values.set(PREFERENCE,'on');globalThis.navigator.globalPrivacyControl=true;api.dispose();api=connect('abcdef0123456789');api.event('begin');assert.equal(posts.length,stopped);assert.equal(check.disabled,true);
  check.checked=true;check.dispatchEvent(new Event('change'));assert.equal(check.checked,false);api.dispose();
  await Promise.resolve();
 }finally{for(const [k,v]of Object.entries(original)){if(v)Object.defineProperty(globalThis,k,v);else delete globalThis[k];}}
});
test('browser descriptions are coarse and never contain the raw user agent',()=>{
 const context=browserContext({userAgent:'private Windows device details Chrome/130 Edg/130'},700);
 assert.deepEqual(context,{browser:'edge',os:'windows',viewport:'small'});assert(!JSON.stringify(context).includes('private'));
});
