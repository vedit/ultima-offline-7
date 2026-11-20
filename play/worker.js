"use strict";
const buildVersion=new URL(self.location.href).searchParams.get('v')||'dev';
importScripts('trinsic.js?v='+buildVersion);

async function download(url) {
    const res = await fetch(url);
    if (!res.ok) throw new Error("Could not load " + url);
    return res;
}

function unpackSave(fs, bytes) {
    const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
    if (view.getUint32(80, true) !== 0xffff1a00) throw new Error("Invalid Black Gate save");
    const count = view.getUint32(84, true);
    const end = 128 + count * 8;
    if (end > bytes.length) throw new Error("Incomplete save directory");
    const names = new Set();
    for (let i = 128; i < end; i += 8) {
        const off = view.getUint32(i, true), size = view.getUint32(i+4, true);
        if (!size) continue;
        if (off < end || size < 13 || off+size > bytes.length) throw new Error("Invalid save member");
        const name = new TextDecoder().decode(bytes.subarray(off,off+13)).split("\0")[0];
        if (!/^[A-Z0-9_]{1,8}(\.[A-Z0-9_]{1,3})?$/.test(name) || names.has(name))
            throw new Error("Invalid save member name");
        names.add(name);
        fs.writeFile("GAMEDAT/" + name, bytes.subarray(off+13, off+size));
    }
    if (!names.has("U7IBUF.DAT") || !names.has("U7NBUF.DAT")) throw new Error("Missing actors in save");
}

onmessage = async ({data}) => {
    try {
        const {NativeAudioRing}=await import('./audio-ring.js?v='+buildVersion);
        const [module, seed] = await Promise.all([
            createBlackGate({mailbox: new Int32Array(data.mailbox), nativeAudio:new NativeAudioRing(data.audioRing),
                developerWand:data.experience.developerWand===true, noInitialRun:true,
                locateFile: name=>new URL(name+'?v='+buildVersion,self.location.href).href,
                onAbort: message => postMessage({error:String(message)})}),
            data.save || download("investigation.u7").then(r => r.arrayBuffer())
        ]);
        const fs = module.FS;
        fs.mkdir("STATIC");
        fs.mkdir("GAMEDAT");
        for (const [name, bytes] of data.install) fs.writeFile(name, new Uint8Array(bytes));
        unpackSave(fs, new Uint8Array(seed));
        if (!data.save) {
            // Same native INITGAME/character-creation entry as desktop --from-opening.
            const args=new Uint8Array(16);
            args[0]=data.experience.newGame.female?1:0;
            args.set(new TextEncoder().encode(data.experience.newGame.name).subarray(0,14),1);
            fs.writeFile('gameargs.dat',args);
        }
        for(const [slot,bytes] of data.saves||[])if(bytes&&slot>=0&&slot<10)fs.writeFile('GAME'+String(slot).padStart(2,'0')+'.U7',new Uint8Array(bytes));
        const slot=data.activeSlot>=0&&data.activeSlot<10?data.activeSlot:0;
        fs.writeFile('active-slot.txt',String(slot));
        module.callMain([]);
        throw new Error("The Black Gate engine exited.");
    } catch (e) {
        console.error('Black Gate startup failed', e.stack || e);
        postMessage({error:e.message || String(e),stack:e.stack});
    }
};
