import {validSave} from './analytics/crash-save.js?v=712fee8ef5a9ee43';
export {validSave};

// A browser can remember a granted directory, but cannot open an arbitrary OS path.
export function steamPath(platform){
    if(/win/i.test(platform))return 'C:\\Program Files (x86)\\Steam\\steamapps\\common';
    if(/mac/i.test(platform))return '~/Library/Application Support/Steam/steamapps/common';
    return '';
}
async function child(root,path){try{for(const name of path)root=await root.getDirectoryHandle(name);return root}catch{return null}}
export async function gameRoot(handle){
    if(/^static$/i.test(handle.name)||await child(handle,['STATIC'])||await child(handle,['static']))return handle;
    for(const path of [['steamapps','common'],['common']]){const common=await child(handle,path);if(common)return gameRoot(common)}
    const candidates=[];
    for await(const entry of handle.values())if(entry.kind==='directory'&&/ultima.*(7|vii)|black.?gate|forge.?of.?virtue/i.test(entry.name))candidates.push(entry);
    if(candidates.length===1)return candidates[0];
    if(/^common$/i.test(handle.name))throw Error('Choose the Ultima VII folder inside steamapps/common.');
    return handle;
}
export async function folderFiles(root,{music=false}={}){
    const result=[];let visited=0;
    async function walk(folder,path,depth){
        if(depth>12||++visited>5000)throw Error('Choose the game or Exult folder more directly.');
        for await(const entry of folder.values()){
            if(entry.name.startsWith('.'))continue;
            const name=path+'/'+entry.name;
            if(entry.kind==='directory')await walk(entry,name,depth+1);
            else if(!music||/^\d{2}bg\.ogg$/i.test(entry.name)){
                const file=await entry.getFile();Object.defineProperty(file,'webkitRelativePath',{value:name});result.push(file);
                if(result.length>20000)throw Error('Choose the Ultima VII game folder rather than the whole library.');
            }
        }
    }
    await walk(root,root.name,0);return result;
}
export class SaveFolder{
    constructor(onChange=()=>{}){this.onChange=onChange;this.handle=null;this.available=false;this.message='In this browser'}
    async set(handle){this.handle=handle;this.available=!!handle&&await handle.queryPermission({mode:'readwrite'})==='granted';this.update()}
    update(message){this.message=message||(this.handle?(this.available?this.handle.name+' + browser backup':this.handle.name+' · reconnect to write'):'In this browser');this.onChange(this.message)}
    async reconnect(){if(!this.handle||this.available)return;this.available=await this.handle.requestPermission({mode:'readwrite'})==='granted';this.update()}
    async read(){
        if(!this.available)return null;
        try{const file=await(await this.handle.getFileHandle('ultima-offline-trinsic.u7')).getFile();const bytes=await file.arrayBuffer();if(!validSave(bytes))throw Error('The folder save is not a valid Trinsic save.');this.modified=file.lastModified;return bytes}
        catch(error){if(error.name==='NotFoundError')return null;throw error}
    }
    async write(bytes){
        if(!this.available)return false;
        let writer;
        try{const file=await this.handle.getFileHandle('ultima-offline-trinsic.u7',{create:true});writer=await file.createWritable();await writer.write(bytes);await writer.close();return true}
        catch(error){await writer?.abort().catch(()=>{});this.available=false;this.update('Saved in browser · folder unavailable');console.warn('Save folder unavailable:',error.name);return false}
    }
}
