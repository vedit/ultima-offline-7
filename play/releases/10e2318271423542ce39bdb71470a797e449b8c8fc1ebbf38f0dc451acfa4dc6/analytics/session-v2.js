import {Session,MAX_MS,STAGES} from './core.js?v=bf66b178215c6a33';
import {CONTEXT,MILESTONES,emptyMetrics,defaultContext,actionGroup} from './schema.js?v=bf66b178215c6a33';

export class PlayerSession extends Session {
  constructor(options) {
    super(options);
    Object.assign(this.data,{v:2,player:options.player||'',returning:!!options.returning,
      context:{...defaultContext(),...options.context},metrics:emptyMetrics(),
      stages:Object.fromEntries(STAGES.map(s=>[s,0])),
      milestones:Object.fromEntries(MILESTONES.map(k=>[k,-1])),baseline:[]});
    this.lastVisibleDraw=null;this.firstWorld=true;
  }
  add(key,value=1){this.data.metrics[key]=Math.min(MAX_MS,this.data.metrics[key]+Math.max(0,value));}
  tick(now) {
    now=Math.min(now,this.begin+MAX_MS);
    const d=this.data,dt=now-this.last;
    if(d.metrics && Number.isFinite(dt) && dt>=0 && !this.closed) {
      const bounded=Math.min(dt,Math.max(0,MAX_MS-d.wallMs));
      if(dt>15000)this.add('suspendedMs',bounded);
      else if(!this.visible)this.add('hiddenMs',bounded);
      else if(!this.focused)this.add('unfocusedMs',bounded);
      else if(this.paused)this.add('pausedMs',bounded);
      else if(d.state==='playing')this.add('stalledMs',Math.max(0,now-Math.max(this.last,this.draw+15000)));
      if(d.state==='loading')d.stages[d.stage]=Math.min(MAX_MS,d.stages[d.stage]+bounded);
    }
    super.tick(now);
  }
  event(type,value,now) {
    if(this.closed)return;
    const was={visible:this.visible,focused:this.focused,paused:this.paused};
    super.event(type,value,now);
    const d=this.data;
    if(type==='visible'&&!value&&was.visible)this.add('backgrounds');
    if(type==='focused'&&!value&&was.focused)this.add('focusLosses');
    if(type==='paused'&&value&&!was.paused)this.add('pauses');
    if(['visible','focused','paused'].includes(type))this.lastVisibleDraw=null;
    if(type==='draw'){
      this.add('drawSignals');
      if(this.visible&&this.focused&&!this.paused){
        if(this.lastVisibleDraw!==null)d.metrics.maxDrawGapMs=Math.max(d.metrics.maxDrawGapMs,Math.min(MAX_MS,now-this.lastVisibleDraw));
        this.lastVisibleDraw=now;
      }
    }
    if(type==='fail'){
      this.add('errors');
      if(value&&(value.tile||value.save)&&!d.crash){
        const tile=t=>t&&{x:t.x,y:t.y,z:t.z};
        d.crash={tile:tile(value.tile),save:value.save&&{slot:value.save.slot,tile:tile(value.save.tile),savedAtMs:value.save.savedAtMs}};
      }
    }
    if(type==='save-fail')this.add('saveFailures');
    if(type==='context')for(const [key,choices]of Object.entries(CONTEXT))if(choices.includes(value?.[key]))d.context[key]=value[key];
    if(type==='longtask'&&Number.isFinite(value)&&value>=0){this.add('longTasks');this.add('longTaskMs',Math.min(value,MAX_MS));}
    if(type==='saved'&&['auto','manual','load'].includes(value?.kind)&&Number.isFinite(value.ms)&&value.ms>=0){
      this.add({auto:'autoSaves',manual:'manualSaves',load:'loads'}[value.kind]);
      this.add('saveMs',Math.min(MAX_MS,value.ms));d.metrics.maxSaveMs=Math.max(d.metrics.maxSaveMs,Math.min(MAX_MS,value.ms));
    }
    if(type==='action'){
      const group=actionGroup(value?.op);
      if(group){this.add('actions');this.add(group);
        if(!['ok','using','merged'].includes(value.result)&&!String(value.result).startsWith('split-'))this.add('rejectedActions');}
    }
  }
  frame(frame){
    super.frame(frame);
    if(!this.previous)return;
    for(const key of MILESTONES)if(this.data[key]&&this.data.milestones[key]<0){
      this.data.milestones[key]=this.data.wallMs;
      if(this.firstWorld&&this.data.context.mode!=='new'&&key!=='gate')this.data.baseline.push(key);
    }
    this.firstWorld=false;
  }
  snapshot(now){
    const d=super.snapshot(now);
    return {...d,context:{...d.context},metrics:Object.fromEntries(Object.entries(d.metrics).map(([k,v])=>[k,Math.floor(v)])),
      stages:Object.fromEntries(Object.entries(d.stages).map(([k,v])=>[k,Math.floor(v)])),
      milestones:Object.fromEntries(Object.entries(d.milestones).map(([k,v])=>[k,Math.floor(v)])),baseline:[...d.baseline]};
  }
}
