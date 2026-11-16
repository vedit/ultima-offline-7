// SPDX-License-Identifier: BSD-2-Clause
using ClassicUO.Game.Scenes;
using ClassicUO.Renderer;
using Microsoft.Xna.Framework;

namespace ClassicUO.Game.UI.Controls
{
    internal sealed class TrinsicPartyButton : Button
    {
        internal TrinsicPartyButton(int id) : base(id, 0x07e2, 0x07e3, 0x07e4)
        {
            ButtonAction = ButtonAction.Activate;
            WantUpdateSize = false;
            ContainsByBounds = true;
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
            // Keep the entire stock oval at native size. Clear only the baked
            // CHAT lettering inside it; stretching a full-height strip also
            // stretched the gold rim into a straight-sided capsule.
            const int textLeft = 13, textTop = 7, textWidth = 36, textHeight = 9;
            lists.AddGumpWithAtlas(batcher =>
            {
                batcher.Draw(texture, new Rectangle(x, y, Width, Height), uv, hue, layer);
                batcher.Draw(texture, new Rectangle(x + textLeft, y + textTop, textWidth, textHeight),
                    new Rectangle(uv.X + 51, uv.Y + textTop, 1, textHeight), hue, layer + CHILD_LAYER_INCREMENT);
                return true;
            });
            depth += 2 * CHILD_LAYER_INCREMENT;
            DrawStockCaption(lists, x + (Width - 38) / 2, y + 7 + (IsClicked ? 1 : 0), depth);
            return true;
        }

        private void DrawStockCaption(RenderLists lists, int x, int y, float depth)
        {
            // The neighboring labels are baked artwork, not a client font.
            // Reuse their native-size glyphs and colors without font scaling.
            var glyphs = new[]
            {
                (Graphic: (ushort)0x07e5, Rect: new Rectangle(15, 8, 6, 8)), // P: PEACE
                (Graphic: (ushort)0x07eb, Rect: new Rectangle(24, 7, 7, 8)), // A: STATUS
                (Graphic: (ushort)0x07dc, Rect: new Rectangle(27, 7, 8, 8)), // R: JOURNAL
                (Graphic: (ushort)0x07eb, Rect: new Rectangle(19, 7, 6, 8))  // T: STATUS
            };
            var hue = ShaderHueTranslator.GetHueVector(Hue, false, Alpha, true);
            foreach (var glyph in glyphs)
            {
                ref readonly var info = ref Client.Game.UO.Gumps.GetGump(glyph.Graphic);
                var texture = info.Texture;
                var source = new Rectangle(info.UV.X + glyph.Rect.X, info.UV.Y + glyph.Rect.Y, glyph.Rect.Width, glyph.Rect.Height);
                var destination = new Rectangle(x, y, glyph.Rect.Width, glyph.Rect.Height);
                lists.AddGumpWithAtlas(batcher => { batcher.Draw(texture, destination, source, hue, depth); return true; });
                x += glyph.Rect.Width + 1;
            }
            // Y is absent from these stock labels. Match their seven-pixel
            // serif capitals, sampling the same silver face and dark shadow.
            string[] rows = { "##   ##", " ## ## ", "  ###  ", "   ##  ", "   ##  ", "   ##  ", "  #### " };
            ref readonly var peace = ref Client.Game.UO.Gumps.GetGump(0x07e5);
            var ink = peace.Texture;
            var light = new Rectangle(peace.UV.X + 16, peace.UV.Y + 8, 1, 1);
            var shadow = new Rectangle(peace.UV.X + 18, peace.UV.Y + 9, 1, 1);
            int letterX = x;
            lists.AddGumpWithAtlas(batcher =>
            {
                for (int pass = 0; pass < 2; pass++)
                    for (int row = 0; row < rows.Length; row++)
                        for (int col = 0; col < rows[row].Length; col++)
                            if (rows[row][col] == '#')
                                batcher.Draw(ink, new Rectangle(letterX + col + (pass == 0 ? 1 : 0), y + row + (pass == 0 ? 1 : 0), 1, 1),
                                    pass == 0 ? shadow : light, hue, depth + pass * CHILD_LAYER_INCREMENT);
                return true;
            });
        }
    }
}
