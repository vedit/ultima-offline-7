// SPDX-License-Identifier: BSD-2-Clause
using System;
using System.IO;
using System.Text.Json;

namespace ClassicUO.Game.Intro
{
    internal sealed class U7IntroData
    {
        public int Version { get; set; }
        public int Width { get; set; }
        public int Height { get; set; }
        public double Duration { get; set; }
        public int[][] Cues { get; set; }
        public string[] Lines { get; set; }
        public double[] TextTimes { get; set; }
        internal static U7IntroData Read(string path)
        {
            var d=JsonSerializer.Deserialize<U7IntroData>(File.ReadAllText(path),new JsonSerializerOptions{PropertyNameCaseInsensitive=true});
            if(d==null || d.Version!=1 || d.Width is <1 or >512 || d.Height is <1 or >512 ||
               !double.IsFinite(d.Duration) || d.Duration is <1 or >120 || d.Cues==null || d.Cues.Length>4096 ||
               d.Lines?.Length!=14 || d.TextTimes?.Length!=15) throw new InvalidDataException("Invalid intro metadata");
            foreach(var c in d.Cues) if(c==null || c.Length!=2 || c[0]<0 || c[0]>7200 || c[1]<0 || c[1]>22) throw new InvalidDataException("Invalid facial cue");
            foreach(var line in d.Lines) if(string.IsNullOrWhiteSpace(line))throw new InvalidDataException("Invalid subtitle line");
            for(int i=0;i<d.TextTimes.Length;i++) if(!double.IsFinite(d.TextTimes[i]) || d.TextTimes[i]<0 || d.TextTimes[i]>d.Duration ||
               (i>0 && d.TextTimes[i]<d.TextTimes[i-1])) throw new InvalidDataException("Invalid subtitle timing");
            return d;
        }
    }

    internal enum DreamPhase { Sleep, Speech, Vanish, Wake, Portal, Enter, Complete }

    // Presentation time only. No gameplay clock, random source, object identity or save flags.
    internal sealed class U7IntroTimeline
    {
        internal const double SleepSeconds=1.5, VanishSeconds=1.3, WakeSeconds=1.2, EnterSeconds=.65;
        internal DreamPhase Phase { get; private set; }
        internal double Seconds { get; private set; }
        internal double SpeechDuration { get; }
        internal bool Paused { get; set; }
        internal int Mouth { get; private set; }
        internal int Eyes { get; private set; }
        internal int CueIndex { get; private set; }
        private int mouthPose=1,eyePose=4,lastEyePose=4;
        private readonly U7IntroData data;
        private static readonly int[,] EyeTable={
            {1,2,3,1,2,3,1,2,3},{4,5,6,4,5,6,4,5,6},{7,8,9,7,8,9,7,8,9},
            {1,1,1,4,4,4,7,7,7},{2,2,2,5,5,5,8,8,8},{3,3,3,6,6,6,9,9,9}};
        // Original mouth poses 1..13 collapse to five authored openings.
        private static readonly int[] MouthTable={0,0,3,3,3,2,1,4,4,4,4,1,0,1,0};
        internal U7IntroTimeline(U7IntroData data) { this.data=data;SpeechDuration=data.Duration; }
        internal void Advance(double seconds)
        {
            if(Paused || Phase==DreamPhase.Complete) return;
            if(!double.IsFinite(seconds) || seconds<0) throw new ArgumentOutOfRangeException(nameof(seconds));
            Seconds+=seconds;
            while(true) {
                double duration=Phase switch {DreamPhase.Sleep=>SleepSeconds,DreamPhase.Speech=>SpeechDuration,
                    DreamPhase.Vanish=>VanishSeconds,DreamPhase.Wake=>WakeSeconds,DreamPhase.Enter=>EnterSeconds,_=>double.PositiveInfinity};
                if(Seconds<duration) break;
                Seconds-=duration;
                Phase=Phase switch {DreamPhase.Sleep=>DreamPhase.Speech,DreamPhase.Speech=>DreamPhase.Vanish,
                    DreamPhase.Vanish=>DreamPhase.Wake,DreamPhase.Wake=>DreamPhase.Portal,DreamPhase.Enter=>DreamPhase.Complete,_=>Phase};
                if(Phase==DreamPhase.Complete) {Seconds=0;break;}
            }
            if(Phase==DreamPhase.Speech) UpdateFace();
            else {Mouth=0;Eyes=0;}
        }
        private void UpdateFace()
        {
            // Consume in original order. Sorting would alter the original late cue sequence.
            while(CueIndex<data.Cues.Length && data.Cues[CueIndex][0]/60.0<=Seconds) {
                int code=data.Cues[CueIndex++][1];
                if(code>=8 && code<23) mouthPose=code-8;
                else if(code==7) eyePose=10;
                else if(code>0 && code<7) {eyePose=EyeTable[code-1,lastEyePose-1];lastEyePose=eyePose;}
            }
            Mouth=MouthTable[mouthPose];
            Eyes=eyePose==10 ? 1 : (eyePose-1)%3;
        }
        internal string Caption {
            get {
                if(Phase!=DreamPhase.Speech) return "";
                int i=-1;while(i+1<data.TextTimes.Length && Seconds>=data.TextTimes[i+1])i++;
                return i>=0 && i<data.Lines.Length ? data.Lines[i] : "";
            }
        }
        internal float FaceAlpha=>Phase switch {DreamPhase.Sleep=>(float)Math.Clamp((Seconds-.5),0,1),
            DreamPhase.Speech=>1,DreamPhase.Vanish=>(float)Math.Clamp(1-Seconds/VanishSeconds,0,1),_=>0};
        internal float FadeAlpha=>Phase==DreamPhase.Enter ? (float)Math.Clamp(Seconds/EnterSeconds,0,1) : 0;
        internal void EnterPortal() {if(Phase==DreamPhase.Portal){Phase=DreamPhase.Enter;Seconds=0;}}
        internal void Skip() {Paused=false;Phase=DreamPhase.Complete;Seconds=0;}
    }
}
