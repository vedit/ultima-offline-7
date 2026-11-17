import test from 'node:test';
import assert from 'node:assert/strict';
import {connect} from '../browser.js';

test('browser lifecycle, opt-out, privacy preference and network failure isolation',async()=>{
 const original={};for(const k of ['window','document','navigator','localStorage','fetch','setInterval','clearInterval'])original[k]=Object.getOwnPropertyDescriptor(globalThis,k);
 const docEvents=new Map(),winEvents=new Map(),values=new Map(),posts=[];
 let change,interval;
 const check={checked:false,disabled:false,addEventListener:(n,fn)=>change=fn,closest:()=>({})};
 const document={hidden:false,hasFocus:()=>true,querySelector:q=>q.startsWith('meta')?{content:'https://telemetry.ultimaoffline7.com/collect'}:check,addEventListener:(n,fn)=>docEvents.set(n,fn)};
 try {
  for(const [k,v]of Object.entries({document,window:{addEventListener:(n,fn)=>winEvents.set(n,fn)},navigator:{doNotTrack:'0'},
    localStorage:{getItem:k=>values.get(k),setItem:(k,v)=>values.set(k,v)},
    fetch:async(url,options)=>{posts.push({url,...options});throw Error('offline');},setInterval:fn=>{interval=fn;return 1;},clearInterval:()=>{}}))
    Object.defineProperty(globalThis,k,{configurable:true,writable:true,value:v});
  const api=connect('abcdef0123456789');api.event('begin');api.event('draw');
  assert.equal(posts.length,2);assert.equal(posts[0].credentials,'omit');assert.equal(posts[0].referrerPolicy,'no-referrer');
  document.hidden=true;docEvents.get('visibilitychange')();assert.equal(posts.length,3);
  const d=JSON.parse(posts[2].body);assert(d.ready);assert.equal(d.state,'playing');
  check.checked=false;change();api.event('draw');interval();assert.equal(posts.length,3);
  assert.equal(values.get('uo7-usage-reporting-v1'),'off');
  api.dispose();
  const off=connect('abcdef0123456789');off.event('begin');assert.equal(posts.length,3);off.dispose();
  values.clear();globalThis.navigator.doNotTrack='1';
  const privateMode=connect('abcdef0123456789');privateMode.event('begin');assert.equal(posts.length,3);assert.equal(check.disabled,true);
  check.checked=true;change();privateMode.event('begin');assert.equal(posts.length,3);assert.equal(check.checked,false);privateMode.dispose();
  await Promise.resolve(); // Rejected uploads must be handled, never propagated.
 } finally {
  for(const [k,v]of Object.entries(original)){if(v)Object.defineProperty(globalThis,k,v);else delete globalThis[k];}
 }
});
