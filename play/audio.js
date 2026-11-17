// Browser implementation of the pinned client's SDL audio contract.
export function installAudio(runtime){
    let context,next=1;const sounds=new Map();
    const unlock=()=>{context??=new AudioContext();context.resume().catch(console.warn);return context};
    addEventListener('pointerdown',unlock,{capture:true});addEventListener('keydown',unlock,{capture:true});
    function start(sound){
        const source=context.createBufferSource();source.buffer=sound.buffer;source.loop=sound.loop;source.connect(sound.gain);
        sound.source=source;sound.started=context.currentTime;sound.state=1;
        source.onended=()=>{if(sound.source===source&&sound.state===1){sound.state=0;source.disconnect();sounds.delete(sound.id)}};
        source.start(0,sound.offset);
    }
    globalThis.__wasm_play_pcm=(ptr,length,volume,rate,channels,loop)=>{
        const ctx=unlock(),bytes=runtime().HEAPU8.slice(ptr,ptr+length),view=new DataView(bytes.buffer);
        const frames=Math.floor(length/2/channels);if(!frames)return 0;
        const buffer=ctx.createBuffer(channels,frames,rate);
        for(let c=0;c<channels;c++){const out=buffer.getChannelData(c);for(let i=0;i<frames;i++)out[i]=view.getInt16((i*channels+c)*2,true)/32768}
        const gain=ctx.createGain();gain.gain.value=Math.max(0,Math.min(1,volume));gain.connect(ctx.destination);
        const sound={id:next++,buffer,gain,loop:!!loop,offset:0,state:0};sounds.set(sound.id,sound);start(sound);return sound.id;
    };
    globalThis.__wasm_stop_sound=id=>{const s=sounds.get(id);if(!s)return;s.state=0;s.source.stop();s.source.disconnect();s.gain.disconnect();sounds.delete(id)};
    globalThis.__wasm_set_sound_volume=(id,volume)=>{const s=sounds.get(id);if(s)s.gain.gain.value=Math.max(0,Math.min(1,volume))};
    globalThis.__trinsic_audio_control=(id,op)=>{
        const s=sounds.get(id);if(!s)return 0;
        if(op===1&&s.state===1){s.offset+=context.currentTime-s.started;s.state=2;s.source.stop();s.source.disconnect()}
        if(op===2&&s.state===2)start(s);
        return s.state;
    };
    return {unlock};
}
