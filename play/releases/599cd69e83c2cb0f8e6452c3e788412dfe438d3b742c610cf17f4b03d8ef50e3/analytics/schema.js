// Version 2 is an explicit allowlist, never a dump of game or browser state.
export const UUID=/^[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}$/;
export const CONTEXT={browser:['chrome','edge','firefox','safari','other'],os:['windows','mac','linux','android','ios','other'],viewport:['small','medium','large'],mode:['unknown','new','resume'],storage:['unknown','browser','folder'],music:['native','exult']};
export const METRICS=['hiddenMs','unfocusedMs','pausedMs','stalledMs','suspendedMs','drawSignals','maxDrawGapMs','longTasks','longTaskMs','backgrounds','focusLosses','pauses','errors','saveFailures','autoSaves','manualSaves','loads','saveMs','maxSaveMs','actions','rejectedActions','movement','uses','inventory','dialogue','spells','combat','debug'];
export const MILESTONES=['trinsic','evidence','reported','gate'];
export const emptyMetrics=()=>Object.fromEntries(METRICS.map(k=>[k,0]));
export const defaultContext=()=>({browser:'other',os:'other',viewport:'medium',mode:'unknown',storage:'unknown',music:'native'});
export const actionGroup=op=>{
  if(typeof op!=='string')return null;
  if(op.startsWith('DBG'))return 'debug';
  if(['STEP','TURN'].includes(op))return 'movement';
  if(['USE','TARGET','TARGETPOS','VIEWCLICK'].includes(op))return 'uses';
  if(['MOVE','GROUND','EQUIP','CLOSE'].includes(op))return 'inventory';
  if(['ANSWER','NUMBER','DISMISS'].includes(op))return 'dialogue';
  if(['BOOKCAST','BOOKSELECT'].includes(op))return 'spells';
  if(['ATTACK','WAR','COMBAT'].includes(op))return 'combat';
  return null;
};
