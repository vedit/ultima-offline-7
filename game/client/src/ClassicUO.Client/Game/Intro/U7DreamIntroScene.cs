// SPDX-License-Identifier: BSD-2-Clause
using System;
using System.IO;
using ClassicUO.Assets;
using ClassicUO.Configuration;
using ClassicUO.Game.GameObjects;
using ClassicUO.Game.Scenes;
using ClassicUO.Input;
using ClassicUO.Renderer;
using Microsoft.Xna.Framework;
using Microsoft.Xna.Framework.Audio;
using Microsoft.Xna.Framework.Graphics;
using SDL3;

namespace ClassicUO.Game.Intro
{
    // An isolated presentation. The native host remains at its existing BEGIN gate.
    internal sealed class U7DreamIntroScene : Scene
    {
        private readonly World world;
        private readonly Action begin;
        private readonly U7IntroData data;
        internal readonly U7IntroTimeline Timeline;
        private Texture2D relief;
        private SoundEffect voice;
        private SoundEffectInstance speech;
        private RenderedText caption, hint;
        private long lastTick;
        private bool handedOff, voiceStarted, manuallyPaused, steering;
        private int arrows, scale=1, originX, originY;
        private byte direction=4;
        private Vector2 actor=new(3.5f,3.5f);
        private static readonly Vector2 Portal=new(.65f,2.8f);
        private bool walking, running;
        private double walkTime;
        private string captionText, hintText;
        private string nativeCheckpoint;
        private double pausedAt;
        private Point? replayPointer;

        internal static bool TryCreate(World world, Action begin, out U7DreamIntroScene scene)
        {
            scene=null;
            string folder=Environment.GetEnvironmentVariable("TRINSIC_INTRO_ASSETS");
            if(string.IsNullOrEmpty(folder) || Environment.GetEnvironmentVariable("TRINSIC_READY")==null) return false;
            try { scene=new U7DreamIntroScene(world,folder,begin);return true; }
            catch(Exception ex) when(ex is IOException || ex is ArgumentException || ex is InvalidOperationException || ex is System.Text.Json.JsonException)
            { Console.Error.WriteLine("Dream intro unavailable; continuing to the original opening: "+ex.Message);return false; }
        }
        private U7DreamIntroScene(World world,string folder,Action begin)
        {
            this.world=world;this.begin=begin;
            data=U7IntroData.Read(Path.Combine(folder,"intro.json"));
            Timeline=new U7IntroTimeline(data);
            try {
                using(var stream=File.OpenRead(Path.Combine(folder,"guardian.png"))) relief=Texture2D.FromStream(Client.Game.GraphicsDevice,stream);
                if(relief.Width!=data.Width*5 || relief.Height!=data.Height*3) throw new InvalidDataException("Invalid relief atlas size");
                try {
                    using var stream=File.OpenRead(Path.Combine(folder,"guardian.wav"));
                    voice=SoundEffect.FromStream(stream);speech=voice.CreateInstance();
                    var profile=ProfileManager.CurrentProfile;
                    speech.Volume=profile.TrinsicSpeechEnabled ? Math.Clamp(profile.TrinsicSpeechVolume/100f,0,1) : 0;
                } catch(Exception ex) { Console.Error.WriteLine("Dream voice unavailable; captions remain active: "+ex.Message); }
            } catch { speech?.Dispose();voice?.Dispose();relief?.Dispose();throw; }
        }
        public override void Load()
        {
            base.Load();
            Client.Game.Window.AllowUserResizing=true;
            if(Settings.GlobalSettings.WindowSize is Point size) Client.Game.SetWindowSize(size.X,size.Y);
            Resize();lastTick=Environment.TickCount64;
            Console.WriteLine("DREAM START: native BEGIN held");
        }
        private void Resize()
        {
            var bounds=Client.Game.Window.ClientBounds;
            Camera.Bounds=new Rectangle(0,0,Math.Max(640,bounds.Width),Math.Max(480,bounds.Height));
        }
        public override void Update()
        {
            long now=Environment.TickCount64;
            double dt=Math.Max((now-lastTick)/1000.0,0);lastTick=now;
            Resize();
            bool pause=manuallyPaused || (!Client.Game.IsActive && !TrinsicReplay.Active);
            if(Timeline.Paused && !pause)dt=0;
            Timeline.Paused=pause;
            if(pause) {arrows=0;steering=false;if(speech?.State==SoundState.Playing)speech.Pause();}
            else if(speech?.State==SoundState.Paused) speech.Resume();
            var previous=Timeline.Phase;
            Timeline.Advance(dt);
            if(Timeline.Phase==DreamPhase.Speech && !voiceStarted) {voiceStarted=true;speech?.Play();}
            if(previous==DreamPhase.Speech && Timeline.Phase!=DreamPhase.Speech) speech?.Stop();
            if(TrinsicReplay.Active && replayPointer is Point pointer)Mouse.Position=pointer;
            if(!pause && Timeline.Phase==DreamPhase.Portal) Move((float)Math.Min(dt,.1));
            else walking=false;
            if(previous!=Timeline.Phase) Console.WriteLine("DREAM "+Timeline.Phase);
            if(Timeline.Phase==DreamPhase.Complete) {Handoff();return;}
            if(TrinsicReplay.Active) TrinsicReplay.Next(world,null,null);
        }
        private void Handoff()
        {
            if(handedOff)return;
            handedOff=true;arrows=0;steering=false;speech?.Stop();
            Mouse.ButtonRelease(MouseButtonType.Right);
            Console.WriteLine("DREAM COMPLETE: releasing original native BEGIN");
            begin();
        }
        private void Move(float dt)
        {
            Vector2 screen=new((arrows&2)!=0 ? 1:0,(arrows&8)!=0 ? 1:0);
            if((arrows&1)!=0)screen.X--;if((arrows&4)!=0)screen.Y--;
            running=false;
            if(steering) {
                Vector2 position=Project(actor);
                screen=new Vector2((Mouse.Position.X-originX)/(float)scale,(Mouse.Position.Y-originY)/(float)scale)-position;
                running=screen.Length()>80;
                if(screen.Length()<5) screen=Vector2.Zero;
            }
            walking=screen.LengthSquared()>.01f;
            if(!walking)return;
            screen.Normalize();
            Vector2 tile=new(screen.X+screen.Y,screen.Y-screen.X);tile.Normalize();
            direction=(byte)((((int)Math.Round(Math.Atan2(tile.Y,tile.X)/(Math.PI/4)))+2+8)%8);
            Vector2 next=actor+tile*(running?4.5f:2.5f)*dt;
            next.X=Math.Clamp(next.X,.5f,4.5f);next.Y=Math.Clamp(next.Y,.5f,5.2f);
            // Bed footprint; slide along its edge instead of walking through it.
            bool Bed(Vector2 p)=>p.X>2.35f && p.X<3.15f && p.Y>1.35f && p.Y<3.15f;
            if(Bed(next)) {next=new Vector2(actor.X,next.Y);if(Bed(next))next=new Vector2(actor.X,actor.Y);}
            actor=next;walkTime+=dt;
            if(Vector2.Distance(actor,Portal)<.6f) Timeline.EnterPortal();
        }
        private static Vector2 Project(Vector2 p)=>new((p.X-p.Y)*22,(p.X+p.Y)*22);
        private Rectangle Rect(float x,float y,int w,int h)=>new(originX+(int)Math.Round(x*scale),originY+(int)Math.Round(y*scale),w*scale,h*scale);
        public override bool Draw(UltimaBatcher2D batcher,RenderTargets targets)
        {
            batcher.GraphicsDevice.SetRenderTarget(targets.WorldRenderTarget);batcher.GraphicsDevice.Clear(Color.Black);
            batcher.GraphicsDevice.SetRenderTarget(targets.LightRenderTarget);batcher.GraphicsDevice.Clear(Color.Transparent);
            return true;
        }
        public override void DrawUI(UltimaBatcher2D batcher)
        {
            var viewport=batcher.GraphicsDevice.Viewport;
            scale=Math.Clamp(Math.Min(viewport.Width/400,viewport.Height/440),1,2);
            originX=viewport.Width/2;originY=viewport.Height/2-27*scale;
            batcher.SetSampler(SamplerState.PointClamp);
            batcher.Draw(SolidColorTextureCache.GetTexture(Color.Black),new Rectangle(0,0,viewport.Width,viewport.Height),Vector3.UnitZ,0);
            for(int sum=0;sum<=9;sum++) for(int x=0;x<5;x++) {int y=sum-x;if(y>=0 && y<6) Art(batcher,0x519,new Vector2(x,y),0);}
            for(int y=0;y<6;y++) for(int level=0;level<2;level++) Art(batcher,0x1b,new Vector2(0,y),level*80);
            Art(batcher,0xa5d,new Vector2(2.75f,1.8f),0);
            Art(batcher,0xa5c,new Vector2(2.75f,2.8f),0);
            if(Timeline.FaceAlpha>0) batcher.Draw(relief,Rect(-107,-102,data.Width,data.Height),
                new Rectangle(Timeline.Mouth*data.Width,Timeline.Eyes*data.Height,data.Width,data.Height),new Vector3(0,0,Timeline.FaceAlpha),0);
            bool sleeping=Timeline.Phase is DreamPhase.Sleep or DreamPhase.Speech or DreamPhase.Vanish;
            if(Timeline.Phase is DreamPhase.Portal or DreamPhase.Enter) Art(batcher,(uint)(0xdda+(int)(Timeline.Seconds*8)%5),Portal,0);
            DrawAvatar(batcher,sleeping);
            string text=Timeline.Caption;
            if(captionText!=text) {caption?.Destroy();captionText=text;caption=Text(text,340);}
            if(caption?.HasContent==true) caption.Draw(batcher,originX-54*scale-caption.Width/2,originY-119*scale-caption.Height,0);
            string controls=Timeline.Paused ? "Paused - Space to resume   |   Esc to skip" : Timeline.Phase==DreamPhase.Portal ?
                "Walk into the red moongate. Hold right mouse or use arrow keys.   |   Esc to skip" : "Space to pause   |   Esc to skip";
            if(hintText!=controls) {hint?.Destroy();hintText=controls;hint=Text(controls,680);}
            hint.Draw(batcher,(viewport.Width-hint.Width)/2,viewport.Height-32-hint.Height,0);
            if(Timeline.FadeAlpha>0) batcher.Draw(SolidColorTextureCache.GetTexture(Color.Black),new Rectangle(0,0,viewport.Width,viewport.Height),new Vector3(0,0,Timeline.FadeAlpha),0);
        }
        private static RenderedText Text(string text,int width)=>RenderedText.Create(text,0x3b2,3,true,FontStyle.BlackBorder,TEXT_ALIGN_TYPE.TS_CENTER,width);
        private void Art(UltimaBatcher2D batcher,uint id,Vector2 location,int lift)
        {
            ref readonly var art=ref Client.Game.UO.Arts.GetArt(id);
            if(art.Texture==null)return;
            var p=Project(location);
            batcher.Draw(art.Texture,Rect(p.X-art.UV.Width/2f,p.Y+22-art.UV.Height-lift,art.UV.Width,art.UV.Height),art.UV,Vector3.UnitZ,0);
        }
        private void DrawAvatar(UltimaBatcher2D batcher,bool sleeping)
        {
            byte dir=sleeping?(byte)4:direction;bool mirror=false;
            Client.Game.UO.Animations.GetAnimDirection(ref dir,ref mirror);
            byte group=sleeping?(byte)21:walking?(byte)(running?2:0):(byte)4;
            var at=Project(sleeping?new Vector2(2.75f,2.2f):actor);
            Vector2 restOffset=Vector2.Zero;
            if(sleeping) {
                var body=Client.Game.UO.Animations.GetAnimationFrames(world.Player.Graphic,group,dir,out _,out _);
                if(body.Length>0) {ref var f=ref body[body.Length-1];restOffset=new Vector2(f.Center.X-f.UV.Width/2f-10,f.Center.Y+f.UV.Height/2f-30);}
            }
            void Layer(ushort id,ushort hue,bool equip)
            {
                var frames=Client.Game.UO.Animations.GetAnimationFrames(id,group,dir,out _,out _,equip);
                if(frames.Length==0)return;
                int i=sleeping?frames.Length-1:walking?(int)(walkTime*(running?14:10))%frames.Length:0;
                ref var f=ref frames[i];if(f.Texture==null)return;
                var dest=Rect(at.X+restOffset.X-(mirror?f.UV.Width-f.Center.X:f.Center.X),at.Y+22+restOffset.Y-f.UV.Height-f.Center.Y,f.UV.Width,f.UV.Height);
                batcher.Draw(f.Texture,dest,f.UV,ShaderHueTranslator.GetHueVector(hue,equip,1),0,Vector2.Zero,mirror?SpriteEffects.FlipHorizontally:SpriteEffects.None,0);
            }
            Layer(world.Player.Graphic,world.Player.Hue,false);
            // Cosmetic equipment only: no proxy objects are allocated in World.
            foreach(byte slot in new byte[]{4,3,7,8,5,13,17,22,19,20,16,11}) {
                var item=world.Player.FindItemByLayer((ClassicUO.Game.Data.Layer)slot);
                if(item?.ItemData.AnimID>0)Layer(item.ItemData.AnimID,item.Hue,true);
            }
        }
        internal override void OnKeyDown(SDL.SDL_KeyboardEvent e)
        {
            if(e.key==(uint)SDL.SDL_Keycode.SDLK_ESCAPE) {Timeline.Skip();return;}
            if(e.key==(uint)SDL.SDL_Keycode.SDLK_SPACE && !e.repeat) {manuallyPaused=!manuallyPaused;return;}
            if(Timeline.Phase!=DreamPhase.Portal || Timeline.Paused)return;
            arrows|=Key((SDL.SDL_Keycode)e.key);
        }
        internal override void OnKeyUp(SDL.SDL_KeyboardEvent e) {arrows&=~Key((SDL.SDL_Keycode)e.key);}
        private static int Key(SDL.SDL_Keycode key)=>key switch {
            SDL.SDL_Keycode.SDLK_LEFT=>1,SDL.SDL_Keycode.SDLK_RIGHT=>2,SDL.SDL_Keycode.SDLK_UP=>4,SDL.SDL_Keycode.SDLK_DOWN=>8,_=>0};
        internal override bool OnMouseDown(MouseButtonType button) {if(button==MouseButtonType.Right && Timeline.Phase==DreamPhase.Portal && !Timeline.Paused)steering=true;return true;}
        internal override bool OnMouseUp(MouseButtonType button) {if(button==MouseButtonType.Right)steering=false;return true;}
        internal override bool OnMouseDoubleClick(MouseButtonType button)=>true;
        internal override bool OnMouseWheel(bool up)=>true;
        internal override bool OnMouseDragging()=>true;
        // Runs only under the existing opt-in client replay driver.
        internal static void Replay(string[] args)
        {
            if(!TrinsicReplay.Active)throw new InvalidOperationException("Replay is disabled");
            var scene=Client.Game.Scene as U7DreamIntroScene;
            if(args[1]=="GAME") {if(Client.Game.Scene is not GameScene)throw new InvalidOperationException($"Dream did not hand off: {scene?.Timeline.Phase}, {scene?.actor}, steering {scene?.steering}");return;}
            if(scene==null)throw new InvalidOperationException("Expected dream scene");
            switch(args[1]) {
                case "PHASE":
                    if(scene.Timeline.Phase.ToString()!=args[2])throw new InvalidOperationException("Unexpected dream phase "+scene.Timeline.Phase);
                    break;
                case "HELD":
                    string checkpoint=TrinsicSession.DreamCheckpoint();
                    if(scene.nativeCheckpoint!=null && scene.nativeCheckpoint!=checkpoint)throw new InvalidOperationException("Native state advanced during dream");
                    scene.nativeCheckpoint=checkpoint;break;
                case "KEY":
                    scene.OnKeyDown(new SDL.SDL_KeyboardEvent {key=(uint)Enum.Parse<SDL.SDL_Keycode>("SDLK_"+args[2])});break;
                case "KEYUP":
                    scene.OnKeyUp(new SDL.SDL_KeyboardEvent {key=(uint)Enum.Parse<SDL.SDL_Keycode>("SDLK_"+args[2])});break;
                case "PAUSESTART":scene.pausedAt=scene.Timeline.Seconds;break;
                case "PAUSED":
                    if(!scene.Timeline.Paused || scene.Timeline.Seconds!=scene.pausedAt || scene.speech?.State==SoundState.Playing)throw new InvalidOperationException("Dream did not pause");break;
                case "AUDIO":
                    if(scene.speech==null || scene.speech.State.ToString()!=args[2])throw new InvalidOperationException("Unexpected dream audio state "+scene.speech?.State);break;
                case "MUTED":
                    if(scene.speech?.Volume!=0 || string.IsNullOrEmpty(scene.Timeline.Caption))throw new InvalidOperationException("Muted speech/captions did not follow preferences");break;
                case "SILENT":
                    if(scene.speech!=null || string.IsNullOrEmpty(scene.Timeline.Caption))throw new InvalidOperationException("Missing-audio fallback failed");break;
                case "PORTAL":
                    var point=Project(Portal);Mouse.Position=new Point(scene.originX+(int)(point.X*scene.scale),scene.originY+(int)(point.Y*scene.scale));
                    scene.replayPointer=Mouse.Position;
                    scene.OnMouseDown(MouseButtonType.Right);break;
                default:throw new InvalidOperationException("Unknown dream replay operation");
            }
        }
        public override void Unload()
        {
            arrows=0;steering=false;speech?.Stop();speech?.Dispose();voice?.Dispose();relief?.Dispose();caption?.Destroy();hint?.Destroy();
            base.Unload();
        }
    }
}
