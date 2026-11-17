// Same extraction as game/intro/prepare.py. Retail speech, captions and monitor
// pixels come only from the player's installation and never from the web host.
function member(bytes,index){
    const v=new DataView(bytes.buffer,bytes.byteOffset,bytes.byteLength);
    if(bytes.length<128||index>=v.getUint32(84,true)||128+(index+1)*8>bytes.length)throw Error('Invalid intro archive');
    const at=v.getUint32(128+index*8,true),size=v.getUint32(132+index*8,true);
    if(at<128||at+size>bytes.length)throw Error('Invalid intro archive member');
    return bytes.subarray(at,at+size);
}
const upper='ÇüéâäàåçêëèïîìÄÅÉæÆôöòûùÿÖÜ¢£¥₧ƒáíóúñÑªº¿⌐¬½¼¡«»░▒▓│┤╡╢╖╕╣║╗╝╜╛┐└┴┬├─┼╞╟╚╔╩╦╠═╬╧╨╤╥╙╘╒╓╫╪┘┌█▄▌▐▀αßΓπΣσµτΦΘΩδ∞φε∩≡±≥≤⌠⌡÷≈°∙·√ⁿ²■ ';
function cp437(bytes){return Array.from(bytes,b=>b<128?String.fromCharCode(b):upper[b-128]).join('')}
function monitor(bytes){
    const raw=member(bytes,19),v=new DataView(raw.buffer,raw.byteOffset,raw.byteLength);
    let at=v.getUint32(4,true)&0xffffff;
    if(at!==8)throw Error('Unsupported intro monitor');
    const right=v.getInt16(at,true),left=v.getInt16(at+2,true),above=v.getInt16(at+4,true),below=v.getInt16(at+6,true);
    if(right!==319||left!==0||above!==0||below!==199)throw Error('Invalid intro monitor dimensions');
    const pixels=new Uint8Array(64000),seen=new Uint8Array(64000);at+=8;
    for(;;){
        const tag=v.getUint16(at,true);at+=2;if(!tag)break;
        const x=v.getInt16(at,true),y=v.getInt16(at+2,true),count=tag>>>1;at+=4;
        if(!count||x<0||x+count>320||y<0||y>=200)throw Error('Invalid intro monitor scanline');
        let written=0;
        while(written<count){
            const code=tag&1?raw[at++]:count*2,n=code>>>1;
            if(!n||n>count-written)throw Error('Invalid intro monitor run');
            const value=code&1?raw[at++]:0;
            for(let i=0;i<n;i++){const dest=y*320+x+written++;pixels[dest]=code&1?value:raw[at++];seen[dest]=1}
        }
        if(at>raw.length)throw Error('Incomplete intro monitor');
    }
    if(seen.includes(0))throw Error('Incomplete intro monitor');
    return pixels;
}
function voice(bytes){
    if(new TextDecoder().decode(bytes.subarray(0,19))!=='Creative Voice File')throw Error('Invalid intro voice');
    const v=new DataView(bytes.buffer,bytes.byteOffset,bytes.byteLength),at=v.getUint16(20,true);
    const length=bytes[at+1]+bytes[at+2]*256+bytes[at+3]*65536;
    if(bytes[at]!==1||length<2||at+4+length>bytes.length||bytes[at+5]!==0)throw Error('Unsupported intro voice');
    const rate=Math.round(1000000/(256-bytes[at+4])),samples=bytes.subarray(at+6,at+4+length);
    if(rate<8000||rate>48000||!samples.length)throw Error('Invalid intro voice rate');
    const wav=new Uint8Array(44+samples.length*2),w=new DataView(wav.buffer),put=(at,s)=>wav.set(new TextEncoder().encode(s),at);
    put(0,'RIFF');w.setUint32(4,wav.length-8,true);put(8,'WAVEfmt ');w.setUint32(16,16,true);w.setUint16(20,1,true);w.setUint16(22,1,true);
    w.setUint32(24,rate,true);w.setUint32(28,rate*2,true);w.setUint16(32,2,true);w.setUint16(34,16,true);put(36,'data');w.setUint32(40,samples.length*2,true);
    samples.forEach((sample,i)=>w.setInt16(44+i*2,(sample-128)*256,true));
    return {wav,duration:samples.length/rate};
}
export async function prepareIntro(install,spec,write){
    const files=new Map(install),read=name=>{const bytes=files.get('STATIC/'+name);if(!bytes)throw Error('Select your Ultima VII folder again: missing STATIC/'+name+' for the opening.');return new Uint8Array(bytes)};
    for(const name of spec.localFiles)read(name);
    const pixels=monitor(read('ENDSHAPE.FLX'));let palette=member(read('INTROPAL.DAT'),2);
    if(palette.length===1536)palette=palette.filter((_,i)=>i%2===0);
    if(palette.length!==768||palette.some(c=>c>63))throw Error('Invalid intro palette');
    const canvas=new OffscreenCanvas(spec.blueWidth*spec.blueColumns,spec.blueHeight*Math.ceil(spec.blueFrames/spec.blueColumns)),ctx=canvas.getContext('2d');
    const frame=ctx.createImageData(320,200);
    for(let phase=0;phase<spec.blueFrames;phase++){
        for(let i=0;i<pixels.length;i++){
            const value=pixels[i],color=value>=16&&value<=93?16+((value-16-phase)%78+78)%78:value;
            for(let c=0;c<3;c++)frame.data[i*4+c]=Math.floor(palette[color*3+c]*255/63);frame.data[i*4+3]=255;
        }
        ctx.putImageData(frame,(phase%spec.blueColumns)*320,Math.floor(phase/spec.blueColumns)*200);
    }
    write('/intro/blue-static.png',new Uint8Array(await (await canvas.convertToBlob({type:'image/png'})).arrayBuffer()));
    const {wav,duration}=voice(read('INTROSND.DAT'));write('/intro/guardian.wav',wav);
    const mains=read('MAINSHP.FLX'),raw=member(mains,15),view=new DataView(raw.buffer,raw.byteOffset,raw.byteLength),cues=[];
    if(raw.length%3)throw Error('Invalid intro cues');
    for(let i=0;i<raw.length;i+=3){if(raw[i+2]>22)throw Error('Invalid intro pose');cues.push([view.getUint16(i,true),raw[i+2]])}
    const lines=cp437(member(mains,13)).trimEnd().split(/\r?\n/).map(s=>s.trim());
    if(lines.length!==14)throw Error('Invalid intro captions');
    write('/intro/intro.json',JSON.stringify({version:1,width:spec.width,height:spec.height,duration,cues,lines,textTimes:spec.textTimes}));
}
