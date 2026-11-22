const cacheKey='classic-cliloc-index-v1';
const digest=async bytes=>Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',bytes)),b=>b.toString(16).padStart(2,'0')).join('');

function buildIndex(bytes){
    return new Promise((resolve,reject)=>{
        const worker=new Worker(new URL('./classic-locale-worker.js',import.meta.url),{type:'module'});
        worker.onmessage=({data})=>{worker.terminate();data instanceof ArrayBuffer?resolve(data):reject(Error(data.error))};
        worker.onerror=event=>{worker.terminate();reject(Error(event.message))};
        worker.postMessage(bytes,[bytes]);
    });
}

export async function prepareLocaleIndex(file,slot){
    if(!file||file.size<6||file.size>64*1024*1024)return null;
    try{
        const source=await file.arrayBuffer(),sourceHash=await digest(source);
        const cached=await slot(cacheKey).catch(()=>null);
        if(cached?.sourceHash===sourceHash&&cached.index instanceof Blob){
            const bytes=await cached.index.arrayBuffer();
            if(await digest(bytes)===cached.indexHash)return new Uint8Array(bytes);
        }
        const bytes=await buildIndex(source);
        const record={sourceHash,indexHash:await digest(bytes),index:new Blob([bytes])};
        await slot(cacheKey,record).catch(()=>{});
        return new Uint8Array(bytes);
    }catch(error){
        console.warn('Using the original ClassicUO localization reader',error);
        return null;
    }
}

export async function prepareArtIndexes(files,sparse,buildInfo){
    try{
        const response=await fetch('classic-art.idx.gz');
        if(!response.ok)throw Error('Missing index package');
        const packed=await response.arrayBuffer(),info=await buildInfo;
        if(await digest(packed)!==info?.artIndexSha256)throw Error('Index package differs from release');
        const stream=new Blob([packed]).stream().pipeThrough(new DecompressionStream('gzip'));
        const bytes=new Uint8Array(await new Response(stream).arrayBuffer());
        const view=new DataView(bytes.buffer),decode=new TextDecoder(),available=new Map(files),result=[];
        if(decode.decode(bytes.subarray(0,4))!=='ART1')throw Error('Invalid art index format');
        for(let at=4;at<bytes.length;){
            const length=bytes[at++],name=decode.decode(bytes.subarray(at,at+length));at+=length;
            const hash=Array.from(bytes.subarray(at,at+32),b=>b.toString(16).padStart(2,'0')).join('');at+=32;
            const size=view.getUint32(at,true);at+=4;
            if(!/^(artlegacymul\.uop|gumpartlegacymul\.uop|tileart\.uop|town-land|town-statics)$/.test(name)||at+size>bytes.length)
                throw Error('Invalid art index section');
            const file=available.get(name);
            // The sparse reader verifies its indexed ranges against this full
            // archive identity. A local or previously installed file must match too.
            if(name.startsWith('town-')||sparse?.files[name]?.sha256===hash||file&&await digest(await file.arrayBuffer())===hash)
                result.push([name,bytes.subarray(at,at+size)]);
            at+=size;
        }
        return result;
    }catch(error){
        console.warn('Using the original ClassicUO art indexes',error);
        return [];
    }
}
