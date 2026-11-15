// SPDX-License-Identifier: BSD-2-Clause
using ClassicUO.Game.Scenes;
using ClassicUO.Renderer;
using Microsoft.Xna.Framework;

namespace ClassicUO.Game.UI.Controls
{
    internal sealed class TrinsicPartyButton : Button
    {
        private readonly Label caption;

        internal TrinsicPartyButton(int id) : base(id, 0x07e2, 0x07e3, 0x07e4)
        {
            ButtonAction = ButtonAction.Activate;
            WantUpdateSize = false;
            ContainsByBounds = true;
            caption = new Label("PARTY", false, 0x386, font: 1);
            Add(caption);
        }

        public override bool AddToRenderLists(RenderLists lists, int x, int y, ref float depth)
        {
            if (IsDisposed) return false;
            ushort graphic = IsClicked ? ButtonGraphicPressed : MouseIsOver ? ButtonGraphicOver : ButtonGraphicNormal;
            ref readonly var info = ref Client.Game.UO.Gumps.GetGump(graphic);
            var texture = info.Texture;
            if (texture == null) return false;
            var uv = info.UV;
            var hue = ShaderHueTranslator.GetHueVector(Hue, false, Alpha, true);
            float layer = depth;
            // Stock blue ovals have baked-in words. Reuse their untouched end
            // caps and a clean blue strip, with a normal client text caption.
            // No replacement art, recolouring or resized ornamental frame.
            const int cap = 12;
            lists.AddGumpWithAtlas(batcher =>
            {
                batcher.Draw(texture, new Rectangle(x, y, cap, Height),
                    new Rectangle(uv.X, uv.Y, cap, uv.Height), hue, layer);
                batcher.Draw(texture, new Rectangle(x + cap, y, Width - 2 * cap, Height),
                    new Rectangle(uv.X + cap - 1, uv.Y, 1, uv.Height), hue, layer);
                batcher.Draw(texture, new Rectangle(x + Width - cap, y, cap, Height),
                    new Rectangle(uv.Right - cap, uv.Y, cap, uv.Height), hue, layer);
                return true;
            });
            depth += CHILD_LAYER_INCREMENT;
            return caption.AddToRenderLists(lists, x + (Width - caption.Width) / 2,
                y + (Height - caption.Height) / 2 + (IsClicked ? 1 : 0), ref depth);
        }
    }
}
