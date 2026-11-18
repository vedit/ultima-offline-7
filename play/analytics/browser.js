import {PlayerSession} from './session-v2.js?v=cc751b07e7183057';
import {UUID} from './schema.js?v=cc751b07e7183057';

export const PREFERENCE='uo7-usage-reporting-v2',IDENTITY='uo7-player-v2';
export const CRASH_PREFERENCE='uo7-crash-details-v1';
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
  let enabled=!privacy()&&get(PREFERENCE)==='on',session,identity,lastSent=-Infinity,observer;
  const check=document.querySelector('#usage-reporting'),reset=document.querySelector('#usage-reset');
  const crashCheck=document.querySelector('#crash-reporting');
  let shareCrash=false;
  const notice=document.querySelector('#usage-notice');
  const tell=message=>{if(notice)notice.textContent=message;};
  const listeners=[];
  function on(target,name,fn){target.addEventListener(name,fn);listeners.push(()=>target.removeEventListener(name,fn));}
  function stop(){session=undefined;identity=undefined;observer?.disconnect();observer=undefined;}
  function sync(){
    enabled=!privacy()&&get(PREFERENCE)==='on';
    if(check){check.checked=enabled;check.disabled=privacy();}
    syncCrash();
    if(!enabled){stop();remove(IDENTITY);}
  }
  function syncCrash(){
    shareCrash=enabled&&get(CRASH_PREFERENCE)==='on';
    if(!shareCrash&&session)delete session.data.crash;
    if(crashCheck){crashCheck.checked=shareCrash;crashCheck.disabled=!enabled;}
  }
  if(check)on(check,'change',()=>{
    enabled=!privacy()&&check.checked;
    const persisted=set(PREFERENCE,enabled?'on':'off');stop();
    tell(persisted?'':`Reporting is ${enabled?'enabled':'off'} for this page. Browser storage is unavailable; this preference could not be saved.`);
    check.checked=enabled;check.disabled=privacy();
    if(!enabled){remove(IDENTITY);remove(CRASH_PREFERENCE);}
    syncCrash();
  });
  if(crashCheck)on(crashCheck,'change',()=>{
    const checked=enabled&&!privacy()&&crashCheck.checked;
    // If storage denies an opt-out, honor it immediately for this session.
    const persisted=set(CRASH_PREFERENCE,checked?'on':'off');
    shareCrash=checked&&persisted;crashCheck.checked=shareCrash;
    if(!shareCrash&&session)delete session.data.crash;
  });
  if(reset)on(reset,'click',()=>{stop();tell(remove(IDENTITY)?'ID reset — applies next launch.':'Reporting stopped for this page, but browser storage prevented removing the saved ID.');});
  sync();
  if(reset)reset.disabled=false;
  on(window,'storage',e=>{
    if(e.key===CRASH_PREFERENCE)syncCrash();
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
  function send(force=false) {
    const now=performance.now();
    if(privacy()){sync();return;}
    if(!enabled||!session||!endpoint||(!force&&now-lastSent<30000))return;
    lastSent=now;
    const snapshot=session.snapshot(now);
    if(!shareCrash||get(CRASH_PREFERENCE)!=='on')delete snapshot.crash;
    const body=JSON.stringify(snapshot);
    fetch(endpoint,{method:'POST',body,headers:{'Content-Type':'text/plain'},mode:'cors',
      credentials:'omit',referrerPolicy:'no-referrer',keepalive:true,signal:AbortSignal.timeout(10000)}).catch(()=>{});
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
    if(type==='fail'||(!wasReady&&session.data.ready))send(true);
  }
  const timer=setInterval(()=>{session?.tick(performance.now());send();},1000);
  on(document,'visibilitychange',()=>{event('visible',!document.hidden);if(document.hidden)send(true);});
  on(window,'blur',()=>{event('focused',false);send(true);});
  on(window,'focus',()=>event('focused',true));
  on(window,'pagehide',e=>{event(e.persisted?'visible':'end',false);send(true);});
  on(window,'pageshow',e=>{if(e.persisted){event('visible',!document.hidden);event('focused',document.hasFocus());}});
  return {event,dispose(){clearInterval(timer);stop();for(const remove of listeners)remove();}};
}
