// SPDX-License-Identifier: BSD-2-Clause
using ClassicUO.Configuration;
using ClassicUO.Game.Managers;
using ClassicUO.Game.UI.Controls;

namespace ClassicUO.Game.UI.Gumps
{
    internal sealed class TrinsicOptionsGump : Gump
    {
        public TrinsicOptionsGump(World world) : base(world, 0, 0)
        {
            X = 260; Y = 130; CanMove = true;
            CanCloseWithEsc = CanCloseWithRightClick = true;
            Add(new ResizePic(0x0a28) { Width = 420, Height = 358 });
            Text(22, 18, "Ultima Offline 7 Options");
            Action(1, 52, "Save world (F5)");
            Action(2, 80, "Load last save (F9)");
            var profile = ProfileManager.CurrentProfile;
            Toggle(122, "See through walls near the Avatar", profile.UseCircleOfTransparency,
                value => profile.UseCircleOfTransparency = value);
            Toggle(150, "Ctrl + mouse wheel zoom", profile.EnableMousewheelScaleZoom,
                value => profile.EnableMousewheelScaleZoom = value);
            Toggle(178, "Always run", profile.AlwaysRun,
                value => profile.AlwaysRun = value);
            Text(22, 215, "Right mouse: move; point farther away to run.");
            Text(22, 237, "Tab: War/Peace. Escape: cancel targeting.");
            Action(3, 273, "Advanced client settings");
            Action(4, 305, "Return to game");
        }
        private void Text(int x, int y, string text) =>
            Add(new Label(text, false, 0x386, 376, font: 1) { X = x, Y = y });
        private void Action(int id, int y, string text)
        {
            Add(new Button(id, 0x837, 0x838, 0x837) { X = 24, Y = y, ButtonAction = ButtonAction.Activate });
            Add(new NiceButton(45, y - 3, 345, 25, ButtonAction.Activate, text,
                align: ClassicUO.Assets.TEXT_ALIGN_TYPE.TS_LEFT, hue: 0x386, unicode: false, font: 1)
                { ButtonParameter = id, IsSelectable = false });
        }
        private void Toggle(int y, string text, bool initial, System.Action<bool> change)
        {
            var check = new Checkbox(0x00d2, 0x00d3, text, 1, 0x386, false)
                { X = 22, Y = y, IsChecked = initial };
            check.ValueChanged += (_, _) =>
            {
                change(check.IsChecked);
                ProfileManager.CurrentProfile.Save(World, ProfileManager.ProfilePath);
            };
            Add(check);
        }
        public override void OnButtonClick(int id)
        {
            switch (id)
            {
                case 1: TrinsicSession.Send("SAVE"); break;
                case 2:
                    if (UIManager.GetGump<QuestionGump>() == null)
                        UIManager.Add(new QuestionGump(World, "Load last save? Unsaved progress will be lost.",
                            yes => { if (yes && TrinsicSession.Enabled) TrinsicSession.Send("LOAD"); }));
                    break;
                case 3: Dispose(); GameActions.OpenSettings(World, advancedClient: true); break;
                case 4: Dispose(); break;
            }
        }
        public override void Update()
        {
            base.Update();
            if (!TrinsicSession.Enabled) Dispose();
        }
    }
}
