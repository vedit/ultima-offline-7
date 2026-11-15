// SPDX-License-Identifier: BSD-2-Clause
// Opt-in reproducible inputs use the same actions and widgets as the playable scene.
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using ClassicUO.Configuration;
using ClassicUO.Game.GameObjects;
using ClassicUO.Game.UI.Controls;
using ClassicUO.Input;
using Microsoft.Xna.Framework;
using ClassicUO.Game.Managers;
using ClassicUO.Game.Data;
using ClassicUO.Game.UI.Gumps;

namespace ClassicUO.Game
{
    internal static class TrinsicReplay
    {
        private static readonly string path=Environment.GetEnvironmentVariable("TRINSIC_REPLAY");
        private static Queue<string> actions;
        private static long due;
        private static readonly HashSet<byte> walkFrames=new();
        private static bool interpolated;
        private static ushort lastClickedGraphic;
        private static Point labelClick;
        private static string expectedLabel;
        private static Point? rightMousePoint;
        private static Point mouseStart;
        private static bool sawWalk,sawRun;
        private static int testBook,testCreature;
        // Optional acknowledged input batches let long journeys react to native
        // schedules and prompts. They still execute the normal replay/UI actions.
        private static readonly bool live=Environment.GetEnvironmentVariable("TRINSIC_REPLAY_LIVE")=="1";
        private static long batch;
        private static string observedFrame,resultFrame;
        internal static void Observe(string frame) { if(Active && live) observedFrame=frame; }
        internal static void ObserveWalk(PlayerMobile player)
        {
            if(rightMousePoint is Point point) {
                Mouse.Position=point;
                if(player.NativeWalking) {
                    if(player.IsRunning)sawRun=true;
                    else sawWalk=true;
                }
            }
            if(player.Steps.Count==0 && !player.NativeWalking) return;
            if(player.Offset.X!=0 || player.Offset.Y!=0)
            { interpolated=true; walkFrames.Add(player.AnimIndex); }
        }
        internal static bool Active => !string.IsNullOrEmpty(path);
        internal static void Record(string cmd,string frame)
        {
            if(live && frame.StartsWith("S ",StringComparison.Ordinal)) resultFrame=frame;
            if(Active) File.AppendAllText(path+".log",cmd+" -> "+frame.Split('\n')[0]+"\n");
        }
        // Exercise the same hit test, pickup threshold and mouse-release routing as a live drag.
        private static (Control icon,Point at) FindIcon(Gump source,uint serial)
        {
            Control icon=null;
            Point at=Point.Zero;
            for(int y=0;y<source.Height && icon==null;y++)
                for(int x=0;x<source.Width && icon==null;x++) {
                    at=new Point(source.X+x,source.Y+y);
                    Control hit=null;
                    source.HitTest(at,ref hit);
                    if(hit?.LocalSerial==serial && (source is not PaperDollGump || hit.Parent is PaperDollInteractable))
                        icon=hit;
                }
            if(icon==null) throw new InvalidOperationException($"No clickable pixels for {serial} in {source.GetType().Name}");
            return (icon,at);
        }
        private static void DragIcon(Gump source,uint serial,Gump destination,Point target,int quantity=0,uint onto=0)
        {
            var (icon,at)=FindIcon(source,serial);
            UIManager.MakeTopMostGump(source);
            Mouse.Position=at;
            Mouse.ButtonPress(MouseButtonType.Left);
            UIManager.OnMouseButtonDown(MouseButtonType.Left);
            Mouse.Position.X+=10;
            icon.Update();
            if(quantity>0) {
                var menu=UIManager.GetGump<SplitMenuGump>(serial) ?? throw new InvalidOperationException("Missing split slider");
                menu.Children.OfType<HSliderBar>().Single().Value=quantity;
                menu.OnKeyboardReturn(0,quantity.ToString());
            }
            if(Client.Game.UO.GameCursor.ItemHold.Serial!=serial || !Client.Game.UO.GameCursor.ItemHold.Enabled)
                throw new InvalidOperationException($"Mouse failed to pick up {serial} at {at} from {icon.GetType().Name}");
            UIManager.MakeTopMostGump(destination);
            Mouse.Position=onto==0?new Point(destination.X+target.X,destination.Y+target.Y):FindIcon(destination,onto).at;
            Mouse.ButtonRelease(MouseButtonType.Left);
            UIManager.OnMouseButtonUp(MouseButtonType.Left);
            if(Client.Game.UO.GameCursor.ItemHold.Enabled)
                throw new InvalidOperationException($"Mouse failed to release over {UIManager.MouseOverControl?.GetType().Name}");
        }

        private static void ClickScenery()
        {
            var scene = Client.Game.GetScene<Scenes.GameScene>();
            var bounds = scene.Camera.Bounds;
            for (int dy = -120; dy <= 120; dy += 20)
            for (int dx = -180; dx <= 180; dx += 20)
            {
                var point = bounds.Center + new Point(dx, dy);
                var pixel = scene.Camera.ScreenToWorld(point - bounds.Location);
                if (scene.PickReplayPixel(pixel) is not Static scenery || string.IsNullOrWhiteSpace(scenery.Name)) continue;
                Mouse.Position = point;
                UIManager.Update();
                scene.OnMouseDown(MouseButtonType.Left);
                if (!scene.OnMouseUp(MouseButtonType.Left)) continue;
                expectedLabel = ClassicUO.Utility.StringHelper.GetPluralAdjustedString(scenery.Name, scenery.ItemData.Count > 1);
                labelClick = point;
                return;
            }
            throw new InvalidOperationException("No visible scenery to click");
        }

        private static long effectWaitStart;
        internal static void Next(World world,ContainerGump chest,Gump dialogue)
        {
            if(Environment.TickCount64<due) return;
            actions??=new Queue<string>(File.ReadAllLines(path));
            if(live && actions.Count==0 && File.Exists(path+".request")) {
                var request=File.ReadAllLines(path+".request");
                if(request.Length>1 && long.TryParse(request[0],out long id) && id>batch) {
                    batch=id;
                    resultFrame=null;
                    actions=new Queue<string>(request.Skip(1));
                }
            }
            if(actions.Count==0) return;
            if (actions.Peek().StartsWith("WAITBARK ", StringComparison.Ordinal))
            {
                string[] expected = actions.Peek().Split(' ', 3);
                foreach (var speaker in world.Mobiles.Values)
                {
                    if (speaker.Name != expected[1] || speaker.Distance > world.ClientViewRange) continue;
                    TextObject found = null;
                    for (var line = speaker.TextContainer?.Items as TextObject; line != null; line = line.Next as TextObject)
                    {
                        if (line.Owner != speaker || line.Time <= Time.Ticks ||
                            line.RenderedText?.HasContent != true || line.RenderedText.Text != expected[2] ||
                            line.RealScreenPosition == Point.Zero) continue;
                        if (found != null) throw new InvalidOperationException("NPC reaction appeared twice");
                        found = line;
                    }
                    if (found == null) continue;
                    File.AppendAllText(path+".log", $"NPC overhead {speaker.Name} ({speaker.Serial}) at {found.RealScreenPosition}: {found.RenderedText.Text}\n");
                    actions.Dequeue();
                    Client.Game.TakeScreenshot();
                    return;
                }
                return;
            }
            if(actions.Peek().StartsWith("FXWAIT ")) {
                var wait=actions.Peek().Split(' ');
                if(TrinsicEffects.Counts.GetValueOrDefault(wait[1])>=int.Parse(wait[2])) {actions.Dequeue();effectWaitStart=0;return;}
                if(effectWaitStart==0) effectWaitStart=Environment.TickCount64;
                if(Environment.TickCount64-effectWaitStart>6000) throw new InvalidOperationException("No native "+wait[1]+" effect; HP="+world.Player.Hits+" "+TrinsicSession.Header);
                return;
            }
            if(actions.Peek()=="WANDWAITCAT") {
                if(!TrinsicDebug.Loading){actions.Dequeue();effectWaitStart=0;return;}
                if(effectWaitStart==0)effectWaitStart=Environment.TickCount64;
                if(Environment.TickCount64-effectWaitStart>60000)throw new InvalidOperationException("Developer catalog did not finish loading");
                return;
            }
            if((actions.Peek().StartsWith("STEP ") || actions.Peek().StartsWith("CONFLICT ")) && !TrinsicSession.WalkReady) return;
            string command=actions.Dequeue();
            string[] a=command.Split(' ');
            int Arg(int i=1)=>int.Parse(a[i]);
            uint Item(int i)=>0x40000000u|(uint)Arg(i);
            due=Environment.TickCount64+(live?20:260);
            switch(a[0])
            {
                case "RIGHTMOVE":
                    var bounds=Client.Game.Scene.Camera.Bounds;
                    int distance=a[1]=="edge"?bounds.Width/2-16:60;
                    rightMousePoint=new Point(bounds.Center.X+distance,bounds.Center.Y+distance/2);
                    mouseStart=world.Player.NativePosition.Value;
                    sawWalk=sawRun=false;
                    Mouse.Position=rightMousePoint.Value;
                    UIManager.Update();
                    Mouse.ButtonPress(MouseButtonType.Right);
                    if(!Client.Game.Scene.OnMouseDown(MouseButtonType.Right))throw new InvalidOperationException("Right mouse press missed the world");
                    due=Environment.TickCount64+Arg(2);
                    break;
                case "RIGHTRELEASE":
                    Mouse.ButtonRelease(MouseButtonType.Right);
                    Client.Game.Scene.OnMouseUp(MouseButtonType.Right);
                    rightMousePoint=null;
                    var travel=world.Player.NativePosition.Value-mouseStart;
                    if(travel==Point.Zero || (a[1]=="edge"?!sawRun:!sawWalk))
                        throw new InvalidOperationException($"Right drag {a[1]} moved {travel} walk {sawWalk} run {sawRun}");
                    File.AppendAllText(path+".log",$"Right drag {a[1]} travelled {travel.X},{travel.Y} walk {sawWalk} run {sawRun}\n");
                    break;
                case "HORSECHECK":
                    var horse=world.Mobiles.Values.Single(m=>m.Graphic==0x00c8 && m.Name=="Horse" && m.Distance<=10);
                    if(!Client.Game.UO.Animations.AnimationExists(horse.Graphic,0) || !Client.Game.UO.Animations.AnimationExists(horse.Graphic,2))
                        throw new InvalidOperationException("Missing horse walk or standing frames");
                    File.AppendAllText(path+".log",$"Stable horse {horse.Serial} at {horse.NativePosition} body {horse.Graphic}\n");
                    break;
                case "MONEY":
                    var purse=world.Player.FindItemByLayer(Layer.Backpack);
                    var coins=world.Items.Values.Where(i=>i.Container==purse.Serial && i.Graphic is >=0xeed and <=0xeef)
                        .OrderBy(i=>i.Amount).ToArray();
                    var bagWindow=UIManager.GetGump<ContainerGump>(purse.Serial);
                    if(a[1]=="split")DragIcon(bagWindow,coins.Last().Serial,bagWindow,new Point(105,99),Arg(2));
                    else if(a[1]=="join")DragIcon(bagWindow,coins.First().Serial,bagWindow,Point.Zero,coins.First().Amount,coins.Last().Serial);
                    else if(a[1]=="look") {
                        var coinHit=FindIcon(bagWindow,coins.First().Serial);
                        UIManager.MakeTopMostGump(bagWindow); Mouse.Position=coinHit.at;Mouse.ButtonPress(MouseButtonType.Left);
                        UIManager.OnMouseButtonDown(MouseButtonType.Left);Mouse.ButtonRelease(MouseButtonType.Left);UIManager.OnMouseButtonUp(MouseButtonType.Left);
                        labelClick=coinHit.at;
                        expectedLabel=coins.First().Amount+" gold coins";
                    } else if(string.Join(",",coins.Select(i=>i.Amount))!=a[1])
                        throw new InvalidOperationException("Stack quantities: "+string.Join(",",coins.Select(i=>i.Amount)));
                    break;
                case "STATUS":
                    UIManager.GetGump<PaperDollGump>(world.Player.Serial).OnButtonClick(8);
                    var stats=StatusGumpBase.GetStatusGump() ?? throw new InvalidOperationException("Missing status");
                    stats.X=660;stats.Y=560;
                    if(!stats.Children.OfType<Label>().Any(l=>l.Text==$"{world.Player.Weight}/{world.Player.WeightMax}"))
                        throw new InvalidOperationException("Missing load on status");
                    break;
                case "SHEETLOOK":
                    var doll=UIManager.GetGump<PaperDollGump>(world.Player.Serial);
                    var worn=world.Player.FindItemByLayer(Enum.Parse<Layer>(a[1]));
                    UIManager.MakeTopMostGump(doll);
                    Mouse.Position=FindIcon(doll,worn.Serial).at;
                    Mouse.ButtonPress(MouseButtonType.Left);
                    UIManager.OnMouseButtonDown(MouseButtonType.Left);
                    Mouse.ButtonRelease(MouseButtonType.Left);
                    UIManager.OnMouseButtonUp(MouseButtonType.Left);
                    labelClick=Mouse.Position;
                    break;
                case "MOVECURSOR":
                    Mouse.Position=labelClick+new Point(-70,50);
                    break;
                case "LABELCHECK":
                    var clickLabel=UIManager.Gumps.OfType<ItemClickLabelGump>().Where(g=>!g.IsDisposed).Single();
                    var lettering=clickLabel.Children.OfType<Label>().Single();
                    string expectedText=a.Length>1?string.Join(" ",a.Skip(1)):expectedLabel;
                    Control hovered=null;
                    clickLabel.HitTest(clickLabel.X+lettering.Width/2,clickLabel.Y+lettering.Height/2,ref hovered);
                    if(lettering.Text!=expectedText || hovered!=null ||
                       !new Rectangle(clickLabel.X,clickLabel.Y,lettering.Width,lettering.Height+8).Contains(labelClick))
                        throw new InvalidOperationException($"Expected '{expectedText}' at {labelClick}, got '{lettering.Text}' at {clickLabel.Bounds}");
                    Client.Game.TakeScreenshot();
                    break;
                case "LABELEXPIRED":
                    if(UIManager.GetGump<ItemClickLabelGump>()!=null) throw new InvalidOperationException("Item label still visible");
                    break;
                case "STATICLOOK":
                    ClickScenery();
                    break;
                case "SHEETWAR":
                    UIManager.GetGump<PaperDollGump>(world.Player.Serial).OnButtonClick(7);break;
                case "TAB":
                    var tab=new SDL3.SDL.SDL_KeyboardEvent {key=(uint)SDL3.SDL.SDL_Keycode.SDLK_TAB};
                    Client.Game.Scene.OnKeyDown(tab);Client.Game.Scene.OnKeyUp(tab);break;
                case "WARSTATE":
                    if(world.Player.InWarMode!=(Arg()!=0))throw new InvalidOperationException("Wrong combat mode");break;
                case "CLOSEDWALK":
                    if(chest!=null || world.Player.NativePosition==new Point(Arg(1),Arg(2)))
                        throw new InvalidOperationException("Container or movement did not update");
                    break;
                case "FACING":
                    if(((int)world.Player.Direction&7)!=Arg())
                        throw new InvalidOperationException($"Expected {Arg()} but facing {world.Player.Direction}");
                    break;
                case "DOORCHANGED":
                    if(world.Items[Item(1)].DisplayedGraphic==lastClickedGraphic)
                        throw new InvalidOperationException("Door failed to swing: "+command);
                    break;
                case "PIXELUSE": case "PIXELPICK": case "PIXELLOOK":
                    var target=world.Items[Item(1)];
                    var scene=Client.Game.GetScene<Scenes.GameScene>();
                    ref readonly var sprite=ref Client.Game.UO.Arts.GetArt(target.DisplayedGraphic);
                    var origin=target.RealScreenPosition+new Point((int)target.Offset.X+22-sprite.UV.Width/2,
                        (int)target.Offset.Y+44-sprite.UV.Height);
                    bool hit=false;
                    int top=a.Length>2?sprite.UV.Height*Arg(2)/100:0;
                    int bottom=a.Length>2?Math.Min(sprite.UV.Height,top+8):sprite.UV.Height;
                    lastClickedGraphic=target.DisplayedGraphic;
                    for(int y=top;y<bottom && !hit;y++)
                        for(int dx=0;dx<sprite.UV.Width && !hit;dx++) {
                            int x=(sprite.UV.Width/2+((dx%2==0)?dx/2:-(dx+1)/2));
                            if(x<0 || x>=sprite.UV.Width)continue;
                            if(!Client.Game.UO.Arts.PixelCheck(target.DisplayedGraphic,x,y))continue;
                            var at=origin+new Point(x,y);
                            if(scene.PickReplayPixel(at)!=target)continue;
                            Mouse.Position=scene.Camera.WorldToScreen(at,true);
                            UIManager.Update();
                            if(a[0]=="PIXELUSE") hit=scene.OnMouseDoubleClick(MouseButtonType.Left);
                            else if(a[0]=="PIXELLOOK") {
                                labelClick=Mouse.Position;
                                scene.OnMouseDown(MouseButtonType.Left);
                                hit=scene.OnMouseUp(MouseButtonType.Left);
                            }
                            else {
                                Mouse.ButtonPress(MouseButtonType.Left);
                                scene.OnMouseDown(MouseButtonType.Left);
                                Mouse.Position.X+=12;
                                scene.OnMouseDragging();
                                Mouse.ButtonRelease(MouseButtonType.Left);
                                hit=Client.Game.UO.GameCursor.ItemHold.Enabled && Client.Game.UO.GameCursor.ItemHold.Serial==target.Serial;
                            }
                            if(hit)File.AppendAllText(path+".log",$"World click {x},{y} on {sprite.UV.Width}x{sprite.UV.Height} sprite\n");
                        }
                    if(!hit)throw new InvalidOperationException($"No actionable world pixel for {command} at {origin}");
                    break;
                case "STEP": world.Player.Walk((Direction)Arg(),false); break;
                case "CONFLICT": world.Player.Walker.WalkingFailed=true; world.Player.Walk((Direction)Arg(),false); world.Player.Walker.WalkingFailed=false; break;
                case "PANELS":
                    var paper=UIManager.GetGump<PaperDollGump>(world.Player.Serial);
                    var bag=world.Player.FindItemByLayer(Layer.Backpack);
                    var pack=bag==null?null:UIManager.GetGump<ContainerGump>(bag.Serial);
                    if(paper==null || paper.X<Client.Game.ClientBounds.Width/2 || UIManager.GetGump<MiniMapGump>()==null ||
                       bag==null || pack==null || !pack.Children.OfType<ItemGump>().Any() || world.Player.FindItemByLayer(Layer.Torso)==null)
                        throw new InvalidOperationException("Missing native player panels or equipment");
                    break;
                case "DRAGICON":
                    Gump Window(string key) {
                        if(key.Contains(':')) {
                            var fields=key.Split(':');
                            uint member=uint.Parse(fields[1]);
                            return fields[0]=="sheet" ? UIManager.GetGump<PaperDollGump>(member)
                                : UIManager.GetGump<ContainerGump>(world.Mobiles.Get(member).FindItemByLayer(Layer.Backpack).Serial);
                        }
                        return key switch {
                        "pack"=>UIManager.GetGump<ContainerGump>(world.Player.FindItemByLayer(Layer.Backpack).Serial),
                        "sheet"=>UIManager.GetGump<PaperDollGump>(world.Player.Serial),
                        "chest"=>chest,_=>throw new InvalidOperationException(key)};
                    }
                    DragIcon(Window(a[2]),Item(1),Window(a[3]),new Point(Arg(4),Arg(5)));
                    break;
                case "WORN":
                    if((a.Length>3?world.Mobiles.Get((uint)Arg(3)):world.Player).FindItemByLayer(Enum.Parse<Layer>(a[2]))?.Serial!=Item(1))
                        throw new InvalidOperationException("Equipment mismatch: "+command);
                    break;
                case "OWNER":
                    if(world.Items[Item(1)].Container!=Item(2)) throw new InvalidOperationException("Wrong owner: "+command);
                    break;
                case "ICONPOSITION":
                    var positioned=world.Items[Item(1)];
                    if(Math.Abs(positioned.X-Arg(2))>16 || Math.Abs(positioned.Y-Arg(3))>16)
                        throw new InvalidOperationException($"Item at {positioned.X},{positioned.Y}: {command}");
                    break;
                case "PACKDROP":
                    UIManager.GetGump<ContainerGump>(world.Player.FindItemByLayer(Layer.Backpack).Serial).DropHeldLocalItem(); break;
                case "PACKCHECK":
                    var bagItem=world.Player.FindItemByLayer(Layer.Backpack);
                    if(world.Items[Item(1)].Container!=bagItem.Serial || !UIManager.GetGump<ContainerGump>(bagItem.Serial).Children.OfType<ItemGump>().Any(icon=>icon.LocalSerial==Item(1)))
                        throw new InvalidOperationException("Backpack ownership or icon mismatch");
                    break;
                case "REOPENPANELS":
                    UIManager.GetGump<MiniMapGump>()?.Dispose(); UIManager.GetGump<PaperDollGump>(world.Player.Serial)?.Dispose();
                    var packSerial=world.Player.FindItemByLayer(Layer.Backpack).Serial;
                    UIManager.GetGump<ContainerGump>(packSerial)?.Dispose();
                    TrinsicSession.ShowMap(); GameActions.DoubleClick(world,world.Player.Serial); GameActions.DoubleClick(world,packSerial); break;
                case "WALKCHECK":
                    if(!interpolated || walkFrames.Count<2) throw new InvalidOperationException("No interpolated walking frames: "+walkFrames.Count);
                    break;
                case "SELF": GameActions.DoubleClick(world,world.Player.Serial); break;
                case "INVENTORY": if(!TrinsicSession.InventoryVisible) throw new InvalidOperationException("Missing Avatar inventory");
                    UIManager.GetGump<PaperDollGump>(world.Player.Serial).Dispose(); break;
                case "CONTENTS":
                    var icons=chest.Children.OfType<ItemGump>().Where(i=>!i.IsDisposed).Select(i=>i.LocalSerial).ToArray();
                    uint[] expected=a.Skip(1).Select(i=>0x40000000u|uint.Parse(i)).ToArray();
                    if(!icons.Order().SequenceEqual(expected.Order())) throw new InvalidOperationException("Chest icons: "+string.Join(",",icons));
                    foreach(var icon in chest.Children.OfType<ItemGump>())
                        File.AppendAllText(path+".log",$"icon {icon.LocalSerial} art {icon.Graphic:x} at {icon.X},{icon.Y} size {icon.Width}x{icon.Height}\n");
                    if(world.Items[Item(1)].Graphic!=0x0eed || world.Items[Item(2)].Graphic!=0x0f61) throw new InvalidOperationException("Chest art");
                    break;
                case "GROUND": GameActions.DropItem(Client.Game.UO.GameCursor.ItemHold.Serial,Arg(1),Arg(2),0,0xffffffff);break;
                case "TURN": TrinsicSession.Send("TURN",Arg()); break;
                case "USE": GameActions.DoubleClick(world,world.Mobiles.Get((uint)Arg())!=null?(uint)Arg():Item(1)); break;
                case "FXCAST": TrinsicSession.Send("AUDITCAST",Arg());break;
                case "WANDOPEN": GameActions.DoubleClick(world,TrinsicDebug.WandSerial);break;
                case "WANDCHECK":
                    var wand=world.Items.Get(TrinsicDebug.WandSerial);
                    if(!TrinsicDebug.Enabled || wand==null || wand.Graphic!=0x0df2 || wand.Container==0 || TrinsicSession.CanDrag(wand.Serial))throw new InvalidOperationException("Developer wand missing or draggable");
                    if(world.Items.Values.Count(i=>i.Serial==TrinsicDebug.WandSerial)!=1)throw new InvalidOperationException("Duplicate developer wand");
                    break;
                case "WANDCLICK":
                case "WANDSELECT":
                    var toolbox=UIManager.GetGump<DeveloperWandGump>();
                    if(toolbox==null || toolbox.IsDisposed)throw new InvalidOperationException("Developer toolbox missing");
                    Mouse.Position=a[0]=="WANDCLICK"?toolbox.ButtonPoint(command.Substring(10)):toolbox.EntryPoint(Arg(1),Arg(2));
                    Mouse.ButtonPress(MouseButtonType.Left);UIManager.OnMouseButtonDown(MouseButtonType.Left);
                    Mouse.ButtonRelease(MouseButtonType.Left);UIManager.OnMouseButtonUp(MouseButtonType.Left);
                    break;
                case "WANDFIELD":
                    var editor=UIManager.GetGump<DeveloperWandGump>();
                    if(editor==null || editor.IsDisposed)throw new InvalidOperationException("Developer toolbox missing");
                    editor.EnterField(a[1],string.Join(" ",a.Skip(2)));break;
                case "WANDTYPING":
                    if(!TrinsicDebug.Typing)throw new InvalidOperationException("Wand textbox does not own keyboard focus");
                    if(TrinsicSession.Walk(Direction.North))throw new InvalidOperationException("Typing allowed movement");
                    break;
                case "WANDTAB":
                    if(UIManager.GetGump<DeveloperWandGump>()?.Tab!=Arg())throw new InvalidOperationException("Wrong developer panel");break;
                case "WANDCREATED":
                    if(TrinsicDebug.NativeCreatedCount!=Arg())throw new InvalidOperationException("Unexpected debug-created count: "+TrinsicDebug.NativeCreatedCount);break;
                case "WANDUSELAST":
                    if(TrinsicDebug.Created.Length==0)throw new InvalidOperationException("No created debug object");
                    uint lastDebug=(uint)TrinsicDebug.Created.Last();
                    GameActions.DoubleClick(world,world.Mobiles.Get(lastDebug)!=null?lastDebug:0x40000000u|lastDebug);break;
                case "WANDUSEROOT":
                    if(TrinsicDebug.Created.Length==0)throw new InvalidOperationException("No created debug object");
                    uint rootDebug=(uint)TrinsicDebug.Created.First();
                    GameActions.DoubleClick(world,world.Mobiles.Get(rootDebug)!=null?rootDebug:0x40000000u|rootDebug);break;
                case "WANDRESULT":
                    if(TrinsicDebug.LastOutcome!=a[1])throw new InvalidOperationException("Developer command result: "+TrinsicDebug.LastOutcome+" "+TrinsicDebug.Message);break;
                case "FXSTATE": TrinsicSession.Send("AUDITFXSTATE",Arg(1),Arg(2)," "+(a.Length>3?a[3]:"0"));break;
                case "FXCOUNT":
                    if(TrinsicEffects.Counts.GetValueOrDefault(a[1])!=Arg(2)) throw new InvalidOperationException("Effect count "+a[1]+": "+TrinsicEffects.Counts.GetValueOrDefault(a[1]));
                    break;
                case "FXART":
                    foreach(ushort graphic in new ushort[]{0x376a,0x373a,0x375a,0x374a,0x3709,0x3728,0x3735,0x36cb,0x379f,0x37eb,0x36d4,0x398c,0x3915,0x3979,0x3946}) {
                        var spellArtBounds=Client.Game.UO.Arts.GetArt(graphic).UV;
                        if(spellArtBounds.Width==0 || spellArtBounds.Height==0) throw new InvalidOperationException("Missing spell art "+graphic.ToString("x"));
                    }
                    break;
                case "MODAL":
                    if(TrinsicSession.Header.Split(' ')[9]!=a[1]) throw new InvalidOperationException("Unexpected interaction mode: "+TrinsicSession.Header);
                    if(a[1]=="5" && (dialogue==null || dialogue.IsDisposed)) throw new InvalidOperationException("Missing original U7 display");
                    break;
                case "CREATUREART":
                    foreach(ushort body in Enumerable.Range(0,1024).Select(TrinsicCreatures.Body).Where(b=>b!=0).Distinct()) {
                        byte attack=TrinsicCreatures.Attack(body);
                        foreach(byte action in new byte[]{0,attack}) for(byte direction=0;direction<5;direction++)
                            if(Client.Game.UO.Animations.GetAnimationFrames(body,action,direction,out _,out _).Length==0)
                                throw new InvalidOperationException($"Missing creature animation {body}/{action}/{direction}");
                    }
                    break;
                case "CREATURE":
                    TrinsicSession.Send("AUDITCREATURE",Arg());
                    testCreature=int.Parse(TrinsicSession.Header.Split(' ')[5].Substring(9));
                    break;
                case "CREATURECHECK":
                    var creature=world.Mobiles.Get((uint)testCreature);
                    if(creature==null || creature.Graphic!=Arg() || creature.HitsMax==0)
                        throw new InvalidOperationException("Missing creature body or native health");
                    File.AppendAllText(path+".log",$"creature {testCreature} body {creature.Graphic} hits {creature.Hits}/{creature.HitsMax} name {creature.Name}\n");
                    break;
                case "ATTACKCREATURE": GameActions.Attack(world,(uint)testCreature);break;
                case "ACTIONCHECK":
                    if(TrinsicSession.PresentedActions==0) throw new InvalidOperationException("No native action was presented");
                    File.AppendAllText(path+".log",$"native actions {TrinsicSession.PresentedActions}\n");
                    break;
                case "PEACE": TrinsicSession.Send("WAR",0);break;
                case "BOOKCREATE":
                    TrinsicSession.Send("AUDITBOOK");
                    testBook=int.Parse(TrinsicSession.Header.Split(' ')[5].Substring(5));
                    break;
                case "BOOKOPEN": GameActions.DoubleClick(world,0x40000000u|(uint)testBook);break;
                case "BOOKCHECK":
                    if(dialogue is not SpellbookGump nativeBook || nativeBook.IsDisposed || nativeBook.TrinsicPage!=Arg(1) || nativeBook.IsMinimized!=(Arg(2)!=0))
                        throw new InvalidOperationException("Native UO spellbook page/minimized state mismatch");
                    break;
                case "BOOKCLICK":
                case "BOOKDOUBLE":
                case "BOOKRIGHT":
                    if(dialogue is not SpellbookGump || dialogue.IsDisposed) throw new InvalidOperationException("Missing UO spellbook");
                    Mouse.Position=new Point(dialogue.X+Arg(1),dialogue.Y+Arg(2));
                    MouseButtonType bookButton=a[0]=="BOOKRIGHT"?MouseButtonType.Right:MouseButtonType.Left;
                    Mouse.ButtonPress(bookButton); UIManager.OnMouseButtonDown(bookButton);
                    if(a[0]=="BOOKDOUBLE") UIManager.OnMouseDoubleClick(bookButton);
                    Mouse.ButtonRelease(bookButton); UIManager.OnMouseButtonUp(bookButton);
                    break;
                case "VIEWCLICK":
                    if(dialogue==null || dialogue.IsDisposed) throw new InvalidOperationException("Missing native controls");
                    Mouse.Position=new Point(dialogue.X+Arg(1)*2,dialogue.Y+Arg(2)*2);
                    Mouse.ButtonPress(MouseButtonType.Left); UIManager.OnMouseButtonDown(MouseButtonType.Left);
                    Mouse.ButtonRelease(MouseButtonType.Left); UIManager.OnMouseButtonUp(MouseButtonType.Left);
                    break;
                case "TARGETGROUND":
                    var tile=world.Map.GetTile(Arg(1),Arg(2));
                    while(tile!=null && tile is not Land) tile=tile.TNext;
                    if(tile==null) throw new InvalidOperationException("Missing ground target");
                    world.TargetManager.Target(tile.Graphic,tile.X,tile.Y,tile.Z);
                    break;
                case "DISMISS":
                    if(dialogue==null || dialogue.IsDisposed) throw new InvalidOperationException("No view to dismiss");
                    dialogue.OnButtonClick(0); break;
                case "ESCAPE":
                    TrinsicSession.Key(new SDL3.SDL.SDL_KeyboardEvent {key=(uint)SDL3.SDL.SDL_Keycode.SDLK_ESCAPE});break;
                case "PAPERDOLL":
                    GameActions.OpenPaperdoll(world,(uint)Arg());
                    break;
                case "TARGETING":
                    if(world.TargetManager.IsTargeting!=(Arg()!=0)) throw new InvalidOperationException("Target cursor mismatch");
                    break;
                case "TARGET":
                    if(!world.TargetManager.IsTargeting) throw new InvalidOperationException("Missing item target cursor");
                    if(Arg()==0) world.TargetManager.CancelTarget();
                    else world.TargetManager.Target(world.Mobiles.Get((uint)Arg())!=null?(uint)Arg():Item(1));
                    break;
                case "ABSENT":
                    if(world.Items.Get(Item(1))!=null) throw new InvalidOperationException("Item still exists: "+command);
                    break;
                case "SHAPECOUNT":
                    if(world.Items.Values.Where(i=>i.Container==Item(2) && i.TrinsicShape==Arg(1)).Sum(i=>i.Amount)!=Arg(3))
                        throw new InvalidOperationException("Wrong inventory quantity: "+command);
                    break;
                case "U7SHEET":
                    var u7sheet=UIManager.GetGump<PaperDollGump>(world.Player.Serial);
                    var ids=u7sheet.Children.OfType<Button>().Where(b=>!b.IsDisposed).Select(b=>b.ButtonID).Order().ToArray();
                    if(!ids.SequenceEqual(new[]{1,2,3,7,8,9}))throw new InvalidOperationException("Unrelated paperdoll buttons remain: "+string.Join(",",ids));
                    if(!u7sheet.Children.OfType<TrinsicPartyButton>().Any(b=>b.ButtonID==9 && b.ButtonGraphicNormal==0x07e2 && b.ButtonGraphicPressed==0x07e3) ||
                        u7sheet.Children.OfType<GumpPic>().Any(p=>!p.IsDisposed && p.Graphic==0x7d2))
                        throw new InvalidOperationException("Party button missing or old scroll remains");
                    break;
                case "PARTYOPEN":
                    var rosterSheet=UIManager.GetGump<PaperDollGump>(world.Player.Serial);
                    var partyButton=rosterSheet.Children.OfType<Button>().Single(b=>b.ButtonID==9);
                    UIManager.MakeTopMostGump(rosterSheet);
                    Mouse.Position=new Point(partyButton.ScreenCoordinateX+30,partyButton.ScreenCoordinateY+12);
                    Mouse.ButtonPress(MouseButtonType.Left);UIManager.OnMouseButtonDown(MouseButtonType.Left);
                    Mouse.ButtonRelease(MouseButtonType.Left);UIManager.OnMouseButtonUp(MouseButtonType.Left);
                    break;
                case "U7OPTIONS":
                    UIManager.GetGump<PaperDollGump>(world.Player.Serial).OnButtonClick(1);
                    if(UIManager.GetGump<TrinsicOptionsGump>()==null)throw new InvalidOperationException("U7 options missing");
                    break;
                case "U7OPTION":
                    var options=UIManager.GetGump<TrinsicOptionsGump>();
                    var option=options.Children.OfType<NiceButton>().Single(b=>b.ButtonParameter==Arg());
                    UIManager.MakeTopMostGump(options);
                    Mouse.Position=new Point(option.ScreenCoordinateX+30,option.ScreenCoordinateY+12);
                    Mouse.ButtonPress(MouseButtonType.Left);UIManager.OnMouseButtonDown(MouseButtonType.Left);
                    Mouse.ButtonRelease(MouseButtonType.Left);UIManager.OnMouseButtonUp(MouseButtonType.Left);
                    break;
                case "U7TOGGLE":
                    var optionMenu=UIManager.GetGump<TrinsicOptionsGump>();
                    var check=optionMenu.Children.OfType<Checkbox>().ElementAt(Arg());
                    bool beforeCheck=check.IsChecked;
                    UIManager.MakeTopMostGump(optionMenu);
                    Mouse.Position=new Point(check.ScreenCoordinateX+6,check.ScreenCoordinateY+6);
                    Mouse.ButtonPress(MouseButtonType.Left);UIManager.OnMouseButtonDown(MouseButtonType.Left);
                    Mouse.ButtonRelease(MouseButtonType.Left);UIManager.OnMouseButtonUp(MouseButtonType.Left);
                    if(check.IsChecked==beforeCheck)throw new InvalidOperationException("Option did not toggle");
                    break;
                case "U7PREFERENCES":
                    var pref=ProfileManager.CurrentProfile;
                    if(pref.UseCircleOfTransparency!=(Arg(1)!=0) || pref.EnableMousewheelScaleZoom!=(Arg(2)!=0) || pref.AlwaysRun!=(Arg(3)!=0))
                        throw new InvalidOperationException("U7 preferences differ");
                    break;
                case "U7LOADANSWER":
                    (UIManager.GetGump<QuestionGump>() ?? throw new InvalidOperationException("Load confirmation missing")).OnButtonClick(Arg());
                    break;
                case "U7ADVANCED":
                    (UIManager.GetGump<OptionsGump>() ?? throw new InvalidOperationException("Advanced settings missing")).Dispose();
                    break;
                case "U7STATUS":
                    var statusLabels=StatusGumpBase.GetStatusGump().Children.OfType<Label>().Select(l=>l.Text).ToArray();
                    if(statusLabels.Contains(world.Player.Title) || statusLabels.Contains("War") || statusLabels.Contains("Peace") ||
                        !new[]{"Strength","Dexterity","Intelligence","Health","Combat","Magic","Mana","Experience","Level","Training","Weight","Gold"}.All(statusLabels.Contains))
                        throw new InvalidOperationException("Status content differs");
                    break;
                case "PARTYSELECT":
                    var roster=UIManager.GetGump<TrinsicPartyGump>();
                    if(roster==null || UIManager.GetGump<PartyGump>()!=null)throw new InvalidOperationException("Native party roster missing or UO party menu opened");
                    int memberIndex=Array.FindIndex(TrinsicSession.RosterMembers,m=>m.Serial==(uint)Arg(1));
                    if(memberIndex<0)throw new InvalidOperationException("Native companion absent from roster");
                    int memberButton=100+memberIndex*2+(a[2]=="pack"?1:0);
                    var rosterButton=roster.Children.OfType<Button>().First(b=>b.ButtonID==memberButton);
                    UIManager.MakeTopMostGump(roster);
                    Mouse.Position=new Point(rosterButton.ScreenCoordinateX+5,rosterButton.ScreenCoordinateY+5);
                    Mouse.ButtonPress(MouseButtonType.Left);UIManager.OnMouseButtonDown(MouseButtonType.Left);
                    Mouse.ButtonRelease(MouseButtonType.Left);UIManager.OnMouseButtonUp(MouseButtonType.Left);
                    break;
                case "PARTYPANELS":
                    var companion=world.Mobiles.Get((uint)Arg());
                    var companionSheet=UIManager.GetGump<PaperDollGump>(companion.Serial);
                    var companionBag=companion.FindItemByLayer(Layer.Backpack);
                    var companionPack=companionBag==null?null:UIManager.GetGump<ContainerGump>(companionBag.Serial);
                    if(companionSheet?.CanLift!=true || companionPack==null ||
                       companionSheet.IsDisposed || companionPack.IsDisposed ||
                       !companionPack.Children.OfType<ItemGump>().Any() ||
                       companion.FindItemByLayer(Layer.Torso)==null)
                        throw new InvalidOperationException("Missing companion equipment or inventory");
                    break;
                case "PARTYTALK":
                    if(UIManager.GetGump<PaperDollGump>((uint)Arg())==null || dialogue==null || dialogue.IsDisposed)
                        throw new InvalidOperationException("Companion double-click must open dialogue and paperdoll");
                    break;
                case "PICK": if(!GameActions.PickUp(world,Item(1),0,0)) throw new InvalidOperationException("pickup refused");break;
                case "GUMPDROP": chest.DropHeldLocalItem();break;
                case "DROP":
                    if(!Client.Game.UO.GameCursor.ItemHold.Enabled) throw new InvalidOperationException("empty cursor");
                    GameActions.DropItem(Client.Game.UO.GameCursor.ItemHold.Serial,40,60,0,Item(1));break;
                case "CLOSE": chest?.Dispose(); break;
                case "GEOGRAPHY":
                    var input=dialogue?.Children.OfType<StbTextBox>().Single();
                    string question=dialogue?.Children.OfType<Label>().First().Text ?? "";
                    int answer=question.Contains("Spektran") || question.Contains("Terfin") ? 120 :
                        question.Contains("Dagger") ? 0 :
                        question.Contains("Skara") && question.Contains("latitude") ? 30 :
                        question.Contains("Buccaneer") || question.Contains("Skara") || question.Contains("Deep Forest") ? 60 :
                        throw new InvalidOperationException("Unknown map question: "+question);
                    input.SetText(answer.ToString());
                    dialogue.OnKeyboardReturn(0,input.Text);
                    break;
                case "NUMBER":
                    var numberInput=dialogue?.Children.OfType<StbTextBox>().Single() ?? throw new InvalidOperationException("No native number prompt");
                    numberInput.SetText(Arg().ToString());
                    dialogue.OnKeyboardReturn(0,numberInput.Text);
                    break;
                case "ANSWER": if(dialogue==null) throw new InvalidOperationException("no prompt"); dialogue.OnButtonClick(Arg());break;
                case "REPLY":case "REPLYSYNC":
                    if(!live || Arg()!=batch) throw new InvalidOperationException("Unexpected live replay acknowledgement");
                    string reply=a[0]=="REPLYSYNC"?observedFrame:resultFrame;
                    if(reply==null) throw new InvalidOperationException("Replay action did not reach the native engine");
                    File.WriteAllText(path+".reply.tmp",batch+"\n"+reply);
                    File.Move(path+".reply.tmp",path+".reply."+batch);
                    break;
                case "U7AUDIO":
                    UIManager.GetGump<TrinsicOptionsGump>()?.OnButtonClick(5);break;
                case "U7AUDIOSET":
                    var audioPanel=UIManager.GetGump<TrinsicAudioGump>() ?? throw new InvalidOperationException("No audio panel");
                    var audioChecks=audioPanel.Children.OfType<Checkbox>().ToArray();
                    var audioSliders=audioPanel.Children.OfType<HSliderBar>().ToArray();
                    for(int i=0;i<3;i++){audioChecks[i].IsChecked=Arg(1+i)!=0;audioSliders[i].Value=Arg(4+i);}
                    break;
                case "U7AUDIOFOLDER":
                    if(!TrinsicAudio.SetFolder(world,string.Join(" ",a.Skip(1)),out string folderResult))throw new InvalidOperationException(folderResult);
                    break;
                case "U7AUDIOACK":
                    if(TrinsicAudio.Acknowledged!=string.Join(" ",a.Skip(1)))throw new InvalidOperationException("Native audio preferences: "+TrinsicAudio.Acknowledged);break;
                case "U7AUDIOCREDITS":UIManager.GetGump<TrinsicAudioGump>().OnButtonClick(4);break;
                case "U7CREDITSCLOSE":UIManager.GetGump<MessageBoxGump>()?.Dispose();break;
                case "U7AUDIOCHECK":
                    if(!TrinsicAudio.Status.Contains(string.Join(" ",a.Skip(1))))throw new InvalidOperationException(TrinsicAudio.Status);
                    break;
                case "U7AUDIOTYPING":
                    UIManager.KeyboardFocusControl=UIManager.GetGump<TrinsicAudioGump>().Children.OfType<StbTextBox>().Single();
                    if(TrinsicSession.Walk((Direction)0,false) || TrinsicSession.Key(new SDL3.SDL.SDL_KeyboardEvent{key=(uint)SDL3.SDL.SDL_Keycode.SDLK_LEFT}))throw new InvalidOperationException("Audio typing moved the player");
                    UIManager.KeyboardFocusControl=null;break;
                case "U7AUDIOCLOSE":UIManager.GetGump<TrinsicAudioGump>()?.Dispose();break;
                case "U7SAVES":UIManager.GetGump<TrinsicOptionsGump>()?.OnButtonClick(6);break;
                case "U7SAVEBUTTON":UIManager.GetGump<TrinsicSavesGump>().OnButtonClick(Arg());break;
                case "U7SAVEACTIVE":if(TrinsicAudio.ActiveSlot!=Arg())throw new InvalidOperationException("Wrong active save");break;
                case "U7SAVECLOSE":UIManager.GetGump<TrinsicSavesGump>()?.Dispose();break;
                case "U7SAVEKEY":TrinsicSession.Key(new SDL3.SDL.SDL_KeyboardEvent{key=(uint)SDL3.SDL.SDL_Keycode.SDLK_F5});break;
                case "U7LOADKEY":TrinsicSession.Key(new SDL3.SDL.SDL_KeyboardEvent{key=(uint)SDL3.SDL.SDL_Keycode.SDLK_F9});break;
                case "U7AUDIOWIRE":
                    TrinsicSession.Send("AUDIO",Arg(1),Arg(2)," "+string.Join(" ",a.Skip(3)));break;
                case "RECONNECT":TrinsicSession.Reconnect();break;
                case "DUP":TrinsicSession.Duplicate();break;
                case "STALE":TrinsicSession.Stale();break;
                case "BEGIN":case "SAVE":case "LOAD":TrinsicSession.Send(a[0]);break;
                case "ARROWDOWN":
                    TrinsicSession.Key(new SDL3.SDL.SDL_KeyboardEvent { key=(uint)Enum.Parse<SDL3.SDL.SDL_Keycode>("SDLK_"+a[1]) });
                    break;
                case "ARROWUP":
                    TrinsicSession.ReleaseArrow(Enum.Parse<SDL3.SDL.SDL_Keycode>("SDLK_"+a[1]));
                    break;
                case "F7":
                    TrinsicSession.Key(new SDL3.SDL.SDL_KeyboardEvent { key=(uint)SDL3.SDL.SDL_Keycode.SDLK_F7 });
                    break;
                case "CAPTURE": Client.Game.TakeScreenshot();break;
                case "OVERLAY": TrinsicSession.Overlay=true;break;
                case "WAIT":due=Environment.TickCount64+Arg();break;
                case "EXIT":Client.Game.Exit();break;
            }
            var held=Client.Game.UO.GameCursor.ItemHold;
            world.Items.TryGetValue(0x40000000u|9968,out var tongs);
            File.AppendAllText(path+".log",$"{command} | {TrinsicSession.Header} | display {world.Player.X} {world.Player.Y} {world.Player.Z} iolo {TrinsicSession.IoloX} {TrinsicSession.IoloY} zoom {Client.Game.Scene.Camera.Zoom} cursor {held.Enabled} parent {tongs?.Container} chest {chest?.IsDisposed} dialogue {dialogue?.IsDisposed}\n");
        }
    }
}

