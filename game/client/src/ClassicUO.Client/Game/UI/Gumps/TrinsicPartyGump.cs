// SPDX-License-Identifier: BSD-2-Clause
using System;
using System.Linq;
using ClassicUO.Game.Data;
using ClassicUO.Game.Managers;
using ClassicUO.Game.UI.Controls;

namespace ClassicUO.Game.UI.Gumps
{
    // Native membership is read-only here; joining/leaving remains U7 dialogue.
    internal sealed class TrinsicPartyGump : Gump
    {
        private string signature;
        private uint[] members = Array.Empty<uint>();
        internal TrinsicPartyGump(World world) : base(world, 0, 0)
        {
            X = 250; Y = 100; CanMove = true;
            CanCloseWithEsc = CanCloseWithRightClick = true;
            Refresh();
        }
        public override void Update()
        {
            base.Update();
            if (!TrinsicSession.Enabled) { Dispose(); return; }
            Refresh();
        }
        private void Refresh()
        {
            var actors = TrinsicSession.RosterMembers;
            string next = string.Join("|", actors.Select(m => $"{m.Serial}:{m.Name}:{m.Hits}:{m.HitsMax}:{m.FindItemByLayer(Layer.Backpack)?.Serial}"));
            if (signature == next) return;
            signature = next; members = actors.Select(m => m.Serial).ToArray(); Clear();
            Width = 420; Height = 100 + actors.Length * 48; WantUpdateSize = false;
            Add(new ResizePic(0x0a28) { Width = Width, Height = Height });
            Add(new Label("Party", false, 0x288, font: 6) { X = 25, Y = 18 });
            for (int i = 0; i < actors.Length; i++)
            {
                var actor = actors[i]; int y = 56 + i * 48;
                Add(new Label(actor.Name, false, 0x288, 175, 9) { X = 25, Y = y });
                Add(new Label($"HP {actor.Hits}/{actor.HitsMax}", false, 0x288, 175, 9) { X = 25, Y = y + 18 });
                Add(new Button(100 + i * 2, 0x837, 0x838, 0x837) { X = 205, Y = y, ButtonAction = ButtonAction.Activate });
                Add(new Label("Paperdoll", false, 0x288, font: 9) { X = 229, Y = y + 1 });
                if (actor.FindItemByLayer(Layer.Backpack) != null)
                {
                    Add(new Button(101 + i * 2, 0x837, 0x838, 0x837) { X = 205, Y = y + 22, ButtonAction = ButtonAction.Activate });
                    Add(new Label("Backpack", false, 0x288, font: 9) { X = 229, Y = y + 23 });
                }
            }
            Add(new Label("Party membership follows U7 conversations.", false, 0x288, 370, 9) { X = 25, Y = Height - 30 });
        }
        public override void OnButtonClick(int id)
        {
            int row = (id - 100) / 2;
            if (id < 100 || row >= members.Length) return;
            var actor = TrinsicSession.RosterMembers.FirstOrDefault(m => m.Serial == members[row]);
            if (actor == null) { Refresh(); return; }
            if ((id & 1) == 0) TrinsicSession.ShowPaperdoll(actor.Serial);
            else if (actor.FindItemByLayer(Layer.Backpack) is { } pack) TrinsicSession.ShowBackpack(pack.Serial);
        }
    }
}
