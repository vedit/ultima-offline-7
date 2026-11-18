import {MAX_MS,STAGES} from './core.js';
import {UUID,CONTEXT,METRICS,MILESTONES} from './schema.js';
const origins=new Set(['https://ultimaoffline7.com','https://www.ultimaoffline7.com']);
const bools=['ready','trinsic','evidence','reported','gate'];
const fields=['v','id','build','started','seq','state','stage','wallMs','activeMs','loadMs',...bools];
const integer=(n,min,max)=>Number.isSafeInteger(n)&&n>=min&&n<=max;
export function validate(d,now=Date.now()) {
  if(d?.v===2){
    const extra=['player','returning','context','metrics','stages','milestones','baseline'];
    if(Object.keys(d).length!==fields.length+extra.length||Object.keys(d).some(k=>!fields.includes(k)&&!extra.includes(k)))return false;
    const base=Object.fromEntries(fields.map(k=>[k,k==='v'?1:d[k]]));
    if(!validate(base,now)||typeof d.player!=='string'||(d.player!==''&&!UUID.test(d.player))||typeof d.returning!=='boolean'||(!d.player&&d.returning))return false;
    const exact=(o,keys)=>o&&typeof o==='object'&&!Array.isArray(o)&&Object.keys(o).length===keys.length&&keys.every(k=>Object.hasOwn(o,k));
    if(!exact(d.context,Object.keys(CONTEXT))||Object.entries(CONTEXT).some(([k,choices])=>!choices.includes(d.context[k])))return false;
    if(!exact(d.metrics,METRICS)||METRICS.some(k=>!integer(d.metrics[k],0,MAX_MS)))return false;
    if(!exact(d.stages,STAGES)||STAGES.some(k=>!integer(d.stages[k],0,d.wallMs))||Object.values(d.stages).reduce((a,b)=>a+b,0)>d.wallMs)return false;
    if(!exact(d.milestones,MILESTONES)||MILESTONES.some(k=>!integer(d.milestones[k],-1,d.wallMs)||d[k]!== (d.milestones[k]>=0)))return false;
    if(!Array.isArray(d.baseline)||d.baseline.length>3||new Set(d.baseline).size!==d.baseline.length||d.baseline.some(k=>!['trinsic','evidence','reported'].includes(k)||!d[k]))return false;
    if(['hiddenMs','unfocusedMs','pausedMs','stalledMs','suspendedMs'].reduce((n,k)=>n+d.metrics[k],d.activeMs)>d.wallMs)return false;
    if(d.metrics.rejectedActions>d.metrics.actions||['movement','uses','inventory','dialogue','spells','combat','debug'].reduce((n,k)=>n+d.metrics[k],0)!==d.metrics.actions)return false;
    return true;
  }
  if (!d || typeof d!=='object' || Array.isArray(d) || Object.keys(d).length!==fields.length ||
      Object.keys(d).some(k=>!fields.includes(k))) return false;
  if(d.v!==1 || typeof d.id!=='string' || !/^[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}$/.test(d.id) ||
    typeof d.build!=='string' || !/^[a-f0-9]{7,64}$/.test(d.build) ||
    !['loading','playing','failed','ended'].includes(d.state) || !STAGES.includes(d.stage)) return false;
  if(!integer(d.started,Math.floor(now/1000)-90000,Math.floor(now/1000)+300) ||
    !integer(d.seq,1,100000) || !integer(d.wallMs,0,MAX_MS) ||
    !integer(d.activeMs,0,d.wallMs) || !integer(d.loadMs,0,d.wallMs) ||
    bools.some(k=>typeof d[k]!=='boolean')) return false;
  if(d.wallMs>(now/1000-d.started+300)*1000) return false;
  if(!d.ready && (d.activeMs || d.loadMs || d.state==='playing')) return false;
  return true;
}
async function boundedBody(request) {
  const reader=request.body?.getReader(); if(!reader) throw Error('empty');
  let size=0, chunks=[];
  while(true) {const {value,done}=await reader.read();if(done)break;size+=value.byteLength;
    if(size>8192){await reader.cancel();throw Error('large');}chunks.push(value);}
  const bytes=new Uint8Array(size);let offset=0;for(const c of chunks){bytes.set(c,offset);offset+=c.length;}
  return JSON.parse(new TextDecoder().decode(bytes));
}
export default {
  async fetch(request,env) {
    const path=new URL(request.url).pathname, origin=request.headers.get('Origin');
    const headers={'Cache-Control':'no-store','Cross-Origin-Resource-Policy':'cross-origin','Vary':'Origin'};
    if(origins.has(origin))headers['Access-Control-Allow-Origin']=origin;
    const reply=(status,body=null)=>new Response(body,{status,headers});
    if(path==='/health' && request.method==='GET')return reply(200,'uo7-analytics-v2');
    if(path!=='/collect')return reply(404);
    if(!origins.has(origin))return reply(403);
    if(request.method==='OPTIONS') {headers['Access-Control-Allow-Methods']='POST';headers['Access-Control-Allow-Headers']='Content-Type';return reply(204);}
    if(request.method!=='POST')return reply(405);
    // Cloudflare uses the address only for edge rate limiting; it is never
    // written to the analytics dataset or application logs.
    if(!env.INGEST_LIMIT || !(await env.INGEST_LIMIT.limit({key:request.headers.get('CF-Connecting-IP')||'unknown'})).success)return reply(429);
    if(Number(request.headers.get('Content-Length'))>8192)return reply(413);
    let d;try{d=await boundedBody(request);}catch{return reply(400);}
    if(!validate(d))return reply(400);
    if(!env.PLAYTIME)return reply(503);
    const blobs=[d.build,d.state,d.stage],doubles=[d.started,d.seq,d.wallMs,d.activeMs,d.loadMs,+d.ready,+d.trinsic,+d.evidence,+d.reported,+d.gate];
    if(d.v===2){
      blobs.push(d.player,d.context.browser,d.context.os,d.context.viewport,d.context.mode,d.context.storage,d.context.music,
        JSON.stringify({metrics:d.metrics,stages:d.stages,milestones:d.milestones,baseline:d.baseline}));
      doubles.push(2,+d.returning,d.metrics.hiddenMs,d.metrics.unfocusedMs,d.metrics.pausedMs,d.metrics.stalledMs,
        d.metrics.autoSaves,d.metrics.manualSaves,d.metrics.loads,d.metrics.errors);
    }
    env.PLAYTIME.writeDataPoint({indexes:[d.id],blobs,doubles});
    return reply(204);
  }
};
