import {NativeAudioRing} from './audio-ring.js?v=d8bce7ddfbb3a8c6';

class NativeAudioOutput extends AudioWorkletProcessor {
    constructor(options){
        super();
        this.ring=new NativeAudioRing(options.processorOptions.buffer);
    }
    process(inputs,outputs){
        const [left,right]=outputs[0];
        this.ring.render(left,right);
        return true;
    }
}
registerProcessor('trinsic-native-output',NativeAudioOutput);
