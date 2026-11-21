// Versioned, resumable downloads from the endpoint configured by the deployment.
const digest=async blob=>[...new Uint8Array(await crypto.subtle.digest('SHA-256',await blob.arrayBuffer()))].map(x=>x.toString(16).padStart(2,'0')).join('');
export async function downloadUO(storage,progress,existing=[]){
    const base=new URL(document.querySelector('meta[name="uo-api-base"]')?.content||'./api/uo/',document.baseURI);
    const pinned=document.querySelector('meta[name="uo-plan"]')?.content;
    const response=pinned
        ? await fetch(new URL(pinned,document.baseURI),{credentials:'omit'})
        : await fetch(new URL('current-manifest',base),{cache:'no-store',credentials:'omit'});
    if(!response.ok)throw Error('Automatic UO download is unavailable. Please retry.');
    const plan=await response.json();
    if(!/^[a-f0-9]{20}$/.test(plan.version)||!Array.isArray(plan.files)||!plan.parts)throw Error('Invalid UO download plan.');
    const ids=Object.keys(plan.parts),loaded=new Map();
    const versionFor=id=>plan.parts[id].version??plan.version;
    const keyFor=id=>'uo-auto:'+versionFor(id)+':'+id;
    const keys=ids.map(keyFor);
    const total=ids.reduce((sum,id)=>sum+plan.parts[id].size,0);let complete=0,inFlight=new Map();
    let reported=0;
    const report=()=>{const now=performance.now();if(now-reported<100&&complete!==total)return;reported=now;progress(Math.min(total,complete+[...inFlight.values()].reduce((a,b)=>a+b,0)),total)};
    const cancel=new AbortController();
    async function part(id){
        if(loaded.has(id))return loaded.get(id);
        const spec=plan.parts[id];
        if(!spec||!/^[a-f0-9]{20}$/.test(versionFor(id))||!/^[a-z0-9._-]+$/.test(id)||!Number.isSafeInteger(spec.size)||spec.size<0||spec.size>100_000_000)throw Error('Invalid UO download part: '+id);
        const key=keyFor(id);
        let blob=await storage.read(key);
        if(blob instanceof Blob&&blob.size===spec.size&&await digest(blob)===spec.sha256){loaded.set(id,blob);complete+=blob.size;report();return blob}
        for(let attempt=0;attempt<3;attempt++){
            try{
                const result=await fetch(new URL(versionFor(id)+'/'+id,base),{signal:cancel.signal,credentials:'omit'});
                if(!result.ok||!result.body)throw Error('UO download returned '+result.status);
                const reader=result.body.pipeThrough(new DecompressionStream('gzip')).getReader(),chunks=[];let size=0;
                try{for(;;){const value=await reader.read();if(value.done)break;size+=value.value.length;if(size>spec.size)throw Error('UO download size mismatch.');chunks.push(value.value);inFlight.set(id,size);report()}}
                finally{await reader.cancel().catch(()=>{})}
                blob=new Blob(chunks);
                if(blob.size!==spec.size||await digest(blob)!==spec.sha256)throw Error('UO data verification failed.');
                await storage.write(key,blob);loaded.set(id,blob);complete+=blob.size;inFlight.delete(id);report();return blob;
            }catch(error){
                inFlight.delete(id);report();
                if(cancel.signal.aborted||attempt===2)throw error;
                await new Promise(resolve=>setTimeout(resolve,1000*(attempt+1)));
            }
        }
    }
    try{
        const cached=new Map(existing),verified=new Map(),needed=new Set(),large=[],small=[];
        for(const file of plan.files){
            const previous=cached.get(file.name);
            if(previous?.size===file.size&&await digest(previous)===file.sha256){
                verified.set(file.name,previous);
                complete+=file.parts.reduce((sum,id)=>sum+plan.parts[id].size,0);report();continue;
            }
            for(const id of file.parts)needed.add(id);
        }
        for(const id of needed){
            (plan.parts[id].size>8*1024*1024?large:small).push(id);
        }
        // Keep one large archive in flight while the other lanes verify smaller
        // parts. Reassemble in manifest order regardless of completion order.
        let nextSmall=0;
        async function smallParts(){
            while(nextSmall<small.length)await part(small[nextSmall++]);
        }
        async function archives(){
            for(const id of large)await part(id);
            await smallParts();
        }
        await Promise.all([archives(), ...Array.from({length:Math.min(3,small.length)},smallParts)]);
        const files=[];
        for(const file of plan.files){
            let blob=verified.get(file.name);
            if(!blob){
                blob=new Blob(file.parts.map(id=>loaded.get(id)));
                if(blob.size!==file.size||await digest(blob)!==file.sha256)throw Error('UO file verification failed: '+file.name);
            }
            files.push([file.name,blob]);
        }
        return {files,keys};
    }catch(error){cancel.abort();throw Error(error.message+' Download progress is saved; press Play now to retry.')}
}
