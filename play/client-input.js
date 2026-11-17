// DOM events feed the browser port's existing SDL event queue.
export function installInput(canvas, m) {
    const keys = {Backspace:8,Tab:9,Enter:13,Escape:27,Delete:127,
        ArrowRight:0x4000004f,ArrowLeft:0x40000050,ArrowDown:0x40000051,ArrowUp:0x40000052,
        Home:0x4000004a,End:0x4000004d,PageUp:0x4000004b,PageDown:0x4000004e,
        Shift:0x400000e1,Control:0x400000e0,Alt:0x400000e2};
    for(let i=1;i<=12;i++) keys['F'+i]=0x40000039+i;
    const held = new Map();
    const buffer = m._malloc(128);
    let last=[0,0];
    let motion, motionFrame;
    const xy=e=>{const r=canvas.getBoundingClientRect();return [Math.round((e.clientX-r.left)*canvas.width/r.width),Math.round((e.clientY-r.top)*canvas.height/r.height)]};
    const stop=e=>{e.preventDefault();e.stopImmediatePropagation()};
    const mods=e=>(e.shiftKey?1:0)|(e.ctrlKey?64:0)|(e.altKey?256:0)|(e.metaKey?1024:0);
    function key(e,down) {
        if(document.activeElement!==canvas && down) return;
        const k=keys[e.key] || (e.key.length===1 ? e.key.toLowerCase().charCodeAt(0):0);
        if(!k)return;
        const scan=k&0x40000000 ? k&0xffff : /^Key[A-Z]$/.test(e.code) ? e.code.charCodeAt(3)-61 : 0;
        m._wasm_push_key(down?1:0,k,scan,mods(e),e.repeat?1:0);
        if(down)held.set(e.code,[k,scan]);else held.delete(e.code);
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
    canvas.addEventListener('pointerdown',e=>{flushMotion();canvas.focus();canvas.setPointerCapture(e.pointerId);last=xy(e);m._wasm_push_mouse_button(1,e.button+1,...last);stop(e)},true);
    canvas.addEventListener('pointerup',e=>{flushMotion();last=xy(e);m._wasm_push_mouse_button(0,e.button+1,...last);stop(e)},true);
    canvas.addEventListener('contextmenu',stop,true);
    canvas.addEventListener('wheel',e=>{flushMotion();m._wasm_push_mouse_wheel(-Math.sign(e.deltaX),-Math.sign(e.deltaY),...xy(e));stop(e)},{capture:true,passive:false});
    canvas.addEventListener('pointerenter',()=>m._wasm_push_mouse_in_window(1),true);
    canvas.addEventListener('pointerleave',()=>m._wasm_push_mouse_in_window(0),true);
    function release(){flushMotion();for(const [k,s]of held.values())m._wasm_push_key(0,k,s,0,0);held.clear();for(let b=1;b<=3;b++)m._wasm_push_mouse_button(0,b,...last)}
    window.addEventListener('blur',()=>{release();m._wasm_push_window_focus(0)},true);
    function resume(){m._wasm_push_window_focus(1);canvas.focus()}
    window.addEventListener('focus',resume,true);
    document.addEventListener('visibilitychange',()=>{if(document.hidden)release();else resume()});
    canvas.addEventListener('pointercancel',release,true);
    return {save(){m._wasm_push_key(1,keys.F5,62,0,0);m._wasm_push_key(0,keys.F5,62,0,0)}};
}
