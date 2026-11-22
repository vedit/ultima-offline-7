import {importInstall} from './install.js?v=92dfba009d583c67';
import {installInput} from './client-input.js?v=92dfba009d583c67';
import {compactUO,megabytes} from './uo-data.js?v=92dfba009d583c67';
import {downloadUO} from './uo-download.js?v=92dfba009d583c67';
import {prepareArtIndexes,prepareLocaleIndex} from './classic-index.js?v=92dfba009d583c67';
import {framePlan,mountFrameArt} from './frame-art.js?v=92dfba009d583c67';
import {steamPath,SaveFolder} from './folders.js?v=92dfba009d583c67';
import {selectMusic,ExultMusic} from './exult-music.js?v=92dfba009d583c67';
import {LoadingScreen} from './loading.js?v=92dfba009d583c67';
import {prepareIntro} from './intro.js?v=92dfba009d583c67';
import {installAudio} from './audio.js?v=92dfba009d583c67';
import {readReplay} from './replay-store.js?v=92dfba009d583c67';

const replayId=new URL(location.href).searchParams.get('replay');
const isReplay=replayId!==null;
const status=document.querySelector('#status');
const details=document.querySelector('#details');
const canvas=document.querySelector('#canvas');
const play=document.querySelector('#play');
const loading=new LoadingScreen();
const toolbar=document.querySelector('#toolbar'),showToolbar=document.querySelector('#show-toolbar');
const downloadCrash=document.querySelector('#download-crash');
let lastTile=null,lastSave=null,crashReport=null;
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
if(isReplay){
    document.title='Ultima Offline 7 Â· Crash replay';
    document.querySelector('#replay-label').hidden=false;
    document.querySelector('#setup h2').textContent='Open crash replay';
    for(const id of ['#save-settings','#usage-settings','#new-game-row'])document.querySelector(id).hidden=true;
}
// UO7 analytics integration v2 (optional; failures cannot stop the game).
const telemetry = isReplay ? {event(){}} : (()=>{
    let sink, pending=[];
    import('./analytics/browser.js?v='+buildVersion).then(({connect})=>{
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
    loading.start();loadingStep('Preparing the browserâ€¦',0);
    setTimeout(()=>{telemetry.event('begin');telemetry.event('fail');status.textContent='Browser setup did not finish. Open this link directly in Chrome or Edge with site storage enabled.';loading.error(status.textContent)},15000);
    // coi-serviceworker reloads this first navigation with isolation enabled.
    await new Promise(()=>{});
}
const installKey='blackgate-local-install-v1', uoKey='classicuo-local-install-v1', saveKey='trinsic-investigation-v1';
let install,uo,previousUO,engine,input,runtime,ready=false,visibleSince=performance.now(),stalledStatus;
let partialInstall,afterFirstFrame;
const partialKey='classicuo-stream-install-v1';
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
        if(afterFirstFrame)setTimeout(afterFirstFrame,0);
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
function frameKeys(){return new Promise((resolve,reject)=>{
    const request=db.transaction('slots').objectStore('slots').getAllKeys(IDBKeyRange.bound('uo-frame:','uo-frame:~'));
    request.onsuccess=()=>resolve(request.result);request.onerror=()=>reject(request.error);
})}
function frameBlobs(keys){return new Promise((resolve,reject)=>{
    const tx=db.transaction('slots'),s=tx.objectStore('slots'),requests=keys.map(key=>s.get(key));
    tx.oncomplete=()=>resolve(requests.map(request=>request.result));tx.onerror=tx.onabort=()=>reject(tx.error);
})}
function browserSave(bytes,time=Date.now(),saveSlot,tile=null,manual=true){
    const numbered=Number.isInteger(saveSlot)&&saveSlot>=0&&saveSlot<10;
    const details={slot:numbered?saveSlot:null,tile,savedAtMs:time};
    if(isReplay){lastSave={bytes,details};return Promise.resolve()}
    return new Promise((resolve,reject)=>{
    const tx=db.transaction('slots','readwrite'),store=tx.objectStore('slots');
    store.put(bytes,saveKey);store.put(time,'trinsic-save-time-v1');
    store.put(details,'trinsic-save-details-v1');
    if(numbered){
        if(manual)store.put(bytes,'trinsic-slot-'+saveSlot+'-v1');
        store.put(saveSlot,'trinsic-active-slot-v1');
    }
    tx.oncomplete=()=>{lastSave={bytes,details};resolve()};tx.onabort=tx.onerror=()=>reject(tx.error);
})}
function readBrowserSave(){return new Promise((resolve,reject)=>{
    const tx=db.transaction('slots','readonly'),store=tx.objectStore('slots');
    const bytes=store.get(saveKey),time=store.get('trinsic-save-time-v1'),details=store.get('trinsic-save-details-v1');
    tx.oncomplete=()=>resolve(bytes.result?{bytes:bytes.result,details:details.result&&details.result.savedAtMs===time.result
        ?details.result:{slot:null,tile:null,savedAtMs:time.result||null}}:null);
    tx.onabort=tx.onerror=()=>reject(tx.error);
})}
function playerTile(frame){
    for(const line of frame.split('\n')){
        if(!line.startsWith('E '))continue;
        const fields=line.split(' ');
        if(fields[8]!=='0')continue;
        const [x,y,z]=fields.slice(4,7).map(Number);
        return [x,y,z].every(Number.isInteger)?{x,y,z}:null;
    }
    return null;
}
function fail(error){
    if(!crashReport){
        const context={tile:lastTile,save:lastSave?.details??null};
        crashReport={context,bytes:lastSave?.bytes,failedAtMs:Date.now()};
        telemetry.event('fail',{...context,bytes:crashReport.bytes});
        downloadCrash.hidden=false;toolbar.hidden=false;showToolbar.hidden=true;
    }
    globalThis.trinsicFailure=error.message||String(error);status.textContent=globalThis.trinsicFailure;console.error(error);
    if(!ready&&!loading.root.hidden)loading.error(globalThis.trinsicFailure);
}
downloadCrash.onclick=async()=>{
    const report=crashReport;if(!report)return;
    downloadCrash.disabled=true;
    try{
        const save=report.context.save&&{...report.context.save};
        if(save&&report.bytes){
            const file=new FileReader();
            save.base64=await new Promise((resolve,reject)=>{
                file.onload=()=>resolve(file.result.slice(file.result.indexOf(',')+1));
                file.onerror=()=>reject(file.error);
                file.readAsDataURL(new Blob([report.bytes],{type:'application/octet-stream'}));
            });
        }
        const contents={version:1,build:buildVersion,failedAtMs:report.failedAtMs,tile:report.context.tile,save};
        const url=URL.createObjectURL(new Blob([JSON.stringify(contents,null,2)],{type:'application/json'}));
        const link=document.createElement('a');link.href=url;link.download='trinsic-crash-report.json';link.click();
        setTimeout(()=>URL.revokeObjectURL(url),1000);
    }catch(error){console.warn(error);status.textContent='Could not create the crash download. Try again.'}
    finally{downloadCrash.disabled=false}
};
function updateSetup(){
    for(const element of document.querySelectorAll('#setup input, #setup button')){
        if(!element.closest('#usage-settings'))element.disabled=selecting||launching;
    }
    play.disabled=!install||selecting||launching;
    document.querySelector('#new-game').disabled=play.disabled;
    document.querySelector('#first-setup').hidden=!!install;
    document.querySelector('#launch-actions').hidden=!install;
    document.querySelector('#folder-title').textContent=install?'Your game folder':'Already have the game?';
    document.querySelector('#folder-description').hidden=!!install;
    const chooseGame=document.querySelector('#choose-game');
    chooseGame.textContent=install?'Change game folder':'Choose game folder';
    chooseGame.classList.toggle('quiet',!!install);
    document.querySelector('#game-selection').textContent=install?'Ultima VII ready in this browser':'No folder selected';
    document.querySelector('#music-selection').textContent=music.tracks.size?music.tracks.size+' MT-32 tracks ready':'No music selected';
    document.querySelector('#clear-music').hidden=!music.tracks.size;
    document.querySelector('#clear-save').hidden=!saveFolder.handle;
    details.textContent=uo?'Ultima Online demo files are ready.':'Ultima Online demo files download automatically on first play.';
}
async function choosing(action,errorNotice){
    if(selecting||launching)return;
    selecting=true;updateSetup();
    try{await action();delete globalThis.trinsicFailure;status.textContent=install?'Ready to play':'Choose your Ultima VII folder'}
    catch(error){
        if(error.name!=='AbortError'){
            if(errorNotice)errorNotice.textContent=error.message;
            else fail(error);
        }
    }
    finally{selecting=false;updateSetup()}
}
// Imports use the read-only file input picker. The File System Access picker
// rejects protected Steam/Exult locations even when only read access is requested.
document.querySelector('#choose-game').onclick=()=>document.querySelector('#folder').click();
document.querySelector('#folder').onchange=event=>{
    const files=[...event.target.files];
    if(!files.length)return;
    event.target.value='';
    const errorNotice=document.querySelector('#folder-error');
    errorNotice.textContent='';
    return choosing(async()=>{
        document.querySelector('#game-selection').textContent='Reading game filesâ€¦';
        const imported=await importInstall(files);
        await slot(installKey,imported);
        install=imported;
        await slot('game-folder-handle-v1',null);
        document.querySelector('#folder-help').open=false;
    },errorNotice);
};
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
    if(isReplay)return;
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
let profileWrites=Promise.resolve();
function flushProfile(){
    profileWrites=profileWrites.catch(()=>{}).then(async()=>{
        await new Promise((resolve,reject)=>runtime.FS.syncfs(false,error=>error?reject(error):resolve()));
        lastProfileSync=Date.now();
    });
    return profileWrites;
}
let lastActionAt=0,mutationVersion=0,persistence=Promise.resolve(),persisting=0;
const autosaveIdleMs=1500;
function publishFrame(frame){telemetry.event('frame',frame);
    const tile=playerTile(frame);
    if(tile){lastTile=tile;document.querySelector('#coords').textContent=tile.x+', '+tile.y}
    globalThis.trinsicLastFrame=frame;
}
async function checkpoint(){
    lastCheckpointAttempt=Date.now();document.querySelector('#save-state').textContent='Savingâ€¦';
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
function saveFailed(error){telemetry.event('save-fail');checkpointDirty=true;document.querySelector('#save-state').textContent='Autosave failed; will retry';console.warn(error)}
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
        const frame=await exchange(command);
        // Original maps and signs return an image payload from SCREEN. Only S records describe world state.
        if(!frame.startsWith('S '))return frame;
        const outcome=frame.split(' ',6)[5];telemetry.event('action',{op,result:outcome});
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
            const tile=playerTile(data.frame);
            await browserSave(data.save,Date.now(),data.saveSlot,tile,!request.automatic);
            if(!isReplay&&runtime&&(!request.automatic||Date.now()-lastProfileSync>=10000)){
                await flushProfile();
            }
            const external=await saveFolder.write(data.save);telemetry.event('saved',{kind:request.loading?'load':request.automatic?'auto':'manual',ms:performance.now()-request.sentAt});
            lastCheckpointAt=Date.now();checkpointDirty=mutationVersion!==request.version;
            document.querySelector('#save-state').textContent=checkpointDirty?'Unsaved changes':isReplay?'Replay checkpoint':request.automatic?'Autosaved':request.loading?'Loaded':'Saved';
            document.querySelector('#save-state').title=(isReplay?'For this replay':external?'Folder + browser backup':'In this browser')+' Â· '+new Date(lastCheckpointAt).toLocaleTimeString();
            globalThis.trinsicLastSave={automatic:request.automatic,time:lastCheckpointAt,coords:tile?tile.x+', '+tile.y:'',durationMs:performance.now()-request.sentAt};
            if(!request.automatic)status.textContent=request.loading?'Loaded saved game':isReplay?'Saved for this replay':external?'Saved in folder and browser':'Saved in this browser';
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
async function stockStatic(link){
    const match=/^uo-static\/(\d+)\/([0-9a-f]{16})$/.exec(link);
    if(!match)throw Error('Invalid stock art reference');
    const fs=runtime.FS,slot=0x4000+Number(match[1]);
    function read(file,start,length){
        const bytes=new Uint8Array(length),stream=fs.open('/uo/'+file,'r');
        try{if(fs.read(stream,bytes,0,length,start)!==length)throw Error('Incomplete UO artwork')}
        finally{fs.close(stream)}
        return bytes;
    }
    if(!fs.analyzePath('/uo/artlegacymul.uop').exists){
        const index=new DataView(read('artidx.mul',slot*12,12).buffer);
        return read('art.mul',index.getUint32(0,true),index.getUint32(4,true));
    }
    const file='artlegacymul.uop',key=BigInt('0x'+match[2]);
    const header=new DataView(read(file,0,28).buffer),visited=new Set();
    let block=Number(header.getBigUint64(12,true));
    while(block && !visited.has(block)){
        visited.add(block);
        const head=new DataView(read(file,block,12).buffer);
        const entries=new DataView(read(file,block+12,head.getUint32(0,true)*34).buffer);
        for(let at=0;at<entries.byteLength;at+=34){
            if(entries.getBigUint64(at+20,true)!==key)continue;
            const start=Number(entries.getBigUint64(at,true))+entries.getUint32(at+8,true);
            const bytes=read(file,start,entries.getUint32(at+12,true));
            if(entries.getUint16(at+32,true)===0)return bytes;
            const inflated=new Blob([bytes]).stream().pipeThrough(new DecompressionStream('deflate'));
            return new Uint8Array(await new Response(inflated).arrayBuffer());
        }
        block=Number(head.getBigUint64(4,true));
    }
    throw Error('Missing stock artwork '+match[1]);
}
async function mountArtwork(){
    const response=await fetch('client-art.tar.gz?v='+buildVersion);if(!response.ok)throw Error('Artwork download failed');
    const bytes=new Uint8Array(await new Response(response.body.pipeThrough(new DecompressionStream('gzip'))).arrayBuffer());
    const decode=new TextDecoder();
    for(let offset=0;offset+512<=bytes.length;){
        const name=decode.decode(bytes.subarray(offset,offset+100)).split('\0')[0];if(!name)break;
        const size=parseInt(decode.decode(bytes.subarray(offset+124,offset+136)).replace(/\0/g,'').trim(),8)||0;
        if(name.startsWith('/')||name.split('/').includes('..'))throw Error('Invalid artwork path');
        if(bytes[offset+156]===48||bytes[offset+156]===0)write('/'+name,bytes.subarray(offset+512,offset+512+size));
        if(bytes[offset+156]===50){
            const link=decode.decode(bytes.subarray(offset+157,offset+257)).split('\0')[0];
            write('/'+name,await stockStatic(link));
        }
        offset+=512+Math.ceil(size/512)*512;
    }
}
async function launch(newGame=false){
    if(isReplay)return startGame(newGame);
    await navigator.locks.request('trinsic-player-session',{ifAvailable:true},async lock=>{
        if(!lock){status.textContent='The game is open in another tab. Close it to play here.';loading.finish();return}
        await startGame(newGame);
        if(engine)await new Promise(()=>{}); // Document lifetime owns the game.
    });
}
// The framework manifest supplies a SHA-256 integrity value for each binary.
// Keep that identity across releases while executable modules use their release URL.
function downloadRuntime(){
    return import('./_framework/dotnet.js?v='+buildVersion).then(async({dotnet})=>{
        let cache;
        async function binary(uri,integrity){
            cache??=Promise.resolve().then(()=>caches.open('trinsic-runtime-sha256-v1')).catch(()=>null);
            const store=await cache;
            const key=new URL('/.trinsic-runtime/'+encodeURIComponent(integrity),location.origin).href;
            const hit=await store?.match(key).catch(()=>null);
            if(hit)return hit;
            const response=await fetch(uri,{integrity});
            if(response.ok&&store)await store.put(key,response.clone()).catch(()=>{});
            return response;
        }
        dotnet.withResourceLoader((_type,name,uri,integrity)=>{
            if(/\.(wasm|dat)$/i.test(name)&&/^sha256-[A-Za-z0-9+/]{43}=$/.test(integrity))return binary(uri,integrity);
        });
        await dotnet.download();
        return dotnet;
    });
}

async function startGame(newGame){
    telemetry.event('begin');
    lastTile=null;crashReport=null;downloadCrash.hidden=true;
    delete globalThis.trinsicFailure;launching=true;play.disabled=true;loading.start();loadingStep('Opening Black Gateâ€¦',2);
    document.querySelector('#setup').hidden=true;document.querySelector('#stage').hidden=false;
    for(const element of document.querySelectorAll('#setup input, #setup button')){
        if(!element.closest('#usage-settings'))element.disabled=true;
    }
    try{
        const replay=isReplay?await readReplay(replayId):null;
        if(isReplay&&!replay)throw Error('This crash replay is missing or expired. Open the report from the analytics dashboard again.');
        if(replay&&replay.build!==buildVersion){
            const label=document.querySelector('#replay-label');
            label.textContent='Crash replay Â· different build from the report';
            label.title='Reported launch: '+replay.build+' Â· This launch: '+buildVersion;
        }
        if(!crossOriginIsolated)throw Error('This site needs cross-origin isolation headers to run ClassicUO.');
        const runtimeDownload=downloadRuntime();
        // Installation can fail before the runtime is awaited.
        runtimeDownload.catch(()=>{});
        await slot(installKey,install);
        await slot('launcher-v2-seen',true);
        const address=new URL(location.href);address.searchParams.delete('setup');history.replaceState(null,'',address);
        const sparse=uo?null:await framePlan();
        let mountedFiles=uo;
        if(sparse&&partialInstall?.version===sparse.version){
            mountedFiles=partialInstall.files;
        }else if(!uo){
            await slot('uo-auto-active',true);
            const downloaded=await downloadUO({read:key=>slot(key),write:(key,value)=>slot(key,value)},(done,total)=>{
                loadingStep('Downloading UO demo dataâ€¦',5+45*done/total,megabytes(done)+' / '+megabytes(total)+' prepared');
                details.textContent=megabytes(done)+' / '+megabytes(total)+' prepared Â· Downloads resume if interrupted';
            },previousUO||partialInstall?.files,sparse);
            if(sparse){
                mountedFiles=downloaded.files;
                partialInstall={version:sparse.version,files:mountedFiles};
                await slot(partialKey,partialInstall);
            }else{
                uo=await compactUO(downloaded.files);mountedFiles=uo;
                await slot(uoKey,uo);
            }
            await slot('uo-auto-active',false);await removeSlots(downloaded.keys);
            updateSetup();play.disabled=true;
        }
        const artIndexes=prepareArtIndexes(mountedFiles,sparse,buildInfo);
        const localeIndex=prepareLocaleIndex(new Map(mountedFiles).get('cliloc.enu'),slot);
        const experience=await fetch('experience.json?v='+buildVersion).then(r=>{if(!r.ok)throw Error('Game startup definition is missing');return r.json()});
        loadingStep('Opening your saved worldâ€¦',50);
        lastSave=replay?{bytes:replay.bytes,details:{slot:null,tile:null,savedAtMs:null}}:await readBrowserSave();
        let saved=lastSave?.bytes;
        try{
            const external=isReplay?null:await saveFolder.read();
            // A newly chosen folder explicitly selects its existing save. Later
            // launches keep a newer browser backup made while permission was lost.
            if(external&&(!saved||await slot('save-folder-load-v1')||saveFolder.modified>=(lastSave?.details.savedAtMs||0))){
                saved=external;await browserSave(external,saveFolder.modified);
            }
            if(saveFolder.available)await slot('save-folder-load-v1',false);
        }
        catch(error){saveFolder.available=false;saveFolder.update('Folder unavailable; using browser save');console.warn(error.message)}
        telemetry.event('stage','native');
        const saves=isReplay?[[0,replay.bytes]]:await Promise.all(Array.from({length:10},async(_,n)=>[n,await slot('trinsic-slot-'+n+'-v1')]));
        let activeSlot=isReplay?0:await slot('trinsic-active-slot-v1')||0;
        // Migrate single-save profiles once. A modern resume archive stays separate from F5.
        if(saved && !isReplay && !(await slot('separate-resume-v1')) && saves.every(([,bytes])=>!bytes)){
            saves[activeSlot][1]=saved;
            await slot('trinsic-slot-'+activeSlot+'-v1',saved);
        }
        if(!isReplay)await slot('separate-resume-v1',true);
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
        telemetry.event('context',{mode:saved?'resume':'new',storage:saveFolder.available?'folder':'browser',music:music.tracks.size>0&&music.enabled?'exult':'native'});
        engine=new Worker('worker.js?v='+buildVersion);engine.onmessage=receive;engine.onerror=e=>fail(Error(e.message));
        engine.postMessage({mailbox:mailbox.buffer,audioRing:audio.buffer,install,save:saved,saves,activeSlot,experience});
        await globalThis.trinsicExchange('0 0 SYNC');
        document.querySelector('#setup').hidden=true;document.querySelector('#stage').hidden=false;canvas.hidden=false;
        loadingStep('Loading ClassicUOâ€¦',55);handOffCanvas();
        const dotnet=await runtimeDownload;
        const hostBuilder=dotnet.withModuleConfig({canvas,onDownloadResourceProgress:(done,total)=>loadingStep('Loading ClassicUOâ€¦',55+20*done/Math.max(1,total,done),done+' / '+total+' resources Â· estimated startup progress'),preRun:[module=>{runtime=module;module.canvas=canvas}]}).
            withEnvironmentVariable('FNA_PLATFORM_BACKEND','SDL2').
            withEnvironmentVariable('FNA3D_FORCE_DRIVER','OpenGL').
            withEnvironmentVariable('TRINSIC_PIPE','browser').
            withEnvironmentVariable('TRINSIC_TOWN','/town').
            withEnvironmentVariable('TRINSIC_INTRO_ASSETS','/intro');
        if(!saved)hostBuilder.withEnvironmentVariable('TRINSIC_READY','1');
        const host=await hostBuilder.create();
        loadingStep('Preparing the clientâ€¦',75);
        globalThis.trinsicRuntime=runtime;
        runtime.FS.mkdirTree('/Data');
        if(!isReplay){
            runtime.FS.mount(runtime.FS.filesystems.IDBFS,{},'/Data');
            await new Promise((resolve,reject)=>runtime.FS.syncfs(true,e=>e?reject(e):resolve()));
            globalThis.__trinsic_flush_profile=()=>flushProfile().catch(error=>console.warn('Could not save client preferences',error));
        }
        write('/settings.json',JSON.stringify({clientversion:'7.0.118.46',ultimaonlinedirectory:'/uo',profilespath:'/Data/Profiles',plugins:[],use_verdata:false,is_win_maximized:false,screen_scale:1,maps_layouts:'7168,4096;7168,4096;2304,1600;2560,2048;1448,1448;1280,4096',window_size:{X:1200,Y:900}}));
        for(let i=0;i<mountedFiles.length;i++){
            const [name,file]=mountedFiles[i];loadingStep('Preparing game dataâ€¦',75+15*(i+1)/mountedFiles.length,`${i+1} / ${mountedFiles.length} files`);
            write('/uo/'+name,new Uint8Array(await file.arrayBuffer()));
        }
        for(const [name,bytes] of await artIndexes)write('/indexes/'+name,bytes);
        const localStrings=await localeIndex;
        if(localStrings)write('/indexes/cliloc.enu',localStrings);
        if(sparse)afterFirstFrame=await mountFrameArt(runtime.FS,sparse,saved?'saved':'opening',{read:slot,write:slot,keys:frameKeys,blobs:frameBlobs},fail);
        loadingStep('Loading Trinsic artworkâ€¦',92);await mountArtwork();loadingStep('Preparing Trinsicâ€¦',97);
        if(!saved){loadingStep('Preparing the openingâ€¦',98);await prepareIntro(install,experience.intro,write)}
        runtime.FS.symlink('/town/tiledata.mul','/uo/tiledata.mul');
        input=installInput(canvas,runtime);canvas.focus();
        loadingStep(saved?'Resuming your saveâ€¦':'Entering Trinsicâ€¦',99);
        host.runMain().then(code=>fail(Error('ClassicUO exited ('+code+'). See the browser console for details.'))).catch(fail);
    }catch(error){launching=false;updateSetup();fail(error)}
}
document.querySelector('#new-game').onclick=()=>launch(true);
const buildInfo=fetch('build-info.json?v='+buildVersion).then(r=>r.json()).then(info=>{
    document.querySelector('#build-info').textContent='Build '+(info.buildId||info.sourceCommit?.slice(0,7)||buildVersion);
    return info;
}).catch(console.warn);
play.onclick=async()=>{music.unlock();try{await saveFolder.reconnect()}catch(error){console.warn(error.message)}await launch()};
try{
    let tracks,musicDisabled,handle,seen;
    [install,uo,tracks,musicDisabled,handle,seen]=await Promise.all([
        slot(installKey),slot(uoKey),
        slot('exult-music-v1'),slot('exult-music-disabled-v1'),slot('save-folder-handle-v1'),slot('launcher-v2-seen')]);
    music.enabled=!musicDisabled;music.set(tracks);
    await saveFolder.set(isReplay?null:handle);
    const useSetup=new URL(location.href).searchParams.has('setup');
    if((seen||isReplay)&&install&&!useSetup){loading.start();loadingStep('Reading your saved installationâ€¦',1)}
    if(uo){try{uo=await compactUO(uo,message=>{status.textContent=message})}catch(error){if(error.code!=='UO_UPDATE_REQUIRED')throw error;previousUO=uo;uo=null}}
    updateSetup();
    if(install&&useSetup)status.textContent='Ready to play';
    if(!uo)partialInstall=await slot(partialKey);
    if(install&&!useSetup&&(isReplay||seen&&(uo||previousUO||partialInstall||await slot('uo-auto-active'))))await launch();
}catch(error){updateSetup();fail(error)}
