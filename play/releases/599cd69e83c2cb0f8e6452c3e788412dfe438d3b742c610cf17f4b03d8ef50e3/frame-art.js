// ClassicUO reads its open files synchronously. Keep their original lengths and
// offsets, loading only verified bytes into the browser's sparse backing store.
import './vendor/js-sha256/sha256.js';

const hex=bytes=>Array.from(new Uint8Array(bytes),v=>v.toString(16).padStart(2,'0')).join('');
const cacheKey=part=>'uo-frame:'+part.sha256;

export async function framePlan(){
    const pinned=document.querySelector('meta[name="uo-frame-art"]')?.content;
    if(!pinned)return null;
    const response=await fetch(new URL(pinned,document.baseURI));
    if(!response.ok)throw Error('Could not load the release’s startup art index.');
    const plan=await response.json();
    if(plan.format!==1||!/^[0-9a-f]{20}$/.test(plan.version)||!(plan.pageBytes>0&&plan.pageBytes<=4194304))throw Error('Invalid startup art index.');
    return plan;
}

export async function mountFrameArt(fs,plan,mode,storage,onError){
    const base=new URL(document.querySelector('meta[name="uo-api-base"]').content,document.baseURI);
    const url=part=>new URL(plan.version+'/'+part.id,base).href;
    const cached=new Set(await storage.keys());
    const loaded=new Map(),pending=new Map(),local=new Map();
    function remember(part,bytes){
        loaded.set(part.sha256,bytes);
        storage.write(cacheKey(part),new Blob([bytes])).catch(error=>console.warn('Art cache write failed',error));
        return bytes;
    }
    async function valid(bytes,part){
        return bytes.byteLength===part.size&&hex(await crypto.subtle.digest('SHA-256',bytes))===part.sha256;
    }
    async function load(part){
        if(loaded.has(part.sha256))return loaded.get(part.sha256);
        if(pending.has(part.sha256))return pending.get(part.sha256);
        const work=(async()=>{
            if(cached.has(cacheKey(part))){
                const blob=await storage.read(cacheKey(part));
                if(blob instanceof Blob&&blob.size===part.size){
                    const bytes=new Uint8Array(await blob.arrayBuffer());
                    if(await valid(bytes,part)){loaded.set(part.sha256,bytes);return bytes}
                }
            }
            const response=await fetch(url(part),{credentials:'omit'});
            if(!response.ok)throw Error('Could not retrieve '+part.id+' ('+response.status+').');
            const bytes=new Uint8Array(await response.arrayBuffer());
            if(!await valid(bytes,part))throw Error('Art verification failed for '+part.id+'.');
            return remember(part,bytes);
        })();
        pending.set(part.sha256,work);
        try{return await work}finally{pending.delete(part.sha256)}
    }
    function readPage(part){
        if(loaded.has(part.sha256))return loaded.get(part.sha256);
        // A player can jump directly to an unfamiliar saved location or panel.
        // A FileStream read must return its genuine bytes on this very call.
        try{
            const fromLocal=local.get(part.sha256);
            const xhr=new XMLHttpRequest();
            const blobUrl=fromLocal&&URL.createObjectURL(fromLocal);
            xhr.open('GET',blobUrl||url(part),false);
            xhr.overrideMimeType('text/plain; charset=x-user-defined');
            try{xhr.send()}finally{if(blobUrl)URL.revokeObjectURL(blobUrl)}
            if(xhr.status!==200||xhr.responseText.length!==part.size)throw Error('Could not read '+part.id+' ('+xhr.status+').');
            const bytes=new Uint8Array(part.size);
            for(let i=0;i<bytes.length;i++)bytes[i]=xhr.responseText.charCodeAt(i)&255;
            if(globalThis.sha256(bytes)!==part.sha256){
                if(fromLocal){local.delete(part.sha256);return readPage(part)}
                throw Error('Art verification failed for '+part.id+'.');
            }
            if(fromLocal){loaded.set(part.sha256,bytes);return bytes}
            return remember(part,bytes);
        }catch(error){queueMicrotask(()=>onError(error));throw error}
    }
    const later=[],onPlay=[];
    let firstFrame=false;
    for(const [name,file] of Object.entries(plan.files)){
        const spans=[];
        async function prime(boot){
            if(!boot)return;
            const bytes=await load(boot);
            let offset=0;
            for(const [start,length] of boot.ranges){
                spans.push({start,end:start+length,bytes:bytes.subarray(offset,offset+length)});
                offset+=length;
            }
            if(offset!==bytes.length)throw Error('Invalid startup art layout for '+name);
            spans.sort((a,b)=>a.start-b.start);
        }
        await prime(file.boot[mode]);
        // IndexedDB returns Blob handles. Read and verify their bytes only when
        // ClassicUO touches the page, even after a long previous play session.
        const prior=file.pages.filter(part=>cached.has(cacheKey(part)));
        const blobs=await storage.blobs(prior.map(cacheKey));
        prior.forEach((part,i)=>{if(blobs[i]?.size===part.size)local.set(part.sha256,blobs[i])});
        if(mode==='opening'&&file.boot.saved)later.push(()=>prime(file.boot.saved));
        // Once play begins, the already published archive is the cheapest way
        // to fill many missing pages. Expose each verified page immediately.
        // Closing the tab preserves completed pages for the next visit.
        let warming=false;
        async function warm(){
            if(warming||prior.length>file.pages.length/2)return;
            warming=true;
            const response=await fetch(new URL(file.original.version+'/'+file.original.id,base),{credentials:'omit',priority:'low'});
            if(!response.ok)throw Error('Archive prefetch returned '+response.status);
            const reader=response.body.pipeThrough(new DecompressionStream('gzip')).getReader();
            let i=0,at=0,bytes=new Uint8Array(file.pages[0].size);
            try{
                for(;;){
                    const {value,done}=await reader.read();
                    if(done)break;
                    for(let cursor=0;cursor<value.length;){
                        if(i>=file.pages.length)throw Error('Oversized '+name);
                        const n=Math.min(bytes.length-at,value.length-cursor);
                        bytes.set(value.subarray(cursor,cursor+n),at);at+=n;cursor+=n;
                        if(at===bytes.length){
                            const part=file.pages[i++];
                            if(!await valid(bytes,part))throw Error('Invalid prefetched '+part.id);
                            if(!local.has(part.sha256)&&!loaded.has(part.sha256)){
                                const blob=new Blob([bytes]);local.set(part.sha256,blob);
                                await storage.write(cacheKey(part),blob);
                            }
                            at=0;if(i<file.pages.length)bytes=new Uint8Array(file.pages[i].size);
                        }
                    }
                }
                if(i!==file.pages.length)throw Error('Incomplete '+name);
            }finally{await reader.cancel().catch(()=>{})}
        }
        const background=()=>warm().catch(error=>console.warn('On-demand reads remain available for '+name,error));
        if(name==='anim.mul'||name==='gumpartlegacymul.uop')onPlay.push(background);
        fs.writeFile('/uo/'+name,new Uint8Array(0));
        const node=fs.lookupPath('/uo/'+name).node;
        node.usedBytes=file.size;
        node.stream_ops={...node.stream_ops,read(stream,buffer,offset,length,position){
            const size=Math.max(0,Math.min(length,file.size-position));
            for(let copied=0;copied<size;){
                const at=position+copied,page=Math.floor(at/plan.pageBytes),part=file.pages[page];
                let bytes=loaded.get(part.sha256),start=page*plan.pageBytes;
                if(!bytes){
                    const span=spans.find(s=>s.start<=at&&at<s.end);
                    if(span){bytes=span.bytes;start=span.start}
                    else{
                        bytes=readPage(part);
                        if(firstFrame&&!warming)queueMicrotask(background);
                    }
                }
                const count=Math.min(size-copied,bytes.length-(at-start));
                buffer.set(bytes.subarray(at-start,at-start+count),offset+copied);
                copied+=count;
            }
            return size;
        }};
    }
    return ()=>{
        firstFrame=true;
        Promise.all(later.map(start=>start())).catch(error=>console.warn('Town art prefetch will retry on use',error));
        const play=()=>{for(const start of onPlay)start();window.removeEventListener('pointerdown',play,true);window.removeEventListener('keydown',play,true)};
        window.addEventListener('pointerdown',play,true);window.addEventListener('keydown',play,true);
    };
}
