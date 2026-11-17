import {importInstall} from './install.js?v=061b846d29b3f66c';
import {installInput} from './client-input.js?v=061b846d29b3f66c';
import {compactUO,megabytes} from './uo-data.js?v=061b846d29b3f66c';
import {downloadUO} from './uo-download.js?v=061b846d29b3f66c';
import {steamPath,SaveFolder} from './folders.js?v=061b846d29b3f66c';
import {selectMusic,ExultMusic} from './exult-music.js?v=061b846d29b3f66c';

const status=document.querySelector('#status');
const details=document.querySelector('#details');
const canvas=document.querySelector('#canvas');
const play=document.querySelector('#play');
const buildVersion=new URL(import.meta.url).searchParams.get('v')||'dev';
const music=new ExultMusic();
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
    status.textContent='Preparing the browser…';
    setTimeout(()=>{status.textContent='Browser setup did not finish. Open this link directly in Chrome or Edge with site storage enabled.'},15000);
    // coi-serviceworker reloads this first navigation with isolation enabled.
    await new Promise(()=>{});
}
const installKey='blackgate-local-install-v1', uoKey='classicuo-local-install-v1', saveKey='trinsic-investigation-v1';
let install,uo,engine,input,runtime,ready=false,visibleSince=performance.now(),stalledStatus;
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
    if(name==='draw-heartbeat'){
        globalThis.trinsicLastDraw=performance.now();
        if(stalledStatus!==undefined&&!globalThis.trinsicFailure){status.textContent=stalledStatus;stalledStatus=undefined}
    }
    console.log('ClassicUO: '+name);
    if(!ready && (name==='draw-heartbeat' || name==='gamescene-active')){
        ready=true;document.querySelector('#folders').hidden=false;status.textContent='Trinsic is ready';
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
function browserSave(bytes,time=Date.now()){return new Promise((resolve,reject)=>{
    const tx=db.transaction('slots','readwrite'),store=tx.objectStore('slots');
    store.put(bytes,saveKey);store.put(time,'trinsic-save-time-v1');
    tx.oncomplete=resolve;tx.onabort=tx.onerror=()=>reject(tx.error);
})}
function fail(error){globalThis.trinsicFailure=error.message||String(error);status.textContent=globalThis.trinsicFailure;console.error(error)}
function updateSetup(){
    for(const element of document.querySelectorAll('#setup input, #setup button'))element.disabled=selecting||launching;
    play.disabled=!install||selecting||launching;
    document.querySelector('#game-selection').textContent=install?'Ultima VII ready':'No folder selected';
    document.querySelector('#music-selection').textContent=music.tracks.size?music.tracks.size+' MT-32 tracks ready':'No music selected';
    document.querySelector('#clear-music').hidden=!music.tracks.size;
    document.querySelector('#music-volume-row').hidden=!music.tracks.size;
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
    const tracks=await selectMusic(files);await slot('exult-music-v1',tracks);music.set(tracks);
    await slot('music-folder-handle-v1',null);
}
document.querySelector('#choose-music').onclick=()=>document.querySelector('#music-folder').click();
document.querySelector('#music-folder').onchange=e=>choosing(async()=>{if(e.target.files.length)await importMusic([...e.target.files])});
document.querySelector('#clear-music').onclick=()=>choosing(async()=>{await slot('exult-music-v1',[]);await slot('music-folder-handle-v1',null);music.set([])});
document.querySelector('#music-volume').oninput=e=>{music.setVolume(e.target.value/100);slot('exult-music-volume-v1',music.volume).catch(console.warn)};
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
document.querySelector('#folders').onclick=()=>{const url=new URL(location.href);url.searchParams.set('setup','1');location.assign(url)};
document.addEventListener('pointerdown',()=>music.unlock(),true);
window.addEventListener('keydown',()=>music.unlock(),true);

let waiting,mailbox,queue=Promise.resolve(),engineFailure;
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
        waiting={resolve,reject};armDeadline();
        globalThis.trinsicTransportState={command,sentAt:performance.now(),pending:true};
        new Uint8Array(mailbox.buffer,16,bytes.length).set(bytes);
        Atomics.store(mailbox,1,bytes.length);Atomics.store(mailbox,0,4);Atomics.notify(mailbox,0);
    });
}
globalThis.trinsicExchange=command=>{
    const next=queue.then(()=>exchange(command));queue=next.catch(()=>{});return next;
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
    if(data.music)music.apply(data.music);
    const request=waiting;if(!request)return;
    waiting=null;clearTimeout(request.timer);
    if(globalThis.trinsicTransportState){globalThis.trinsicTransportState.pending=false;globalThis.trinsicTransportState.receivedAt=performance.now()}
    try{
        if(data.save){
            await browserSave(data.save);
            if(runtime)await new Promise((resolve,reject)=>runtime.FS.syncfs(false,e=>e?reject(e):resolve()));
            const external=await saveFolder.write(data.save);
            status.textContent=external?'Saved in folder and browser':'Saved in this browser';
        }
        const player=data.frame.split('\n').find(line=>line.startsWith('E ')&&line.split(' ')[8]==='0');
        if(player){const fields=player.split(' ');document.querySelector('#coords').textContent=fields[4]+', '+fields[5];}
        globalThis.trinsicLastFrame=data.frame;
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
    const response=await fetch('client-art.tar.gz');if(!response.ok)throw Error('Artwork download failed');
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
async function launch(){
    delete globalThis.trinsicFailure;launching=true;play.disabled=true;status.textContent='Opening Black Gate…';
    for(const element of document.querySelectorAll('#setup input, #setup button'))element.disabled=true;
    try{
        if(!crossOriginIsolated)throw Error('This site needs cross-origin isolation headers to run ClassicUO.');
        await slot(installKey,install);
        await slot('launcher-v2-seen',true);
        const address=new URL(location.href);address.searchParams.delete('setup');history.replaceState(null,'',address);
        if(!uo){
            await slot('uo-auto-active',true);
            const downloaded=await downloadUO({read:key=>slot(key),write:(key,value)=>slot(key,value)},(done,total)=>{
                status.textContent='Downloading UO demo data… '+Math.floor(done/total*100)+'%';
                details.textContent=megabytes(done)+' / '+megabytes(total)+' prepared · Downloads resume if interrupted';
            });
            uo=await compactUO(downloaded.files);
            await slot(uoKey,uo);await slot('uo-auto-active',false);await removeSlots(downloaded.keys);
            updateSetup();play.disabled=true;
        }else await slot(uoKey,uo);
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
        mailbox=new Int32Array(new SharedArrayBuffer(65536));
        engine=new Worker('worker.js?v='+buildVersion);engine.onmessage=receive;engine.onerror=e=>fail(Error(e.message));
        engine.postMessage({mailbox:mailbox.buffer,install,save:saved,music:music.tracks.size>0});
        await globalThis.trinsicExchange('0 0 SYNC');
        document.querySelector('#setup').hidden=true;document.querySelector('#stage').hidden=false;canvas.hidden=false;
        status.textContent='Loading ClassicUO…';handOffCanvas();
        const {dotnet}=await import('./_framework/dotnet.js');
        const host=await dotnet.withModuleConfig({canvas,preRun:[module=>{runtime=module;module.canvas=canvas}]}).
            withEnvironmentVariable('FNA_PLATFORM_BACKEND','SDL2').
            withEnvironmentVariable('FNA3D_FORCE_DRIVER','OpenGL').
            withEnvironmentVariable('TRINSIC_PIPE','browser').
            withEnvironmentVariable('TRINSIC_TOWN','/town').create();
        globalThis.trinsicRuntime=runtime;
        runtime.FS.mkdirTree('/Data');runtime.FS.mount(runtime.FS.filesystems.IDBFS,{},'/Data');
        await new Promise((resolve,reject)=>runtime.FS.syncfs(true,e=>e?reject(e):resolve()));
        write('/settings.json',JSON.stringify({clientversion:'7.0.118.46',ultimaonlinedirectory:'/uo',profilespath:'/Data/Profiles',plugins:[],use_verdata:false,is_win_maximized:false,screen_scale:1,maps_layouts:'7168,4096;7168,4096;2304,1600;2560,2048;1448,1448;1280,4096',window_size:{X:1200,Y:900}}));
        for(let i=0;i<uo.length;i++){
            const [name,file]=uo[i];status.textContent=`Reading local UO data ${i+1}/${uo.length}`;
            write('/uo/'+name,new Uint8Array(await file.arrayBuffer()));
        }
        status.textContent='Loading Trinsic artwork…';await mountArtwork();
        runtime.FS.symlink('/town/tiledata.mul','/uo/tiledata.mul');
        input=installInput(canvas,runtime);canvas.focus();
        status.textContent=saved?'Resuming your save…':'Entering Trinsic…';
        host.runMain().then(code=>fail(Error('ClassicUO exited ('+code+'). See the browser console for details.'))).catch(fail);
    }catch(error){launching=false;updateSetup();fail(error)}
}
play.onclick=async()=>{music.unlock();try{await saveFolder.reconnect()}catch(error){console.warn(error.message)}await launch()};
try{
    let tracks,volume,handle,seen;
    [install,uo,tracks,volume,handle,seen]=await Promise.all([
        slot(installKey),slot(uoKey),
        slot('exult-music-v1'),slot('exult-music-volume-v1'),slot('save-folder-handle-v1'),slot('launcher-v2-seen')]);
    music.set(tracks);if(typeof volume==='number')music.setVolume(volume);
    document.querySelector('#music-volume').value=Math.round(music.volume*100);
    await saveFolder.set(handle);
    if(uo)uo=await compactUO(uo,message=>{status.textContent=message});updateSetup();
    if(seen&&install&&(uo||await slot('uo-auto-active'))&&!new URL(location.href).searchParams.has('setup'))await launch();
}catch(error){updateSetup();fail(error)}
