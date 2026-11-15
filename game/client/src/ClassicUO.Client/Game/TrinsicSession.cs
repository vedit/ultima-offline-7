// SPDX-License-Identifier: BSD-2-Clause
using System;
using System.Collections.Generic;
using System.IO;
using System.IO.Pipes;
using System.Linq;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using ClassicUO.Configuration;
using ClassicUO.Game.Data;
using ClassicUO.Game.GameObjects;
using ClassicUO.Game.Managers;
using ClassicUO.Game.Scenes;
using ClassicUO.Game.UI.Controls;
using ClassicUO.Game.UI.Gumps;
using Microsoft.Xna.Framework;
using SDL3;
using ClassicUO.Input;
using ClassicUO.Renderer;
using Microsoft.Xna.Framework.Graphics;

namespace ClassicUO.Game
{
    internal static class TrinsicSession
    {
        private static readonly string pipeName = Environment.GetEnvironmentVariable("TRINSIC_PIPE");
        public static bool Enabled => !string.IsNullOrEmpty(pipeName);
        private static NamedPipeClientStream pipe;
        private static int generation, last, chest, prompt;
        private static ulong lastBark;
        private static ulong lastRefusal;
        private static readonly Encoding gameTextEncoding = CodePagesEncodingProvider.Instance.GetEncoding(437);
        private static long nextPoll, nextWalk;
        private static string previousWords="";
        private static readonly HashSet<uint> draggable = new();
        private static HashSet<uint> visible = new();
        internal static bool Overlay;
        internal static string Header { get; private set; }
        internal static string LastCommand { get; private set; }
        internal static void Close()
        {
            TrinsicDebug.Close();
            TrinsicAudio.Close();
            TrinsicEffects.Clear();
            observationTimeout?.Cancel(); observationTimeout?.Dispose(); observationTimeout=null;
            pipe?.Dispose(); pipe=null; observation=null; walkingCommand=null; heldArrows=0; pending.Clear();
            if(targetPrompt!=0) world.TargetManager.Reset();
            targetPrompt=prompt=0;
        }
        internal static void Reconnect() { TrinsicDebug.Disconnected();if(FinishObservation()) Apply(Connect(true)); }
        internal static void Duplicate() { Apply(Read(LastCommand)); }
        internal static void Stale() { Apply(Read("1 0 USE 824")); }
        internal static bool InventoryVisible => UIManager.GetGump<PaperDollGump>(world.Player.Serial)!=null;
        private static uint backpack;
        private static readonly HashSet<uint> partyMembers = new();
        private static readonly HashSet<uint> partyBackpacks = new();
        internal static Mobile[] RosterMembers => world == null ? Array.Empty<Mobile>() :
            partyMembers.Append(world.Player.Serial).Distinct().OrderBy(id => id == world.Player.Serial ? 0 : 1).ThenBy(id => id)
                .Select(id => world.Mobiles.Get(id)).Where(m => m != null && !m.IsDestroyed).ToArray();
        internal static void ShowPartyRoster()
        {
            var roster = UIManager.GetGump<TrinsicPartyGump>();
            if (roster == null) UIManager.Add(new TrinsicPartyGump(world));
            else UIManager.MakeTopMostGump(roster);
        }
        private static int targetPrompt;
        private static readonly HashSet<uint> usable = new();
        private static readonly Dictionary<uint,(uint owner,Point position)> placements=new();
        internal static bool ActivateItem(uint serial)
        {
            if(serial==TrinsicDebug.WandSerial){TrinsicDebug.Open(world);return true;}
            var item=world.Items.Get(serial);
            if(item==null) return false;
            if(usable.Contains(serial)){Send("USE",(int)(serial & 0x1fffffff));return true;}
            if(!CanDrag(serial)) return false;
            if(item.Graphic==0x14eb) ShowMap();
            else if(item.ItemData.IsWearable && item.Container!=world.Player.Serial)
                Send("EQUIP",(int)(serial & 0x1fffffff),(int)world.Player.Serial);
            else Send("LOOK",(int)(serial & 0x1fffffff));
            return true;
        }
        internal static void ShowPaperdoll(uint serial=0)
        {
            if(serial==0) serial=world.Player.Serial;
            if(serial!=world.Player.Serial && !partyMembers.Contains(serial)) return;
            var sheet=UIManager.GetGump<PaperDollGump>(serial);
            if(sheet==null) {
                sheet=new PaperDollGump(world,serial,partyMembers.Contains(serial)){X=Math.Max(0,Client.Game.ClientBounds.Width-(serial==world.Player.Serial?267:540)),Y=12};
                UIManager.Add(sheet);
                sheet.RequestUpdateContents();
            } else { sheet.IsMinimized=false; UIManager.MakeTopMostGump(sheet); }
        }
        internal static void ShowBackpack(uint serial=0)
        {
            if(serial==0) serial=backpack;
            if(serial==0) return;
            var pack=UIManager.GetGump<ContainerGump>(serial);
            if(pack==null) {
                pack=new ContainerGump(world,serial,0x3c,false){X=Math.Max(0,Client.Game.ClientBounds.Width-(serial==backpack?258:531)),Y=350};
                UIManager.Add(pack); pack.RequestUpdateContents();
            } else { pack.IsMinimized=false; UIManager.MakeTopMostGump(pack); }
        }
        internal static void ShowMap()
        {
            var map=UIManager.GetGump<MiniMapGump>();
            if(map==null) UIManager.Add(new MiniMapGump(world){X=16,Y=16});
            else UIManager.MakeTopMostGump(map);
        }
        internal static bool OpenPlayerWindow(uint serial)
        {
            if(targetPrompt!=0) {Send("TARGET",targetPrompt,(int)(serial & 0x1fffffff));return true;}
            bool requestedPaperdoll=(serial&0x80000000)!=0;
            serial &= 0x7fffffff;
            if(serial==world.Player.Serial) { ShowPaperdoll(); return true; }
            if(partyMembers.Contains(serial)) {
                ShowPaperdoll(serial);
                return requestedPaperdoll;
            }
            if(partyBackpacks.Contains(serial) || (backpack!=0 && serial==backpack)) { ShowBackpack(serial); return true; }
            return false;
        }
        internal static int CameraX,CameraY;
        internal static bool CameraOnly { get; private set; }
        internal static int IoloX,IoloY;
        private static World world;
        private static ContainerGump chestWindow;
        private static Gump inventoryWindow;
        private static Task<string> observation;
        private static CancellationTokenSource observationTimeout;
        private static bool connectionFault;
        private static string lastInteraction="startup";
        private static string health="";
        private static long lastBlockedNotice;
        private static string walkingCommand;
        private static bool runningCommand;
        private static int heldArrows;
        private static int Arrow(SDL.SDL_Keycode key) => key switch {
            SDL.SDL_Keycode.SDLK_UP=>1, SDL.SDL_Keycode.SDLK_RIGHT=>2,
            SDL.SDL_Keycode.SDLK_DOWN=>4, SDL.SDL_Keycode.SDLK_LEFT=>8, _=>0 };
        internal static void ReleaseArrow(SDL.SDL_Keycode key)
        {
            heldArrows &= ~Arrow(key);
        }
        private static void WalkHeld()
        {
            int x=((heldArrows>>1)&1)-((heldArrows>>3)&1);
            int y=((heldArrows>>2)&1)-(heldArrows&1);
            if(x!=0 || y!=0) Walk((Direction)(y<0 ? (x<0?7:x>0?1:0) : y>0 ? (x<0?5:x>0?3:4) : x>0?2:6));
        }
        private static readonly Queue<(string op,int a,int b,string extra,int gen,Point? click)> pending=new();
        private static Gump dialog;
        private static bool capture = Environment.GetEnvironmentVariable("TRINSIC_CAPTURE") != null;
        private static int updates;
        private const uint ItemBase = 0x40000000;

        private static async Task<string> Exchange(string command, CancellationToken cancel)
        {
            var stream=pipe;
            await stream.WriteAsync(Encoding.ASCII.GetBytes(command),cancel).ConfigureAwait(false);
            using var message=new MemoryStream();
            byte[] buffer=new byte[65536];
            do
            {
                int count=await stream.ReadAsync(buffer.AsMemory(),cancel).ConfigureAwait(false);
                if(count==0) throw new EndOfStreamException();
                message.Write(buffer,0,count);
            } while(!stream.IsMessageComplete);
            return Encoding.ASCII.GetString(message.ToArray());
        }
        private static string Read(string command, int timeoutSeconds=2)
        {
            using var timeout=new CancellationTokenSource(TimeSpan.FromSeconds(timeoutSeconds));
            return Exchange(command,timeout.Token).GetAwaiter().GetResult();
        }
        private static string Connect(bool waitForDisconnect=false)
        {
            pipe?.Dispose();
            pipe = new NamedPipeClientStream(".", pipeName, PipeDirection.InOut, PipeOptions.Asynchronous);
            // An explicit reconnect must let the native poll observe the old pipe closing.
            // Automatic retries stay short so a missing host does not block the UI.
            pipe.Connect(world?.Player == null ? 120000 : waitForDisconnect ? 2000 : 50);
            pipe.ReadMode = PipeTransmissionMode.Message;
            string frame = Read("0 0 SYNC");
            if (world?.Player != null) TrinsicReplay.Record("RECONNECTED", frame);
            return frame;
        }
        public static void Start(World target)
        {
            TrinsicDebug.Close();
            world = target;
            TrinsicEffects.Start(world);
            lastBark = 0;
            TrinsicTown.Load();
            string data = Connect();
            ProfileManager.Load("Trinsic", "Local", "Avatar");
            var profile = ProfileManager.CurrentProfile;
            if(TrinsicTown.Enabled && !profile.TrinsicTransparencyInitialized) {
                profile.UseCircleOfTransparency=true;
                profile.CircleOfTransparencyType=1;
                profile.TrinsicTransparencyInitialized=true;
                profile.EnableMousewheelScaleZoom=true;
            }
            profile.GameWindowSize = new Point(920, 640);
            if(TrinsicTown.Enabled && Settings.GlobalSettings.WindowSize is Point requested) {
                var handle=Client.Game.Window.Handle;
                if(SDL.SDL_GetDisplayUsableBounds(SDL.SDL_GetDisplayForWindow(handle),out var work)) {
                    SDL.SDL_GetWindowBordersSize(handle,out int top,out int left,out int bottom,out int right);
                    requested.X=Math.Min(requested.X,work.w-left-right);
                    requested.Y=Math.Min(requested.Y,work.h-top-bottom);
                }
                Settings.GlobalSettings.WindowSize=requested;
                float dpi=Client.Game.DpiScale;
                profile.GameWindowPosition=new Point(8,8);
                profile.GameWindowSize=new Point(Math.Max(640,(int)(requested.X/dpi)-284),
                                                 Math.Max(480,(int)(requested.Y/dpi)-24));
            }
            profile.TopbarGumpIsDisabled = true;
            profile.HideScreenshotStoredInMessage = true;
            if(TrinsicTown.Enabled) profile.DoubleClickToLootInsideContainers=false;
            if(float.TryParse(Environment.GetEnvironmentVariable("TRINSIC_ZOOM"), System.Globalization.CultureInfo.InvariantCulture, out float zoom)) profile.DefaultScale = zoom;
            int[] avatar = Rows(data).First(r => r[7] == 0);
            world.CreatePlayer((uint)avatar[0]);
            world.MapIndex = 0;
            Apply(data);
            if(Environment.GetEnvironmentVariable("TRINSIC_INTRO_ASSETS")!=null && data.Contains("\nNEWCHAR 1\n")) {
                Client.Game.SetScene(new Intro.U7CharacterCreationScene(world,BeginCreatedCharacter));
                return;
            }
            StartOpening(data);
        }
        private static void StartOpening(string data)
        {
            if(Intro.U7DreamIntroScene.TryCreate(world,()=>BeginAfterDream(data),out var dream)) {
                Client.Game.SetScene(dream);
                return;
            }
            BeginPresentation(data,false);
        }
        internal static async Task<string> CreateCharacterAsync(string encoded,bool female,CancellationToken cancel)
        {
            using var timeout=CancellationTokenSource.CreateLinkedTokenSource(cancel);
            timeout.CancelAfter(TimeSpan.FromSeconds(5));
            string command=$"{last+1} {generation} CREATEAVATAR {(female?1:0)} 0 {encoded}";
            string frame=await Exchange(command,timeout.Token).ConfigureAwait(false);
            return frame;
        }
        internal static string CharacterResult(string data) {TrinsicReplay.Record("CREATEAVATAR",data);Apply(data);return data.Split(' ')[5];}
        private static void BeginCreatedCharacter(string data) {heldArrows=0;StartOpening(data);}
        private static void BeginAfterDream(string data)
        {
            heldArrows=0;
            BeginPresentation(data,true);
        }
        internal static string DreamCheckpoint()
        {
            if(Client.Game.Scene is not (Intro.U7DreamIntroScene or Intro.U7CharacterCreationScene)) throw new InvalidOperationException("No active opening");
            return Read("0 0 SYNC");
        }
        private static void BeginPresentation(string data,bool afterDream)
        {
            Client.Game.SetScene(new GameScene(world));
            ShowBarks(data.Split('\n'));
            ShowMap(); ShowPaperdoll(); ShowBackpack();
            if(Environment.GetEnvironmentVariable("TRINSIC_READY")!=null && (afterDream || !TrinsicReplay.Active)) {
                if(TrinsicTown.Enabled) Send("BEGIN",afterDream?1:0);
                else { Overlay=true; GameActions.Print(world,"Iolo is ready. Ctrl+wheel changes zoom. Press F6 to begin."); }
            }
        }
        private static IEnumerable<int[]> Rows(string frame)
        {
            foreach (string line in frame.Split('\n'))
                if (line.StartsWith("E ")) yield return Array.ConvertAll(line.Substring(2).Split(' '), int.Parse);
        }
        public static void Update(World target)
        {
            TrinsicEffects.Update();
            if(TrinsicReplay.Active) TrinsicReplay.ObserveWalk(target.Player);
            if((!Client.Game.IsActive && !TrinsicReplay.Active) || (TrinsicDebug.Typing || TrinsicAudio.Typing)) heldArrows=0;
            try
            {
                if(observation!=null)
                {
                    if(!FinishObservation()) return;
                    if (chest!=0 && (chestWindow?.IsDisposed==true || inventoryWindow?.IsDisposed==true)) Send("CLOSE");
                    if(pending.TryDequeue(out var intent) && intent.gen==generation) Send(intent.op,intent.a,intent.b,intent.extra,intent.click);
                    if (TrinsicReplay.Active) TrinsicReplay.Next(world,chestWindow,dialog);
                    if (capture && ++updates==14) { Client.Game.TakeScreenshot(); capture=false; }
                }
                TrinsicDebug.Update();
                if(observation==null && prompt==0) TrinsicAudio.Update();
                if(TrinsicTown.Compact && heldArrows!=0 && prompt==0 && !(TrinsicDebug.Typing || TrinsicAudio.Typing)) WalkHeld();
                if(observation!=null || Environment.TickCount64<nextPoll) return;
                nextPoll=Environment.TickCount64+110;
                if(pipe==null) Apply(Connect());
                Observe("0 0 SYNC");
            }
            catch (Exception ex) when (ex is IOException || ex is TimeoutException || ex is OperationCanceledException)
            { ConnectionFailure(ex); }
        }
        private static void Observe(string command)
        {
            observationTimeout?.Dispose();
            observationTimeout=new CancellationTokenSource(TimeSpan.FromSeconds(5));
            observation=Exchange(command,observationTimeout.Token);
        }
        private static void ConnectionFailure(Exception error)
        {
            Console.Error.WriteLine($"TRINSIC interaction timeout/error after {lastInteraction}; state={Header}; health={health}; {error.GetType().Name}");
            if(!connectionFault) GameActions.Print(world,"The game stopped responding during an interaction. See the client log for details.");
            connectionFault=true;
            Close(); nextPoll=Environment.TickCount64+1000;
        }
        private static bool FinishObservation()
        {
            if(observation==null) return true;
            if(!observation.IsCompleted) return false;
            var result=observation;
            observation=null;
            string frame=result.GetAwaiter().GetResult();
            observationTimeout?.Dispose(); observationTimeout=null;
            bool run=walkingCommand!=null && runningCommand;
            if(walkingCommand!=null) {
                LastCommand=walkingCommand;
                TrinsicReplay.Record(walkingCommand,frame);
                string outcome=frame.Split(' ')[5];
                if((outcome=="busy" || outcome=="movement-held") && Environment.TickCount64-lastBlockedNotice>3000) {
                    GameActions.Print(world,"An original-game action is holding movement. Its state has been recorded in the client log.");
                    Console.Error.WriteLine($"TRINSIC movement held after {lastInteraction}; {frame.Split('\n')[0]}; {frame.Split('\n').FirstOrDefault(l=>l.StartsWith("H "))}");
                    lastBlockedNotice=Environment.TickCount64;
                }
                walkingCommand=null;
            }
            Apply(frame,run);
            return true;
        }
        private static readonly HashSet<uint> nativeContainers=new();
        private static readonly HashSet<uint> stacks=new();
        internal static bool IsStack(uint serial) => stacks.Contains(serial);
        internal static bool MergeTarget(uint source,uint target)
            => source!=target && IsStack(source) && IsStack(target);
        internal static int[] AvatarStats { get; private set; }
        internal static bool IsContainer(Item item) => TrinsicTown.Enabled ? nativeContainers.Contains(item.Serial) : item.ItemData.IsContainer;
        public static bool CanDrag(uint serial) => draggable.Contains(serial);
        public static void Send(string op, int a=0, int b=0, string extra="", Point? clickPosition=null)
        {
            if (pipe == null) return;
            try
            {
                if(!FinishObservation()) {
                    if(pending.Count<8 && (op!="STEP" || pending.Count==0)) pending.Enqueue((op,a,b,extra,generation,clickPosition));
                    return;
                }
                string command=$"{last+1} {generation} {op} {a} {b}{extra}";
                if(op!="STEP" && op!="TURN") lastInteraction=command;
                if(op=="STEP" && TrinsicTown.Compact) {
                    walkingCommand=command;
                    runningCommand=b!=0;
                    Observe(command);
                    return;
                }
                // Native checkpoint I/O can exceed the ordinary interaction budget,
                // especially while another development build is using the disk.
                string frame = Read(command,op is "SAVE" or "DBGSAVE" or "LOAD" ? 30 : 2);
                LastCommand=command; TrinsicReplay.Record(command,frame);
                string outcome=frame.Split(' ')[5];
                if(op.StartsWith("DBG",StringComparison.Ordinal))TrinsicDebug.LastOutcome=outcome;
                if(op=="MOVE" && (outcome=="ok" || outcome=="same" || outcome.StartsWith("split-"))) {
                    int moved=outcome.StartsWith("split-")?int.Parse(outcome.Substring(6)):a;
                    string[] xy=extra.Trim().Split(' ');
                    if(xy.Length>=2 && int.TryParse(xy[0],out int px) && int.TryParse(xy[1],out int py) && px>=0 && py>=0)
                        placements[ItemBase|(uint)moved]=(ItemBase|(uint)b,new Point(px,py));
                }
                Apply(frame);
                if(op=="TURN" && outcome=="ok" && TrinsicTown.Compact) world.Player.Direction=(Direction)(a&7);
                if(outcome=="locked" || outcome=="refused3") GameActions.Print(world,"The metal chest is locked.");
                else if(outcome=="unreachable") GameActions.Print(world,"Move closer to the item.");
                else if(outcome=="occupied") GameActions.Print(world,"That equipment slot is occupied.");
                else if(outcome=="notwearable") GameActions.Print(world,"You cannot wear that item.");
                else if(outcome=="refused1") GameActions.Print(world,"That is too heavy to carry.");
                else if(outcome=="refused4" || outcome=="cannotstore") GameActions.Print(world,"That item will not fit in this container.");
                else if(outcome.StartsWith("name-")) {
                    string name=gameTextEncoding.GetString(Convert.FromHexString(outcome.Substring(5))).Trim();
                    if(!TrinsicTown.Enabled) {var parts=name.Split('/');name=parts.Length>1?parts[1]:parts[0];}
                    uint serial=ItemBase|(uint)a;
                    if (clickPosition is Point at) ItemClickLabelGump.Show(world, name, at, serial);
                    else if (world.Items.Get(serial) is Item item) GameActions.Print(world, item, name);
                }
                else if(outcome=="stackfull") GameActions.Print(world,"That stack is full.");
                else if (op=="SAVE" || op=="LOAD" || ((op=="MOVE" || op=="GROUND") && outcome!="ok" && outcome!="same" && outcome!="merged" && !outcome.StartsWith("split-"))) GameActions.Print(world,op+" "+outcome);
            }
            catch (Exception ex) when (ex is IOException || ex is TimeoutException || ex is OperationCanceledException) { ConnectionFailure(ex); }
        }
        internal static bool WalkReady => Environment.TickCount64>=nextWalk && world.Player.Steps.Count<=1;
        public static bool Walk(Direction dir,bool run=false)
        {
            if((TrinsicDebug.Typing || TrinsicAudio.Typing))return false;
            if (!WalkReady) return false;
            if(TrinsicTown.Compact && prompt!=0) {
                if(Environment.TickCount64-lastBlockedNotice>3000) {
                    GameActions.Print(world,targetPrompt!=0?"Choose a target, or press Escape to cancel.":
                        dialog is NativeDisplay?"Close the open view or press Escape to move.":"Finish the conversation or reading to move.");
                    lastBlockedNotice=Environment.TickCount64;
                }
                return false;
            }
            if(TrinsicTown.Compact && chest!=0) Send("CLOSE");
            run=TrinsicTown.Compact && (run || ProfileManager.CurrentProfile.AlwaysRun);
            nextWalk=Environment.TickCount64+Mobile.NativeStepDuration(run);
            Send("STEP",(int)dir&7,run?1:0);
            return true;
        }
        public static bool Key(SDL.SDL_KeyboardEvent e)
        {
            var key=(SDL.SDL_Keycode)e.key;
            if(key==SDL.SDL_Keycode.SDLK_ESCAPE && TrinsicDebug.Targeting){TrinsicDebug.CancelTarget();return true;}
            if((TrinsicDebug.Typing || TrinsicAudio.Typing)){heldArrows=0;return false;}
            switch(key)
            {
                case SDL.SDL_Keycode.SDLK_ESCAPE when targetPrompt!=0: Send("TARGET",targetPrompt,0);return true;
                case SDL.SDL_Keycode.SDLK_ESCAPE when dialog is NativeDisplay || dialog is SpellbookGump: dialog.OnButtonClick(0);return true;
                case SDL.SDL_Keycode.SDLK_F2: ShowPaperdoll();return true;
                case SDL.SDL_Keycode.SDLK_F3: ShowBackpack();return true;
                case SDL.SDL_Keycode.SDLK_F4: ShowMap();return true;
                case SDL.SDL_Keycode.SDLK_F6: if(Environment.GetEnvironmentVariable("TRINSIC_READY")!=null) Send("BEGIN"); return true;
                case SDL.SDL_Keycode.SDLK_F7 when TrinsicTown.Enabled:
                    if(!e.repeat) {
                        var profile=ProfileManager.CurrentProfile;
                        profile.TrinsicHalfResolution=!profile.TrinsicHalfResolution;
                        GameActions.Print(world,profile.TrinsicHalfResolution ? "World resolution: half (2x pixels)." : "World resolution: native.");
                    }
                    return true;
                case SDL.SDL_Keycode.SDLK_F8: Overlay=!Overlay; return true;
                case SDL.SDL_Keycode.SDLK_F5: Send("SAVE",-1); return true;
                case SDL.SDL_Keycode.SDLK_F9: Send("LOAD",-1); return true;
                case SDL.SDL_Keycode.SDLK_UP: case SDL.SDL_Keycode.SDLK_RIGHT:
                case SDL.SDL_Keycode.SDLK_DOWN: case SDL.SDL_Keycode.SDLK_LEFT:
                    int d = key==SDL.SDL_Keycode.SDLK_UP ? 0 : key==SDL.SDL_Keycode.SDLK_RIGHT ? 2 : key==SDL.SDL_Keycode.SDLK_DOWN ? 4 : 6;
                    if ((e.mod & SDL.SDL_Keymod.SDL_KMOD_SHIFT)!=0) {
                        heldArrows=0;
                        if(!e.repeat) Send("TURN",d);
                    } else if(TrinsicTown.Compact) {
                        if(!e.repeat && prompt==0) {
                            heldArrows |= Arrow(key);
                            WalkHeld();
                        }
                    } else Walk((Direction)d);
                    return true;
                default: return false;
            }
        }
        private static ushort Art(int shape,int frame) => shape switch
        {
            594 => 0x0f52, 569 => 0x13cc, 574 => 0x13cb, 587 => 0x170b, 801 => 0x0e75,
            178 => 0x14eb, 627 => 0x14fc, 595 => 0x0f6b, 701 => 0x0a12, 628 => 0x0995, 616 => 0x099f,
            377 => 0x097b, 641 => 0x100e, 644 => 0x0eed, 599 => 0x0f61, 873 => (ushort)(0x0b2c+(frame&3)), 994 => 0x0fbb, 800 => 0x0e43, 522 => 0x0e40,
            270 => 0x0675, 376 => 0x0676, 432 => 0x0679, 433 => 0x067a,
            _ => 0x0e76
        };
        private static void ShowBarks(string[] lines)
        {
            foreach (string line in lines)
            {
                if (!line.StartsWith("B ", StringComparison.Ordinal)) continue;
                string[] fields = line.Split(' ');
                ulong sequence = ulong.Parse(fields[1]);
                if (sequence <= lastBark) continue;
                lastBark = sequence;
                uint serial = uint.Parse(fields[2]);
                Entity speaker=world.Mobiles.Get(serial) ?? (Entity)world.Items.Get(ItemBase|serial);
                if(speaker==null) continue;
                string text = gameTextEncoding.GetString(Convert.FromHexString(fields[3])).Replace('@', '"');
                var profile = ProfileManager.CurrentProfile;
                GameActions.Print(world, speaker, text, profile.SpeechHue, font: profile.ChatFont);
            }
        }

        // Poses are source animation groups, not simulated combat outcomes.
        private static readonly Dictionary<uint,int> actorActions=new();
        internal static int PresentedActions { get; private set; }
        private static void PresentAction(Mobile mobile,int nativeFrame,bool reset)
        {
            int pose=nativeFrame&15;
            int group=pose switch { >=4 and <=6=>1, >=7 and <=9=>2, >=14=>3, 11 or 12 when mobile.IsHuman=>4, _=>0 };
            if(!reset && actorActions.TryGetValue(mobile.Serial,out int old) && group!=0 && group!=old) {
                // Stock UO's bow is the closest living bend/kneel animation.
                // The native frame and posted recovery still own the action.
                byte action=mobile.IsHuman ? (byte)(group==1?9:group==2?12:group==4?32:16) :
                    TrinsicCreatures.Attack(mobile.Graphic);
                mobile.SetAnimation(action,repeatCount:1,forward:true,fromServer:true);
                PresentedActions++;
                if(group==4) TrinsicReplay.Record("NATIVEPOSE "+mobile.Serial+" "+pose+" "+action,"native frame "+nativeFrame);
            }
            actorActions[mobile.Serial]=group;
        }
        private static void Apply(string frame,bool run=false)
        {
            string[] lines = frame.Split('\n');
            TrinsicEffects.Prepare(lines);
            Header=lines[0];
            TrinsicReplay.Observe(frame);
            var actorState=lines.Where(l=>l.StartsWith("C ")).Select(l=>l.Split(' ')).ToDictionary(c=>uint.Parse(c[1]));
            health=lines.FirstOrDefault(l=>l.StartsWith("H "))??"";
            connectionFault=false;
            string refusal=lines.FirstOrDefault(l=>l.StartsWith("R "));
            if(refusal!=null) {
                string[] r=refusal.Split(' ');
                ulong sequence=ulong.Parse(r[1]);
                if(sequence>lastRefusal) {
                    lastRefusal=sequence;
                    GameActions.Print(world,int.Parse(r[2]) switch {
                        2=>"That is out of range.", 3=>"No ammunition.", 4=>"That is too heavy.",
                        5=>"There is not enough room.", 7=>"You cannot reach that.",
                        _=>"You cannot do that now."
                    });
                }
            }
            string[] s=lines[0].Split(' ');
            int gen=int.Parse(s[2]);
            bool reset=gen!=generation;
            if(reset && targetPrompt!=0) world.TargetManager.Reset();
            if (reset)
            {
                lastBark = 0;
                UIManager.GetGump<ItemClickLabelGump>()?.Dispose();
                foreach (uint serial in visible) world.Mobiles.Get(serial)?.TextContainer?.Clear();
            }
            if (reset) { actorActions.Clear(); heldArrows=0; targetPrompt=0; placements.Clear(); inventoryWindow?.Dispose(); inventoryWindow=null; chestWindow?.Dispose(); chestWindow=null; dialog?.Dispose(); chest=prompt=0; Client.Game.UO.GameCursor.ItemHold.Clear(); }
            generation=gen; last=int.Parse(s[4]); CameraX=int.Parse(s[6]); CameraY=int.Parse(s[7]);
            CameraOnly=Array.IndexOf(lines,"CAMERA_ONLY")>=0;
            int[][] rows=Rows(frame).ToArray();
            int[] avatar=rows.First(r=>r[7]==0);
            var iolo=rows.FirstOrDefault(r=>r[7]==1);
            if(iolo!=null){IoloX=iolo[3]; IoloY=iolo[4];}
            var keep=new HashSet<uint>();
            string avatarName=gameTextEncoding.GetString(Convert.FromHexString(lines.First(l=>l.StartsWith("N ")).Substring(2)));
            if(string.IsNullOrWhiteSpace(avatarName)) avatarName="Avatar";
            world.Player.Title=TrinsicTown.Enabled ? $"{avatarName}, Avatar of Legend" : avatarName;
            var stats=Array.ConvertAll(lines.First(l=>l.StartsWith("V ")).Substring(2).Split(' '),ushort.Parse);
            world.Player.Strength=stats[0]; world.Player.Dexterity=stats[1]; world.Player.Intelligence=stats[2];
            world.Player.Hits=stats[3]; world.Player.HitsMax=stats[0]; world.Player.Mana=stats[4]; world.Player.ManaMax=stats[5];
            uint oldBackpack=backpack;
            backpack=0;
            if(TrinsicTown.Enabled) {
                AvatarStats=Array.ConvertAll(lines.First(l=>l.StartsWith("P ")).Substring(2).Split(' '),int.Parse);
                world.Player.Hits=(ushort)Math.Max(0,AvatarStats[0]);
                world.Player.Weight=(ushort)AvatarStats[5]; world.Player.WeightMax=(ushort)AvatarStats[6];
                world.Player.Gold=(uint)AvatarStats[7]; world.Player.InWarMode=AvatarStats[8]!=0;
            }
            var parents=new HashSet<int>{avatar[0]};
            partyMembers.Clear(); partyBackpacks.Clear();
            foreach(var member in rows.Where(r=>r[7]>=0 && r.Length>11 && (r[11]&16)!=0)) {
                partyMembers.Add((uint)member[0]); parents.Add(member[0]);
            }
            var slots=new Dictionary<int,int>();
            draggable.Clear(); usable.Clear(); nativeContainers.Clear(); stacks.Clear();
            foreach (int[] r in rows)
            {
                int id=r[0], shape=r[1], x=r[3], y=r[4], z=r[5]*4, parent=r[6], npc=r[7];
                if (parent==0 && npc!=0 && !partyMembers.Contains((uint)id) && Math.Max(Math.Abs(x-avatar[3]),Math.Abs(y-avatar[4]))>36) continue;
                if (parent!=0 && !parents.Contains(parent)) continue;
                uint serial=(uint)id | (npc<0?ItemBase:0u);
                if(parent==0 && TrinsicEffects.IsMissile(id)) continue;
                ushort fieldGraphic=parent==0 ? TrinsicEffects.FieldGraphic(shape) : (ushort)0;
                ushort townGraphic = 0;
                if(TrinsicTown.Enabled && npc<0) {
                    townGraphic=fieldGraphic!=0 ? fieldGraphic : TrinsicTown.Graphic(shape,r[2],x,y,r[5],parent==0);
                    if(townGraphic==0) continue;
                    // The complete street-sign sprite includes its ground-level support.
                    if(parent==0 && shape==361) z=0;
                    if(parent==0 && TrinsicTown.IsFittedShutter(shape,x,y,r[5])) z-=8;
                }
                keep.Add(serial);
                Entity entity;
                if (npc>=0)
                {
                    Mobile mob=npc==0 ? world.Player : world.GetOrCreateMobile(serial);
                    mob.Graphic=0x0190; mob.Hue=(ushort)(npc==0?1002:npc==12?1021:1008);
                    mob.Name=npc switch {0=>avatarName,1=>"Iolo",2=>"Spark",12=>"Finnigan",_=>"Companion"};
                    ushort body=TrinsicCreatures.Body(shape);
                    if(TrinsicTown.Enabled && body!=0) {
                        mob.Graphic=body; mob.Hue=0;
                        mob.Name=TrinsicCreatures.Name(shape);
                    } else if(TrinsicTown.Enabled && npc!=0) {
                        mob.Name=TrinsicTown.Name(npc);
                        TrinsicTown.Dress(world,mob,shape,partyMembers.Contains(serial));
                        mob.Title=mob.Name;
                    }
                    if(actorState.TryGetValue(serial,out var state)) {
                        mob.Hits=(ushort)Math.Max(0,int.Parse(state[2]));
                        mob.HitsMax=(ushort)Math.Max(1,int.Parse(state[3]));
                        mob.InWarMode=int.Parse(state[4])!=0;
                        if(state.Length>7) {
                            mob.Flags=(mob.Flags & ~(Flags.Hidden|Flags.Poisoned)) |
                                ((int.Parse(state[7])&1)!=0 ? Flags.Hidden : 0) |
                                ((int.Parse(state[5])&0x2000)!=0 ? Flags.Poisoned : 0);
                        }
                        if(npc!=0 && state.Length>6 && state[6].Length>0)
                            mob.Name=gameTextEncoding.GetString(Convert.FromHexString(state[6]));
                    }
                    if(TrinsicTown.Enabled && npc==0) {
                        mob.IsFemale=AvatarStats[9]!=0;
                        mob.Graphic=(ushort)(mob.IsFemale?0x191:0x190);
                        mob.Hue=0x041c;
                        TrinsicTown.AvatarHair(world,mob);
                    }
                    mob.CheckGraphicChange();
                    PresentAction(mob,r[2],reset || !visible.Contains(serial));
                    Direction facing=(Direction)(r[8]&7);
                    if(TrinsicTown.Compact) {
                        mob.SetNativePosition(x,y,(sbyte)z,facing,reset || !visible.Contains(serial),npc==0 && run);
                        continue;
                    }
                    mob.GetEndPosition(out int endX,out int endY,out sbyte endZ,out Direction endDir);
                    int distance=Math.Max(Math.Abs(endX-x),Math.Abs(endY-y));
                    if(reset || !visible.Contains(serial) || distance>1 || (distance==0 && endZ!=z))
                    {
                        mob.ClearSteps(); mob.SetInWorldTile((ushort)x,(ushort)y,(sbyte)z); mob.Direction=facing;
                    }
                    else if(distance!=0 || endDir!=facing)
                    {
                        if(!mob.EnqueueStep(x,y,(sbyte)z,facing,false)) { mob.ClearSteps(); mob.SetInWorldTile((ushort)x,(ushort)y,(sbyte)z); mob.Direction=facing; }
                    }
                    continue;
                }
                else
                {
                    Item item=world.GetOrCreateItem(serial); entity=item;
                    item.FittedFaceDepth = parent==0 && TrinsicTown.Compact
                        ? TrinsicTown.ShutterDepth(shape,x,y,r[5]) : 0;
                    item.FurnitureWall = parent==0 && TrinsicTown.Compact
                        ? TrinsicTown.FurnitureWall(shape,x,y,r[5]) : 0;
                    if(parent!=0) { item.NativePosition=null; item.Offset=Vector3.Zero; }
                    if(fieldGraphic!=0) item.Hue=(ushort)(shape==902?0x0480:0);
                    item.Graphic=fieldGraphic!=0 ? fieldGraphic : TrinsicTown.Enabled ? townGraphic : Art(shape,r[2]); item.Amount=TrinsicTown.Enabled && (r[11]&8)==0 ? (ushort)1 : (ushort)Math.Max(1,r[9]);
                    if(TrinsicTown.Enabled) {
                        int capabilities=r[11];
                        if((capabilities&8)!=0) stacks.Add(serial);
                        if((capabilities&1)!=0) draggable.Add(serial);
                        if((capabilities&2)!=0) nativeContainers.Add(serial);
                        if((capabilities&6)!=0) usable.Add(serial);
                    } else if(shape is 178 or 377 or 569 or 574 or 587 or 594 or 595 or 599 or 616 or 627 or 628 or 641 or 644 or 701 or 994) draggable.Add(serial);
                    if(shape==994) item.Name="Tongs";
                    if(placements.TryGetValue(serial,out var placed) && (parent==0 || placed.owner!=(ItemBase|(uint)parent))) placements.Remove(serial);
                    if(shape==800 || shape==522 || shape==801 || nativeContainers.Contains(serial)) parents.Add(id);
                    if(parent==avatar[0] || partyMembers.Contains((uint)parent)) {
                        var wearer=world.Mobiles.Get((uint)parent);
                        // U7 chooses the occupied hand. Clothing draws on the layer of its stock UO artwork.
                        Layer wornLayer = shape == 801 ? Layer.Backpack : r[10] switch
                        {
                            1 => Layer.OneHanded,
                            2 => Layer.TwoHanded,
                            >= 0 when item.ItemData.IsWearable => (Layer)item.ItemData.Layer,
                            _ => Layer.Invalid
                        };
                        bool changedOwner = item.Container != wearer.Serial;
                        if (changedOwner)
                        {
                            world.RemoveItemFromContainer(item);
                            wearer.PushToBack(item);
                            item.Container = wearer.Serial;
                        }
                        if (changedOwner || item.Layer != wornLayer)
                        {
                            item.Layer = wornLayer;
                            UIManager.GetGump<PaperDollGump>(wearer.Serial)?.RequestUpdateContents();
                        }
                        if(shape==801) {
                            partyBackpacks.Add(serial);
                            if(parent==avatar[0]) backpack=serial;
                        }
                        continue;
                    }
                    item.Layer=Layer.Invalid;
                    if(parent!=0)
                    {
                        uint owner=ItemBase|(uint)parent;
                        slots.TryGetValue(parent,out int slot); slots[parent]=slot+1;
                        bool inPack=owner==backpack || partyBackpacks.Contains(owner);
                        ushort gx=(ushort)(inPack?46+slot%4*23:23+slot%3*46);
                        ushort gy=(ushort)(inPack?62+slot/4*21:112+slot/3%2*32);
                        if(placements.TryGetValue(serial,out var placement)) {
                            gx=(ushort)placement.position.X; gy=(ushort)placement.position.Y;
                        }
                        bool moved=item.X!=gx || item.Y!=gy;
                        if(item.Container!=owner)
                        {
                            item.RemoveFromTile(); world.RemoveItemFromContainer(item);
                            world.Items.Get(owner).PushToBack(item); item.Container=owner;
                            moved=true;
                        }
                        if(moved) { item.X=gx; item.Y=gy; UIManager.GetGump<ContainerGump>(owner)?.RequestUpdateContents(); }
                        continue;
                    }
                    if(TrinsicTown.Compact) {
                        item.NativePosition=new Point(x,y);
                        var sub=TrinsicTown.Subtile(x,y);
                        // Buildings and fitted furniture use the baked cell anchor.
                        if(TrinsicTown.FitsGrid(shape,r[2]) || TrinsicTown.IsFittedShutter(shape,x,y,r[5]))sub=Point.Zero;
                        item.Offset=new Vector3(sub.X,sub.Y,0);
                        x/=2; y/=2;
                    }
                    if(!item.OnGround) { world.RemoveItemFromContainer(item); item.Container=0xffffffff; item.SetInWorldTile((ushort)x,(ushort)y,(sbyte)z); }
                }
                if(!visible.Contains(serial) || entity.X!=x || entity.Y!=y || entity.Z!=z)
                    entity.SetInWorldTile((ushort)x,(ushort)y,(sbyte)z);
            }
            foreach(uint id in visible.Except(keep))
                if((id&ItemBase)!=0) world.RemoveItem(id,true); else world.RemoveMobile(id,true);
            visible=keep;
            TrinsicEffects.Apply(world,lines,gen);
            foreach(var sheet in UIManager.Gumps.OfType<PaperDollGump>().Where(g=>g.LocalSerial!=world.Player.Serial).ToArray())
                if(!partyMembers.Contains(sheet.LocalSerial)) sheet.Dispose();
            TrinsicDebug.Apply(world,lines,gen,backpack);
            TrinsicAudio.Apply(lines,gen);
            if (Client.Game.Scene is GameScene) ShowBarks(lines);
            if(oldBackpack!=0 && oldBackpack!=backpack) {
                UIManager.GetGump<ContainerGump>(oldBackpack)?.Dispose();
                if(backpack!=0) ShowBackpack();
            }
            int scale=TrinsicTown.Compact?2:1;
            world.RangeSize.X=avatar[3]/scale; world.RangeSize.Y=avatar[4]/scale;
            int open=int.Parse(s[8]);
            if(int.Parse(s[9])==6 || rows.Any(r=>r[0]==open && r[1]==761) || lines.Any(l=>l.StartsWith("U controls "))) open=0;
            if(open!=0 || int.Parse(s[9])!=0) heldArrows=0;
            if(open!=chest)
            {
                chestWindow?.Dispose(); inventoryWindow?.Dispose(); chestWindow=null; inventoryWindow=null; chest=open;
                if(open!=0 && world.Mobiles.TryGetValue((uint)open,out var owner))
                {
                    var contents=lines.Where(l=>l.StartsWith("I ")).Select(l=>{
                        var fields=l.Split(' ');
                        var name=Encoding.Latin1.GetString(Convert.FromHexString(fields[3])).Split('/');
                        return name.Length>1?name[1]:name[0];
                    });
                    inventoryWindow=new MessageBoxGump(world,360,260,owner.Name+" inventory\n\n"+string.Join("\n",contents),_=>Send("CLOSE"));
                    UIManager.Add(inventoryWindow);
                }
                else if(open!=0) {
                    chestWindow=new ContainerGump(world,ItemBase|(uint)open,0x49,false){X=200,Y=110};
                    UIManager.Add(chestWindow); chestWindow.RequestUpdateContents();
                }
            }
            int mode=int.Parse(s[9]), wanted=mode!=0?int.Parse(s[10]):0;
            if(wanted!=prompt || (mode!=0 && mode!=4 && (dialog==null || dialog.IsDisposed)))
            {
                if(dialog is SpellbookGump oldBook) oldBook.CloseFromSession(); else dialog?.Dispose();
                dialog=null; prompt=wanted;
                if(targetPrompt!=0) world.TargetManager.Reset();
                targetPrompt=mode==4?wanted:0;
                if(mode==4) GameActions.Print(world,"Choose a target. Escape cancels.");
                else if(mode==6) {
                    int token=prompt;
                    uint serial=ItemBase|uint.Parse(lines.First(l=>l.StartsWith("K ")).Split(' ')[1]);
                    dialog=new SpellbookGump(world,serial,lines,(op,spell)=>Send(op,token,spell));
                    UIManager.Add(dialog);
                }
                else if(mode==5) {
                    dialog=new NativeDisplay(world,prompt,Read("0 0 SCREEN"),lines.FirstOrDefault(l=>l.StartsWith("U controls ")));
                    UIManager.Add(dialog);
                    UIManager.KeyboardFocusControl=dialog; dialog.SetKeyboardFocus();
                }
                else if(mode!=0)
                {
                    string Decode(string line)=>gameTextEncoding.GetString(Convert.FromHexString(line.Substring(2))).Replace('@','"').Replace('~',' ');
                    string text=Decode(lines.First(l=>l.StartsWith("T ")));
                    if (text.Length==0) text=previousWords; else previousWords=text;
                    string[] options=mode==1?new[]{"Continue"}:lines.Where(l=>l.StartsWith("A ")).Select(Decode).ToArray();
                    var range=mode==3 ? lines.First(l=>l.StartsWith("D ")).Substring(2).Split(' ') : null;
                    dialog=new TrinsicDialogue(world,prompt,int.Parse(s[11]),text,options,range);
                    UIManager.Add(dialog);
                }
            }
            if(targetPrompt!=0 && !world.TargetManager.IsTargeting) {
                int token=targetPrompt;
                world.TargetManager.SetTargeting(target=>{
                    if(target==null || target is Entity)
                        Send("TARGET",token,target is Entity entity ? (int)(entity.Serial&0x1fffffff) : 0);
                    else {
                        var position=TrinsicTown.Compact?TrinsicTown.NativeGround(target.X,target.Y):new Point(target.X,target.Y);
                        Send("TARGETPOS",token,position.X,$" {position.Y} {Math.Clamp(target.Z/4,0,15)}");
                    }
                },(uint)token,TargetType.Neutral);
            }
        }
        // One presentation adapter for original map/sign/view screens, independent of item shapes.
        private sealed class NativeDisplay : Gump
        {
            private readonly int token;
            private readonly Texture2D texture;
            private readonly int pictureWidth,pictureHeight;
            private readonly bool interactive;
            private readonly Point origin;
            private static long lastClick;
            private static Point lastPoint;
            public NativeDisplay(World w,int id,string frame,string controls=null) : base(w,0,0)
            {
                interactive=controls!=null;
                if(interactive) {var fields=controls.Split(' ');origin=new Point(int.Parse(fields[2]),int.Parse(fields[3]));}
                string[] data=frame.Trim().Split(' ');
                if((data.Length!=5 && data.Length!=6) || data[0]!="F" || !int.TryParse(data[1],out int width) || !int.TryParse(data[2],out int height) ||
                    width<1 || width>320 || height<1 || height>200) throw new IOException("Invalid native display");
                byte[] palette=Convert.FromHexString(data[3]), pixels=Convert.FromHexString(data[4]);
                if(palette.Length!=768 || pixels.Length!=width*height) throw new IOException("Incomplete native display");
                byte[] mask=data.Length==6?Convert.FromHexString(data[5]):null;
                if(mask!=null && mask.Length!=(pixels.Length+7)/8) throw new IOException("Incomplete native display mask");
                var colors=new Color[pixels.Length];
                for(int i=0;i<pixels.Length;i++) {
                    int p=pixels[i]*3;
                    colors[i]=mask!=null && (mask[i/8]&(1<<(i%8)))==0?Color.Transparent:new Color(palette[p]*255/63,palette[p+1]*255/63,palette[p+2]*255/63);
                }
                texture=new Texture2D(Client.Game.GraphicsDevice,width,height);
                texture.SetData(colors);
                token=id; IsModal=true; CanMove=true; AcceptMouseInput=AcceptKeyboardInput=true;
                CanCloseWithEsc=CanCloseWithRightClick=false;
                pictureWidth=width*2;pictureHeight=height*2;
                Width=Math.Max(160,pictureWidth); Height=pictureHeight+40; WantUpdateSize=false;
                X=Math.Max(0,(Client.Game.ClientBounds.Width-Width)/2);Y=Math.Max(0,(Client.Game.ClientBounds.Height-Height)/2);
                Add(new ResizePic(0x0a28){Y=pictureHeight,Width=Width,Height=40});
                Add(new Button(0,0x481,0x482,0x483){X=Width/2-25,Y=pictureHeight+7,ButtonAction=ButtonAction.Activate});
            }
            public override bool AddToRenderLists(RenderLists lists,int x,int y,ref float depth)
            {
                float layer=depth;
                lists.AddGumpNoAtlas(batcher=>{
                    if(!texture.IsDisposed) batcher.Draw(texture,new Rectangle(x+(Width-pictureWidth)/2,y,pictureWidth,pictureHeight),ShaderHueTranslator.GetHueVector(0),layer);
                    return true;
                });
                return base.AddToRenderLists(lists,x,y,ref depth);
            }
            protected override void OnKeyDown(SDL.SDL_Keycode key,SDL.SDL_Keymod mod) {
                if(key==SDL.SDL_Keycode.SDLK_ESCAPE || key==SDL.SDL_Keycode.SDLK_RETURN) OnButtonClick(0);
                else base.OnKeyDown(key,mod);
            }
            protected override void OnMouseUp(int x,int y,MouseButtonType button) {
                if(button==MouseButtonType.Right) OnButtonClick(0);
                else if(interactive && button==MouseButtonType.Left && x>=0 && x<pictureWidth && y>=0 && y<pictureHeight) {
                    var point=new Point(x/2,y/2);
                    long now=Environment.TickCount64;
                    int action=now-lastClick<500 && Math.Abs(point.X-lastPoint.X)<3 && Math.Abs(point.Y-lastPoint.Y)<3?2:1;
                    lastClick=action==2?0:now; lastPoint=point;
                    Send("VIEWCLICK",token,point.X+origin.X,$" {point.Y+origin.Y} {action}");
                }
                else base.OnMouseUp(x,y,button);
            }
            public override void OnButtonClick(int id) { Send("DISMISS",token); }
            public override void Dispose() { texture?.Dispose(); base.Dispose(); }
        }
        private sealed class TrinsicDialogue : Gump
        {
            private const int Padding=44;
            private readonly int token;
            private readonly StbTextBox number;
            private readonly int minimum, maximum, increment;
            private Point centeredWindow;
            public TrinsicDialogue(World w,int id,int face,string text,string[] options,string[] range) : base(w,0,0)
            {
                bool numeric=range!=null;
                token=id; CanMove=true; IsModal=true;
                CanCloseWithRightClick=false; CanCloseWithEsc=false;
                var label=new Label(text,false,0x386,398,1){X=109,Y=Padding};
                int top=Math.Max(Padding+70,Padding+12+label.Height);
                var background=new ResizePic(0x0a28){Width=558};
                Add(background);
                if(face==12 || face==-12) Add(new GumpPic(48,Padding,64012,0));
                Add(label);
                if(numeric) {
                    minimum=int.Parse(range[0]); maximum=int.Parse(range[1]); increment=int.Parse(range[2]);
                    var hint=new Label($"Enter {minimum} to {maximum} in steps of {increment}.",false,0x386,398){X=109,Y=top+30};
                    Add(hint);
                    Add(new ResizePic(0xbb8){X=109,Y=top,Width=120,Height=27});
                    number=new StbTextBox(1,5,104){X=115,Y=top+4,Width=104,Height=22,NumbersOnly=true};
                    Add(number);
                    Add(new Button(0,0x481,0x482,0x483){X=240,Y=top,ButtonAction=ButtonAction.Activate});
                    background.Height=Math.Max(top+45,hint.Y+hint.Height)+Padding;
                    UIManager.KeyboardFocusControl=number;
                    number.SetKeyboardFocus();
                }
                else
                {
                    int y=top;
                    for(int row=0;row<options.Length;row+=2)
                    {
                        int rowHeight=27;
                        for(int i=row;i<Math.Min(row+2,options.Length);i++)
                        {
                            int x=49+(i%2)*237;
                            Add(new Button(i,0x837,0x838,0x837){X=x,Y=y,ButtonAction=ButtonAction.Activate});
                            var choice=new Label(options[i],false,0x386,205){X=x+23,Y=y};
                            Add(choice);
                            rowHeight=Math.Max(rowHeight,choice.Height+8);
                        }
                        y+=rowHeight;
                    }
                    background.Height=y+Padding;
                }
                Width=background.Width;Height=background.Height;
                CenterInWindow();
            }
            private void CenterInWindow()
            {
                var bounds=Client.Game.ClientBounds;
                centeredWindow=new Point(bounds.Width,bounds.Height);
                X=Math.Max(0,(bounds.Width-Width)/2);Y=Math.Max(0,(bounds.Height-Height)/2);
            }
            public override void Update()
            {
                base.Update();
                var bounds=Client.Game.ClientBounds;
                // Recenter on window resize, but retain the player's drag otherwise.
                if(centeredWindow!=new Point(bounds.Width,bounds.Height))CenterInWindow();
            }
            public override void OnKeyboardReturn(int textID,string text) {
                if(number!=null) OnButtonClick(0);
            }
            public override void OnButtonClick(int id) {
                if(number==null) Send("ANSWER",token,id);
                else if(int.TryParse(number.Text,out int value) && value>=minimum && value<=maximum && (value-minimum)%increment==0)
                    Send("NUMBER",token,value);
            }
        }
    }
}
