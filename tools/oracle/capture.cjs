// Drive the installed DOS game through js-dos's public video and input interfaces.
// Run: node tools/oracle/capture.cjs E:\UltimaOffline
// Replay: node tools/oracle/capture.cjs E:\UltimaOffline <previous-receipt.json> [--reconsider]
// Continue: node tools/oracle/capture.cjs E:\UltimaOffline --checkpoint <native-save-export>
// Append --teleport-setup to enable the game's F2 menu in a checkpoint run.
// Append --morning-appointment to start the restored save at 05:55 with the stock DOS configuration.
// The receipt records the DOS batch bytes and both configuration hashes.
// Send JSON lines on stdin. An empty line captures a frame.
"use strict";
const fs = require("node:fs");
const path = require("node:path");
const crypto = require("node:crypto");
const readline = require("node:readline");
const zlib = require("node:zlib");

const root = fs.realpathSync(process.argv[2]);
const install = path.join(root, "Assets", "UltimaVII-Steam");
const pkg = path.join(root, "Tools", "js-dos-8.5.3", "package");
const dist = path.join(pkg, "dist");
const parent = path.join(root, "Evidence", "dos-reference");
fs.mkdirSync(parent, { recursive: true });
const output = fs.mkdtempSync(path.join(parent, "session-"));
const sha = data => crypto.createHash("sha256").update(data).digest("hex");
const delay = ms => new Promise(resolve => setTimeout(resolve, ms));
function nativeMembers(raw) {
  if(raw.length<128 || raw.readUInt32LE(80)!==0xffff1a00) throw Error("Invalid native save header");
  const count=raw.readUInt32LE(84), end=128+count*8;
  if(end>raw.length) throw Error("Incomplete native save directory");
  const members=[], names=new Set(), intervals=[];
  for(let index=0;index<count;index++) {
    const off=raw.readUInt32LE(128+index*8), size=raw.readUInt32LE(132+index*8);
    if(!size) continue;
    if(size<13 || off<end || off+size>raw.length) throw Error("Incomplete native save member");
    const name=raw.subarray(off,off+13).toString("latin1").split("\0")[0].replace(/\.$/,"").toUpperCase();
    if(!/^[A-Z0-9_-]{1,8}(\.[A-Z0-9_-]{1,3})?$/.test(name)||names.has(name)) throw Error("Invalid native save filename");
    names.add(name); intervals.push([off,off+size]);
    members.push({path:"GAMEDAT/"+name,contents:raw.subarray(off+13,off+size)});
  }
  intervals.sort((a,b)=>a[0]-b[0]);
  if(intervals.some((a,i)=>i&&a[0]<intervals[i-1][1])) throw Error("Overlapping native save members");
  if(!["U7IBUF.DAT","U7NBUF.DAT","FLAGINIT","IDENTITY","ITEMNODE.DAT"].every(n=>names.has(n))) throw Error("Incomplete native campaign");
  return members;
}
const receipt = { schema: 1, backend: "js-dos dosboxNode", backend_version: require(path.join(pkg, "package.json")).version,
  started: new Date().toISOString(), fresh_filesystem: true, inputs: {}, actions: [], frames: [] };
function save() {
  const temp = path.join(output, "receipt.tmp");
  fs.writeFileSync(temp, JSON.stringify(receipt, null, 2) + "\n", {flush:true});
  // A Windows reader may briefly hold the previous receipt open during a live capture.
  for(let attempt=0;;attempt++) {
    try { fs.renameSync(temp, path.join(output, "receipt.json")); return; }
    catch(err) {
      if(attempt>=12 || !["EPERM","EBUSY","EACCES"].includes(err.code)) throw err;
      Atomics.wait(new Int32Array(new SharedArrayBuffer(4)),0,0,25*(attempt+1));
    }
  }
}
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
function guestMemory(ci) {
  const backend=ci.transport?.module;
  if(typeof backend?._dumpMemory!=="function") throw Error("Guest debugger unavailable");
  if(!backend.HEAPU16) Object.defineProperty(backend,"HEAPU16",{
    get:()=>new Uint16Array(backend.HEAPU8.buffer)
  });
  backend._dumpMemory(true);
  const copy=backend.memoryContents.memoryCopy;
  if(!(copy instanceof Uint8Array)||!copy.length) throw Error("Missing guest debugger snapshot");
  return Buffer.from(copy.buffer,copy.byteOffset,copy.byteLength);
}
async function main() {
  require(pkg);
  const engine=global.emulators;
  engine.pathPrefix=dist+path.sep;
  const files=[];
  const names=["ULTIMA7.COM","U7.EXE","INTRO.EXE","MAINMENU.EXE","ENDGAME.EXE","U7.CFG"];
  for(const entry of fs.readdirSync(path.join(install,"STATIC"),{withFileTypes:true})) {
    if (entry.isFile()) names.push("STATIC/"+entry.name);
  }
  for(const name of names.sort()) {
    const source=path.join(install,...name.split("/"));
    if (fs.realpathSync(source).toLowerCase()!==source.toLowerCase()) throw Error("Unexpected redirected source");
    const contents=fs.readFileSync(source);
    files.push({path:name,contents:new Uint8Array(contents)});
    receipt.inputs[name]={bytes:contents.length,sha256:sha(contents)};
  }
  if(process.argv[3]==="--numeric-probe") {
    const spec=JSON.parse(fs.readFileSync(process.argv[4],"utf8"));
    const file=files.find(f=>f.path==="STATIC/USECODE");
    if(sha(file.contents)!=="49a3fcaf8a763972d0a6006571e8d8eef11eb1602f88898808b520523d0a8576" ||
        spec.source_sha256!==sha(file.contents) || spec.base!==170138 || !/^[0-9a-f]{3716}$/.test(spec.code_hex) ||
        spec.extern_offset!==170124 || spec.extern_target!==0x932 ||
        !/^[0-9a-f]{12}$/.test(spec.prefix) || !/^[0-9a-f]{12}$/.test(spec.suffix) ||
        !Number.isInteger(spec.count) || spec.count<1 || spec.count>64) throw Error("Unexpected Forge diagnostic");
    file.contents.set(Buffer.from(spec.code_hex,"hex"),spec.base);
    new DataView(file.contents.buffer,file.contents.byteOffset,file.contents.byteLength)
      .setUint16(spec.extern_offset,spec.extern_target,true);
    // DOS preloads each root's callees from LINKDEP2. In 0401's private
    // block replace its now unused last dependency with the smaller 0932.
    const dep=files.find(f=>f.path==="STATIC/LINKDEP2");
    if(sha(dep.contents)!=="c5bbf242aa1dc5a94eb8c3056e174cf9489388a6ab279c9dfc968e454491fdcb" ||
       receipt.inputs["STATIC/LINKDEP1"].sha256!=="7f8c60be31b537cd3d1455b2b5ca290edd654df4e9a5c6c9e1b87dd5ff57a570")
      throw Error("Unexpected DOS routine preload table");
    new DataView(dep.contents.buffer,dep.contents.byteOffset,dep.contents.byteLength)
      .setUint32(1121*4,1506991,true);
    receipt.inputs[dep.path].sha256=sha(dep.contents);
    receipt.numeric_fixture=spec;
    receipt.inputs[file.path].sha256=sha(file.contents);
  }
  // Preserve the Steam CPU/memory and sound settings. Only the virtual filesystem is mounted.
  const steam=fs.readFileSync(path.join(install,"dosboxULTIMA7.conf"),"utf8");
  const baseConf=steam.split(/^\[autoexec\]/im)[0]+"\r\n[autoexec]\r\n@echo off\r\nmount c .\r\nc:\r\nultima7.com\r\n";
  let conf=baseConf;
  const awardTrace=process.argv[3]==="--checkpoint" && process.argv[5]==="--award-trace";
  const appointment=process.argv[3]==="--checkpoint" && process.argv[5]==="--morning-appointment";
  const occupiedChair=process.argv[3]==="--checkpoint" && process.argv[5]==="--occupied-chair";
  const directRestore=awardTrace || occupiedChair || (process.argv[3]==="--checkpoint" && process.argv[5]==="--direct-teleport");
  if(process.argv[3]==="--checkpoint" && (process.argv[5]==="--teleport-setup" || directRestore)) {
    const batch=Buffer.from("@echo off\r\nultima7.com ABCD\xff\r\n","latin1");
    files.push({path:"U7PROBE.BAT",contents:batch});
    conf=baseConf.replace(/ultima7\.com\r\n$/,"U7PROBE.BAT\r\n");
    receipt.scene_setup={method:"Original F2 debug menu",batch_hex:batch.toString("hex"),base_config_sha256:sha(Buffer.from(baseConf))};
  }
  fs.writeFileSync(path.join(output,"dosbox.conf"),conf,{flush:true});
  receipt.config_sha256=sha(Buffer.from(conf));
  receipt.wasm_sha256=sha(fs.readFileSync(path.join(dist,"wdosbox.wasm")));
  if(process.argv[3]==="--checkpoint") {
    const source=fs.realpathSync(process.argv[4]), rel=path.relative(parent,source);
    if(rel.startsWith("..") || path.isAbsolute(rel)) throw Error("Expected private native checkpoint");
    const priorPath=path.join(path.dirname(source),"receipt.json");
    const prior=JSON.parse(fs.readFileSync(priorPath,"utf8")), basename=path.basename(source);
    if(JSON.stringify(prior.inputs)!==JSON.stringify(receipt.inputs) ||
       ![sha(Buffer.from(baseConf)),receipt.config_sha256].includes(prior.config_sha256) || prior.wasm_sha256!==receipt.wasm_sha256) throw Error("Checkpoint inputs differ");
    const trusted=prior.checkpoints?.find(c=>c.file===basename);
    const raw=fs.readFileSync(source);
    if(!trusted || trusted.sha256!==sha(raw) || trusted.bytes!==raw.length || !Number.isInteger(trusted.slot)
       || trusted.slot<0 || trusted.slot>9) throw Error("Unverified original checkpoint");
    const members=nativeMembers(raw);
    // A DOS save is a delta against the game's own initialized GAMEDAT.
    // Let the original new-game and Load Gumps create and apply that state.
    files.push({path:"GAME0"+trusted.slot+".U7",contents:raw});
    receipt.fresh_filesystem=false;
    receipt.native_continuation={source,original_receipt:priorPath,sha256:trusted.sha256,
      bytes:raw.length,slot:trusted.slot,validated_members:members.length,restore:"Original Load Gump"};
    if(directRestore || appointment) {
      // A paired diagnostic changes only the Avatar's two packed cell coordinates in the
      // disposable save. Retain region, chunk membership, lift, route owner and all script data.
      let avatarPlacement;
      if(occupiedChair) {
        const member=name=>Buffer.from(members.find(m=>m.path==="GAMEDAT/"+name).contents);
        const npcs=member("U7NBUF.DAT"),items=member("U7IBUF.DAT"),owners=member("PATH.DAT");
        const mayor=npcs.readUInt16LE(12*105+2),avatar=npcs.readUInt16LE(2);
        const slot=Array.from({length:15},(_,i)=>i).find(i=>owners[i]===1 && owners.readUInt16LE(15+2*i)===mayor);
        if(slot===undefined || npcs[12*105+46]!==16 || npcs[12*105+53]!==35 || npcs[12*105+54]!==5)
          throw Error("Expected Finnigan on an active native chair route");
        const route=member("PATH"+slot+".DAT"),x=route.readUInt16LE(27),y=route.readUInt16LE(29);
        const ext=items.readUInt16LE(avatar+6),region=items[ext+2];
        const before=[(region%12)*256+items[avatar+2],Math.floor(region/12)*256+items[avatar+3]];
        if((before[0]>>4)!==(x>>4) || (before[1]>>4)!==(y>>4) ||
            (items[ext+5]>>4)!==route.readInt8(31) || route.readUInt16LE(21)!==mayor)
          throw Error("Occupied-chair control must stay within the same native chunk and lift");
        avatarPlacement={member:"GAMEDAT/U7IBUF.DAT",actor:avatar,offset:avatar+2,before,after:[x,y],
                         original_sha256:sha(items)};
      }
      // The native save packs GAMEDAT. The original Journey Onward menu
      // restores this directory directly (GameFiles::restoreGame(-1)).
      for(const m of members) {
        const contents = Buffer.from(m.contents);
          if(avatarPlacement && m.path===avatarPlacement.member) {
            contents.writeUInt16LE((avatarPlacement.after[0]&255)+(avatarPlacement.after[1]&255)*256,avatarPlacement.offset);
            receipt.occupied_chair={...avatarPlacement,modified_sha256:sha(contents)};
          }
        if(appointment && m.path === "GAMEDAT/GAMETIMM.DAT") {
          if(contents.length !== 6 || contents.readUInt16LE(4) !== 1) throw Error("Unexpected saved world clock");
          receipt.appointment_clock = {member:m.path, before:contents.toString("hex"), ticks:8875};
          contents.writeUInt16LE(receipt.appointment_clock.ticks, 0); // 05:55, original day and rate.
          receipt.appointment_clock.after = contents.toString("hex");
        }
        files.push({path:m.path,contents:new Uint8Array(contents)});
      }
      if(appointment && !receipt.appointment_clock) throw Error("The native checkpoint lacks the world clock");
      receipt.native_continuation.restore="Journey Onward from the verified native save directory";
    }
    if(awardTrace) {
      receipt.award_trace=require("./award_trace.cjs").instrument(files);
      for(const f of receipt.award_trace.files) {
        const contents=files.find(entry=>entry.path===f.path).contents;
        receipt.inputs[f.path]={bytes:contents.length,sha256:f.instrumented};
      }
    }
  }
  files.unshift({dosboxConf:conf,jsdosConf:{version:"8"}});
  save();
  console.log(output);
  const ci=await engine.dosboxNode(files);
  // A native PARTY save serializes the two arrays separately. The DOS game
  // keeps their eight and sixteen word buffers adjacent in guest memory.
  let partyAddress;
  function observeParty(sampleAward=false, cacheSnapshot) {
    if (!receipt.native_continuation) throw Error("A verified native continuation is required");
    const saved=nativeMembers(fs.readFileSync(receipt.native_continuation.source))
      .find(m=>m.path==="GAMEDAT/PARTY")?.contents;
    if (!saved || saved.length!==191) throw Error("Missing DOS party tables");
    const memory=guestMemory(ci);
    if(cacheSnapshot!==undefined) {
      if(!sampleAward || !/^[a-z0-9-]{1,45}$/.test(cacheSnapshot)) throw Error("Invalid DOS cache observation label");
      fs.writeFileSync(path.join(output,cacheSnapshot+".bin"),memory,{flag:"wx",flush:true});
    }
    // partymov.c declares DirectionDX, DirectionDY, DirectionBySign and
    // DirectionSignRow immediately before the 61 bytes of party state.
    const prefix=Buffer.concat([Buffer.from([0,1,1,1,0,255,255,255,255,255,0,1,1,1,0,255]),
      Buffer.from([7,6,5,0,255,4,1,2,3,0,0,1,2,2,2,1,0])]);
    const anchor=Buffer.from("PARTY\0","latin1");
    const exe=files.find(f=>f.path==="U7.EXE").contents;
    const disk=Buffer.from(exe.buffer,exe.byteOffset,exe.byteLength);
    const fileOffset=disk.indexOf(prefix)+prefix.length;
    if (fileOffset<prefix.length || !disk.subarray(fileOffset,fileOffset+61).equals(Buffer.alloc(61)) ||
        !disk.subarray(fileOffset+61,fileOffset+67).equals(anchor)) throw Error("Unqualified executable party layout");
    const candidates=[];
    for(let i=memory.indexOf(prefix);i>=0;i=memory.indexOf(prefix,i+1)) {
      const at=i+prefix.length;
      if (memory.subarray(at+61,at+67).equals(anchor) && memory.readUInt16LE(at)===saved.readUInt16LE(0) &&
          memory[at+48]>=1 && memory[at+48]<=8 && memory[at+49]<=16) candidates.push(at);
    }
    if (candidates.length!==1 || (partyAddress!==undefined && candidates[0]!==partyAddress))
      throw Error("Live DOS party table is missing, moved or ambiguous");
    partyAddress=candidates[0];
    const words=(at,n)=>Array.from({length:n},(_,i)=>memory.readUInt16LE(partyAddress+at+2*i));
    const active=words(0,memory[partyAddress+48]), downed=words(16,memory[partyAddress+49]);
    if(new Set([...active,...downed]).size!==active.length+downed.length) throw Error("Overlapping DOS party members");
    const sample={frame:receipt.frames.at(-1)?.file,elapsed_ms:Date.now()-t,guest_bytes:memory.length,
      executable_table_offset:fileOffset,guest_table_offset:partyAddress,active,downed};
    if(sampleAward) {
      const records=nativeMembers(fs.readFileSync(receipt.native_continuation.source))
        .find(m=>m.path==="GAMEDAT/U7NBUF.DAT").contents;
      if(cacheSnapshot) sample.cache_snapshot={file:cacheSnapshot+".bin",sha256:sha(memory)};
      try {sample.npc_progress=require("./npc_cache.cjs").read(memory,records);}
      catch(error) {sample.npc_diagnostic=String(error);}
    }
    (receipt.party_observations??=[]).push(sample);
    console.log(JSON.stringify(sample)); save();
  }
  let frame=null;
  ci.events().onFrame((rgb,rgba)=>{
    const pixels=rgb??rgba;
    if (pixels) frame={data:Buffer.from(pixels),width:ci.width(),height:ci.height(),channels:rgb?3:4};
  });
  ci.events().onStdout(message=>fs.appendFileSync(path.join(output,"dos-stdout.txt"),message+"\n"));
  let count=0;
  const t=Date.now();
  async function snap(label="frame") {
    if (!/^[A-Za-z0-9-]{1,55}$/.test(label)) throw Error("Invalid frame label");
    if (!frame) throw Error("Waiting for a video frame");
    const {width,height,data,channels}=frame;
    const png=rgbaPng(width,height,data,channels);
    const file=String(++count).padStart(3,"0")+"-"+label+".png";
    fs.writeFileSync(path.join(output,file),png,{flush:true});
    const record={file,width,height,sha256:sha(png),elapsed_ms:Date.now()-t};
    receipt.frames.push(record); save(); console.log(JSON.stringify(record));
  }
  async function action(a) {
    const hold=a.hold??100;
    if (!Number.isSafeInteger(hold)||hold<10||hold>8000) throw Error("Invalid duration");
    if (a.type==="pause") {ci.pause();}
    else if(a.type==="resume") {ci.resume();}
    else if (a.type==="key") {
      const keys=Array.isArray(a.keys)?a.keys:[a.key];
      if (!keys.length||keys.length>3||keys.some(k=>!Number.isInteger(k)||k<1||k>348)) throw Error("Invalid keys");
      keys.forEach(k=>ci.sendKeyEvent(k,true));await delay(hold);
      [...keys].reverse().forEach(k=>ci.sendKeyEvent(k,false));
    } else if (a.type==="move"||a.type==="click") {
      if (![a.x,a.y].every(v=>Number.isFinite(v)&&v>=0&&v<=1)) throw Error("Invalid position");
      ci.sendMouseMotion(a.x,a.y);ci.sendMouseSync();
      if(a.type==="click") {
        const b=a.button??0, n=a.count??1;
        if (![0,1,2].includes(b)||![1,2].includes(n)) throw Error("Invalid mouse event");
        for(let i=0;i<n;i++){ci.sendMouseButton(b,true);await delay(hold);ci.sendMouseButton(b,false);if(i+1<n) await delay(80);}
      }
    } else if(a.type==="drag") {
      if (![a.x,a.y,a.toX,a.toY].every(v=>Number.isFinite(v)&&v>=0&&v<=1)) throw Error("Invalid drag");
      ci.sendMouseMotion(a.x,a.y);ci.sendMouseSync();await delay(90);
      ci.sendMouseButton(0,true);await delay(110);
      for(let i=1;i<=8;i++) {
        ci.sendMouseMotion(a.x+(a.toX-a.x)*i/8,a.y+(a.toY-a.y)*i/8);ci.sendMouseSync();await delay(30);
      }
      ci.sendMouseButton(0,false);
    } else if(a.type==="wait") {
      if (!Number.isSafeInteger(a.ms)||a.ms<0||a.ms>15000) throw Error("Invalid wait");
      await delay(a.ms);
    } else if(a.type==="snapshot") {await snap(a.label);return}
    else if(a.type==="party") {observeParty(a.award===true,a.cache_snapshot);}
    else if(a.type==="state") {
      const tree=await ci.fsTree();
      fs.writeFileSync(path.join(output,"guest-files.json"),JSON.stringify(tree,null,2));
      console.log("Guest file inventory saved");
      const slot=a.slot??0;
      if(!Number.isInteger(slot)||slot<0||slot>9) throw Error("Invalid original save slot");
      const saveName="GAME0"+slot+".U7";
      const saved = tree.nodes.find(n => n.name.toUpperCase() === saveName && n.nodes === null);
      if (saved) {
        const bytes = Buffer.from(await ci.fsReadFile(saved.name));
        nativeMembers(bytes); // The DOS archive can still be incomplete while the save Gump is writing.
        if(a.label && !/^[A-Za-z0-9-]{1,55}$/.test(a.label)) throw Error("Invalid checkpoint label");
        const file=a.label?a.label+"-"+saveName:saveName;
        fs.writeFileSync(path.join(output,file),bytes,{flush:true});
        const checkpoint={file,slot,bytes:bytes.length,sha256:sha(bytes)};
        if(a.label) (receipt.checkpoints??=[]).push(checkpoint);
        else if(slot===0) receipt.original_save=checkpoint;
      }
    }
    else if(a.type==="stop") {receipt.finished=new Date().toISOString();save();await ci.exit();process.exit(0)}
    else throw Error("Unknown action");
    save();
  }
  async function recorded(a) {
    if(a.type!=="snapshot") receipt.actions.push({elapsed_ms:Date.now()-t,...a});
    await action(a);
  }
  console.log("Command interface ready");
  if(receipt.numeric_fixture) {
    const wait=ms=>recorded({type:"wait",ms});
    // Observe stable glyphs from the installed game's menus. Fades and
    // emulator load can consume keystrokes sent on a fixed wall-clock delay.
    function glyphs(x0,y0,x1,y1) {
      if(!frame || frame.width!==320 || frame.height!==200) return "";
      const mask=[];
      for(let y=y0;y<y1;y++) for(let x=x0;x<x1;x++) {
        const i=(320*y+x)*frame.channels;
        mask.push(Number(Math.max(...frame.data.subarray(i,i+3))>4));
      }
      return sha(Buffer.from(mask));
    }
    const characterForm=()=>glyphs(38,119,75,130)==="27110190174a5bcfe94ace33947efcdc166e7a86b0c1f8f4755a9cc1aca529a7";
    const mainMenu=()=>glyphs(111,146,208,155)==="6ad06b3ea490deba3501fd9c65952680e3844ae508215e9047e6b5db5850464a";
    async function waitForMenu(check,label) {
      for(let i=0;i<50;i++) {
        if(check()) return;
        await wait(400);
      }
      await snap(label+"-timeout");
      await ci.exit();
      throw Error("DOS did not display "+label);
    }
    await wait(12000);
    await recorded({type:"key",key:256});
    await waitForMenu(mainMenu,"new-game-menu");
    await wait(1600);
    await recorded({type:"click",x:0.49375,y:0.75,hold:260});
    await waitForMenu(characterForm,"character-form");
    await wait(1800);
    for(const key of [72,69,88,69,78,257]) {
      await recorded({type:"key",key,hold:180});
      await wait(120);
    }
    await recorded({type:"click",x:0.275,y:0.92,hold:260});
    const spec=receipt.numeric_fixture;
    const prefix=Buffer.from(spec.prefix,"hex"), suffix=Buffer.from(spec.suffix,"hex");
    for(let attempt=0;attempt<18;attempt++) {
      await wait(2000);
      if(characterForm() && attempt>0 && attempt%3===0)
        await recorded({type:"click",x:0.275,y:0.92,hold:260});
      const memory=guestMemory(ci);
      const address=memory.indexOf(prefix);
      const end=address+prefix.length+Math.ceil(spec.count/8);
      if(address>=0 && memory.indexOf(prefix,address+1)<0 && memory.subarray(end,end+suffix.length).equals(suffix)) {
        fs.writeFileSync(path.join(output,"numeric-memory.bin"),memory,{flag:"wx",flush:true});
        receipt.numeric_result={address,memory_sha256:sha(memory)};
        await snap("numeric-probe-finished");
        await recorded({type:"stop"});
        return;
      }
    }
    await snap("numeric-probe-timeout");
    await ci.exit();
    throw Error("No completed numeric diagnostic in DOS memory");
  }
  if(process.argv[3] && process.argv[3]!=="--checkpoint") {
    const source=fs.realpathSync(process.argv[3]);
    if(path.relative(parent,source).startsWith("..") || path.basename(source)!=="receipt.json") {
      throw Error("Replay source must be an earlier private DOS receipt");
    }
    const previous=JSON.parse(fs.readFileSync(source,"utf8"));
    if(JSON.stringify(previous.inputs)!==JSON.stringify(receipt.inputs)||previous.config_sha256!==receipt.config_sha256||
      previous.wasm_sha256!==receipt.wasm_sha256) throw Error("Replay inputs differ");
    receipt.replay_of=source;
    const sequence=[...previous.actions.filter(a=>a.type!=="stop"),...previous.frames.map(f=>({
      type:"snapshot",label:f.file.replace(/^\d+-/,"").replace(/\.png$/,""),elapsed_ms:f.elapsed_ms
    }))].sort((a,b)=>a.elapsed_ms-b.elapsed_ms);
    for(const {elapsed_ms,...a} of sequence) {
      if(!Number.isSafeInteger(elapsed_ms)||elapsed_ms<0||elapsed_ms>3600000) throw Error("Invalid replay time");
      await delay(Math.max(0,elapsed_ms-(Date.now()-t)));
      await recorded(a);
      if(process.argv[4]==="--reconsider" && a.type==="snapshot" && a.label==="decline-murder-investigation") {
        await recorded({type:"click",x:0.78,y:0.78});
        await recorded({type:"wait",ms:120});
        await recorded({type:"snapshot",label:"immediate-post-refusal"});
        await recorded({type:"click",x:128/320,y:86/200,count:2,hold:45});
        await recorded({type:"wait",ms:500});
        await recorded({type:"snapshot",label:"original-reentry"});
        break;
      }
      if(receipt.original_save) break;
    }
    console.log("Replay actions complete");
  }
  const consoleInput=readline.createInterface({input:process.stdin,terminal:false});
  for await(const line of consoleInput) {
    try {
      const value=line.trim()?JSON.parse(line):{type:"snapshot"};
      for(const a of Array.isArray(value)?value:[value]) {
        await recorded(a);
      }
    } catch (err) {
      if(!process.stdin.isTTY) { await ci.exit(); throw err; }
      console.error(String(err));
    }
  }
  await ci.exit();
}
main().catch(err=>{ console.error(err);process.exitCode=1; });
