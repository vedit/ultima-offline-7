using System;
using System.Collections.Generic;
using System.IO;
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
        private static readonly Dictionary<(int x,int y,int lift),int> furnitureWalls = new();
        internal static int FurnitureWall(int shape,int x,int y,int lift)
            => shape is 407 or 633 or 847 or 890 or 971 or 1000 or 1003 or 1018
                ? furnitureWalls.GetValueOrDefault((x,y,lift)) : 0;
        private static readonly Dictionary<(int,int),ushort> carriedGraphics = new();
        private static readonly Dictionary<(int,int,int,int,int),ushort> placedGraphics = new();
        private static readonly Dictionary<int,string> names = new();
        private static readonly Dictionary<int,List<(ushort body,ushort skin,Layer layer,ushort graphic,ushort hue)>> outfits = new();
        private static readonly HashSet<(int,int,int,int,int)> fixedRoofs = new();
        internal static bool Enabled => !string.IsNullOrEmpty(Folder);

        private static readonly HashSet<(int,int)> gridFrames=new();
        internal static bool FitsGrid(int shape,int frame) => gridFrames.Contains((shape,frame));
        private static readonly Dictionary<(int,int,int),(ushort open,ushort closed)> windowFittings=new();
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
        internal static bool Compact { get; private set; }

        // The two native positions on either axis are a quarter-tile to either
        // side of the UO centre. Keep both positions individually pickable.
        internal static Microsoft.Xna.Framework.Point Subtile(int x,int y)
            => new(11*((x&1)-(y&1)),11*((x&1)+(y&1)-1));

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
            foreach (string line in File.ReadLines(Path.Combine(Folder,"graphics.tsv"))) {
                var f=line.Split('\t');
                graphics[(int.Parse(f[0]),int.Parse(f[1]))]=ushort.Parse(f[2]);
            }
            string windowFile=Path.Combine(Folder,"window-fittings.tsv");
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
            if(onGround && IsFittedShutter(shape,x,y,lift)) {
                var fit=windowFittings[(x,y,lift)];
                return shape is 290 or 291 ? fit.closed : fit.open;
            }
            if(onGround && fixedRoofs.Contains((shape,frame,x,y,lift))) return 0;
            if(onGround && placedGraphics.TryGetValue((shape,frame,x,y,lift),out ushort placed))
                return placed;
            if(!onGround && carriedGraphics.TryGetValue((shape,frame),out ushort carried))
                return carried;
            return graphics.GetValueOrDefault((shape,frame));
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
