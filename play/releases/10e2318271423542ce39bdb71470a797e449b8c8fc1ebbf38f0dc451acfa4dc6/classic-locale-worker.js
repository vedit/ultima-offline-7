// Build a random-access table from the player's own Cliloc file. Only the
// resulting local cache contains text. Sorted integer keys preserve last-wins
// records and let ClassicUO materialize strings as gameplay requests them.
function decodeBwt(source){
    const ranks=new Uint8Array(source.length-4),symbols=Uint8Array.from({length:256},(_,i)=>i);
    for(let i=0;i<ranks.length-1;i++){
        const rank=source[i+4],value=symbols[rank];
        if(rank){symbols.copyWithin(1,0,rank);symbols[0]=value}
        ranks[i]=value;
    }
    if(ranks.length<1024)throw Error('Incomplete Cliloc frequency table');
    const view=new DataView(ranks.buffer),counts=Array.from({length:256},(_,i)=>view.getUint32(i*4,true));
    const size=counts.reduce((a,b)=>a+b,0);
    if(!size||size>ranks.length-1024)throw Error('Invalid Cliloc size');
    const frequency=counts.map((_,i)=>i).filter(i=>counts[i]).sort((a,b)=>counts[b]-counts[a]||a-b);
    const next=new Uint32Array(256),end=new Uint32Array(256);
    for(let i=0;i<256;i++)symbols[i]=i;
    let position=0;
    for(const value of frequency){
        symbols[ranks[1024+position]]=value;
        next[value]=position+1;position+=counts[value];end[value]=position;
    }
    const bytes=new Uint8Array(size);
    let value=symbols[0],active=frequency.length;
    for(let i=0;i<size;i++){
        bytes[i]=value;
        if(next[value]>=end[value]){
            if(active>0){active--;symbols.copyWithin(0,1,active+1);value=symbols[0]}
        }else{
            const rank=ranks[1024+next[value]++];
            if(rank){symbols.copyWithin(0,1,rank+1);symbols[rank]=value;value=symbols[0]}
        }
    }
    return bytes;
}

export function buildLocaleIndex(source){
    const bytes=source[3]===0x8e?decodeBwt(source):source;
    if(bytes.length<6)throw Error('Incomplete Cliloc header');
    const data=new DataView(bytes.buffer,bytes.byteOffset,bytes.byteLength),entries=new Map();
    for(let at=6;at<bytes.length;){
        if(at+7>bytes.length)throw Error('Incomplete Cliloc record');
        const id=data.getInt32(at,true),length=data.getInt16(at+5,true);
        if(length<0||at+7+length>bytes.length)throw Error('Invalid Cliloc record length');
        entries.set(id,at);at+=7+length;
    }
    const ids=[...entries.keys()].sort((a,b)=>a-b),start=8+ids.length*8;
    const result=new Uint8Array(start+bytes.length),header=new DataView(result.buffer);
    header.setUint32(0,0x31494c43,true);header.setUint32(4,ids.length,true);
    for(let i=0;i<ids.length;i++){
        header.setInt32(8+i*8,ids[i],true);
        header.setUint32(12+i*8,start+entries.get(ids[i]),true);
    }
    result.set(bytes,start);
    return result;
}

if(typeof WorkerGlobalScope!=='undefined'&&self instanceof WorkerGlobalScope){
    self.onmessage=({data})=>{
        try{
            const index=buildLocaleIndex(new Uint8Array(data));
            self.postMessage(index.buffer,[index.buffer]);
        }catch(error){self.postMessage({error:error.message})}
    };
}
