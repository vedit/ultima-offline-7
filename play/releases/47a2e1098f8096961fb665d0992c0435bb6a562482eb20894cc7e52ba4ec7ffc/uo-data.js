// Lossless, browser-local subset of the pinned Trinsic demo's UO dependencies.
// Only code and numeric dependency IDs are hosted. Retail bytes never leave here.
const marker='trinsic-demo.json';
const allowed=/^(artlegacymul\.uop|art(idx)?\.mul|gumpartlegacymul\.uop|gump(art|idx)\.mul|mainmisc\.uop|soundlegacymul\.uop|sound(idx)?\.mul|anim[2-5]?\.(mul|idx)|animdata\.mul|fonts\.mul|unifont\d*\.mul|hues\.mul|cliloc\.enu|light(idx)?\.mul|skills\.(mul|idx)|multi\.(mul|idx)|multicollection\.uop|multimap\.rle|texmaps\.mul|texidx\.mul|speech\.mul|tileart\.uop|string_dictionary\.uop|[^/]+\.def|mobtypes\.txt|prof\.txt|citytext\.enu|intloc\d+\.enu|trinsic-demo\.json)$/;
const encode=new TextEncoder(),decode=new TextDecoder();
let manifestPromise;
function manifest(){return manifestPromise??=fetch('uo-demo.json').then(r=>{if(!r.ok)throw Error('Could not load the demo data list.');return r.json()})}
export const dataSize=files=>files.reduce((sum,[,file])=>sum+file.size,0);
export const megabytes=bytes=>(bytes/1e6).toFixed(1)+' MB';

function validate(files){
    const names=new Set();
    for(const [name,file] of files){
        if(!allowed.test(name)||names.has(name)||!(file instanceof Blob))throw Error('Invalid UO data file: '+name);
        names.add(name);
    }
    for(const name of ['fonts.mul','hues.mul','anim.mul','anim.idx','texmaps.mul','texidx.mul'])if(!names.has(name))throw Error('Missing UO data: '+name);
    for(const [uop,mul,idx] of [['artlegacymul.uop','art.mul','artidx.mul'],['gumpartlegacymul.uop','gumpart.mul','gumpidx.mul'],['soundlegacymul.uop','sound.mul','soundidx.mul']]){
        if(!(names.has('mainmisc.uop')&&names.has(uop))&&!(names.has(mul)&&names.has(idx)))throw Error('Missing UO data: '+uop+' or '+mul+' / '+idx);
    }
}
export async function selectUO(files,progress,spec){
    const candidates=files.filter(f=>f.name.toLowerCase()==='hues.mul');
    if(candidates.length!==1)throw Error('Choose one UO Classic client folder containing hues.mul.');
    const parent=f=>f.webkitRelativePath.split('/').slice(0,-1).join('/');
    const root=parent(candidates[0]);
    return compactUO(files.filter(f=>parent(f)===root&&allowed.test(f.name.toLowerCase())).map(f=>[f.name.toLowerCase(),f]),progress,spec);
}

// The same lookup3 filename hash used by ClassicUO's UOP reader.
function uopHash(name){
    const bytes=encode.encode(name),rot=(v,n)=>(v<<n)|(v>>>(32-n));
    let a=(0xdeadbeef+bytes.length)>>>0,b=a,c=a,offset=0;
    const word=i=>(bytes[i]||0)|((bytes[i+1]||0)<<8)|((bytes[i+2]||0)<<16)|((bytes[i+3]||0)<<24);
    while(bytes.length-offset>12){
        a=(a+word(offset))>>>0;b=(b+word(offset+4))>>>0;c=(c+word(offset+8))>>>0;
        for(const n of [4,6,8,16,19,4]){a=(((a-c)>>>0)^rot(c,n))>>>0;c=(c+b)>>>0;[a,b,c]=[b,c,a]}
        offset+=12;
    }
    a=(a+word(offset))>>>0;b=(b+word(offset+4))>>>0;c=(c+word(offset+8))>>>0;
    for(const n of [14,11,25,16,4,14,24]){c=((c^b)-rot(b,n))>>>0;[a,b,c]=[b,c,a]}
    return (BigInt(a)<<32n)|BigInt(b);
}
async function subsetUOP(file,archive,ids,extension){
    const bytes=new Uint8Array(await file.arrayBuffer()),view=new DataView(bytes.buffer);
    const keys=new Set(ids.map(id=>uopHash(`build/${archive}/${String(id).padStart(8,'0')}.${extension}`)));
    const bound=(offset,size)=>{if(!Number.isSafeInteger(offset)||offset<0||size<0||offset+size>bytes.length)throw Error('Invalid '+archive+' archive bounds.')};
    bound(0,28);
    if(view.getUint32(0,true)!==0x50594d)throw Error('Invalid '+archive+' archive.');
    let block=Number(view.getBigUint64(12,true));
    const entries=[],seen=new Set();
    while(block){
        bound(block,12);if(seen.has(block))throw Error('Invalid UOP block chain.');seen.add(block);
        const count=view.getUint32(block,true);bound(block+12,count*34);
        for(let i=0;i<count;i++){
            const at=block+12+i*34,offset=Number(view.getBigUint64(at,true));
            if(!offset||!keys.has(view.getBigUint64(at+20,true)))continue;
            const size=view.getUint32(at+8,true)+view.getUint32(at+12,true);bound(offset,size);
            entries.push({header:bytes.slice(at,at+34),payload:file.slice(offset,offset+size)});
        }
        block=Number(view.getBigUint64(block+4,true));
    }
    if(!entries.length)throw Error('No matching demo records in '+archive+'.');
    const header=bytes.slice(0,28),h=new DataView(header.buffer),directory=new Uint8Array(12+entries.length*34),d=new DataView(directory.buffer);
    h.setBigUint64(12,28n,true);h.setUint32(20,entries.length,true);h.setUint32(24,entries.length,true);d.setUint32(0,entries.length,true);
    let offset=28+directory.length;
    for(let i=0;i<entries.length;i++){
        directory.set(entries[i].header,12+i*34);d.setBigUint64(12+i*34,BigInt(offset),true);offset+=entries[i].payload.size;
    }
    return new Blob([header,directory,...entries.map(e=>e.payload)]);
}
async function subsetMUL(file,index,ids){
    const bytes=new Uint8Array(await index.arrayBuffer()),src=new DataView(bytes.buffer);
    if(bytes.length%12)throw Error('Invalid UO index length.');
    const out=new Uint8Array(bytes.length).fill(255),dst=new DataView(out.buffer),parts=[],copied=new Map();
    let offset=0;
    for(const id of [...new Set(ids)].sort((a,b)=>a-b)){
        const at=id*12;if(at<0||at+12>bytes.length)continue;
        const start=src.getUint32(at,true),size=src.getInt32(at+4,true);
        if(start===0xffffffff||size<=0)continue;
        if(start+size>file.size)throw Error('Invalid UO record bounds.');
        const key=start+':'+size;
        if(!copied.has(key)){copied.set(key,offset);parts.push(file.slice(start,start+size));offset+=size}
        out.set(bytes.subarray(at,at+12),at);dst.setUint32(at,copied.get(key),true);
    }
    return [new Blob(parts.length?parts:[new Uint8Array(1)]),new Blob([out])];
}
async function animationRecords(files,initial){
    const bodies=new Set(initial),definitions=[];
    for(const name of ['body.def','corpse.def']){
        for(const line of (await files.get(name)?.text()||'').split('\n')){
            const match=line.match(/^\s*(\d+)\s*\{([^}]+)\}/);
            if(match)definitions.push([+match[1],match[2].match(/\d+/g)?.map(Number)||[]]);
        }
    }
    for(const line of (await files.get('equipconv.def')?.text()||'').split('\n')){
        const m=line.match(/^\s*(400|401)\s+(\d+)\s+(\d+)/);if(m)definitions.push([+m[2],[+m[3]]]);
    }
    let changed=true;
    while(changed){changed=false;for(const [from,to] of definitions)if(bodies.has(from))for(const id of to)if(!bodies.has(id)){bodies.add(id);changed=true}}
    const types=new Map();
    for(const line of (await files.get('mobtypes.txt')?.text()||'').split('\n')){
        const m=line.match(/^\s*(\d+)\s+(\w+)\s+([\da-fA-F]+)/);if(m)types.set(+m[1],[m[2].toLowerCase(),parseInt(m[3],16)]);
    }
    const records=new Map();
    function add(body,file=0,source=body){
        const name='anim'+(file?file+1:'');
        if(!files.has(name+'.mul')||!files.has(name+'.idx'))return;
        if(!records.has(name))records.set(name,[]);
        const fallback=file===1?(body<200?'monster':'animal'):file===2?(body<300?'animal':body<400?'monster':'human'):(body<200?'monster':body<400?'animal':'human');
        const [type,flags]=types.get(source)||[fallback,0];
        let group=type==='monster'?'high':type==='animal'?'low':'people';
        if(type==='monster'||type==='animal'&&(flags&0x20))group=(flags&0x400)?'people':(flags&0x40)?'low':'high';
        const count=type==='sea_monster'?65:group==='high'?110:group==='low'?65:175;
        const first=type==='sea_monster'||group==='high'?body*110:group==='low'?(body-200)*65+22000:(body-400)*175+35000;
        for(let i=0;i<count;i++)records.get(name).push(first+i);
    }
    for(const body of bodies)add(body);
    // Same body-conversion archives as desktop. Do not silently fall back to
    // older animation art merely because the compact pack omitted an archive.
    for(const line of (await files.get('bodyconv.def')?.text()||'').split('\n')){
        const values=line.split('#')[0].trim().split(/\s+/).map(Number);
        if(!bodies.has(values[0]))continue;
        for(let file=1;file<values.length&&file<=4;file++)if(values[file]>=0)add(values[file],file,values[0]);
    }
    return records;
}
export async function compactUO(input,progress=()=>{},spec){
    validate(input);spec??=await manifest();const files=new Map(input);
    if(files.has(marker)){
        const info=JSON.parse(await files.get(marker).text());
        if(info.version!==spec.version||info.dependencySha256!==spec.dependencySha256){const error=Error('Updating the cached game data…');error.code='UO_UPDATE_REQUIRED';throw error}
        return input;
    }
    const before=dataSize(input);
    for(const [archive,mul,idx,ids,ext] of [
        ['artlegacymul','art.mul','artidx.mul',spec.art,'tga'],
        ['soundlegacymul','sound.mul','soundidx.mul',spec.sounds,'dat']]){
        progress('Keeping demo '+(archive.startsWith('art')?'artwork':'sounds')+'…');
        if(files.has('mainmisc.uop')&&files.has(archive+'.uop')){
            files.set(archive+'.uop',await subsetUOP(files.get(archive+'.uop'),archive,ids,ext));files.delete(mul);files.delete(idx);
        }else{
            const pair=await subsetMUL(files.get(mul),files.get(idx),ids);files.set(mul,pair[0]);files.set(idx,pair[1]);files.delete(archive+'.uop');
        }
    }
    progress('Keeping demo animations…');
    const animation=await animationRecords(files,spec.animations);
    for(const name of ['anim2','anim3','anim4','anim5'])if(!animation.get(name)?.length){files.delete(name+'.mul');files.delete(name+'.idx')}
    for(const [mul,idx,ids] of [...['anim','anim2','anim3','anim4','anim5'].filter(name=>files.has(name+'.mul')).map(name=>[name+'.mul',name+'.idx',animation.get(name)||[]]),['texmaps.mul','texidx.mul',spec.textures]]){
        const pair=await subsetMUL(files.get(mul),files.get(idx),ids);files.set(mul,pair[0]);files.set(idx,pair[1]);
    }
    files.set(marker,new Blob([JSON.stringify({version:spec.version,artworkSha256:spec.artworkSha256,dependencySha256:spec.dependencySha256,originalBytes:before})]));
    return [...files];
}

const magic=encode.encode('TRINSICUO1\n'),maxBytes=800*1024*1024;
export async function exportUO(files){
    validate(files);
    const header=encode.encode(JSON.stringify(files.map(([name,file])=>[name,file.size]))),length=new Uint8Array(4);
    new DataView(length.buffer).setUint32(0,header.length,true);
    const blob=new Blob([magic,length,header,...files.map(([,file])=>file)]);
    return new Response(blob.stream().pipeThrough(new CompressionStream('gzip'))).blob();
}
export async function importUO(file){
    if(file.size>maxBytes)throw Error('This demo pack is too large.');
    // Bound decompression before buffering to reject corrupt/oversized input.
    const reader=file.stream().pipeThrough(new DecompressionStream('gzip')).getReader(),parts=[];
    let size=0;
    try{for(;;){const {done,value}=await reader.read();if(done)break;size+=value.length;if(size>maxBytes)throw Error('This demo pack expands beyond the size limit.');parts.push(value)}}
    finally{await reader.cancel().catch(()=>{})}
    const blob=new Blob(parts),prefix=new Uint8Array(await blob.slice(0,magic.length+4).arrayBuffer());
    if(prefix.length!==magic.length+4||magic.some((byte,i)=>prefix[i]!==byte))throw Error('Choose a Trinsic UO demo pack.');
    const length=new DataView(prefix.buffer).getUint32(magic.length,true);
    if(length>65536||length<2||prefix.length+length>blob.size)throw Error('Invalid demo pack directory.');
    const entries=JSON.parse(await blob.slice(prefix.length,prefix.length+length).text());
    if(!Array.isArray(entries)||entries.length>200)throw Error('Invalid demo pack files.');
    let at=prefix.length+length;
    const files=entries.map(entry=>{
        if(!Array.isArray(entry)||entry.length!==2)throw Error('Invalid demo pack entry.');
        const [name,size]=entry;
        if(typeof name!=='string'||!Number.isSafeInteger(size)||size<0||at+size>blob.size)throw Error('Invalid demo pack entry.');
        const value=[name,blob.slice(at,at+size)];at+=size;return value;
    });
    if(at!==blob.size||!files.some(([name])=>name===marker))throw Error('Invalid demo pack contents.');
    return compactUO(files);
}
