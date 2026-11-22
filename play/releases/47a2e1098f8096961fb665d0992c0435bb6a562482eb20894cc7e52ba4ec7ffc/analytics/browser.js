import {PlayerSession} from './session-v2.js?v=92dfba009d583c67';
import {UUID} from './schema.js?v=92dfba009d583c67';
import {CRASH_SAVE_MAX_BYTES} from './crash-save.js?v=92dfba009d583c67';

export const PREFERENCE='uo7-usage-reporting-v2',IDENTITY='uo7-player-v2';
export const CRASH_PREFERENCE='uo7-crash-details-v1';
export const SAVE_PREFERENCE='uo7-crash-save-v1';
export function browserContext(nav=navigator,width=window.innerWidth){
  const ua=nav.userAgent||'';
  return {browser:/Edg\//.test(ua)?'edge':/Firefox\//.test(ua)?'firefox':/Chrome\//.test(ua)?'chrome':/Safari\//.test(ua)?'safari':'other',
    os:/Android/.test(ua)?'android':/iPhone|iPad/.test(ua)?'ios':/Windows/.test(ua)?'windows':/Mac/.test(ua)?'mac':/Linux/.test(ua)?'linux':'other',
    viewport:width<800?'small':width<1400?'medium':'large'};
}
export function connect(build) {
  const endpoint=document.querySelector('meta[name="uo7-analytics"]')?.content;
  const privacy=()=>navigator.globalPrivacyControl===true||navigator.doNotTrack==='1';
  const get=k=>{try{return localStorage.getItem(k);}catch{return null;}};
  const set=(k,v)=>{try{localStorage.setItem(k,v);return localStorage.getItem(k)===v;}catch{return false;}};
  const remove=k=>{try{localStorage.removeItem(k);return localStorage.getItem(k)===null;}catch{return false;}};
  let enabled,session,identity,lastSent=-Infinity,observer;
  const check=document.querySelector('#usage-reporting'),reset=document.querySelector('#usage-reset');
  const crashCheck=document.querySelector('#crash-reporting');
  const saveCheck=document.querySelector('#crash-save-reporting');
  let shareCrash=false,shareSave=false,upload;
  const notice=document.querySelector('#usage-notice');
  const policy=document.querySelector('#usage-policy');
  const tell=message=>{if(notice)notice.textContent=message;};
  const listeners=[];
  function on(target,name,fn){target.addEventListener(name,fn);listeners.push(()=>target.removeEventListener(name,fn));}
  function stop(){session=undefined;identity=undefined;observer?.disconnect();observer=undefined;upload?.abort();}
  function sync(){
    enabled=get(PREFERENCE)==='on';
    if(check){check.checked=enabled;check.disabled=false;}
    if(policy)policy.hidden=!privacy();
    syncCrash();
    syncSave();
    if(!enabled||privacy()){stop();remove(IDENTITY);}
  }
  function syncCrash(){
    const selected=get(CRASH_PREFERENCE)==='on';
    shareCrash=enabled&&!privacy()&&selected;
    if(!shareCrash&&session)delete session.data.crash;
    if(crashCheck){crashCheck.checked=selected;crashCheck.disabled=false;}
  }
  function syncSave(){
    const selected=get(SAVE_PREFERENCE)==='on';
    shareSave=enabled&&!privacy()&&selected;
    if(!shareSave)upload?.abort();
    if(saveCheck){saveCheck.checked=selected;saveCheck.disabled=false;}
  }
  if(check)on(check,'change',()=>{
    enabled=check.checked;
    const persisted=set(PREFERENCE,enabled?'on':'off');stop();
    tell(persisted?'':'Your browser could not save this preference.');
    if(!enabled){remove(IDENTITY);remove(CRASH_PREFERENCE);remove(SAVE_PREFERENCE);}
    syncCrash();
    syncSave();
  });
  if(crashCheck)on(crashCheck,'change',()=>{
    const checked=crashCheck.checked;
    // If storage denies an opt-out, honor it immediately for this session.
    const persisted=set(CRASH_PREFERENCE,checked?'on':'off');
    crashCheck.checked=checked&&persisted;
    shareCrash=enabled&&!privacy()&&crashCheck.checked;
    tell(persisted?'':'Your browser could not save the crash details preference.');
    if(!shareCrash&&session)delete session.data.crash;
  });
  if(saveCheck)on(saveCheck,'change',()=>{
    const checked=saveCheck.checked;
    const persisted=set(SAVE_PREFERENCE,checked?'on':'off');
    saveCheck.checked=checked&&persisted;
    shareSave=enabled&&!privacy()&&saveCheck.checked;
    tell(persisted?'':'Your browser could not save the crash upload preference.');
    if(!shareSave)upload?.abort();
  });
  if(reset)on(reset,'click',()=>{stop();tell(remove(IDENTITY)?'ID reset — applies next launch.':'Reporting stopped for this page, but browser storage prevented removing the saved ID.');});
  sync();
  if(reset)reset.disabled=false;
  on(window,'storage',e=>{
    if(e.key===CRASH_PREFERENCE)syncCrash();
    if(e.key===SAVE_PREFERENCE)syncSave();
    if(e.key===PREFERENCE||e.key===IDENTITY||e.key===null){
      let next;try{next=JSON.parse(e.newValue);}catch{}
      const changed=e.key===IDENTITY&&identity&&identity.id!==next?.id;
      sync();if(changed)stop();
    }
  });
  function loadIdentity(){
    let current;try{current=JSON.parse(get(IDENTITY));}catch{}
    if(!current||typeof current.id!=='string'||!UUID.test(current.id)||typeof current.played!=='boolean')current={id:crypto.randomUUID(),played:false};
    // Do not pretend an ephemeral ID is a repeatable unique player.
    if(!set(IDENTITY,JSON.stringify(current)))return {id:'',played:false};
    return current;
  }
  function send(force=false,crashBytes) {
    const now=performance.now();
    if(privacy()){if(session||identity)sync();return;}
    if(!enabled||!session||!endpoint||(!force&&now-lastSent<30000))return;
    lastSent=now;
    const snapshot=session.snapshot(now);
    if(!shareCrash||get(CRASH_PREFERENCE)!=='on')delete snapshot.crash;
    const body=JSON.stringify(snapshot);
    fetch(endpoint,{method:'POST',body,headers:{'Content-Type':'text/plain'},mode:'cors',
      credentials:'omit',referrerPolicy:'no-referrer',keepalive:true,signal:AbortSignal.timeout(10000)}).catch(()=>{});
    if(!shareSave||get(SAVE_PREFERENCE)!=='on'||get(PREFERENCE)!=='on'||
        snapshot.state!=='failed'||!(crashBytes instanceof ArrayBuffer||ArrayBuffer.isView(crashBytes))||
        crashBytes.byteLength<128||crashBytes.byteLength>CRASH_SAVE_MAX_BYTES)return;
    upload?.abort();
    const controller=new AbortController();
    upload=controller;
    const signal=AbortSignal.any([controller.signal,AbortSignal.timeout(20000)]);
    fetch(new URL('crash-save',endpoint),{method:'POST',
      body:new Blob([body,'\n',crashBytes],{type:'application/octet-stream'}),
      mode:'cors',credentials:'omit',referrerPolicy:'no-referrer',signal}).catch(()=>{}).finally(()=>{
        if(upload===controller)upload=undefined;
      });
  }
  function event(type,value,now=performance.now()) {
    if(!enabled||privacy()||!endpoint)return;
    if(type==='begin'){
      if(session){session.event('end',null,now);send(true);}
      identity=loadIdentity();
      session=new PlayerSession({id:crypto.randomUUID(),player:identity.id,returning:identity.played,
        build,started:Math.floor(Date.now()/1000),now,visible:!document.hidden,focused:document.hasFocus(),context:browserContext()});
      observer?.disconnect();
      if(typeof PerformanceObserver!=='undefined'&&PerformanceObserver.supportedEntryTypes?.includes('longtask')){
        try{observer=new PerformanceObserver(list=>{for(const task of list.getEntries())event('longtask',task.duration);});observer.observe({type:'longtask'});}catch{}
      }
      send(true);return;
    }
    if(!session)return;
    const wasReady=session.data.ready;
    session.event(type,type==='fail'&&(!shareCrash||get(CRASH_PREFERENCE)!=='on')?null:value,now);
    if(!wasReady&&session.data.ready&&identity.id){identity.played=true;set(IDENTITY,JSON.stringify(identity));}
    if(type==='fail'||(!wasReady&&session.data.ready))send(true,type==='fail'?value?.bytes:undefined);
  }
  const timer=setInterval(()=>{session?.tick(performance.now());send();},1000);
  on(document,'visibilitychange',()=>{event('visible',!document.hidden);if(document.hidden)send(true);});
  on(window,'blur',()=>{event('focused',false);send(true);});
  on(window,'focus',()=>event('focused',true));
  on(window,'pagehide',e=>{event(e.persisted?'visible':'end',false);send(true);});
  on(window,'pageshow',e=>{if(e.persisted){event('visible',!document.hidden);event('focused',document.hasFocus());}});
  return {event,dispose(){clearInterval(timer);stop();for(const remove of listeners)remove();}};
}
