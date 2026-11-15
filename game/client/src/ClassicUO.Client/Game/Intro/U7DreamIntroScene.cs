// SPDX-License-Identifier: BSD-2-Clause
using System;
using System.IO;
using System.Linq;
using System.Collections.Generic;
using ClassicUO.Assets;
using ClassicUO.Configuration;
using ClassicUO.Game.Data;
using ClassicUO.Game.GameObjects;
using ClassicUO.Game.Map;
using ClassicUO.Game.Scenes;
using ClassicUO.Game.Managers;
using ClassicUO.Input;
using ClassicUO.Renderer;
using Microsoft.Xna.Framework;
using Microsoft.Xna.Framework.Audio;
using Microsoft.Xna.Framework.Graphics;
using SDL3;

namespace ClassicUO.Game.Intro
{
    // A real GameScene and independent client World. Native U7 remains behind BEGIN.
    internal sealed class U7DreamIntroScene : GameScene
    {
        private static U7DreamIntroScene current;
        internal static bool Active => current != null;
        internal static bool Owns(World w) => current?.room == w;
        internal static bool CanWalk => current != null && !current.Timeline.Paused && current.Timeline.Phase == DreamPhase.Portal;
        private readonly World nativeWorld, room;
        private readonly Action begin;
        private readonly U7IntroData data;
        internal readonly U7IntroTimeline Timeline;
        private Texture2D relief, blueStatic;
        private SoundEffect voice;
        private SoundEffectInstance speech;
        private RenderedText caption, hint;
        private string captionText, hintText, nativeCheckpoint;
        private long lastTick;
        private bool handedOff, voiceStarted, manuallyPaused, awakened;
        private double visualSeconds, pausedVisualAt, pausedAt;
        private Item portal, bed;
        private Point? replayDestination;
        private readonly Queue<Point> replayRoute=new();
        private Point replayStart;
        private bool sawWalk, sawRun;
        private const int Origin=64;
        // The bed is anchored at its southeast end; its visible mattress is
        // centered over the 10-by-10 platform at this tile, not at tile (5,5).
        private static readonly Point BedTile=new(Origin+6,Origin+6);
        private static readonly Point WakeTile=BedTile+new Point(1,1);
        internal static readonly Point PortalTile=new(Origin+1,Origin+5);
        private const int BlueWidth=320, BlueHeight=200, BlueColumns=13, BlueFrames=78;
        private int BlueFrame=>(int)(visualSeconds*20)%BlueFrames;

        internal static bool TryCreate(World world,Action begin,out U7DreamIntroScene scene)
        {
            scene=null;
            string folder=Environment.GetEnvironmentVariable("TRINSIC_INTRO_ASSETS");
            if(string.IsNullOrEmpty(folder) || Environment.GetEnvironmentVariable("TRINSIC_READY")==null)return false;
            try {scene=new U7DreamIntroScene(world,new World(),folder,begin);return true;}
            catch(Exception ex) when(ex is IOException || ex is ArgumentException || ex is InvalidOperationException || ex is System.Text.Json.JsonException)
            { current=null;Console.Error.WriteLine("Dream room unavailable: "+ex.Message);return false; }
        }
        private U7DreamIntroScene(World native,World room,string folder,Action begin):base(room)
        {
            nativeWorld=native;this.room=room;this.begin=begin;
            data=U7IntroData.Read(Path.Combine(folder,"intro.json"));Timeline=new U7IntroTimeline(data);
            try {
                using(var stream=File.OpenRead(Path.Combine(folder,"guardian.png")))relief=Texture2D.FromStream(Client.Game.GraphicsDevice,stream);
                using(var stream=File.OpenRead(Path.Combine(folder,"blue-static.png")))blueStatic=Texture2D.FromStream(Client.Game.GraphicsDevice,stream);
                if(relief.Width!=data.Width*5 || relief.Height!=data.Height*3 || blueStatic.Width!=BlueWidth*BlueColumns || blueStatic.Height!=BlueHeight*6)
                    throw new InvalidDataException("Invalid dream artwork atlas");
                try {
                    using var stream=File.OpenRead(Path.Combine(folder,"guardian.wav"));
                    voice=SoundEffect.FromStream(stream);speech=voice.CreateInstance();
                    var profile=ProfileManager.CurrentProfile;
                    speech.Volume=profile.TrinsicSpeechEnabled?Math.Clamp(profile.TrinsicSpeechVolume/100f,0,1):0;
                } catch(Exception ex) {Console.Error.WriteLine("Dream voice unavailable; captions remain active: "+ex.Message);}
                current=this;
                Chunk.ClearPool();
                room.CreatePlayer(0x7ffe);
                room.Player.Graphic=native.Player.Graphic;room.Player.Hue=native.Player.Hue;room.Player.Name=native.Player.Name;
                room.Player.IsFemale=native.Player.IsFemale;
                room.Player.Stamina=room.Player.StaminaMax=30;
                room.Player.Hits=room.Player.HitsMax=30;
                room.MapIndex=0;
                room.Player.SetInWorldTile((ushort)BedTile.X,(ushort)BedTile.Y,4);
                room.Player.Direction=(Direction)7;
                uint serial=0x7ffe0100;
                // Keep the actual Avatar's body, skin and hair, without copying combat gear.
                foreach(var layer in new[]{Layer.Hair,Layer.Beard}) {
                    var source=native.Player.FindItemByLayer(layer);if(source==null)continue;
                    var item=Item.Create(room,serial++);item.Graphic=source.Graphic;item.Hue=source.Hue;
                    item.Layer=layer;item.Container=room.Player.Serial;item.Amount=1;
                    room.Items.Add(item);room.Player.PushToBack(item);
                }
                void Clothes(ushort graphic,ushort hue,Layer layer) {
                    var item=Item.Create(room,serial++);item.Graphic=graphic;item.Hue=hue;
                    item.Layer=layer;item.Container=room.Player.Serial;item.Amount=1;
                    room.Items.Add(item);room.Player.PushToBack(item);
                }
                Clothes(0x1517,0,Layer.Shirt);Clothes(0x1539,0x0386,Layer.Pants);
                bed=Item.Create(room,0x7ffe0003);
                bed.Graphic=TrinsicTown.Graphic(696,0,0,0,0,true);bed.Amount=1;bed.Name="Bed";
                if(bed.Graphic==0)throw new InvalidDataException("The approved town bed is unavailable");
                room.Items.Add(bed);bed.SetInWorldTile((ushort)BedTile.X,(ushort)BedTile.Y,0);
                room.Player.NativeLyingDown=true;
                room.Player.NativeBedAnchor=BedTile;
                room.Player.NativeBedAcrossX=true;
                room.Player.NativeRestOffset=new Point(-5,-17);
                room.Player.SetAnimation(21,frameCount:byte.MaxValue,fromServer:true);room.Player.ExecuteAnimation=false;
                var vision=new VisionItem(this) {Serial=0x7ffe0001,Graphic=0x1b,Name="Guardian",Amount=1};
                room.Items.Add(vision);vision.SetInWorldTile(Origin,Origin,0);
            } catch {current=null;speech?.Dispose();voice?.Dispose();relief?.Dispose();blueStatic?.Dispose();room.Clear();Chunk.ClearPool();throw;}
        }
        internal static bool PopulateChunk(World world,Chunk chunk)
        {
            if(!Owns(world))return false;
            // Black void outside the room. Normal Static surfaces supply the walkable floor.
            for(int y=0;y<8;y++)for(int x=0;x<8;x++) {
                ushort wx=(ushort)(chunk.X*8+x),wy=(ushort)(chunk.Y*8+y);
                var land=Land.Create(world,2);land.AllowedToDraw=false;land.X=wx;land.Y=wy;land.Z=0;land.UpdateScreenPosition();chunk.AddGameObject(land,x,y);
                void Add(ushort graphic,sbyte z,bool visible=true) {
                    var tile=Static.Create(world,graphic,0,y*8+x);tile.AllowedToDraw=visible;tile.X=wx;tile.Y=wy;tile.Z=z;tile.UpdateScreenPosition();chunk.AddGameObject(tile,x,y);
                }
                int rx=wx-Origin,ry=wy-Origin;
                if(rx>=1 && rx<=10 && ry>=1 && ry<=10)Add(0x519,0);
                // The approved bed is one whole sprite; these invisible stock
                // collision tiles cover its two-tile length, without extra bed art.
                if((wx==BedTile.X-1 || wx==BedTile.X) && wy==BedTile.Y)Add(0xa63,0,false);
            }
            return true;
        }
        public override void Load()
        {
            base.Load();lastTick=Environment.TickCount64;
            Camera.Zoom=1;UpdateDrawPosition=true;
            Console.WriteLine("DREAM WORLD START: normal GameScene, native BEGIN held");
        }
        private void Wake()
        {
            if(awakened)return;awakened=true;
            room.Player.NativeLyingDown=false;room.Player.NativeBedAnchor=null;room.Player.NativeRestOffset=Point.Zero;
            room.Player.ExecuteAnimation=true;room.Player.SetAnimation(0xff);
            room.Player.ClearSteps();room.Player.Walker.Reset();room.Player.SetInWorldTile((ushort)WakeTile.X,(ushort)WakeTile.Y,0);
            UpdateDrawPosition=true;
        }
        public override void Update()
        {
            long now=Environment.TickCount64;double dt=Math.Max((now-lastTick)/1000.0,0);lastTick=now;
            bool pause=manuallyPaused || (!Client.Game.IsActive && !TrinsicReplay.Active);
            if(Timeline.Paused && !pause)dt=0;
            Timeline.Paused=pause;
            if(pause) {ClearDreamInput();room.Player.ClearSteps();room.Player.Walker.Reset();if(speech?.State==SoundState.Playing)speech.Pause();}
            else if(speech?.State==SoundState.Paused)speech.Resume();
            var previous=Timeline.Phase;Timeline.Advance(dt);
            if(!pause)visualSeconds+=dt;
            if(Timeline.Phase==DreamPhase.Speech && !voiceStarted){voiceStarted=true;speech?.Play();}
            if(previous==DreamPhase.Speech && Timeline.Phase!=DreamPhase.Speech)speech?.Stop();
            if(Timeline.Phase>=DreamPhase.Wake)Wake();
            if(Timeline.Phase==DreamPhase.Portal && portal==null) {
                portal=Item.Create(room,0x7ffe0002);portal.Graphic=0xdda;portal.Amount=1;portal.Name="Red moongate";
                room.Items.Add(portal);portal.SetInWorldTile((ushort)PortalTile.X,(ushort)PortalTile.Y,0);
            }
            if(TrinsicReplay.Active && replayDestination is Point target && CanWalk) {
                // Aim the ordinary right-button movement control; never set player coordinates.
                Point centre=new(Camera.Bounds.Center.X,Camera.Bounds.Center.Y);
                int px=room.Player.X,py=room.Player.Y;
                if(room.Player.Steps.Count>0) {px=room.Player.Steps.Back().X;py=room.Player.Steps.Back().Y;}
                int dx=target.X-px,dy=target.Y-py;
                if(dx==0 && dy==0) {
                    ClearDreamInput();
                    if(room.Player.Steps.Count==0)replayDestination=replayRoute.Count>0?replayRoute.Dequeue():null;
                } else {
                    BeginDreamMouse();
                    Mouse.Position=centre+new Point((dx-dy)*44,(dx+dy)*44);
                }
            }
            room.RangeSize=new Point(room.Player.X,room.Player.Y);
            base.Update();
            sawWalk |= room.Player.Steps.Count>0 && !room.Player.IsRunning;
            sawRun |= room.Player.Steps.Count>0 && room.Player.IsRunning;
            if(CanWalk && room.Player.X==PortalTile.X && room.Player.Y==PortalTile.Y) {
                ClearDreamInput();room.Player.ClearSteps();room.Player.Walker.Reset();replayDestination=null;Timeline.EnterPortal();
                Console.WriteLine("DREAM PORTAL: player walked onto gate tile");
            }
            if(previous!=Timeline.Phase)Console.WriteLine("DREAM "+Timeline.Phase);
            if(Timeline.Phase==DreamPhase.Complete){Handoff();return;}
            if(TrinsicReplay.Active)TrinsicReplay.Next(nativeWorld,null,null);
        }
        private void Handoff()
        {
            if(handedOff)return;handedOff=true;ClearDreamInput();speech?.Stop();
            Console.WriteLine("DREAM COMPLETE: releasing original native BEGIN");begin();
        }
        // World objects above are drawn by GameScene.Draw/RenderLists. Only captions are UI.
        public override void DrawUI(UltimaBatcher2D batcher)
        {
            base.DrawUI(batcher);
            string text=Timeline.Caption;
            if(captionText!=text){caption?.Destroy();captionText=text;caption=Text(text,440);}
            if(caption?.HasContent==true)caption.Draw(batcher,Camera.Bounds.Center.X-caption.Width/2,Camera.Bounds.Y+26,0);
            string controls=Timeline.Paused?"Paused - Space to resume":Timeline.Phase==DreamPhase.Portal?
                "Walk into the red moongate. Hold right mouse or use arrow keys.":"Space to pause   |   Esc to wake";
            if(hintText!=controls){hint?.Destroy();hintText=controls;hint=Text(controls,680);}
            hint.Draw(batcher,Camera.Bounds.Center.X-hint.Width/2,Camera.Bounds.Bottom-32-hint.Height,0);
        }
        private static RenderedText Text(string text,int width)=>RenderedText.Create(text,0x3b2,3,true,FontStyle.BlackBorder,TEXT_ALIGN_TYPE.TS_CENTER,width);
        internal override void OnKeyDown(SDL.SDL_KeyboardEvent e)
        {
            if(e.key==(uint)SDL.SDL_Keycode.SDLK_SPACE && !e.repeat){manuallyPaused=!manuallyPaused;return;}
            if(e.key==(uint)SDL.SDL_Keycode.SDLK_ESCAPE){manuallyPaused=false;speech?.Stop();Timeline.Skip();ClearDreamInput();return;}
            if(CanWalk && e.key is (uint)SDL.SDL_Keycode.SDLK_LEFT or (uint)SDL.SDL_Keycode.SDLK_RIGHT or (uint)SDL.SDL_Keycode.SDLK_UP or (uint)SDL.SDL_Keycode.SDLK_DOWN)base.OnKeyDown(e);
        }
        internal override void OnKeyUp(SDL.SDL_KeyboardEvent e)
        {
            if(e.key is (uint)SDL.SDL_Keycode.SDLK_LEFT or (uint)SDL.SDL_Keycode.SDLK_RIGHT or (uint)SDL.SDL_Keycode.SDLK_UP or (uint)SDL.SDL_Keycode.SDLK_DOWN)base.OnKeyUp(e);
        }
        internal override bool OnMouseDown(MouseButtonType button)=>button==MouseButtonType.Right && CanWalk?base.OnMouseDown(button):true;
        internal override bool OnMouseUp(MouseButtonType button)=>button==MouseButtonType.Right?base.OnMouseUp(button):true;
        internal override bool OnMouseDoubleClick(MouseButtonType button)=>true;
        internal override bool OnMouseDragging()=>true;
        internal override void OnTextInput(string text) { }
        public override void Unload()
        {
            ClearDreamInput();speech?.Stop();speech?.Dispose();voice?.Dispose();relief?.Dispose();blueStatic?.Dispose();caption?.Destroy();hint?.Destroy();
            base.Unload();current=null;
        }
        private sealed class VisionItem : Item
        {
            private readonly U7DreamIntroScene scene;
            internal VisionItem(U7DreamIntroScene scene):base(scene.room){this.scene=scene;}
            public override bool Draw(UltimaBatcher2D batcher,int x,int y,float depth)
            {
                int phase=scene.BlueFrame;
                // A viewport-filling backdrop in the world render target. The floor,
                // bed, player and portal retain their ordinary world depth in front.
                var topLeft=scene.Camera.ScreenToWorld(Point.Zero);
                var bottomRight=scene.Camera.ScreenToWorld(new Point(scene.Camera.Bounds.Width,scene.Camera.Bounds.Height));
                batcher.Draw(scene.blueStatic,new Vector2(topLeft.X-1,topLeft.Y-1),
                    new Rectangle(phase%BlueColumns*BlueWidth,phase/BlueColumns*BlueHeight,BlueWidth,BlueHeight),
                    new Vector3(0,0,1),0,Vector2.Zero,
                    new Vector2((bottomRight.X-topLeft.X+2f)/BlueWidth,(bottomRight.Y-topLeft.Y+2f)/BlueHeight),SpriteEffects.None,0);
                float alpha=scene.Timeline.FaceAlpha;if(alpha<=0)return true;
                void Layer(Texture2D texture,Rectangle source,int dx,int dy,float bias) {
                    for(int col=0;col<source.Width;col++) {
                        float bay=Math.Max(0,(int)Math.Ceiling((-dx-col)/22f));
                        batcher.Draw(texture,new Vector2(x+22+dx+col,y+22+dy),
                            new Rectangle(source.X+col,source.Y,1,source.Height),new Vector3(0,0,alpha),0,
                            Vector2.Zero,Vector2.One,SpriteEffects.None,depth+bay+1f+bias);
                    }
                }
                // Left of the far corner, at the user's marked position: the
                // three-quarter face looks diagonally toward the centered bed.
                Layer(scene.relief,new Rectangle(scene.Timeline.Mouth*scene.data.Width,scene.Timeline.Eyes*scene.data.Height,scene.data.Width,scene.data.Height),-scene.data.Width/2-148,-42,.1f);
                return true;
            }
            public override bool CheckMouseSelection()=>false;
        }
        internal static void Replay(string[] args)
        {
            if(!TrinsicReplay.Active)throw new InvalidOperationException("Replay is disabled");
            if(Client.Game.Scene is U7CharacterCreationScene creation){creation.Replay(args);return;}
            var scene=Client.Game.Scene as U7DreamIntroScene;
            if(args[1]=="DIALOGUECENTER") {
                var dialog=UIManager.Gumps.Single(g=>!g.IsDisposed && g.GetType().Name=="TrinsicDialogue");
                var bounds=Client.Game.ClientBounds;
                if(Math.Abs(dialog.X+dialog.Width/2-bounds.Width/2)>1 || Math.Abs(dialog.Y+dialog.Height/2-bounds.Height/2)>1)
                    throw new InvalidOperationException($"Dialogue is not centered: {dialog.Bounds} in {bounds}");
                return;
            }
            if(args[1]=="IDENTITY") {
                var native=Client.Game.UO.World.Player;
                bool female=args[3]=="1";
                string expected=System.Text.CodePagesEncodingProvider.Instance.GetEncoding(437).GetString(Convert.FromHexString(args[2]));
                if(native.Name!=expected || native.IsFemale!=female || native.Graphic!=(female?0x191:0x190))
                    throw new InvalidOperationException($"Wrong native identity: {native.Name}/{native.Graphic:x}");
                if(scene!=null && (scene.room.Player.Name!=native.Name || scene.room.Player.Graphic!=native.Graphic))
                    throw new InvalidOperationException("Dream identity differs from native Avatar");
                return;
            }
            if(args[1]=="GAME"){if(scene!=null || Client.Game.Scene is not GameScene)throw new InvalidOperationException($"Dream did not hand off at {scene?.room.Player.X-Origin},{scene?.room.Player.Y-Origin}, phase {scene?.Timeline.Phase}");return;}
            if(scene==null)throw new InvalidOperationException("Expected dream world scene");
            switch(args[1]) {
                case "APPEARANCE":
                    var player=scene.room.Player;var native=scene.nativeWorld.Player;
                    if(player.Graphic!=native.Graphic || player.Hue!=native.Hue || player.IsFemale!=native.IsFemale)
                        throw new InvalidOperationException("Dream Avatar identity differs from the game");
                    var hair=player.FindItemByLayer(Layer.Hair);var nativeHair=native.FindItemByLayer(Layer.Hair);
                    if(hair==null || nativeHair==null || hair.Graphic!=nativeHair.Graphic || hair.Hue!=nativeHair.Hue)
                        throw new InvalidOperationException("Dream hair differs from the game");
                    for(int layer=1;layer<=27;layer++)
                        if((Layer)layer is not (Layer.Hair or Layer.Beard or Layer.Shirt or Layer.Pants) && player.FindItemByLayer((Layer)layer)!=null)
                            throw new InvalidOperationException("Combat equipment leaked into the dream");
                    if(player.NativeLyingDown!=!scene.awakened || player.NativeBedAnchor.HasValue!=!scene.awakened)
                        throw new InvalidOperationException("Dream sleeping pose did not reset on waking");
                    if(!scene.awakened) {
                        var restOrigin=player.RealScreenPosition+new Point(22,19)+player.NativeRestDrawOffset;
                        var restBounds=new Rectangle(restOrigin.X-player.FrameInfo.X,restOrigin.Y-player.FrameInfo.Y,player.FrameInfo.Width,player.FrameInfo.Height);
                        var uv=Client.Game.UO.Arts.GetArt(scene.bed.Graphic).UV;
                        var bedBounds=new Rectangle(scene.bed.RealScreenPosition.X+22-uv.Width/2,scene.bed.RealScreenPosition.Y+44-uv.Height,uv.Width,uv.Height);
                        if(!bedBounds.Contains(restBounds.Center))throw new InvalidOperationException($"Sleeper misses bed: {restBounds} / {bedBounds}");
                        Console.WriteLine($"DREAM BED: {scene.bed.Graphic:x}, body {restBounds}, bed {bedBounds}, hair {hair.Graphic:x}/{hair.Hue:x}");
                    }
                    break;
                case "PHASE":if(scene.Timeline.Phase.ToString()!=args[2])throw new InvalidOperationException("Unexpected dream phase "+scene.Timeline.Phase);break;
                case "WORLD":Console.WriteLine($"DREAM WORLD: body={scene.room.Player.Graphic:x}, pos={scene.room.Player.X-Origin},{scene.room.Player.Y-Origin}, objects={scene.room.Items.Count}");if(scene.room==scene.nativeWorld || scene.RenderedObjectsCount<30)throw new InvalidOperationException("Room was not rendered by GameScene");break;
                case "COLLISION":
                    foreach(var start in new[]{new Point(Origin+1,Origin+7),BedTile+new Point(1,0)}) {
                        int x=start.X,y=start.Y;sbyte z=0;Direction direction=Direction.West;
                        if(scene.room.Player.Pathfinder.CanWalk(ref direction,ref x,ref y,ref z))throw new InvalidOperationException("Void or bed allowed walking");
                    }break;
                case "RAN":if(!scene.sawRun)throw new InvalidOperationException("Mouse-distance running did not occur");break;
                case "STILL":if(scene.replayStart!=new Point(scene.room.Player.X,scene.room.Player.Y))throw new InvalidOperationException("Player moved while paused");break;
                case "HELD":string state=TrinsicSession.DreamCheckpoint();if(scene.nativeCheckpoint!=null && scene.nativeCheckpoint!=state)throw new InvalidOperationException("Native state advanced during dream");scene.nativeCheckpoint=state;break;
                case "KEY":scene.OnKeyDown(new SDL.SDL_KeyboardEvent{key=(uint)Enum.Parse<SDL.SDL_Keycode>("SDLK_"+args[2])});break;
                case "KEYUP":scene.OnKeyUp(new SDL.SDL_KeyboardEvent{key=(uint)Enum.Parse<SDL.SDL_Keycode>("SDLK_"+args[2])});break;
                case "PAUSESTART":scene.pausedAt=scene.Timeline.Seconds;scene.pausedVisualAt=scene.visualSeconds;break;
                case "PAUSED":if(!scene.Timeline.Paused || scene.Timeline.Seconds!=scene.pausedAt || scene.visualSeconds!=scene.pausedVisualAt || scene.speech?.State==SoundState.Playing)throw new InvalidOperationException("Dream did not pause");break;
                case "AUDIO":if(scene.speech==null || scene.speech.State.ToString()!=args[2])throw new InvalidOperationException("Unexpected audio state");break;
                case "MUTED":if(scene.speech?.Volume!=0 || string.IsNullOrEmpty(scene.Timeline.Caption))throw new InvalidOperationException("Muted speech/captions failed");break;
                case "SILENT":if(scene.speech!=null || string.IsNullOrEmpty(scene.Timeline.Caption))throw new InvalidOperationException("Missing-audio fallback failed");break;
                case "PORTAL":
                    scene.replayRoute.Clear();scene.replayDestination=new Point(Origin+5,Origin+7);
                    scene.replayRoute.Enqueue(new Point(Origin+1,Origin+7));scene.replayRoute.Enqueue(PortalTile);break;
                case "MOVE":scene.replayDestination=new Point(Origin+int.Parse(args[2]),Origin+int.Parse(args[3]));scene.BeginDreamMouse();break;
                case "STOP":scene.replayDestination=null;scene.ClearDreamInput();break;
                case "POSITION":if(scene.room.Player.X!=Origin+int.Parse(args[2]) || scene.room.Player.Y!=Origin+int.Parse(args[3]))throw new InvalidOperationException($"Position {scene.room.Player.X-Origin},{scene.room.Player.Y-Origin}");break;
                case "RECORDPOS":scene.replayStart=new Point(scene.room.Player.X,scene.room.Player.Y);break;
                case "MOVED":if(scene.replayStart==new Point(scene.room.Player.X,scene.room.Player.Y) || !scene.sawWalk && !scene.sawRun)throw new InvalidOperationException("Normal movement did not occur");break;
                default:throw new InvalidOperationException("Unknown dream replay operation");
            }
        }
    }
}
