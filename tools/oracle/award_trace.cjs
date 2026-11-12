"use strict";
const crypto=require("node:crypto");
const digest=bytes=>crypto.createHash("sha256").update(bytes).digest("hex");

// Insert a display-only loop just after 0911 has stored the original result
// of intrinsic 23 in local 1. Local 5 holds a delimiter. The original FOREACH
// initializes locals 2 and 3 again before awarding any XP.
const code=Buffer.from([
  0x44,124, 0x12,5,0, 0x2e,
  2,2,0,3,0,4,0,1,0,19,0,
  0x2f,3,0, 0x2f,5,0, 0x2f,2,0, 0x2f,5,0, 0x2f,4,0, 0x33,
  6,0xe2,0xff
]);
const sourceOffset=1498467, record=1498455, insertion=sourceOffset+7;
function instrument(files) {
  const get=name=>files.find(f=>f.path==="STATIC/"+name);
  const uc=get("USECODE"), first=get("LINKDEP1"), second=get("LINKDEP2");
  const before=[uc,first,second].map(f=>digest(f.contents));
  if(before.join(" ")!==[
    "49a3fcaf8a763972d0a6006571e8d8eef11eb1602f88898808b520523d0a8576",
    "7f8c60be31b537cd3d1455b2b5ca290edd654df4e9a5c6c9e1b87dd5ff57a570",
    "c5bbf242aa1dc5a94eb8c3056e174cf9489388a6ab279c9dfc968e454491fdcb"].join(" "))
    throw Error("Expected the original Forge routine and preload tables");
  const raw=Buffer.from(uc.contents), a=Buffer.from(first.contents), b=Buffer.from(second.contents);
  if(raw.readUInt16LE(record)!==0x911 || raw.subarray(sourceOffset,insertion).toString("hex")!=="38230000120100")
    throw Error("The observation must follow the actual party-list call and local store");
  const groups=[];
  for(let pos=0;pos+4<a.length;pos+=4) {
    const start=a.readUInt16LE(pos), end=a.readUInt16LE(pos+4);
    let extra=0;
    for(let i=start;i<end;i++) if(b.readUInt32LE(i*4)===record) extra+=code.length;
    if(extra) {
      a.writeUInt16LE(a.readUInt16LE(pos+2)+extra,pos+2);
      groups.push(pos/4);
    }
  }
  if(!groups.includes(0x911) || !groups.includes(0x40c)) throw Error("Missing award or mayor preload group");
  for(let i=0;i<b.length;i+=4) {
    const offset=b.readUInt32LE(i);
    if(offset>record) b.writeUInt32LE(offset+code.length,i);
  }
  raw.writeUInt16LE(raw.readUInt16LE(record+2)+code.length,record+2);
  uc.contents=Buffer.concat([raw.subarray(0,insertion),code,raw.subarray(insertion)]);
  first.contents=a;
  second.contents=b;
  return {function_id:0x911,source_offset:sourceOffset,insert_after_pc:7,inserted_hex:code.toString("hex"),
    display:"array length | next one-based iterator | returned object handle",preload_groups:groups,
    files:[uc,first,second].map((f,i)=>({path:f.path,original:before[i],instrumented:digest(f.contents)}))};
}
module.exports={instrument};
