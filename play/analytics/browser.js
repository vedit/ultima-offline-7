import {Session} from './core.js';

export function connect(build) {
  const endpoint = document.querySelector('meta[name="uo7-analytics"]')?.content;
  const key = 'uo7-usage-reporting-v1';
  const privacy = navigator.globalPrivacyControl === true || navigator.doNotTrack === '1';
  let enabled = !privacy, session, lastSent=-Infinity;
  try {enabled = !privacy && localStorage.getItem(key)!=='off';} catch {}
  const check = document.querySelector('#usage-reporting');
  if (check) {
    check.checked=enabled; check.disabled=privacy;
    if (privacy) check.closest('label').title='Disabled by your browser privacy preference';
    check.addEventListener('change',()=>{
      enabled=!privacy && check.checked;
      check.checked=enabled;
      try {localStorage.setItem(key,enabled?'on':'off');} catch {}
      // Never replay activity recorded before permission was enabled.
      session=undefined;
    });
  }
  function send(force=false) {
    const now=performance.now();
    if (!enabled || !session || !endpoint || (!force && now-lastSent<30000)) return;
    lastSent=now;
    const body=JSON.stringify(session.snapshot(now));
    // No cookies, no persistent identifier, no raw game/error data, no retry
    // queue on disk. A later cumulative snapshot recovers a failed upload.
    fetch(endpoint,{method:'POST',body,headers:{'Content-Type':'text/plain'},
      mode:'cors',credentials:'omit',referrerPolicy:'no-referrer',keepalive:true,
      signal:AbortSignal.timeout(10000)}).catch(()=>{});
  }
  function event(type,value,now=performance.now()) {
    if (!enabled || !endpoint) return;
    if (type==='begin') {
      if (session) {session.event('end',null,now);send(true);}
      session=new Session({id:crypto.randomUUID(),build,started:Math.floor(Date.now()/1000),now,
        visible:!document.hidden,focused:document.hasFocus()});
      send(true); return;
    }
    if (!session) return;
    const wasReady=session.data.ready;
    session.event(type,value,now);
    if (type==='fail' || (!wasReady && session.data.ready)) send(true);
  }
  const timer=setInterval(()=>{session?.tick(performance.now());send();},1000);
  document.addEventListener('visibilitychange',()=>{event('visible',!document.hidden);if(document.hidden)send(true);});
  window.addEventListener('blur',()=>{event('focused',false);send(true);});
  window.addEventListener('focus',()=>event('focused',true));
  window.addEventListener('pagehide',e=>{event(e.persisted?'visible':'end',false);send(true);});
  window.addEventListener('pageshow',e=>{if(e.persisted){event('visible',!document.hidden);event('focused',document.hasFocus());}});
  return {event, dispose(){clearInterval(timer);session=undefined;}};
}
