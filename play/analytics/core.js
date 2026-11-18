// Cumulative counters: repeated or reordered deliveries never add playtime twice.
export const MAX_MS = 86400000;
export const STAGES = ['none','startup','download','save','native','client','artwork','render','runtime'];
export class Session {
  constructor({id, build, started, now = 0, visible = true, focused = true}) {
    this.data = {v:1,id,build,started,seq:0,state:'loading',stage:'none',wallMs:0,activeMs:0,loadMs:0,
      ready:false,trinsic:false,evidence:false,reported:false,gate:false};
    this.last = this.begin = now;
    this.draw = -Infinity;
    this.visible = visible; this.focused = focused; this.paused = false;
  }
  tick(now) {
    if (!Number.isFinite(now) || now < this.last) return;
    const d = this.data;
    if (!this.closed) {
      d.wallMs = Math.min(MAX_MS, now - this.begin);
      if (d.state === 'playing' && this.visible && this.focused && !this.paused) {
        // Long event-loop gaps (sleep/suspension) are not evidence of gameplay.
        const dt = now - this.last;
        if (dt <= 15000) d.activeMs += Math.max(0, Math.min(now, this.draw + 15000) - this.last);
        d.activeMs = Math.min(d.activeMs, d.wallMs, MAX_MS);
      }
    }
    this.last = now;
  }
  event(type, value, now) {
    this.tick(now);
    const d = this.data;
    if (type === 'visible') this.visible = value;
    if (type === 'focused') this.focused = value;
    if (type === 'paused') this.paused = value;
    if (type === 'draw') {
      this.draw = now;
      if (d.state === 'loading') {d.ready = true; d.loadMs = d.wallMs; d.state = 'playing';}
    }
    if (type === 'stage' && STAGES.includes(value)) d.stage = value;
    if (type === 'fail' && d.state !== 'ended') d.state = 'failed';
    if (type === 'end') {this.closed=true;if(d.state!=='failed')d.state = 'ended';}
    if (type === 'frame') this.frame(value);
  }
  frame(frame) {
    // Read only the existing native snapshot. Never send names, text, positions,
    // inventory, flags, saves or commands to the collection endpoint.
    let player, flags, openGate = false, cameraOnly = false;
    for (const line of frame.split('\n')) {
      const f = line.split(' ');
      if (f[0] === 'Q' && f.length === 9) flags = f.slice(1).map(Number);
      if (f[0] === 'CAMERA_ONLY') cameraOnly = true;
      if (f[0] !== 'E') continue;
      if (f[8] === '0') player = [Number(f[4]), Number(f[5])];
      if (f[2] === '271' && Math.abs(Number(f[4])-1102)<4 && Number(f[6])>0) openGate=true;
    }
    if (!player || !flags || cameraOnly) {this.previous=undefined; return;}
    const [x,y] = player, d = this.data;
    if (!Number.isFinite(x+y) || flags.some(f=>!Number.isInteger(f))) return;
    if (x>=896 && x<=1103 && y>=2048 && y<=2303) d.trinsic=true;
    // Q order: flags 60,61,62,64,66,67,72,90. See investigation.py.
    if (flags[0] && flags[2]) d.evidence=true;
    if (flags[1]) d.reported=true;
    const p=this.previous;
    if (p && p[0]<=1103 && x>1103 && y>=2210 && y<=2218 &&
        Math.max(Math.abs(x-p[0]), Math.abs(y-p[1]))<=3 && flags[1] && openGate) d.gate=true;
    this.previous=player;
  }
  snapshot(now) {
    this.tick(now);
    return {...this.data, seq:++this.data.seq, wallMs:Math.floor(this.data.wallMs),
      activeMs:Math.floor(this.data.activeMs),loadMs:Math.floor(this.data.loadMs)};
  }
}
