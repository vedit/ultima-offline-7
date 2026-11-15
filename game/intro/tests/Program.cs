using System;
using ClassicUO.Game.Intro;
var d=U7IntroData.Read(args[0]);
void Check(bool condition,string name) {if(!condition)throw new Exception(name);Console.WriteLine("PASS "+name);}
var t=new U7IntroTimeline(d);
Check(t.Phase==DreamPhase.Sleep && t.FaceAlpha==0,"starts asleep");
t.EnterPortal();Check(t.Phase==DreamPhase.Sleep,"portal cannot bypass speech");
t.Advance(1.5);Check(t.Phase==DreamPhase.Speech && t.Seconds==0,"speech starts after sleep");
t.Advance(2);double seconds=t.Seconds;int cue=t.CueIndex;t.Paused=true;t.Advance(200);
Check(t.Seconds==seconds && t.CueIndex==cue,"pause holds captions and facial cues");
t.Paused=false;
var mouths=new System.Collections.Generic.HashSet<int>();var eyes=new System.Collections.Generic.HashSet<int>();
while(t.Phase==DreamPhase.Speech) {t.Advance(1.0/120);mouths.Add(t.Mouth);eyes.Add(t.Eyes);}
Check(mouths.Count==5 && eyes.Count==3,"original cues exercise every authored pose");
Check(t.CueIndex==d.Cues.Length,"all original cues consumed in source order");
t.Advance(3);Check(t.Phase==DreamPhase.Portal && t.FaceAlpha==0,"face gone before portal");
t.Advance(999);Check(t.Phase==DreamPhase.Portal,"portal waits for player movement");
t.EnterPortal();t.EnterPortal();t.Advance(.65);Check(t.Phase==DreamPhase.Complete,"portal handoff completes once");
foreach(DreamPhase phase in new[]{DreamPhase.Sleep,DreamPhase.Speech,DreamPhase.Vanish,DreamPhase.Wake,DreamPhase.Portal,DreamPhase.Enter}) {
 var s=new U7IntroTimeline(d);
 double elapsed=phase switch {DreamPhase.Sleep=>0,DreamPhase.Speech=>2,DreamPhase.Vanish=>1.5+d.Duration+.1,DreamPhase.Wake=>1.5+d.Duration+1.4,_=>1.5+d.Duration+3};
 s.Advance(elapsed);if(phase==DreamPhase.Enter)s.EnterPortal();s.Paused=true;s.Skip();s.Skip();s.Advance(20);
 Check(s.Phase==DreamPhase.Complete && !s.Paused,"skip idempotent from "+phase);
}
try {new U7IntroTimeline(d).Advance(double.NaN);throw new Exception("accepted NaN");}catch(ArgumentOutOfRangeException) {Console.WriteLine("PASS invalid elapsed time rejected");}
