import {importInstall} from './install.js?v=f0f9499d14bffd4d';
import {installInput} from './client-input.js?v=f0f9499d14bffd4d';
import {compactUO,megabytes} from './uo-data.js?v=f0f9499d14bffd4d';
import {downloadUO} from './uo-download.js?v=f0f9499d14bffd4d';
import {steamPath,SaveFolder} from './folders.js?v=f0f9499d14bffd4d';
import {selectMusic,ExultMusic} from './exult-music.js?v=f0f9499d14bffd4d';
import {LoadingScreen} from './loading.js?v=f0f9499d14bffd4d';
import {prepareIntro} from './intro.js?v=f0f9499d14bffd4d';
import {installAudio} from './audio.js?v=f0f9499d14bffd4d';

const status=document.querySelector('#status');
const details=document.querySelector('#details');
const canvas=document.querySelector('#canvas');
const play=document.querySelector('#play');
const loading=new LoadingScreen();
const toolbar=document.querySelector('#toolbar'),showToolbar=document.querySelector('#show-toolbar');
let toolbarHidden=false;
try{toolbarHidden=localStorage.getItem('trinsic-hide-toolbar')==='1'}catch{}
function setToolbarHidden(hidden){
    toolbarHidden=hidden;toolbar.hidden=hidden;showToolbar.hidden=!hidden;
    try{localStorage.setItem('trinsic-hide-toolbar',hidden?'1':'0')}catch{}
    canvas.focus();
}
document.querySelector('#hide-toolbar').onclick=()=>setToolbarHidden(true);
showToolbar.onclick=()=>setToolbarHidden(false);
function loadingStep(message,percent,detail){telemetry.event('stage',percent<5?'startup':percent<50?'download':percent<55?'save':percent<92?'client':percent<97?'artwork':'render');status.textContent=message;loading.update(percent,message,detail)}
const buildVersion=new URL(import.meta.url).searchParams.get('v')||'dev';
// UO7 analytics integration v1 (optional; failures cannot stop the game).
const telemetry = (()=>{
    let sink, pending=[];
    import('./analytics/browser.js?v=1').then(({connect})=>{
        sink=connect(buildVersion);
        for(const args of pending)sink.event(...args);
        pending=[];
    }).catch(()=>{pending=[];sink={event(){}}});
    return {event(type,value){try{
        const args=[type,value,performance.now()];
        if(sink)sink.event(...args);else if(pending.length<64)pending.push(args);
    }catch{}}};
})();

let recordingFlags=0;
function updateRecordingState(){
    if(!recordingFlags)return;
    const files=music.tracks.size>0,playing=music.current&&music.context?.state==='running';
    Atomics.store(runtime.HEAP32,recordingFlags>>2,(music.revision<<3)|(playing?4:0)|(files&&music.enabled?2:0)|(files?1:0));
}
const music=new ExultMusic(updateRecordingState);
const saveFolder=new SaveFolder(message=>{document.querySelector('#save-selection').textContent=message});
globalThis.trinsicMusic=music;
let selecting=false,launching=false;
// The SDL desktop window-resize path is not used by this fixed-resolution
// client. ResizeObserver below scales presentation without resizing WebGL.
window.addEventListener('resize',event=>event.stopImmediatePropagation(),true);
// Fit the entire client uniformly: world, interface panels and input all share
// 1200 x 900 logical pixels, independent of browser size or display DPI.
new ResizeObserver(([entry])=>{
    const scale=Math.min(entry.contentRect.width/1200,entry.contentRect.height/900);
    canvas.style.width=1200*scale+'px';canvas.style.height=900*scale+'px';
}).observe(document.querySelector('#stage'));
if(!crossOriginIsolated){
    document.querySelector('#setup').hidden=true;
    loading.start();loadingStep('Preparing the browser…',0);
    setTimeout(()=>{telemetry.event('begin');telemetry.event('fail');status.textContent='Browser setup did not finish. Open this link directly in Chrome or Edge with site storage enabled.';loading.error(status.textContent)},15000);
    // coi-serviceworker reloads this first navigation with isolation enabled.
    await new Promise(()=>{});
}
const installKey='blackgate-local-install-v1', uoKey='classicuo-local-install-v1', saveKey='trinsic-investigation-v1';
let install,uo,previousUO,engine,input,runtime,ready=false,visibleSince=performance.now(),stalledStatus;
const audio=installAudio(()=>runtime,fail);
document.addEventListener('visibilitychange',()=>{visibleSince=performance.now()});
setInterval(()=>{
    if(!ready||document.hidden||globalThis.trinsicFailure)return;
    const age=performance.now()-Math.max(visibleSince,globalThis.trinsicLastDraw||0);
    if(age>15000 && stalledStatus===undefined){
        stalledStatus=status.textContent;
        status.textContent='The client stopped drawing. Refresh to resume your last save.';
        console.error('ClassicUO renderer stalled',{drawAgeMs:age,coords:document.querySelector('#coords').textContent});
    }
},1000);
globalThis.__uo_signal=name=>{
    if(name==='draw-heartbeat')telemetry.event('draw');
    if(name==='paused'||name==='resumed')telemetry.event('paused',name==='paused');
    if(name==='draw-heartbeat'){
        globalThis.trinsicLastDraw=performance.now();
        if(stalledStatus!==undefined&&!globalThis.trinsicFailure){status.textContent=stalledStatus;stalledStatus=undefined}
    }
    console.log('ClassicUO: '+name);
    if(!ready && name==='draw-heartbeat'){
        audio.startNative();
        ready=true;loading.finish();document.querySelector('#folders').hidden=false;document.querySelector('#hide-toolbar').hidden=false;setToolbarHidden(toolbarHidden);status.textContent='Trinsic is ready';requestCheckpoint();
    }
};
const db=await new Promise((resolve,reject)=>{
    const request=indexedDB.open('ultima-offline',1);
    request.onupgradeneeded=()=>request.result.createObjectStore('slots');
    request.onsuccess=()=>resolve(request.result);request.onerror=()=>reject(request.error);
});
function slot(key,value){return new Promise((resolve,reject)=>{
    const tx=db.transaction('slots',value===undefined?'readonly':'readwrite');
    const request=value===undefined?tx.objectStore('slots').get(key):tx.objectStore('slots').put(value,key);
    tx.oncomplete=()=>resolve(request.result);tx.onabort=tx.onerror=()=>reject(tx.error||request.error);
})}
function removeSlots(keys){return new Promise((resolve,reject)=>{
    const tx=db.transaction('slots','readwrite');for(const key of keys)tx.objectStore('slots').delete(key);
    tx.oncomplete=resolve;tx.onabort=tx.onerror=()=>reject(tx.error);
})}
function browserSave(bytes,time=Date.now(),saveSlot){return new Promise((resolve,reject)=>{
    const tx=db.transaction('slots','readwrite'),store=tx.objectStore('slots');
    store.put(bytes,saveKey);store.put(time,'trinsic-save-time-v1');
    if(Number.isInteger(saveSlot)&&saveSlot>=0&&saveSlot<10){store.put(bytes,'trinsic-slot-'+saveSlot+'-v1');store.put(saveSlot,'trinsic-active-slot-v1')}
    tx.oncomplete=resolve;tx.onabort=tx.onerror=()=>reject(tx.error);
})}
function fail(error){telemetry.event('fail');globalThis.trinsicFailure=error.message||String(error);status.textContent=globalThis.trinsicFailure;console.error(error);if(!ready&&!loading.root.hidden)loading.error(globalThis.trinsicFailure)}
function updateSetup(){
    for(const element of document.querySelectorAll('#setup input, #setup button'))element.disabled=selecting||launching;
    play.disabled=!install||selecting||launching;
    document.querySelector('#new-game').disabled=play.disabled;
    document.querySelector('#game-selection').textContent=install?'Ultima VII ready':'No folder selected';
    document.querySelector('#music-selection').textContent=music.tracks.size?music.tracks.size+' MT-32 tracks ready':'No music selected';
    document.querySelector('#clear-music').hidden=!music.tracks.size;
    document.querySelector('#clear-save').hidden=!saveFolder.handle;
    details.textContent=uo?'UO demo data is ready':'UO demo data downloads automatically on first play.';
}
async function choosing(action){
    if(selecting||launching)return;
    selecting=true;updateSetup();
    try{await action();delete globalThis.trinsicFailure;status.textContent=install?'Ready to enter Trinsic':'Choose your Ultima VII folder'}
    catch(error){if(error.name!=='AbortError')fail(error)}
    finally{selecting=false;updateSetup()}
}
// Imports use the read-only file input picker. The File System Access picker
// rejects protected Steam/Exult locations even when only read access is requested.
document.querySelector('#choose-game').onclick=()=>document.querySelector('#folder').click();
document.querySelector('#folder').onchange=e=>choosing(async()=>{
    if(!e.target.files.length)return;
    const imported=await importInstall([...e.target.files]);await slot(installKey,imported);install=imported;
    await slot('game-folder-handle-v1',null);
});
async function importMusic(files){
    const tracks=await selectMusic(files);await slot('exult-music-v1',tracks);
    await slot('exult-music-disabled-v1',false);music.enabled=true;music.set(tracks);
    await slot('music-folder-handle-v1',null);
}
document.querySelector('#choose-music').onclick=()=>document.querySelector('#music-folder').click();
document.querySelector('#music-folder').onchange=e=>choosing(async()=>{if(e.target.files.length)await importMusic([...e.target.files])});
document.querySelector('#clear-music').onclick=()=>choosing(async()=>{await slot('exult-music-v1',[]);await slot('music-folder-handle-v1',null);music.set([])});
globalThis.__trinsic_recording=(operation,value,pointer)=>{
    recordingFlags=pointer;
    if(operation===1)music.play(value);
    if(operation===2)music.stop();
    if(operation===3)music.setVolume(value/100);
    if(operation===4){music.enabled=!!value;slot('exult-music-disabled-v1',!music.enabled).catch(console.warn)}
    if(operation===5){
        const picker=document.createElement('input');picker.type='file';picker.webkitdirectory=true;
        picker.onchange=()=>importMusic([...picker.files]).catch(error=>{status.textContent=error.message});
        picker.click();
    }
    updateRecordingState();
};
document.querySelector('#choose-save').hidden=!window.showDirectoryPicker;
document.querySelector('#choose-save').onclick=()=>choosing(async()=>{
    const handle=await showDirectoryPicker({id:'ultima-offline-save',mode:'readwrite',startIn:saveFolder.handle||'documents'});
    const candidate=new SaveFolder();await candidate.set(handle);await candidate.read();
    await slot('save-folder-handle-v1',handle);await slot('save-folder-load-v1',true);await saveFolder.set(handle);
});
document.querySelector('#clear-save').onclick=()=>choosing(async()=>{await slot('save-folder-handle-v1',null);await slot('save-folder-load-v1',false);await saveFolder.set(null)});
const steam=steamPath(navigator.userAgentData?.platform||navigator.platform);
document.querySelector('#steam-hint').hidden=!steam;
document.querySelector('#steam-path').textContent=steam;
document.querySelector('#copy-steam').onclick=async()=>{try{await navigator.clipboard.writeText(steam);document.querySelector('#copy-steam').textContent='Copied'}catch{status.textContent='Select and copy the Steam path shown below.'}};
async function leaveFor(url){await requestCheckpoint(true);await persistence;location.assign(url)}
document.querySelector('#folders').onclick=()=>{const url=new URL(location.href);url.searchParams.set('setup','1');leaveFor(url).catch(fail)};
document.querySelector('header h1 a').onclick=event=>{if(ready&&!event.ctrlKey&&!event.metaKey&&!event.shiftKey&&!event.altKey){event.preventDefault();leaveFor(event.currentTarget.href).catch(fail)}};
document.addEventListener('pointerdown',()=>music.unlock(),true);
window.addEventListener('keydown',()=>music.unlock(),true);

let waiting,mailbox,queue=Promise.resolve(),engineFailure;
let checkpointDirty=true,lastCheckpointAt=0,lastCheckpointAttempt=0,lastProfileSync=0,checkpointRequest;
let lastActionAt=0,mutationVersion=0,persistence=Promise.resolve(),persisting=0;
const autosaveIdleMs=1500;
function publishFrame(frame){telemetry.event('frame',frame);
    const player=frame.split('\n').find(line=>line.startsWith('E ')&&line.split(' ')[8]==='0');
    if(player){const fields=player.split(' ');document.querySelector('#coords').textContent=fields[4]+', '+fields[5]}
    globalThis.trinsicLastFrame=frame;
}
async function checkpoint(){
    lastCheckpointAttempt=Date.now();document.querySelector('#save-state').textContent='Saving…';
    const frame=await exchange('0 0 CHECKPOINT');
    if(frame.split(' ')[5]!=='ok')document.querySelector('#save-state').textContent='Autosave pending';
    return frame;
}
function requestCheckpoint(force=false){
    if(!ready||engineFailure||globalThis.trinsicFailure)return Promise.resolve();
    if(force&&checkpointRequest)return checkpointRequest.then(()=>requestCheckpoint(true));
    if(!checkpointRequest){
        // Recheck when this reaches the engine queue: movement may have resumed.
        const next=queue.then(()=>force||checkpointDirty&&!input?.active()&&Date.now()-lastActionAt>=autosaveIdleMs?checkpoint():undefined);
        queue=next.catch(()=>{});
        checkpointRequest=next.catch(saveFailed).finally(()=>{checkpointRequest=null});
    }
    return checkpointRequest;
}
function saveFailed(error){checkpointDirty=true;document.querySelector('#save-state').textContent='Autosave failed; will retry';console.warn(error)}
// No timer-driven checkpoints during active walking. One snapshot after a pause,
// then asynchronous browser/folder persistence, coalesces any number of steps.
setInterval(()=>{if(ready&&!document.hidden&&!persisting&&!input?.active()&&checkpointDirty&&Date.now()-lastActionAt>=autosaveIdleMs&&Date.now()-lastCheckpointAttempt>=3000)requestCheckpoint()},250);
document.addEventListener('visibilitychange',()=>{if(document.hidden)requestCheckpoint(true)});
window.addEventListener('pagehide',()=>{requestCheckpoint(true)});
function armDeadline(){
    if(!waiting)return;
    clearTimeout(waiting.timer);
    if(!document.hidden)waiting.timer=setTimeout(()=>{
        const request=waiting;waiting=null;
        const error=Error('Black Gate stopped responding. Refresh to resume your last save.');
        engineFailure=error;engine.terminate();request.reject(error);fail(error);
    },30000);
}
// Browsers suspend background tabs. Hidden time must not kill the game worker.
document.addEventListener('visibilitychange',armDeadline);
function exchange(command){
    return new Promise((resolve,reject)=>{
        if(engineFailure)return reject(engineFailure);
        const bytes=new TextEncoder().encode(command);
        if(bytes.length>mailbox.byteLength-16)return reject(Error('Command too large'));
        const op=command.split(' ')[2];
        waiting={resolve,reject,automatic:op==='CHECKPOINT',loading:op==='LOAD',version:mutationVersion,sentAt:performance.now()};armDeadline();
        globalThis.trinsicTransportState={command,sentAt:performance.now(),pending:true};
        new Uint8Array(mailbox.buffer,16,bytes.length).set(bytes);
        Atomics.store(mailbox,1,bytes.length);Atomics.store(mailbox,0,4);Atomics.notify(mailbox,0);
    });
}
globalThis.trinsicExchange=command=>{
    const op=command.trim().split(' ')[2];
    if(!['SYNC','CHECKPOINT'].includes(op))lastActionAt=Date.now();
    const next=queue.then(async()=>{
        if(op==='CHECKPOINT')return checkpoint();
        const frame=await exchange(command),outcome=frame.split(' ')[5];
        const changed=ready&&!['SYNC','SAVE','DBGSAVE','LOAD','LOOK'].includes(op)&&(['ok','using','merged'].includes(outcome)||outcome.startsWith('split-'));
        if(changed){checkpointDirty=true;mutationVersion++;lastActionAt=Date.now();document.querySelector('#save-state').textContent='Unsaved changes'}
        // Deliver movement immediately; it never waits for checkpoint or disk I/O.
        publishFrame(frame);return frame;
    });queue=next.catch(()=>{});return next;
};
async function receive({data}){
    // NPC updates run between commands too. An error without a waiting request
    // must still stop the transport and reach the player.
    if(data.error){
        const error=Error(data.error);
        engineFailure=error;engine.terminate();
        if(waiting){const request=waiting;waiting=null;clearTimeout(request.timer);request.reject(error)}
        fail(error);return;
    }
    const request=waiting;if(!request)return;
    waiting=null;clearTimeout(request.timer);
    if(globalThis.trinsicTransportState){globalThis.trinsicTransportState.pending=false;globalThis.trinsicTransportState.receivedAt=performance.now()}
    try{
        if(data.save){
            persisting++;
            const saved=persistence.catch(()=>{}).then(async()=>{
            await browserSave(data.save,Date.now(),data.saveSlot);
            if(runtime&&(!request.automatic||Date.now()-lastProfileSync>=10000)){
                await new Promise((resolve,reject)=>runtime.FS.syncfs(false,e=>e?reject(e):resolve()));lastProfileSync=Date.now();
            }
            const external=await saveFolder.write(data.save);
            lastCheckpointAt=Date.now();checkpointDirty=mutationVersion!==request.version;
            document.querySelector('#save-state').textContent=checkpointDirty?'Unsaved changes':request.automatic?'Autosaved':request.loading?'Loaded':'Saved';
            document.querySelector('#save-state').title=(external?'Folder + browser backup':'In this browser')+' · '+new Date(lastCheckpointAt).toLocaleTimeString();
            const row=data.frame.split('\n').find(line=>line.startsWith('E ')&&line.split(' ')[8]==='0')?.split(' ');
            globalThis.trinsicLastSave={automatic:request.automatic,time:lastCheckpointAt,coords:row?row[4]+', '+row[5]:'',durationMs:performance.now()-request.sentAt};
            if(!request.automatic)status.textContent=request.loading?'Loaded saved game':external?'Saved in folder and browser':'Saved in this browser';
            }).finally(()=>{persisting--});
            persistence=saved;
            if(request.automatic)saved.catch(saveFailed);else await saved;
        }
        request.resolve(data.frame);
    }catch(error){request.reject(error);fail(error)}
}

function handOffCanvas(){
    const send=Worker.prototype.postMessage;
    const observed=new WeakSet();
    let transferred=false;
    Worker.prototype.postMessage=function(message,options){
        if(!observed.has(this)){
            observed.add(this);
            this.addEventListener('error',()=>fail(Error('The game stopped. Refresh to resume your last save.')));
        }
        if(!transferred && message?.cmd==='run' && message.moduleCanvasId==='canvas'){
            if(!Object.keys(message.offscreenCanvases||{}).length && !canvas.controlTransferredOffscreen){
                const offscreen=canvas.transferControlToOffscreen();offscreen.id='canvas';
                message.offscreenCanvases={canvas:{offscreenCanvas:offscreen,id:'canvas',canvasSharedPtr:0}};
                transferred=true;return send.call(this,message,[...(Array.isArray(options)?options:[]),offscreen]);
            }
            transferred=true;
        }
        return send.apply(this,arguments);
    };
}
function write(path,bytes){runtime.FS.mkdirTree(path.slice(0,path.lastIndexOf('/'))||'/');runtime.FS.writeFile(path,bytes)}
async function mountArtwork(){
    const response=await fetch('client-art.tar.gz?v='+buildVersion);if(!response.ok)throw Error('Artwork download failed');
    const bytes=new Uint8Array(await new Response(response.body.pipeThrough(new DecompressionStream('gzip'))).arrayBuffer());
    const decode=new TextDecoder();
    for(let offset=0;offset+512<=bytes.length;){
        const name=decode.decode(bytes.subarray(offset,offset+100)).split('\0')[0];if(!name)break;
        const size=parseInt(decode.decode(bytes.subarray(offset+124,offset+136)).replace(/\0/g,'').trim(),8)||0;
        if(name.startsWith('/')||name.split('/').includes('..'))throw Error('Invalid artwork path');
        if(bytes[offset+156]===48||bytes[offset+156]===0)write('/'+name,bytes.subarray(offset+512,offset+512+size));
        offset+=512+Math.ceil(size/512)*512;
    }
}
async function launch(newGame=false){
    telemetry.event('begin');
    delete globalThis.trinsicFailure;launching=true;play.disabled=true;loading.start();loadingStep('Opening Black Gate…',2);
    document.querySelector('#setup').hidden=true;document.querySelector('#stage').hidden=false;
    for(const element of document.querySelectorAll('#setup input, #setup button'))element.disabled=true;
    try{
        if(!crossOriginIsolated)throw Error('This site needs cross-origin isolation headers to run ClassicUO.');
        await slot(installKey,install);
        await slot('launcher-v2-seen',true);
        const address=new URL(location.href);address.searchParams.delete('setup');history.replaceState(null,'',address);
        if(!uo){
            await slot('uo-auto-active',true);
            const downloaded=await downloadUO({read:key=>slot(key),write:(key,value)=>slot(key,value)},(done,total)=>{
                loadingStep('Downloading UO demo data…',5+45*done/total,megabytes(done)+' / '+megabytes(total)+' prepared');
                details.textContent=megabytes(done)+' / '+megabytes(total)+' prepared · Downloads resume if interrupted';
            },previousUO);
            uo=await compactUO(downloaded.files);
            await slot(uoKey,uo);await slot('uo-auto-active',false);await removeSlots(downloaded.keys);
            updateSetup();play.disabled=true;
        }else await slot(uoKey,uo);
        const experience=await fetch('experience.json?v='+buildVersion).then(r=>{if(!r.ok)throw Error('Game startup definition is missing');return r.json()});
        loadingStep('Opening your saved world…',50);
        let saved=await slot(saveKey);
        try{
            const external=await saveFolder.read();
            // A newly chosen folder explicitly selects its existing save. Later
            // launches keep a newer browser backup made while permission was lost.
            if(external&&(!saved||await slot('save-folder-load-v1')||saveFolder.modified>=(await slot('trinsic-save-time-v1')||0))){
                saved=external;await browserSave(external,saveFolder.modified);
            }
            if(saveFolder.available)await slot('save-folder-load-v1',false);
        }
        catch(error){saveFolder.available=false;saveFolder.update('Folder unavailable; using browser save');console.warn(error.message)}
        telemetry.event('stage','native');
        const saves=await Promise.all(Array.from({length:10},async(_,n)=>[n,await slot('trinsic-slot-'+n+'-v1')]));
        let activeSlot=await slot('trinsic-active-slot-v1')||0;
        if(newGame&&saved){
            const latest=new Uint8Array(saved);
            const same=bytes=>bytes&&bytes.byteLength===latest.byteLength&&new Uint8Array(bytes).every((value,i)=>value===latest[i]);
            const previous=saves.find(([,bytes])=>same(bytes))||(!saves[activeSlot][1]?saves[activeSlot]:saves.find(([,bytes])=>!bytes));
            const free=saves.find(row=>row!==previous&&!row[1]);
            if(!free)throw Error('All ten save slots are occupied. Load a game and manage its slots before starting another journey.');
            if(!previous[1]){previous[1]=saved;await slot('trinsic-slot-'+previous[0]+'-v1',saved)}
            activeSlot=free[0];saved=null;
        }
        mailbox=new Int32Array(new SharedArrayBuffer(65536));
        engine=new Worker('worker.js?v='+buildVersion);engine.onmessage=receive;engine.onerror=e=>fail(Error(e.message));
        engine.postMessage({mailbox:mailbox.buffer,audioRing:audio.buffer,install,save:saved,saves,activeSlot,experience});
        await globalThis.trinsicExchange('0 0 SYNC');
        document.querySelector('#setup').hidden=true;document.querySelector('#stage').hidden=false;canvas.hidden=false;
        loadingStep('Loading ClassicUO…',55);handOffCanvas();
        const {dotnet}=await import('./_framework/dotnet.js?v='+buildVersion);
        const hostBuilder=dotnet.withModuleConfig({canvas,onDownloadResourceProgress:(done,total)=>loadingStep('Loading ClassicUO…',55+20*done/Math.max(1,total,done),done+' / '+total+' resources · estimated startup progress'),preRun:[module=>{runtime=module;module.canvas=canvas}]}).
            withEnvironmentVariable('FNA_PLATFORM_BACKEND','SDL2').
            withEnvironmentVariable('FNA3D_FORCE_DRIVER','OpenGL').
            withEnvironmentVariable('TRINSIC_PIPE','browser').
            withEnvironmentVariable('TRINSIC_TOWN','/town').
            withEnvironmentVariable('TRINSIC_INTRO_ASSETS','/intro');
        if(!saved)hostBuilder.withEnvironmentVariable('TRINSIC_READY','1');
        const host=await hostBuilder.create();
        loadingStep('Preparing the client…',75);
        globalThis.trinsicRuntime=runtime;
        runtime.FS.mkdirTree('/Data');runtime.FS.mount(runtime.FS.filesystems.IDBFS,{},'/Data');
        await new Promise((resolve,reject)=>runtime.FS.syncfs(true,e=>e?reject(e):resolve()));
        write('/settings.json',JSON.stringify({clientversion:'7.0.118.46',ultimaonlinedirectory:'/uo',profilespath:'/Data/Profiles',plugins:[],use_verdata:false,is_win_maximized:false,screen_scale:1,maps_layouts:'7168,4096;7168,4096;2304,1600;2560,2048;1448,1448;1280,4096',window_size:{X:1200,Y:900}}));
        for(let i=0;i<uo.length;i++){
            const [name,file]=uo[i];loadingStep('Preparing game data…',75+15*(i+1)/uo.length,`${i+1} / ${uo.length} files`);
            write('/uo/'+name,new Uint8Array(await file.arrayBuffer()));
        }
        loadingStep('Loading Trinsic artwork…',92);await mountArtwork();loadingStep('Preparing Trinsic…',97);
        if(!saved){loadingStep('Preparing the opening…',98);await prepareIntro(install,experience.intro,write)}
        runtime.FS.symlink('/town/tiledata.mul','/uo/tiledata.mul');
        input=installInput(canvas,runtime);canvas.focus();
        loadingStep(saved?'Resuming your save…':'Entering Trinsic…',99);
        host.runMain().then(code=>fail(Error('ClassicUO exited ('+code+'). See the browser console for details.'))).catch(fail);
    }catch(error){launching=false;updateSetup();fail(error)}
}
document.querySelector('#new-game').onclick=()=>launch(true);
fetch('build-info.json?v='+buildVersion).then(r=>r.json()).then(info=>{
    document.querySelector('#build-info').textContent='Build '+(info.buildId||info.sourceCommit?.slice(0,7)||buildVersion);
}).catch(console.warn);
play.onclick=async()=>{music.unlock();try{await saveFolder.reconnect()}catch(error){console.warn(error.message)}await launch()};
try{
    let tracks,musicDisabled,handle,seen;
    [install,uo,tracks,musicDisabled,handle,seen]=await Promise.all([
        slot(installKey),slot(uoKey),
        slot('exult-music-v1'),slot('exult-music-disabled-v1'),slot('save-folder-handle-v1'),slot('launcher-v2-seen')]);
    music.enabled=!musicDisabled;music.set(tracks);
    await saveFolder.set(handle);
    if(seen&&install&&!new URL(location.href).searchParams.has('setup')){loading.start();loadingStep('Reading your saved installation…',1)}
    if(uo){try{uo=await compactUO(uo,message=>{status.textContent=message})}catch(error){if(error.code!=='UO_UPDATE_REQUIRED')throw error;previousUO=uo;uo=null}}
    updateSetup();
    if(seen&&install&&(uo||previousUO||await slot('uo-auto-active'))&&!new URL(location.href).searchParams.has('setup'))await launch();
}catch(error){updateSetup();fail(error)}
