"use strict";
const fs = require("node:fs");
const path = require("node:path");
const crypto = require("node:crypto");
const root = path.resolve(__dirname, "..");
const install = path.resolve(root,"../../Assets/UltimaVII-Steam");
const pkg = path.resolve(root,"../../Tools/js-dos-8.5.3/package");
const wait = ms => new Promise(resolve => setTimeout(resolve,ms));
const sha = bytes => crypto.createHash("sha256").update(bytes).digest("hex");
const zlib = require("node:zlib");
function rgbaPng(w, h, data, channels) {
  if (w*h*channels !== data.length) throw Error("Frame dimensions differ from the video buffer");
  const rows = Buffer.alloc(h*(1+w*4));
  for (let y=0;y<h;y++) for(let x=0;x<w;x++) {
    const dst=y*(1+w*4)+1+x*4, src=(y*w+x)*channels;
    rows[dst]=data[src]; rows[dst+1]=data[src+1]; rows[dst+2]=data[src+2]; rows[dst+3]=255;
  }
  function chunk(type, payload) {
    const s=Buffer.from(type), b=Buffer.alloc(payload.length+12);
    b.writeUInt32BE(payload.length); s.copy(b,4); payload.copy(b,8);
    b.writeUInt32BE(zlib.crc32(Buffer.concat([s,payload])),8+payload.length); return b;
  }
  const head=Buffer.alloc(13);head.writeUInt32BE(w);head.writeUInt32BE(h,4);head[8]=8;head[9]=6;
  return Buffer.concat([Buffer.from("89504e470d0a1a0a","hex"),chunk("IHDR",head),chunk("IDAT",zlib.deflateSync(rows)),chunk("IEND",Buffer.alloc(0))]);
}
async function run(scenario) {
    if (!["inside","edge","outside"].includes(scenario)) throw Error("unknown case");
    const folder = fs.mkdtempSync(path.join(root,"evidence","dos-"+scenario+"-"));
    const seed = fs.readFileSync(path.join(root,"fixtures","Iolo-"+scenario+".U7"));
    const expected = JSON.parse(fs.readFileSync(path.join(root,"../../Evidence/dos-reference/session-5j7GWY/receipt.json"),"utf8"));
    const files = [];
    for (const [name,meta] of Object.entries(expected.inputs)) {
        const data = fs.readFileSync(path.join(install,name));
        if (sha(data)!==meta.sha256) throw Error(name);
        files.push({path:name,contents:data});
    }
    for (let i=0;i<seed.readUInt32LE(84);i++) {
        const at=seed.readUInt32LE(128+8*i), size=seed.readUInt32LE(132+8*i);
        if (!size) continue;
        const name=seed.subarray(at,at+13).toString("latin1").split("\0")[0];
        if (!/^[A-Z0-9_]{1,8}(\.[A-Z0-9_]{1,3})?$/.test(name)) throw Error(name);
        files.push({path:"GAMEDAT/"+name, contents:seed.subarray(at+13,at+size)});
    }
    files.push({path:"GAME02.U7",contents:seed});
    const conf = fs.readFileSync(path.join(install,"dosboxULTIMA7.conf"),"utf8").split(/^\[autoexec\]/im)[0]+"\r\n[autoexec]\r\n@echo off\r\nmount c .\r\nc:\r\nultima7.com\r\n";
    const savedItems=Buffer.from(files.find(f=>f.path==="GAMEDAT/U7IBUF.DAT").contents);
    for(const file of files) file.contents = new Uint8Array(file.contents);
    files.unshift({dosboxConf:conf,jsdosConf:{version:"8"}});
    require(pkg);
    const engine=global.emulators;
    engine.pathPrefix=path.join(pkg,"dist")+path.sep;
    const ci=await engine.dosboxNode(files);
    ci.events().onStdout(s=>fs.appendFileSync(path.join(folder,"dos.log"),s+"\n"));
    let frame;
    const samples=[]; let nextProbe=0;
    let memoryBase=-1,clockBase=-1;
    let observation=false;
    const backend=ci.transport.module;
    if(!backend.HEAPU16) Object.defineProperty(backend,"HEAPU16",{get:()=>new Uint16Array(backend.HEAPU8.buffer)});
    function sampleFrame(){
        if(!observation || (memoryBase<0 && Date.now()<nextProbe)) return; nextProbe=Date.now()+120;
        backend._dumpMemory(true);
        const memory=Buffer.from(backend.memoryContents.memoryCopy.buffer,backend.memoryContents.memoryCopy.byteOffset,backend.memoryContents.memoryCopy.byteLength);
        if(memoryBase<0){
            // Require two distant intact parts of the saved item array and the exact live
            // Avatar shape, region and location. Shape and extension handles survive animation.
            for(let offset=8192;offset<22000;offset+=256){
                const sig=savedItems.subarray(offset,offset+48);
                if(new Set(sig).size<12) continue;
                for(let n=memory.indexOf(sig);n>=0;n=memory.indexOf(sig,n+1)){
                    const base=n-offset;
                    if(base<0 || base+savedItems.length>memory.length) continue;
                    if(memory.readUInt16LE(base+58)!==savedItems.readUInt16LE(58) || (memory.readUInt16LE(base+60)&1023)!==721 || memory.readUInt16LE(base+62)!==64) continue;
                    if(!memory.subarray(base+3100,base+3136).equals(savedItems.subarray(3100,3136))) continue;
                    if(memoryBase>=0 && memoryBase!==base) throw Error("ambiguous item buffer");
                    memoryBase=base;
                }
                if(memoryBase>=0) break;
            }
        }
        if(memoryBase<0) return;
        if(clockBase<0){
            const tag=Buffer.from("GAMETIMM.DAT\0","latin1");
            const matches=[];
            for(let n=memory.indexOf(tag);n>=0;n=memory.indexOf(tag,n+1)){
                const at=n+14;
                if(at+8<=memory.length && memory.readUInt16LE(at)>=15864 && memory.readUInt16LE(at)<15964 && memory.readUInt16LE(at+2)===1 && memory.readUInt16LE(at+4)===1) matches.push(at);
            }
            if(matches.length===1)clockBase=matches[0];
        }
        const tick=clockBase>=0?memory.readUInt16LE(clockBase):null;
        const at=memoryBase+184, ext=memory.readUInt16LE(at+6);
        if(ext!==192 || (memory.readUInt16LE(at+4)&1023)!==465) throw Error("Iolo identity changed");
        const r=memory[memoryBase+ext+2];
        const xyz=[(r%12)*256+memory[at+2],Math.floor(r/12)*256+memory[at+3],memory[memoryBase+ext+5]>>4];
        if(!samples.length || String(samples.at(-1).xyz)!==String(xyz)) samples.push({ms:Date.now()-start,xyz,tick});
    }
    ci.events().onFrame((rgb,rgba)=>{
        const pixels=rgb||rgba;
        if(pixels) frame={w:ci.width(),h:ci.height(),pixels:Buffer.from(pixels),channels:rgb?3:4}; sampleFrame();
    });
    function shot(name){if(frame) fs.writeFileSync(path.join(folder,name+".png"),rgbaPng(frame.w,frame.h,frame.pixels,frame.channels));}
    const trace=[];
    const start=Date.now();
    async function key(keys) {
        trace.push([Date.now()-start,"key",keys]);
        for(const k of keys) ci.sendKeyEvent(k,true);
        await wait(150);
        for(const k of [...keys].reverse()) ci.sendKeyEvent(k,false);
    }
    async function click(x,y) {
        trace.push([Date.now()-start,"click",x,y]);
        ci.sendMouseMotion(x/320,y/200); ci.sendMouseSync();
        ci.sendMouseButton(0,true); await wait(190); ci.sendMouseButton(0,false);
    }
    try {
        await wait(18000); shot("intro"); await key([256]); await wait(14000); shot("menu"); await click(160,164); await wait(700); observation=true;
        for(let n=0;n<120 && (!samples.length || String(samples.at(-1).xyz)!=="986,2202,0");n++) await wait(250); observation=false; fs.writeFileSync(path.join(folder,"trace.json"),JSON.stringify({memoryBase,clockBase,samples},null,2)); shot("world"); await key([342,83]); await wait(750); shot("dialog");
        await click(77,54); await wait(500); await click(94,157); await wait(500); await click(149,108);
        await wait(2200); shot("after");
        const save=Buffer.from(await ci.fsReadFile("GAME02.U7"));
        if (sha(save)===sha(seed)) throw Error("Original save dialog did not write the checkpoint");
        fs.writeFileSync(path.join(folder,"checkpoint.U7"),save);
        fs.writeFileSync(path.join(folder,"receipt.json"),JSON.stringify({scenario,source:sha(seed),save:sha(save),trace,samples,memoryBase, config:sha(conf),wasm:sha(fs.readFileSync(path.join(pkg,"dist","wdosbox.wasm")))},null,2));
        console.log(folder);
    } finally {await ci.exit();}
}
run(process.argv[2]).catch(err=>{console.error(err);process.exitCode=1;});
