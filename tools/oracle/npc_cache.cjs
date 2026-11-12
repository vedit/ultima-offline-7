"use strict";

// DOS voonpc.cpp keeps 32 NPC buffers in conventional memory and the remaining
// records in XMS. NpcSlotOf[356] is the inverse of NpcInSlot[32].
function locate(memory, saved) {
  const stride=105, count=356;
  if(saved.length!==count*129+4) throw Error("Unexpected DOS NPC save layout");
  const handles=Buffer.alloc(64);
  for(let i=0;i<32;i++) handles.writeUInt16LE(saved.readUInt16LE(i*stride+2),i*2);
  const refs=memory.indexOf(handles);
  if(refs<0 || memory.indexOf(handles,refs+1)>=0) throw Error("DOS NPC handle array missing or ambiguous");
  const map=refs-count, forward=map-2*32, used=forward-32, pointer=used-4;
  if(pointer<0) throw Error("Invalid DOS NPC directory address");
  const buffers=memory.readUInt16LE(pointer)+16*memory.readUInt16LE(pointer+2);
  if(buffers+32*stride>memory.length) throw Error("DOS NPC cache is outside conventional memory");
  let occupied=0, named=0;
  for(let slot=0;slot<32;slot++) {
    const flag=memory[used+slot];
    if(flag===0) continue;
    const actor=memory.readUInt16LE(forward+2*slot);
    if(flag!==1 || actor>=count || memory[map+actor]!==slot) throw Error("Inconsistent DOS NPC cache slot");
    occupied++;
    const at=buffers+slot*stride;
    if(actor<256 && saved[actor*stride+89]!==0) {
      if(memory.readUInt16LE(at+2)!==saved.readUInt16LE(actor*stride+2) ||
         !memory.subarray(at+89,at+105).equals(saved.subarray(actor*stride+89,actor*stride+105)))
        throw Error("DOS NPC buffer identity disagrees with the slot directory");
      named++;
    }
  }
  for(let actor=0;actor<count;actor++) {
    const slot=memory[map+actor];
    if(slot!==255 && (slot>=32 || memory[used+slot]!==1 || memory.readUInt16LE(forward+2*slot)!==actor))
      throw Error("Inconsistent DOS NPC reverse map");
  }
  if(named<3) throw Error("Insufficient original named actors to qualify the DOS cache");
  return {map,forward,buffers,refs,occupied,named};
}

function read(memory,saved) {
  const cache=locate(memory,saved);
  const members=[0,1,2].map(actor=>{
    const slot=memory[cache.map+actor], handle=saved.readUInt16LE(actor*105+2);
    if(slot===255) return {actor,handle,cached:false};
    const at=cache.buffers+slot*105;
    if(memory.readUInt16LE(at+2)!==handle) throw Error("Cached NPC identity differs from save");
    return {actor,handle,cached:true,slot,status:memory.readUInt16LE(at+4),
      xp:memory.readInt32LE(at+20),training:memory[at+24]};
  });
  return {cache,members};
}

module.exports={read};
