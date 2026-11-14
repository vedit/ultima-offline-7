// SPDX-License-Identifier: BSD-2-Clause
using System;
using System.Collections.Generic;
using System.Linq;
using ClassicUO.Game.GameObjects;
using ClassicUO.Game.Managers;
using Microsoft.Xna.Framework;

namespace ClassicUO.Game
{
    // U7 owns all gameplay. This class only translates observed events to stock art.
    internal static class TrinsicEffects
    {
        private static EffectManager manager;
        private static ulong last;
        private static bool shaking;
        internal static Point CameraOffset => shaking ? new Point((int)(2*Math.Sin(Environment.TickCount64*.07)),(int)(2*Math.Cos(Environment.TickCount64*.09))) : Point.Zero;
        private static int generation=-1;
        private static readonly Dictionary<int,FixedEffect> missiles=new();
        private static readonly HashSet<int> nativeMissiles=new();
        private static readonly List<GameEffect> bursts=new();
        internal static int Played { get; private set; }
        internal static int ActiveMissiles => missiles.Count;
        internal static readonly Dictionary<string,int> Counts=new();
        internal static void Clear()
        {
            foreach(var effect in missiles.Values) effect.Destroy();
            foreach(var effect in bursts) if(!effect.IsDestroyed) effect.Destroy();
            missiles.Clear(); nativeMissiles.Clear(); bursts.Clear();shaking=false;
        }
        internal static void Start(World world) { Clear();manager=new EffectManager(world);last=0;generation=-1;Played=0;Counts.Clear(); }
        internal static void Update() => manager?.Update();
        internal static void Prepare(string[] lines)
        {
            nativeMissiles.Clear();
            foreach(string line in lines)
                if(line.StartsWith("FM ")) nativeMissiles.Add(int.Parse(line.Split(' ')[1]));
        }
        internal static bool IsMissile(int id) => nativeMissiles.Contains(id);
        // Fields remain normal selectable native items: Dispel Field targets the same
        // identity, and removal/expiry is driven by the next native observation.
        internal static ushort FieldGraphic(int shape) => shape switch {
            895=>0x398c, 900=>0x3915, 902=>0x3979, 768=>0x3946, _=>0
        };
        private static void Position(GameEffect effect,float x,float y,float z)
        {
            bool compact=TrinsicTown.Compact;
            float scale=compact?2:1, px=x/scale, py=y/scale;
            int ix=(int)Math.Floor(px), iy=(int)Math.Floor(py);
            effect.SetSource((ushort)ix,(ushort)iy,(sbyte)Math.Clamp((int)(z*4),-128,127));
            float dx=px-ix,dy=py-iy;
            effect.Offset=new Vector3(22*(dx-dy),22*(dx+dy)-(compact?11:0),0);
        }
        private static FixedEffect Fixed(World world,ushort graphic,ushort hue,int duration,float x,float y,float z,uint serial=0)
        {
            var effect=new FixedEffect(world,manager,graphic,hue,duration,0);
            Position(effect,x,y,z);
            var source=world.Get(serial);
            if(source!=null) effect.SetSource(source);
            manager.PushToBack(effect);
            return effect;
        }
        private static (ushort graphic,ushort hue,int sound) Art(string kind,int spell,int detail) => kind switch {
            "heal" => (0x376a,0,spell is 44 or 63?0x202:0x1f2),
            "cure" or "awaken" => (0x373a,0,0x1e0),
            "protect" => (0x375a,0,0x1e9),
            "curse" => (0x374a,0,0x1e1),
            "paralyze" => (0x376a,0,0x204),
            "poison" => (0x374a,0,0x205),
            "sleep" => (0x376a,0x0480,0x204),
            "charm" => (0x373a,0x0489,0x1e9),
            "might" => (0x373a,0,0x1ea),
            "hide" or "reveal" => (0x376a,0,0x203),
            "explosion" => (0x36cb,0,0x207),
            "flamestrike" => (0x3709,0,0x208),
            "dispel" or "disarm" => (0x376a,0,0x201),
            "unlock" or "telekinesis" => (0x376a,0,0x1fe),
            "mark" or "travel" => (0x3728,0,0x1fc),
            "resurrect" or "summon" => (0x376a,0,0x214),
            "light" => (0x376a,0,0x1e3),
            "ignite" => (0x3709,0,0),
            "douse" => (0x3735,0,0),
            "transform" or "create" => (0x373a,0,0x1e2),
            "fear" => (0x374a,0x0455,0),
            "dance" => (0x373a,0x0489,0),
            "tremor" => (0x3728,0,0x2f3),
            "timestop" => (0x376a,0x0480,0),
            "death" => (0x374a,0x0455,0),
            "swordstrike" => (0x37eb,0,0),
            "sprite" when spell==-2 => (0x3735,0,0x5c),
            "sprite" when spell==3 => (0x373a,0x0026,0),
            "sprite" when spell==10 => (0x373a,0x0035,0),
            "sprite" when spell==38 => (0x376a,0x0480,0),
            "sprite" when detail is 4 or 5 or 6 or 18 or 19 => (0x36cb,0,0x207),
            "sprite" when detail==8 => (0x379f,0x0455,0),
            "sprite" when detail==13 => (0x376a,0x0480,0),
            "sprite" when detail==23 => (0x37eb,0,0),
            "sprite" when spell>=0 => (0x373a,0,0),
            _ => (0,0,0)
        };
        internal static void Apply(World world,string[] lines,int gen)
        {
            string header=lines.FirstOrDefault(l=>l.StartsWith("FX "));
            // Older native hosts can still use the client without the optional channel.
            if(header==null) {Clear();return;}
            ulong watermark=ulong.Parse(header.Substring(3));
            if(generation!=gen || watermark<last) {Clear();generation=gen;last=watermark<last?0:last;}
            string[] environment=lines.First(l=>l.StartsWith("FV ")).Split(' ');
            int weather=int.Parse(environment[1]);
            shaking=environment.Length>4 && int.Parse(environment[4])>0;
            if(weather is 1 or 2) world.Weather.Generate(weather==1?WeatherType.WT_SNOW:WeatherType.WT_RAIN,45,0);
            else if(world.Weather.CurrentWeather.HasValue) world.Weather.Reset();
            bursts.RemoveAll(e=>e.IsDestroyed);
            var keep=new HashSet<int>();
            foreach(string line in lines) {
                if(line.StartsWith("FM ")) {
                    int[] m=Array.ConvertAll(line.Substring(3).Split(' '),int.Parse);
                    int missileId=m[0],type=m[1];keep.Add(missileId);
                    ushort graphic=(ushort)(type switch {856=>0x36d4,527=>0x379f,639=>0x379f,399=>0x376a,287=>0x37eb,807=>0x379f,_=>0x36d4});
                    ushort hue=(ushort)(type==639?0x0455:type==399?0x0480:0);
                    if(!missiles.TryGetValue(missileId,out var effect) || effect.IsDestroyed)
                        missiles[missileId]=effect=Fixed(world,graphic,hue,0,m[2]/8f,m[3]/8f,m[4]/8f);
                    // The native projectile controls movement, collision and lifetime.
                    Position(effect,m[2]/8f,m[3]/8f,m[4]/8f);
                    continue;
                }
                if(!line.StartsWith("F ")) continue;
                string[] e=line.Split(' ');
                ulong seq=ulong.Parse(e[1]);if(seq<=last) continue;last=seq;
                string kind=e[3];int spell=int.Parse(e[4]),id=int.Parse(e[5]);
                int x=int.Parse(e[6]),y=int.Parse(e[7]),z=int.Parse(e[8]),detail=int.Parse(e[9]);
                int scale=TrinsicTown.Compact?2:1;
                if(Math.Max(Math.Abs(x/scale-world.Player.X),Math.Abs(y/scale-world.Player.Y))>world.ClientViewRange) continue;
                uint serial=world.Mobiles.Get((uint)id)!=null?(uint)id:0x40000000u|(uint)id;
                if(kind=="flamestrike") serial=0; // field anchor: a burst per accepted native target
                if(kind=="lightning") {
                    var bolt=new LightningEffect(world,manager,serial,(ushort)(x/scale),(ushort)(y/scale),(sbyte)(z*4),0);
                    manager.PushToBack(bolt);bursts.Add(bolt);
                } else {
                    var art=Art(kind,spell,detail);if(art.graphic==0) continue;
                    var effect=Fixed(world,art.graphic,art.hue,kind=="flamestrike"?1500:950,x,y,z,serial);
                    bursts.Add(effect);
                    // Native audio already plays casting sounds. Only matching impact
                    // sounds are added, once per accepted event sequence.
                    if(art.sound!=0) Client.Game.Audio.PlaySound(art.sound);
                }
                Played++; Counts[kind]=Counts.GetValueOrDefault(kind)+1;
                TrinsicReplay.Record("EFFECT "+seq+" "+kind+" "+spell+" "+id+" "+x+" "+y+" "+z,line);
            }
            foreach(int id in missiles.Keys.Where(id=>!keep.Contains(id)).ToArray()) {missiles[id].Destroy();missiles.Remove(id);}
        }
    }
}
