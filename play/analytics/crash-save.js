export const CRASH_SAVE_MAX_BYTES = 2 * 1024 * 1024;
export const CRASH_SAVE_TTL = 7 * 86400;
export const CRASH_METADATA_MAX_BYTES = 8192;

export function validSave(bytes){
    if(!(bytes instanceof ArrayBuffer)||bytes.byteLength<128||bytes.byteLength>64*1024*1024)return false;
    const view=new DataView(bytes);if(view.getUint32(80,true)!==0xffff1a00)return false;
    const count=view.getUint32(84,true),end=128+count*8;if(count<1||end>bytes.byteLength)return false;
    const names=new Set(),decode=new TextDecoder();
    for(let i=128;i<end;i+=8){
        const offset=view.getUint32(i,true),length=view.getUint32(i+4,true);if(!length)continue;
        if(offset<end||length<13||offset+length>bytes.byteLength)return false;
        const name=decode.decode(new Uint8Array(bytes,offset,13)).split('\0')[0];
        if(!/^[A-Z0-9_]{1,8}(\.[A-Z0-9_]{1,3})?$/.test(name)||names.has(name))return false;
        names.add(name);
    }
    return names.has('U7IBUF.DAT')&&names.has('U7NBUF.DAT');
}
