export async function selectMusic(files){
    const tracks=new Map();
    for(const file of files){
        const match=/^(\d{2})bg\.ogg$/i.exec(file.name);if(!match)continue;
        const number=Number(match[1]);if(number>=60)continue;
        if(file.size>20*1024*1024||new TextDecoder().decode(await file.slice(0,4).arrayBuffer())!=='OggS')throw Error('Invalid Exult music file: '+file.name);
        if(tracks.has(number))throw Error('Multiple music folders found. Choose Exult’s data/music folder.');
        tracks.set(number,file);
    }
    if(!tracks.size)throw Error('Choose Exult or its data/music folder containing tracks such as 35bg.ogg.');
    return [...tracks];
}
export class ExultMusic{
    constructor(){this.tracks=new Map();this.buffers=new Map();this.current=null;this.key='';this.token=0;this.volume=.6}
    set(tracks){this.stop();this.tracks=new Map(tracks||[]);this.buffers.clear();this.key=''}
    unlock(){
        if(!this.tracks.size)return;
        if(!this.context){this.context=new AudioContext();this.gain=this.context.createGain();this.gain.gain.value=this.volume;this.gain.connect(this.context.destination)}
        this.context.resume().catch(()=>{});
    }
    setVolume(value){this.volume=Math.max(0,Math.min(1,value));if(this.gain)this.gain.gain.value=this.volume}
    stop(){this.token++;if(this.current){this.current.stop();this.current.disconnect();this.current=null}}
    async apply(cue){
        if(!cue||!this.tracks.size)return;
        this.lastCue=cue;
        const key=cue.cue+'/'+cue.track+'/'+cue.playing;if(key===this.key)return;
        this.key=key;this.stop();
        if(!cue.playing||!this.tracks.has(cue.track))return;
        this.unlock();const token=this.token;
        try{
            let buffer=this.buffers.get(cue.track);
            if(!buffer){buffer=await this.context.decodeAudioData(await this.tracks.get(cue.track).arrayBuffer());if(this.buffers.size>=2)this.buffers.delete(this.buffers.keys().next().value);this.buffers.set(cue.track,buffer)}
            if(token!==this.token)return;
            const source=this.context.createBufferSource();source.buffer=buffer;source.loop=true;source.connect(this.gain);source.start();this.current=source;
        }catch(error){console.warn('Exult music could not play:',error.message)}
    }
}
