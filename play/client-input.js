// DOM events feed the browser port's existing SDL event queue.
export function installInput(canvas, m) {
    const keys = {Backspace:8,Tab:9,Enter:13,Escape:27,Delete:127,
        ArrowRight:0x4000004f,ArrowLeft:0x40000050,ArrowDown:0x40000051,ArrowUp:0x40000052,
        Home:0x4000004a,End:0x4000004d,PageUp:0x4000004b,PageDown:0x4000004e,
        Insert:0x40000049,CapsLock:0x40000039,NumLock:0x40000053};
    const modifiers={ControlLeft:[224,64],ShiftLeft:[225,1],AltLeft:[226,256],MetaLeft:[227,1024],
        ControlRight:[228,128],ShiftRight:[229,2],AltRight:[230,512],MetaRight:[231,2048]};
    const scans={Enter:40,Escape:41,Backspace:42,Tab:43,Space:44,Minus:45,Equal:46,
        BracketLeft:47,BracketRight:48,Backslash:49,Semicolon:51,Quote:52,Backquote:53,
        Comma:54,Period:55,Slash:56,Delete:76,NumpadDivide:84,NumpadMultiply:85,
        NumpadSubtract:86,NumpadAdd:87,NumpadEnter:88,Numpad0:98,NumpadDecimal:99};
    for(let i=1;i<=9;i++)scans['Numpad'+i]=88+i;
    for(let i=0;i<=9;i++)scans['Digit'+i]=i===0?39:29+i;
    for(let i=1;i<=12;i++) keys['F'+i]=0x40000039+i;
    const held = new Map();
    const buffer = m._malloc(128);
    let last=[0,0],buttons=0;
    let motion, motionFrame;
    const xy=e=>{const r=canvas.getBoundingClientRect();return [Math.round((e.clientX-r.left)*canvas.width/r.width),Math.round((e.clientY-r.top)*canvas.height/r.height)]};
    const stop=e=>{e.preventDefault();e.stopImmediatePropagation()};
    function mods(e){
        let value=(e.getModifierState('CapsLock')?8192:0)|(e.getModifierState('NumLock')?4096:0);
        for(const code of held.keys())value|=modifiers[code]?.[1]||0;
        return value;
    }
    function key(e,down) {
        if(down?document.activeElement!==canvas:!held.has(e.code))return;
        const special=modifiers[e.code]?.[0]||(e.code.startsWith('Numpad')?scans[e.code]:0);
        const k=held.get(e.code)?.[0]||(special?0x40000000|special:keys[e.key])||
                (/^Key[A-Z]$/.test(e.code)&&e.key.length===1?e.key.toLowerCase().charCodeAt(0):
                /^Digit[0-9]$/.test(e.code)?e.code.charCodeAt(5):e.key.length===1?e.key.charCodeAt(0):0);
        if(!k)return;
        const scan=scans[e.code]||(k&0x40000000 ? k&0xffff : /^Key[A-Z]$/.test(e.code) ? e.code.charCodeAt(3)-61 : 0);
        if(down)held.set(e.code,[k,scan]);else held.delete(e.code);
        m._wasm_push_key(down?1:0,k,scan,mods(e),e.repeat?1:0);
        if(down && e.key.length===1 && !e.ctrlKey && !e.altKey && !e.metaKey){
            const b=new TextEncoder().encode(e.key);m.HEAPU8.set(b,buffer);m.HEAPU8[buffer+b.length]=0;m._wasm_push_text(buffer);
        }
        stop(e);
    }
    window.addEventListener('keydown',e=>key(e,true),true);
    window.addEventListener('keyup',e=>key(e,false),true);
    function flushMotion(){
        if(motionFrame){cancelAnimationFrame(motionFrame);motionFrame=0}
        if(!motion)return;
        const {p,buttons}=motion;motion=null;
        m._wasm_push_mouse_motion(...p,p[0]-last[0],p[1]-last[1],buttons);last=p;
    }
    // A high-polling-rate mouse can outpace the managed event consumer.
    // Preserve its latest position once per display frame; never coalesce clicks.
    canvas.addEventListener('pointermove',e=>{motion={p:xy(e),buttons:(e.buttons&1)|((e.buttons&2)<<1)|((e.buttons&4)>>1)};if(!motionFrame)motionFrame=requestAnimationFrame(flushMotion);stop(e)},true);
    canvas.addEventListener('pointerdown',e=>{buttons=e.buttons;flushMotion();canvas.focus();canvas.setPointerCapture(e.pointerId);last=xy(e);m._wasm_push_mouse_button(1,e.button+1,...last);stop(e)},true);
    canvas.addEventListener('pointerup',e=>{buttons=e.buttons;flushMotion();last=xy(e);m._wasm_push_mouse_button(0,e.button+1,...last);stop(e)},true);
    canvas.addEventListener('contextmenu',stop,true);
    canvas.addEventListener('wheel',e=>{flushMotion();m._wasm_push_mouse_wheel(-Math.sign(e.deltaX),-Math.sign(e.deltaY),...xy(e));stop(e)},{capture:true,passive:false});
    canvas.addEventListener('pointerenter',()=>m._wasm_push_mouse_in_window(1),true);
    canvas.addEventListener('pointerleave',()=>m._wasm_push_mouse_in_window(0),true);
    function release(){
        flushMotion();
        for(const [k,s]of held.values())m._wasm_push_key(0,k,s,0,0);
        held.clear();
        for(const [mask,button]of [[1,1],[2,3],[4,2],[8,4],[16,5]])
            if(buttons&mask)m._wasm_push_mouse_button(0,button,...last);
        buttons=0;
    }
    window.addEventListener('blur',()=>{release();m._wasm_push_window_focus(0)},true);
    function resume(){m._wasm_push_window_focus(1);canvas.focus()}
    window.addEventListener('focus',resume,true);
    document.addEventListener('visibilitychange',()=>{if(document.hidden)release();else resume()});
    canvas.addEventListener('pointercancel',release,true);
    return {active:()=>buttons!==0||held.size>0,save(){m._wasm_push_key(1,keys.F5,62,0,0);m._wasm_push_key(0,keys.F5,62,0,0)}};
}
