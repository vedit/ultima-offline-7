// SPDX-License-Identifier: BSD-2-Clause

using System;
using ClassicUO.Game.Data;
using ClassicUO.Game.Managers;
using ClassicUO.Game.UI.Controls;
using Microsoft.Xna.Framework;

namespace ClassicUO.Game.UI.Gumps
{
    internal sealed class ItemClickLabelGump : Gump
    {
        private const ushort LabelHue = 0x03b2;
        private readonly uint _expires = Time.Ticks + 4000;

        private ItemClickLabelGump(World world, string text, Point click) : base(world, 0, 0)
        {
            LayerOrder = UILayer.Over;
            CanCloseWithRightClick = false;
            var bounds = Client.Game.ClientBounds;
            int wrap = Client.Game.UO.FileManager.Fonts.GetWidthUnicode(3, text) >= bounds.Width ? bounds.Width : 0;
            var label = Add(new Label(text, true, LabelHue, maxwidth: wrap, font: 3, style: FontStyle.BlackBorder));
            X = Math.Clamp(click.X - label.Width / 2, 0, Math.Max(0, bounds.Width - label.Width));
            int above = click.Y - label.Height - 5;
            Y = Math.Clamp(above >= 0 ? above : click.Y + 8, 0, Math.Max(0, bounds.Height - label.Height));
        }

        internal static void Show(World world, string text, Point click, uint? serial = null)
        {
            if (string.IsNullOrWhiteSpace(text)) return;
            UIManager.GetGump<ItemClickLabelGump>()?.Dispose();
            UIManager.Add(new ItemClickLabelGump(world, text, click));
            world.Journal.Add(text, LabelHue, string.Empty, serial, TextType.CLIENT, true, MessageType.Label);
        }

        public override void Update()
        {
            base.Update();
            if (Time.Ticks >= _expires) Dispose();
        }
    }
}
