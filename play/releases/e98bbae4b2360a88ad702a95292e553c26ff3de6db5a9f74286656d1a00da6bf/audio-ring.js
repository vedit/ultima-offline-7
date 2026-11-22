// Single producer and single consumer. Positions count stereo frames at 48 kHz.
const WRITE=0, READ=1, EPOCH=2, PRODUCER=3, START=4, READER=5;
const MISSED=6, HEADER_WORDS=7, CAPACITY=8192, MASK=CAPACITY-1, BLOCK=800;
// Match the desktop device's two-block startup and 60 ms queue target.
const PREFILL=2*BLOCK, AHEAD=2880;
export class NativeAudioRing {
    static allocate(){return new SharedArrayBuffer(HEADER_WORDS*4+CAPACITY*2*2)}
    constructor(buffer){
        this.state=new Int32Array(buffer,0,HEADER_WORDS);
        this.samples=new Int16Array(buffer,HEADER_WORDS*4);
        this.primed=false;
        this.started=false;
    }
    get missedFrames(){return Atomics.load(this.state,MISSED)>>>0}
    get queuedFrames(){return (Atomics.load(this.state,WRITE)-Atomics.load(this.state,READ))>>>0}
    enable(enabled){
        const epoch=Atomics.load(this.state,EPOCH);
        if(Boolean(epoch&1)!==enabled)Atomics.add(this.state,EPOCH,1);
    }
    blocksDue(elapsed){
        const s=this.state, epoch=Atomics.load(s,EPOCH);
        if(Atomics.load(s,PRODUCER)!==epoch){
            Atomics.store(s,START,Atomics.load(s,WRITE));
            Atomics.store(s,PRODUCER,epoch);
        }
        if(!(epoch&1)||Atomics.load(s,READER)!==epoch)return elapsed;
        const queued=(Atomics.load(s,WRITE)-Atomics.load(s,READ))>>>0;
        return Math.max(0,Math.ceil((AHEAD-queued)/BLOCK));
    }
    write(pcm){
        const s=this.state, epoch=Atomics.load(s,EPOCH);
        if(!(epoch&1)||Atomics.load(s,READER)!==epoch||Atomics.load(s,PRODUCER)!==epoch)return;
        const written=Atomics.load(s,WRITE), frames=pcm.length/2;
        if(((written-Atomics.load(s,READ))>>>0)+frames>CAPACITY)return;
        const offset=(written&MASK)*2, first=Math.min(pcm.length,this.samples.length-offset);
        this.samples.set(pcm.subarray(0,first),offset);
        if(first<pcm.length)this.samples.set(pcm.subarray(first));
        Atomics.store(s,WRITE,written+frames);
    }
    render(left,right){
        const s=this.state, epoch=Atomics.load(s,EPOCH);
        if(Atomics.load(s,PRODUCER)!==epoch||!(epoch&1)){this.primed=false;return 0}
        if(Atomics.load(s,READER)!==epoch){
            this.started=this.primed=false;
            Atomics.store(s,READ,Atomics.load(s,START));
            Atomics.store(s,READER,epoch);
        }
        const read=Atomics.load(s,READ), queued=(Atomics.load(s,WRITE)-read)>>>0;
        if(!this.primed && queued<PREFILL){
            if(this.started)Atomics.add(s,MISSED,left.length);
            return 0;
        }
        const count=Math.min(queued,left.length);
        for(let i=0;i<count;i++){
            const offset=((read+i)&MASK)*2;
            left[i]=this.samples[offset]/32768;
            right[i]=this.samples[offset+1]/32768;
        }
        Atomics.store(s,READ,read+count);
        this.primed=count===left.length;
        this.started=true;
        if(!this.primed)Atomics.add(s,MISSED,left.length-count);
        return count;
    }
}
