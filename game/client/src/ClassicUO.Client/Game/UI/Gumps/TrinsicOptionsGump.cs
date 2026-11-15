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
            Add(new ResizePic(0x0a28) { Width = 520, Height = 530 });
            Text(44, 44, "Ultima Offline 7 Options");
            Action(1, 85, "Save world (F5)");
            Action(2, 115, "Load last save (F9)");
            Action(6, 145, "Saved worlds...");
            Action(5, 175, "Music, sound and speech...");
            var profile = ProfileManager.CurrentProfile;
            Toggle(235, "See through walls near the Avatar", profile.UseCircleOfTransparency,
                value => profile.UseCircleOfTransparency = value);
            Toggle(265, "Ctrl + mouse wheel zoom", profile.EnableMousewheelScaleZoom,
                value => profile.EnableMousewheelScaleZoom = value);
            Toggle(295, "Always run", profile.AlwaysRun,
                value => profile.AlwaysRun = value);
            Text(44, 338, "Right mouse: move; point farther away to run.");
            Text(44, 365, "Tab: War/Peace. Escape: cancel targeting.");
            Action(3, 402, "Advanced client settings");
            Action(8, 432, "Quit game...");
            Action(4, 462, "Return to game");
        }
        private void Text(int x, int y, string text) =>
            Add(new Label(text, false, 0x386, 432, font: 1) { X = x, Y = y });
        private void Action(int id, int y, string text)
        {
            Add(new Button(id, 0x837, 0x838, 0x837) { X = 44, Y = y, ButtonAction = ButtonAction.Activate });
            Add(new NiceButton(65, y - 3, 410, 25, ButtonAction.Activate, text,
                align: ClassicUO.Assets.TEXT_ALIGN_TYPE.TS_LEFT, hue: 0x386, unicode: false, font: 1)
                { ButtonParameter = id, IsSelectable = false });
        }
        private void Toggle(int y, string text, bool initial, System.Action<bool> change)
        {
            var check = new Checkbox(0x00d2, 0x00d3, text, 1, 0x386, false)
                { X = 44, Y = y, IsChecked = initial };
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
                case 1: TrinsicSession.Send("SAVE", -1); break;
                case 2:
                    if (UIManager.GetGump<QuestionGump>() == null)
                        UIManager.Add(new QuestionGump(World, "Load last save? Unsaved progress will be lost.",
                            yes => { if (yes && TrinsicSession.Enabled) TrinsicSession.Send("LOAD", -1); }));
                    break;
                case 3: Dispose(); GameActions.OpenSettings(World, advancedClient: true); break;
                case 4: Dispose(); break;
                case 5: if(UIManager.GetGump<TrinsicAudioGump>()==null)UIManager.Add(new TrinsicAudioGump(World));break;
                case 6: if(UIManager.GetGump<TrinsicSavesGump>()==null)UIManager.Add(new TrinsicSavesGump(World));break;
                case 8:
                    if(UIManager.GetGump<QuestionGump>()==null)
                        UIManager.Add(new QuestionGump(World,"Quit game? Unsaved progress will be lost.",yes=>{if(yes)Client.Game.Exit();}));
                    break;
            }
        }
        internal static void Credits(World world) => UIManager.Add(new MessageBoxGump(world, 560, 370,
            "Music credits\n\nOriginal Ultima VII music: Dana Glover.\nAdditional music: Raymond Benson, Herman Miller, David Watson, Kathleen Jones and Kirk Winterrowd.\nOrigin Systems.\n\nOptional MT-32 recordings: Simon Quinn.\nMusic pack and playback reference: the Exult project (exult.info).\n\nRecordings are read from your own local installation and are not bundled with Ultima Offline 7.", _=>{}));
        public override void Update()
        {
            base.Update();
            if (!TrinsicSession.Enabled) Dispose();
        }
    }
}
