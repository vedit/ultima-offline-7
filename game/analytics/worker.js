import {MAX_MS,STAGES} from './core.js';
const origins=new Set(['https://ultimaoffline7.com','https://www.ultimaoffline7.com']);
const bools=['ready','trinsic','evidence','reported','gate'];
const fields=['v','id','build','started','seq','state','stage','wallMs','activeMs','loadMs',...bools];
const integer=(n,min,max)=>Number.isSafeInteger(n)&&n>=min&&n<=max;
export function validate(d,now=Date.now()) {
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
    if(size>2048){await reader.cancel();throw Error('large');}chunks.push(value);}
  const bytes=new Uint8Array(size);let offset=0;for(const c of chunks){bytes.set(c,offset);offset+=c.length;}
  return JSON.parse(new TextDecoder().decode(bytes));
}
export default {
  async fetch(request,env) {
    const path=new URL(request.url).pathname, origin=request.headers.get('Origin');
    const headers={'Cache-Control':'no-store','Cross-Origin-Resource-Policy':'cross-origin','Vary':'Origin'};
    if(origins.has(origin))headers['Access-Control-Allow-Origin']=origin;
    const reply=(status,body=null)=>new Response(body,{status,headers});
    if(path==='/health' && request.method==='GET')return reply(200,'uo7-analytics-v1');
    if(path!=='/collect')return reply(404);
    if(!origins.has(origin))return reply(403);
    if(request.method==='OPTIONS') {headers['Access-Control-Allow-Methods']='POST';headers['Access-Control-Allow-Headers']='Content-Type';return reply(204);}
    if(request.method!=='POST')return reply(405);
    // Cloudflare uses the address only for edge rate limiting; it is never
    // written to the analytics dataset or application logs.
    if(!env.INGEST_LIMIT || !(await env.INGEST_LIMIT.limit({key:request.headers.get('CF-Connecting-IP')||'unknown'})).success)return reply(429);
    if(Number(request.headers.get('Content-Length'))>2048)return reply(413);
    let d;try{d=await boundedBody(request);}catch{return reply(400);}
    if(!validate(d))return reply(400);
    if(!env.PLAYTIME)return reply(503);
    env.PLAYTIME.writeDataPoint({indexes:[d.id],blobs:[d.build,d.state,d.stage],
      doubles:[d.started,d.seq,d.wallMs,d.activeMs,d.loadMs,+d.ready,+d.trinsic,+d.evidence,+d.reported,+d.gate]});
    return reply(204);
  }
};
