// Identify the campaign from its own INITGAME archive, independently of the
// storefront directory name. A Complete Edition may contain both campaigns.
const required = ("AMMO.DAT ARMOR.DAT ENDSHAPE.FLX EQUIP.DAT FACES.VGA FONTS.VGA GUMPS.VGA " +
    "INITGAME.DAT LINKDEP1 LINKDEP2 MONSTERS.DAT OCCLUDE.DAT PALETTES.FLX POINTERS.SHP " +
    "READY.DAT SCHEDULE.DAT SHAPES.VGA SHPDIMS.DAT SPRITES.VGA TEXT.FLX TFA.DAT " +
    "U7CHUNKS U7MAP USECODE WEAPONS.DAT WGTVOL.DAT WIHH.DAT XFORM.TBL").split(" ");
const optional = ("ADLIB.ADV ADLIBMUS.DAT ADLIBSFX.DAT ENDGAME.DAT ENDSCORE.XMI INTROADM.DAT " +
    "INTROPAL.DAT INTRORDM.DAT INTROSND.DAT MAINSHP.FLX MT32MPU.ADV MT32MUS.DAT MT32SFX.DAT " +
    "NPCFLAG.DAT SBDIG.ADV U7INTRO.TIM U7SPEECH.SPC U7STRAX.DRV U7VOICE.FLX XMIDI.AD XMIDI.MT").split(" ");
const regions = Array.from({length:144}, (_,i) => "U7IFIX" + i.toString(16).padStart(2,"0").toUpperCase());

function campaign(buffer) {
    const view = new DataView(buffer);
    if (buffer.byteLength < 128 || view.getUint32(80,true) !== 0xffff1a00) return "";
    const end = 128 + 8 * view.getUint32(84,true);
    if (end > buffer.byteLength) return "";
    const decoder = new TextDecoder();
    for (let i=128; i<end; i+=8) {
        const offset = view.getUint32(i,true), length = view.getUint32(i+4,true);
        if (!length) continue;
        if (length < 13 || offset < end || offset + length > buffer.byteLength) return "";
        const name = decoder.decode(new Uint8Array(buffer,offset,13)).split("\0")[0];
        if (name.toUpperCase().replace(/\.$/,"") === "IDENTITY")
            return decoder.decode(new Uint8Array(buffer,offset+13,length-13)).split(/[\x00\r\n\x1a]/)[0];
    }
    return "";
}

export async function importInstall(files) {
    const groups = new Map();
    const configs = new Map();
    for (const file of files) {
        const parts = file.webkitRelativePath.split("/");
        const name = parts.pop().toUpperCase();
        const parent = parts.join("/");
        if (name === "U7.CFG") configs.set(parent,file);
        if (parts.pop()?.toUpperCase() !== "STATIC") continue;
        const root = parts.join("/");
        if (!groups.has(root)) groups.set(root,new Map());
        groups.get(root).set(name,file);
    }
    const matches = [];
    for (const [root, group] of groups) {
        const seed = group.get("INITGAME.DAT");
        if (seed && campaign(await seed.arrayBuffer()) === "FORGE") matches.push([root,group]);
    }
    if (!matches.length) throw Error("Choose the Black Gate + Forge of Virtue installation folder, or its STATIC folder.");
    if (matches.length > 1) throw Error("Multiple Black Gate installations found. Choose the one you want to play.");
    const [root, group] = matches[0];
    const missing = required.concat(regions).find(name => !group.get(name)?.size);
    if (missing) throw Error("Incomplete Black Gate installation. Missing STATIC/" + missing + ".");
    const entries = [];
    for (const name of [...required,...regions,...optional]) {
        if (group.has(name)) entries.push(["STATIC/"+name, await group.get(name).arrayBuffer()]);
    }
    // The portable sound-config reader supplies defaults when U7.CFG is absent.
    if (configs.has(root)) entries.push(["U7.CFG", await configs.get(root).arrayBuffer()]);
    return entries;
}
