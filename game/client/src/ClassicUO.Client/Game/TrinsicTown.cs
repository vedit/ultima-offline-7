using System;
using System.Collections.Generic;
using System.IO;
using ClassicUO.Configuration;
using ClassicUO.Game.Data;
using ClassicUO.Game.GameObjects;

namespace ClassicUO.Game
{
    internal static class TrinsicTown
    {
        internal static readonly string Folder = Environment.GetEnvironmentVariable("TRINSIC_TOWN");
        private static readonly Dictionary<(int,int),ushort> graphics = new();
        private static readonly Dictionary<ushort,(int cut,int left,int right)> artDepth = new();
        internal static (int cut,int left,int right) ArtDepth(ushort graphic) => artDepth.GetValueOrDefault(graphic);
        private static readonly Dictionary<ushort,Microsoft.Xna.Framework.Point> artOffsets = new();
        internal static Microsoft.Xna.Framework.Point ArtOffset(ushort graphic) => artOffsets.GetValueOrDefault(graphic);
        private static readonly Dictionary<(int x,int y,int lift),int> furnitureWalls = new();
        internal static int FurnitureWall(int shape,int x,int y,int lift)
            => shape==890 && x==968 && y==2317 && lift==0 ? 3
                : shape is 407 or 633 or 847 or 890 or 971 or 1000 or 1003 or 1018
                ? furnitureWalls.GetValueOrDefault((x,y,lift)) : 0;
        private static readonly Dictionary<(int,int),ushort> carriedGraphics = new();
        private static readonly Dictionary<(int shape,bool female,Layer hand),ushort> handGumps=new();
        private static readonly Dictionary<int,ushort> weaponGraphics=new();
        private static readonly Dictionary<(int,int,bool,Layer),ushort> stateGumps=new();
        internal static bool HasHandArt(Item item) => weaponGraphics.ContainsKey(item.TrinsicShape);
        internal static ushort HandGump(Item item, bool female, Layer layer) =>
            item==null ? (ushort)0 : stateGumps.TryGetValue((item.TrinsicShape,item.TrinsicFrame & 31,female,layer),out ushort state)
                ? state : handGumps.GetValueOrDefault((item.TrinsicShape,female,layer));
        private static readonly Dictionary<(int,int,int,int,int),ushort> placedGraphics = new();
        private static readonly Dictionary<int,string> names = new();
        private static readonly Dictionary<int,List<(ushort body,ushort skin,Layer layer,ushort graphic,ushort hue)>> outfits = new();
        private static readonly HashSet<(int,int,int,int,int)> fixedRoofs = new();
        internal static bool Enabled => !Intro.U7DreamIntroScene.Active && !string.IsNullOrEmpty(Folder);
        internal const uint MantleSerial = 0x7fff0001;
        internal const string MantleName = "Avatar's mantle";
        private static readonly Dictionary<Layer,Item> mantleLayers=new();
        private static World mantleWorld;
        private static readonly Dictionary<int,(ushort graphic,ushort hue)> chestArmArt=new() { [666]=(0x1410,0x08AB) };
        private static readonly Dictionary<int,Item> chestArmLayers=new();

        internal static bool WearingMantle(Entity entity) =>
            Enabled && entity is PlayerMobile && ProfileManager.CurrentProfile?.TrinsicAvatarMantleEquipped==true
            && entity.World.Items.Get(MantleSerial)?.Container==entity.Serial;

        internal static Item VisibleLayer(Entity entity,Layer layer)
        {
            if(!WearingMantle(entity) || layer is Layer.Hair or Layer.Mount or Layer.Backpack or Layer.OneHanded or Layer.TwoHanded)
                return entity.FindItemByLayer(layer);
            return mantleLayers.GetValueOrDefault(layer);
        }

        internal static void PrepareMantle(World world)
        {
            if(mantleWorld==world) return;
            mantleLayers.Clear();
            // The cuirass owns this animation. It has no inventory or paperdoll slot.
            chestArmLayers.Clear();
            foreach(var pair in chestArmArt) {
                var arms=Item.Create(world,MantleSerial);
                arms.Graphic=pair.Value.graphic;
                arms.Hue=pair.Value.hue;
                arms.Layer=Layer.Arms;
                arms.Amount=1;
                chestArmLayers.Add(pair.Key,arms);
            }
            foreach(var part in outfits[721]) {
                if(part.layer==Layer.Hair) continue;
                // Drawing proxies never enter the equipment list or the native save.
                var item=Item.Create(world,MantleSerial);
                item.Graphic=part.graphic; item.Hue=part.hue; item.Layer=part.layer;
                item.Amount=1;
                mantleLayers.Add(part.layer,item);
            }
            mantleWorld=world;
        }

        internal static Item WorldLayer(Entity entity,Layer layer)
        {
            if (layer==Layer.Arms && Enabled && entity.World==mantleWorld &&
                VisibleLayer(entity,Layer.Torso) is Item chest &&
                chestArmLayers.TryGetValue(chest.TrinsicShape,out var arms))
                return arms;
            return VisibleLayer(entity,layer);
        }

        private static readonly HashSet<(int,int)> gridFrames=new();
        internal static bool FitsGrid(int shape,int frame) => gridFrames.Contains((shape,frame));
        private static readonly Dictionary<(int,int,int),(ushort open,ushort closed)> windowFittings=new();
        private static readonly Dictionary<ushort,ushort> windowAliases=new();
        internal static bool IsFittedShutter(int shape,int x,int y,int lift)
            => (shape is 290 or 291 or 322 or 372) && windowFittings.ContainsKey((x,y,lift));

        internal static float ShutterDepth(int shape,int x,int y,int lift)
        {
            if (!(shape is 290 or 291 or 322 or 372) || !windowFittings.TryGetValue((x,y,lift),out var fit))
                return 0;
            // A full wall replaces the native shutter. Its outward face may
            // share a compact cell with furniture one native step inside.
            int across = fit.open is 14 or 0x22 or 0x13a ? y : x;
            return (across & 1) != 0 ? 0.25f : -0.25f;
        }
        private static bool compact;
        internal static bool Compact { get => compact && !Intro.U7DreamIntroScene.Active; private set => compact=value; }

        internal static ushort BedroomCutaway(Static scenery)
        {
            // From inside Klog and Ellen's bedroom the east wall and the
            // tree beyond it cross both the bed and its mouse target.
            if (!Compact || scenery.Z != 0 ||
                scenery.World.Player?.NativePosition is not { X: > 1028 and < 1039, Y: > 2192 and < 2208 } ||
                scenery.World.Player.Z != 0)
                return 0;

            if (scenery.X == 519 && scenery.Y is >= 1097 and <= 1103 &&
                (scenery.Graphic is 0x1B or 0x23 || windowAliases.GetValueOrDefault(scenery.Graphic)==0x23))
                return 0x32; // Matching low stone course along the east wall.
            if (scenery.X == 521 && scenery.Y == 1099 && graphics.GetValueOrDefault((453,1)) == scenery.Graphic)
                return Constants.TREE_REPLACE_GRAPHIC;
            return 0;
        }

        // The two native positions on either axis are a quarter-tile to either
        // side of the UO centre. Keep both positions individually pickable.
        internal static Microsoft.Xna.Framework.Point Subtile(int x,int y)
            => new(11*((x&1)-(y&1)),11*((x&1)+(y&1)-1));

        internal static int WallAxis(int shape,int frame)
        {
            int axis = shape switch { 849 or 657 or 282 => 1, 293 or 678 or 821 => -1, _ => 0 };
            return (frame & 32) == 0 ? axis : -axis;
        }

        internal static Microsoft.Xna.Framework.Point NativeGround(int x,int y)
        {
            var hit=SelectedObject.Object as GameObject;
            if(hit!=null && hit.X==x && hit.Y==y) {
                if(hit is Entity e && e.NativePosition is Microsoft.Xna.Framework.Point p) return p;
                var m=SelectedObject.TranslatedMousePositionByViewport;
                int dx=m.X-hit.RealScreenPosition.X-22,dy=m.Y-hit.RealScreenPosition.Y-22;
                return new(2*x+(dx+dy>=0?1:0),2*y+(dy-dx>=0?1:0));
            }
            return new(Math.Clamp(TrinsicSession.CameraX,2*x,2*x+1),
                       Math.Clamp(TrinsicSession.CameraY,2*y,2*y+1));
        }
        internal static void Load()
        {
            if (!Enabled) return;
            string armsFile=Path.Combine(Folder,"weapon-gumps","chest-arms.tsv");
            if(File.Exists(armsFile))
                foreach(string line in File.ReadLines(armsFile)) {
                    var fields=Array.ConvertAll(line.Split('\t'),int.Parse);
                    chestArmArt[fields[0]]=((ushort)fields[1],(ushort)fields[2]);
                }
            string states=Path.Combine(Folder,"weapon-gumps","states.tsv");
            if(File.Exists(states))
                foreach(string line in File.ReadLines(states)) {
                    var v=Array.ConvertAll(line.Split('\t'),int.Parse);
                    stateGumps[(v[0],v[1],v[2]!=0,(Layer)v[3])]=(ushort)v[4];
                    weaponGraphics.TryAdd(v[0],(ushort)v[5]);
                }
            string hands=Path.Combine(Folder,"weapon-gumps","hands.tsv");
            if(File.Exists(hands))
                foreach(string line in File.ReadLines(hands)) {
                    var fields=Array.ConvertAll(line.Split('\t'),int.Parse);
                    handGumps[(fields[0],fields[1]!=0,(Layer)fields[2])]=(ushort)fields[3];
                    weaponGraphics[fields[0]]=(ushort)fields[4];
                }
            foreach (string line in File.ReadLines(Path.Combine(Folder,"graphics.tsv"))) {
                var f=line.Split('\t');
                graphics[(int.Parse(f[0]),int.Parse(f[1]))]=ushort.Parse(f[2]);
            }
            string windowFile=Path.Combine(Folder,"window-fittings.tsv");
            string aliasFile=Path.Combine(Folder,"window-aliases.tsv");
            if(File.Exists(aliasFile))
                foreach(string line in File.ReadLines(aliasFile)) {
                    var v=Array.ConvertAll(line.Split('\t'),ushort.Parse);
                    windowAliases[v[0]]=v[1];
                }
            if(File.Exists(windowFile))
                foreach(string line in File.ReadLines(windowFile)) {
                    var v=Array.ConvertAll(line.Split('\t'),int.Parse);
                    windowFittings[(v[0],v[1],v[2])]=((ushort)v[3],(ushort)v[4]);
                }
            string carriedFile=Path.Combine(Folder,"carried-graphics.tsv");
            if(File.Exists(carriedFile)) {
                foreach(string line in File.ReadLines(carriedFile)) {
                    var fields=line.Split('\t');
                    carriedGraphics[(int.Parse(fields[0]),int.Parse(fields[1]))]=ushort.Parse(fields[2]);
                }
            }
            string roofFile=Path.Combine(Folder,"fixed-roofs.tsv");
            Compact=File.Exists(Path.Combine(Folder,"baked-world.tsv"));
            if(Compact) {
                string offsetFile=Path.Combine(Folder,"art-offsets.tsv");
                if(File.Exists(offsetFile))
                    foreach(string line in File.ReadLines(offsetFile)) {
                        var v=Array.ConvertAll(line.Split('\t'),int.Parse);
                        artOffsets[(ushort)v[0]]=new(v[1],v[2]);
                    }
                string wallFile=Path.Combine(Folder,"furniture-walls.tsv");
                if(File.Exists(wallFile))
                    foreach(string line in File.ReadLines(wallFile)) {
                        var v=Array.ConvertAll(line.Split('\t'),int.Parse);
                        furnitureWalls[(v[0],v[1],v[2])]=v[3];
                    }
                string depthFile=Path.Combine(Folder,"art-depth.tsv");
                if(File.Exists(depthFile))
                    foreach(string line in File.ReadLines(depthFile)) {
                        var v=Array.ConvertAll(line.Split('\t'),int.Parse);
                        artDepth[(ushort)v[0]]=(v[1],v[2],v[3]);
                    }
                roofFile=Path.Combine(Folder,"baked-world.tsv");
                foreach(string line in File.ReadLines(Path.Combine(Folder,"grid-frames.tsv"))) {
                    var v=Array.ConvertAll(line.Split('\t'),int.Parse);
                    gridFrames.Add((v[0],v[1]));
                }
            }
            if(File.Exists(roofFile))
                foreach(string line in File.ReadLines(roofFile)) {
                    var v=Array.ConvertAll(line.Split('\t'),int.Parse);
                    fixedRoofs.Add((v[0],v[1],v[2],v[3],v[4]));
                }
            string placedFile=Path.Combine(Folder,"world-facings.tsv");
            if(File.Exists(placedFile)) {
                foreach(string line in File.ReadLines(placedFile)) {
                    var values=Array.ConvertAll(line.Split('\t'),int.Parse);
                    placedGraphics[(values[0],values[1],values[2],values[3],values[4])]=(ushort)values[5];
                }
            }
            foreach (string line in File.ReadLines(Path.Combine(Folder,"actors.tsv"))) {
                var f=line.Split('\t');
                names[int.Parse(f[0])]=f[1];
            }
            foreach (string line in File.ReadLines(Path.Combine(Folder,"outfits.csv"))) {
                if(line.StartsWith("u7_shape")) continue;
                var f=line.Split(',');
                int shape=int.Parse(f[0]);
                if(!outfits.TryGetValue(shape,out var items)) outfits[shape]=items=new();
                items.Add((Convert.ToUInt16(f[2],16),Convert.ToUInt16(f[3],16),(Layer)int.Parse(f[5]),Convert.ToUInt16(f[6],16),Convert.ToUInt16(f[^1],16)));
            }
        }

        internal static ushort Graphic(int shape,int frame,int x,int y,int lift,bool onGround)
        {
            // Spellbooks may be learned/acquired outside the town's source census.
            if(shape==761) return 0x0efa;
            // Native TEXT.FLX reagent order; the town census contains no loose reagents.
            if(shape==842 && frame>=0 && frame<8) return frame switch {
                0=>0x0f7a,1=>0x0f7b,2=>0x0f88,3=>0x0f86,
                4=>0x0f84,5=>0x0f85,6=>0x0f8d,_=>0x0f8c
            };
            if(onGround && IsFittedShutter(shape,x,y,lift)) {
                var fit=windowFittings[(x,y,lift)];
                return shape is 290 or 291 ? fit.closed : fit.open;
            }
            if(onGround && fixedRoofs.Contains((shape,frame,x,y,lift))) return 0;
            if(onGround && placedGraphics.TryGetValue((shape,frame,x,y,lift),out ushort placed))
                return placed;
            if(!onGround && carriedGraphics.TryGetValue((shape,frame),out ushort carried))
                return carried;
            ushort graphic=graphics.GetValueOrDefault((shape,frame));
            return graphic!=0 ? graphic : weaponGraphics.GetValueOrDefault(shape);
        }
        internal static ushort MappedBody(int shape)
        {
            ushort body=TrinsicCreatures.Body(shape);
            return body!=0?body:outfits.TryGetValue(shape,out var parts) && parts.Count>0?parts[0].body:(ushort)0;
        }
        internal static void AvatarHair(World world,Mobile avatar)
        {
            if(avatar.FindItemByLayer(Layer.Hair)!=null) return;
            var hair=world.GetOrCreateItem(0x60000000u|(avatar.Serial<<5)|(uint)Layer.Hair);
            avatar.PushToBack(hair); hair.Container=avatar.Serial;
            hair.Layer=Layer.Hair; hair.Graphic=0x203c; hair.Hue=0x0460; hair.Amount=1;
        }
        internal static string Name(int npc) => names.GetValueOrDefault(npc,"Traveller");
        internal static void Dress(World world,Mobile mob,int shape,bool nativeEquipment=false)
        {
            if(!outfits.TryGetValue(shape,out var items)) return;
            foreach (var part in items) {
                mob.Graphic=part.body;
                mob.Hue=part.skin;
                uint id=0x60000000u | (mob.Serial<<5) | (uint)part.layer;
                if(nativeEquipment && part.layer!=Layer.Hair && part.layer!=Layer.Beard) {
                    if(world.Items.Get(id)!=null) world.RemoveItem(id,true);
                    continue;
                }
                Item item=world.GetOrCreateItem(id);
                if(item.Container!=mob.Serial) {
                    world.RemoveItemFromContainer(item);
                    mob.PushToBack(item);
                    item.Container=mob.Serial;
                }
                item.Layer=part.layer;
                item.Graphic=part.graphic;
                item.Hue=part.hue;
                item.Amount=1;
            }
        }
    }
}
