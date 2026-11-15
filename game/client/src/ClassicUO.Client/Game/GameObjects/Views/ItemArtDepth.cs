// SPDX-License-Identifier: BSD-2-Clause

using ClassicUO.Renderer;
using Microsoft.Xna.Framework;
using Microsoft.Xna.Framework.Graphics;

namespace ClassicUO.Game.GameObjects
{
    internal partial class Item
    {
        internal int TrinsicShape;
        internal int TrinsicFrame;
        internal float FittedFaceDepth;
        internal int FurnitureWall;
        internal Point? WorkSurface;
        internal int WorkSurfaceDrop;
        internal int EaselAxis;

        // The opaque sprite may span the preceding wall bay. Both drawing and
        // picking use that bay's depth for the part of the tabletop behind it.
        private int FurnitureBay(int dx)
        {
            if (EaselAxis != 0)
            {
                // The canvas can cross into the next back-wall bay while its
                // feet remain on the interior subtile. Keep both sides visible.
                return System.Math.Max(0,(int)System.Math.Ceiling((EaselAxis*dx)/22.0));
            }
            int along = FurnitureWall switch { 1 => dx, 2 => -dx-1, _ => System.Math.Min(dx,-dx-1) };
            return System.Math.Min(0,(int)System.Math.Floor((along+22)/22.0));
        }

        internal float FurnitureDepth(int dx) => X+Y+FurnitureBay(dx)+(127+Z)*0.01f+(EaselAxis!=0 ? 0.02f : -0.3f);

        private void DrawFurniture(UltimaBatcher2D batcher,int x,int y,Vector3 hue)
        {
            ref readonly var art = ref Client.Game.UO.Arts.GetArt(DisplayedGraphic);
            if (art.Texture == null) return;
            int origin = (int)Offset.X-art.UV.Width/2;
            for (int start=0;start<art.UV.Width;)
            {
                int bay=FurnitureBay(origin+start), end=start+1;
                while (end<art.UV.Width && FurnitureBay(origin+end)==bay) end++;
                var source=new Rectangle(art.UV.X+start,art.UV.Y,end-start,art.UV.Height);
                var dest=new Vector2(x+22-art.UV.Width/2+start,y+44-art.UV.Height);
                batcher.Draw(art.Texture,dest,source,hue,0f,Vector2.Zero,Vector2.One,
                             SpriteEffects.None,FurnitureDepth(origin+start)+0.5f);
                start=end;
            }
        }

        // Picking is already alpha-tested against the complete sprite. Resolve
        // which leaf contributed the pixel using the same cut as the draw call.
        internal int DoorDepthAt(int viewportX)
        {
            var profile = TrinsicTown.ArtDepth(DisplayedGraphic);
            if (profile.cut == 0) return 0;
            int width = Client.Game.UO.Arts.GetArt(DisplayedGraphic).UV.Width;
            int column = viewportX - RealScreenPosition.X - (int)Offset.X - 22 + width / 2;
            return column < profile.cut ? profile.left : profile.right;
        }

        private bool DrawDoorLeaves(UltimaBatcher2D batcher, int x, int y, Vector3 hue, float depth)
        {
            var profile = TrinsicTown.ArtDepth(DisplayedGraphic);
            if (profile.cut == 0) return false;
            ref readonly var art = ref Client.Game.UO.Arts.GetArt(DisplayedGraphic);
            if (art.Texture == null) return true;
            var bounds = art.UV;
            var texture = art.Texture;
            void DrawLeaf(int start, int end, int depthOffset)
            {
                var source = new Rectangle(bounds.X + start, bounds.Y, end - start, bounds.Height);
                var position = new Vector2(x + 22 - bounds.Width / 2 + start, y + 44 - bounds.Height);
                batcher.Draw(texture, position, source, hue, 0f, Vector2.Zero, Vector2.One,
                             SpriteEffects.None, depth + depthOffset + 0.5f);
            }
            DrawLeaf(0, profile.cut, profile.left);
            DrawLeaf(profile.cut, bounds.Width, profile.right);
            return true;
        }
    }
}
