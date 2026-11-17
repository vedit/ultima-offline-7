import {importInstall} from './install.js';
import {installInput} from './client-input.js';
import {selectUO,compactUO,importUO,exportUO,dataSize,megabytes} from './uo-data.js';
import {downloadUO} from './uo-download.js';

const status=document.querySelector('#status');
const details=document.querySelector('#details');
const canvas=document.querySelector('#canvas');
const play=document.querySelector('#play');
const saveButton=document.querySelector('#save');
const exportButton=document.querySelector('#export-uo');
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
        ready=true;saveButton.disabled=false;status.textContent='Trinsic is ready';
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
function fail(error){globalThis.trinsicFailure=error.message||String(error);status.textContent=globalThis.trinsicFailure;console.error(error);saveButton.disabled=true}
let selectingUO=false;
function updateSetup(){play.disabled=!install||selectingUO;exportButton.disabled=!uo||selectingUO;details.textContent=[install?'Ultima VII ready':'Select Ultima VII',uo?'UO demo data: '+megabytes(dataSize(uo)):'UO demo data downloads automatically on first play'].join(' · ')}
document.querySelector('#folder').onchange=async e=>{try{install=await importInstall([...e.target.files]);updateSetup()}catch(error){fail(error)}};
document.querySelector('#uo-folder').onchange=async e=>{try{
    if(!e.target.files.length)return;
    selectingUO=true;uo=null;updateSetup();
    uo=await selectUO([...e.target.files],message=>{status.textContent=message});
    status.textContent='Smaller UO demo data is ready';updateSetup();
}catch(error){uo=null;fail(error)}finally{selectingUO=false;updateSetup()}};
document.querySelector('#uo-pack').onchange=async e=>{try{
    if(!e.target.files.length)return;
    selectingUO=true;uo=null;updateSetup();status.textContent='Opening UO demo pack…';
    uo=await importUO(e.target.files[0]);status.textContent='UO demo pack is ready';updateSetup();
}catch(error){uo=null;fail(error)}finally{selectingUO=false;updateSetup()}};
exportButton.onclick=async()=>{
    exportButton.disabled=true;const label=exportButton.textContent;exportButton.textContent='Packing…';
    try{
        const blob=await exportUO(uo),url=URL.createObjectURL(blob),link=document.createElement('a');
        link.href=url;link.download='trinsic-uo-demo.gz';link.click();setTimeout(()=>URL.revokeObjectURL(url),60000);
        exportButton.title=megabytes(blob.size)+' compressed; for use with this demo build';
        if(!ready)details.textContent='Demo pack: '+megabytes(blob.size)+' compressed. Your original files are unchanged.';
    }catch(error){console.error(error);exportButton.title='Could not export: '+error.message}
    finally{exportButton.disabled=false;exportButton.textContent=label}
};

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
    const request=waiting;if(!request)return;
    waiting=null;clearTimeout(request.timer);
    if(globalThis.trinsicTransportState){globalThis.trinsicTransportState.pending=false;globalThis.trinsicTransportState.receivedAt=performance.now()}
    try{
        if(data.save){
            await slot(saveKey,data.save);
            if(runtime)await new Promise((resolve,reject)=>runtime.FS.syncfs(false,e=>e?reject(e):resolve()));
            status.textContent='Saved in this browser';
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
    delete globalThis.trinsicFailure;play.disabled=true;status.textContent='Opening Black Gate…';
    for(const element of document.querySelectorAll('#setup input'))element.disabled=true;
    try{
        if(!crossOriginIsolated)throw Error('This site needs cross-origin isolation headers to run ClassicUO.');
        await slot(installKey,install);
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
        const saved=await slot(saveKey);
        mailbox=new Int32Array(new SharedArrayBuffer(65536));
        engine=new Worker('worker.js');engine.onmessage=receive;engine.onerror=e=>fail(Error(e.message));
        engine.postMessage({mailbox:mailbox.buffer,install,save:saved});
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
    }catch(error){fail(error);play.disabled=false;for(const element of document.querySelectorAll('#setup input'))element.disabled=false}
}
play.onclick=launch;saveButton.onclick=()=>{if(ready){input.save();canvas.focus()}};
try{[install,uo]=await Promise.all([slot(installKey),slot(uoKey)]);if(uo)uo=await compactUO(uo,message=>{status.textContent=message});updateSetup();if(install&&(uo||await slot('uo-auto-active')))await launch()}catch(error){uo=null;updateSetup();fail(error)}

