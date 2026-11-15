// SPDX-License-Identifier: BSD-2-Clause
using System;
using System.Runtime.InteropServices;
using System.Threading;
using ClassicUO.Configuration;
using ClassicUO.Game.Managers;
using ClassicUO.Game.UI.Controls;
using SDL3;

namespace ClassicUO.Game.UI.Gumps
{
    internal sealed class TrinsicAudioGump : Gump
    {
        private readonly StbTextBox folder;
        private readonly Label message, playback;
        private static readonly SDL.SDL_DialogFileCallback folderCallback = FolderSelected;
        private static TrinsicAudioGump pickerOwner;
        private string selectedFolder;
        internal TrinsicAudioGump(World world) : base(world, 0, 0)
        {
            X=230;Y=100;CanMove=true;CanCloseWithEsc=CanCloseWithRightClick=true;
            Add(new ResizePic(0x0a28){Width=560,Height=540});
            Text(44,"Music, sound and speech");
            var p=ProfileManager.CurrentProfile;
            Row(90,"Music",p.TrinsicMusicEnabled,p.TrinsicMusicVolume,v=>p.TrinsicMusicEnabled=v,v=>p.TrinsicMusicVolume=v);
            Row(140,"Sound effects",p.EnableSound,p.SoundVolume,v=>p.EnableSound=v,v=>p.SoundVolume=v);
            Row(190,"Speech",p.TrinsicSpeechEnabled,p.TrinsicSpeechVolume,v=>p.TrinsicSpeechEnabled=v,v=>p.TrinsicSpeechVolume=v);
            Text(245,"Optional Exult MT-32 music folder");
            Add(new ResizePic(0x0bb8){X=44,Y=274,Width=472,Height=32});
            folder=new StbTextBox(1,1024,452,false,hue:0x386){X=54,Y=282,Width=452,Height=22,Text=p.TrinsicExultMusicFolder??""};Add(folder);
            Button(1,44,320,"Browse...");Button(2,185,320,"Use folder");Button(3,326,320,"Use native music");
            message=Text(361,"Recordings stay in your local folder. Missing tracks use native music.");
            playback=Text(414,TrinsicAudio.Status);
            Button(4,44,465,"Credits");Button(5,326,465,"Return");
        }
        private Label Text(int y,string text){var label=new Label(text,false,0x386,472,font:1){X=44,Y=y};Add(label);return label;}
        private void Button(int id,int x,int y,string text)=>Add(new NiceButton(x,y,184,25,ButtonAction.Activate,text,align:ClassicUO.Assets.TEXT_ALIGN_TYPE.TS_LEFT,hue:0x386,unicode:false,font:1){ButtonParameter=id,IsSelectable=false});
        private void Row(int y,string name,bool on,int volume,Action<bool> toggle,Action<int> gain)
        {
            var check=new Checkbox(0xd2,0xd3,name,1,0x386,false){X=44,Y=y,IsChecked=on};
            var slider=new HSliderBar(260,y,210,0,100,Math.Clamp(volume,0,100),HSliderBarStyle.MetalWidgetRecessedBar,true,1,0x386,false);
            check.ValueChanged+=(_,_)=>{toggle(check.IsChecked);Save();};
            slider.ValueChanged+=(_,_)=>{gain(slider.Value);Save();};Add(check);Add(slider);
        }
        private void Save(){Client.Game.Audio.UpdateCurrentSoundsVolume();ProfileManager.CurrentProfile.Save(World,ProfileManager.ProfilePath);}
        private static void FolderSelected(IntPtr data,IntPtr list,int filter)
        {
            var owner=Interlocked.Exchange(ref pickerOwner,null);
            if(owner==null || list==IntPtr.Zero)return;
            IntPtr first=Marshal.ReadIntPtr(list);
            if(first!=IntPtr.Zero)Interlocked.Exchange(ref owner.selectedFolder,Marshal.PtrToStringUTF8(first));
        }
        public override void OnButtonClick(int id)
        {
            if(id==1 && pickerOwner==null)
            {
                pickerOwner=this;
                try{SDL.SDL_ShowOpenFolderDialog(folderCallback,IntPtr.Zero,IntPtr.Zero,folder.Text,false);}
                catch(Exception e) when(e is EntryPointNotFoundException || e is DllNotFoundException)
                {pickerOwner=null;message.Text="Folder picker unavailable. Paste the folder path above.";}
            }
            if(id==2 || id==3)
            {
                if(TrinsicAudio.SetFolder(World,id==3?"":folder.Text,out string result))folder.SetText(ProfileManager.CurrentProfile.TrinsicExultMusicFolder);
                message.Text=result;
            }
            if(id==4)TrinsicOptionsGump.Credits(World);
            if(id==5)Dispose();
        }
        public override void Update()
        {
            base.Update();if(!TrinsicSession.Enabled){Dispose();return;}
            string chosen=Interlocked.Exchange(ref selectedFolder,null);
            if(chosen!=null){folder.SetText(chosen);OnButtonClick(2);}
            playback.Text=TrinsicAudio.Status;
        }
        public override void Dispose(){if(UIManager.KeyboardFocusControl?.RootParent==this)UIManager.KeyboardFocusControl=null;base.Dispose();}
    }
}
