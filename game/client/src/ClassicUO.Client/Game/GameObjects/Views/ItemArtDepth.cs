// SPDX-License-Identifier: BSD-2-Clause

using ClassicUO.Renderer;
using Microsoft.Xna.Framework;
using Microsoft.Xna.Framework.Graphics;

namespace ClassicUO.Game.GameObjects
{
    internal partial class Item
    {
        internal float FittedFaceDepth;

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
