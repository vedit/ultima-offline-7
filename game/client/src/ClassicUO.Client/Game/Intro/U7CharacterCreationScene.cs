// SPDX-License-Identifier: BSD-2-Clause
using System;
using System.Linq;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using ClassicUO.Game.Managers;
using ClassicUO.Game.Scenes;
using ClassicUO.Game.UI.Controls;
using ClassicUO.Game.UI.Gumps;
using SDL3;

namespace ClassicUO.Game.Intro
{
    // No GameScene updates or gameplay input while the native opening is held.
    internal sealed class U7CharacterCreationScene : Scene
    {
        private readonly World world;
        private readonly Action<string> complete;
        private readonly CancellationTokenSource cancellation=new();
        private CreationGump panel;
        private Task<string> request;
        private string checkpoint;
        private string submittedName;
        private bool submittedFemale;
        internal U7CharacterCreationScene(World world,Action<string> complete)
        {this.world=world;this.complete=complete;}
        public override void Load()
        {
            base.Load();UIManager.Add(panel=new CreationGump(world,this));
            UIManager.KeyboardFocusControl=panel.NameInput;
            Console.WriteLine("NEW CHARACTER: native opening held");
        }
        public override void Update()
        {
            base.Update();
            panel.X=(Client.Game.ClientBounds.Width-panel.Width)/2;
            panel.Y=(Client.Game.ClientBounds.Height-panel.Height)/2;
            if(request?.IsCompleted==true) {
                var result=request;request=null;
                try {
                    string frame=result.GetAwaiter().GetResult();
                    string outcome=TrinsicSession.CharacterResult(frame);
                    if(outcome=="ok") {complete(frame);return;}
                    panel.Error.Text="Could not begin: "+outcome+". Check your choices.";
                } catch(Exception e) {
                    // Keep the original choices on an uncertain acknowledgement;
                    // retry the same sequence instead of accidentally renaming it.
                    panel.Error.Text="Connection interrupted. Press Begin to retry.";Console.Error.WriteLine(e.Message);return;
                }
                submittedName=null;
                panel.Busy(false);
            }
            if(TrinsicReplay.Active)TrinsicReplay.Next(world,null,null);
        }
        private void Submit()
        {
            if(request!=null)return;
            if(submittedName!=null) {
                request=TrinsicSession.CreateCharacterAsync(submittedName,submittedFemale,cancellation.Token);return;
            }
            string name=panel.NameInput.Text.Trim();
            if(name.Length==0 || name.Length>14 || name.Any(char.IsControl)) {
                panel.Error.Text="Enter a name of 1 to 14 characters.";return;
            }
            byte[] bytes;
            try {
                var encoding=(Encoding)CodePagesEncodingProvider.Instance.GetEncoding(437).Clone();
                encoding.EncoderFallback=EncoderFallback.ExceptionFallback;
                bytes=encoding.GetBytes(name);
            } catch(EncoderFallbackException) {
                panel.Error.Text="This name contains characters the original game cannot display.";return;
            }
            panel.Busy(true);panel.Error.Text="Beginning your journey...";
            submittedName=Convert.ToHexString(bytes);submittedFemale=panel.Female.IsChecked;
            request=TrinsicSession.CreateCharacterAsync(submittedName,submittedFemale,cancellation.Token);
        }
        internal override void OnKeyDown(SDL.SDL_KeyboardEvent e)
        {
            if(!e.repeat && e.key is (uint)SDL.SDL_Keycode.SDLK_RETURN or (uint)SDL.SDL_Keycode.SDLK_KP_ENTER)Submit();
        }
        public override void Unload()
        {
            cancellation.Cancel();cancellation.Dispose();panel?.Dispose();base.Unload();
        }
        internal void Replay(string[] args)
        {
            switch(args[1]) {
                case "FORM":if(panel.IsDisposed)throw new InvalidOperationException("Missing character form");break;
                case "NAME":panel.NameInput.SetText("");panel.NameInput.InvokeTextInput(string.Join(" ",args.Skip(2)));break;
                case "NAMEHEX":panel.NameInput.SetText("");panel.NameInput.InvokeTextInput(CodePagesEncodingProvider.Instance.GetEncoding(437).GetString(Convert.FromHexString(args[2])));break;
                case "SEX":panel.Female.IsChecked=args[2]=="1";panel.Male.IsChecked=args[2]!="1";break;
                case "SUBMIT":panel.OnButtonClick(1);break;
                case "INVALID":if(request!=null || string.IsNullOrEmpty(panel.Error.Text))throw new InvalidOperationException("Invalid name was accepted");break;
                case "HELD":string state=TrinsicSession.DreamCheckpoint();if(checkpoint!=null && state!=checkpoint)throw new InvalidOperationException("Creation advanced the game");checkpoint=state;break;
                case "KEY":OnKeyDown(new SDL.SDL_KeyboardEvent{key=(uint)Enum.Parse<SDL.SDL_Keycode>("SDLK_"+args[2])});break;
                default:throw new InvalidOperationException("Expected character creation, got "+args[1]);
            }
        }
        private sealed class CreationGump : Gump
        {
            private readonly U7CharacterCreationScene scene;
            internal readonly StbTextBox NameInput;
            internal readonly RadioButton Male,Female;
            internal readonly Label Error;
            internal CreationGump(World world,U7CharacterCreationScene scene):base(world,0,0)
            {
                this.scene=scene;CanMove=false;CanCloseWithEsc=CanCloseWithRightClick=false;
                Width=440;Height=400;
                Add(new ResizePic(0xa28){Width=440,Height=400});
                Text(40,"Ultima Offline 7");Text(74,"Begin a new journey");
                Text(122,"Your name (up to 14 characters)");
                Add(new ResizePic(0xbb8){X=44,Y=148,Width=352,Height=36});
                Add(NameInput=new StbTextBox(1,14,328,true,hue:0x386){X=56,Y=157,Width=328,Height=22});
                Text(196,"Choose your Avatar");
                Add(Male=new RadioButton(1,0xd0,0xd1,"Male",1,0x386,false){X=44,Y=228,IsChecked=true});
                Add(Female=new RadioButton(1,0xd0,0xd1,"Female",1,0x386,false){X=220,Y=228});
                Error=Text(268,"");
                NameInput.TextChanged+=(_,_)=>{if(scene.request==null)Error.Text="";};
                Add(new NiceButton(44,334,144,28,ButtonAction.Activate,"Quit",hue:0x386,unicode:false,font:1){ButtonParameter=2,IsSelectable=false});
                Add(new NiceButton(252,334,144,28,ButtonAction.Activate,"Begin",hue:0x386,unicode:false,font:1){ButtonParameter=1,IsSelectable=false});
            }
            private Label Text(int y,string text){var label=new Label(text,false,0x386,352,font:1){X=44,Y=y};Add(label);return label;}
            internal void Busy(bool busy){NameInput.IsEnabled=Male.IsEnabled=Female.IsEnabled=!busy;}
            public override void OnButtonClick(int id){if(id==1)scene.Submit();else if(id==2)Client.Game.Exit();}
            public override void Dispose(){if(UIManager.KeyboardFocusControl?.RootParent==this)UIManager.KeyboardFocusControl=null;base.Dispose();}
        }
    }
}
