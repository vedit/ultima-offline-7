// SPDX-License-Identifier: BSD-2-Clause
using System;
using System.Text;
using ClassicUO.Game.Managers;
using ClassicUO.Game.UI.Controls;

namespace ClassicUO.Game.UI.Gumps
{
    internal sealed class TrinsicSavesGump : Gump
    {
        private int selected;
        private readonly Label[] labels=new Label[10];
        private readonly StbTextBox title;
        internal TrinsicSavesGump(World world):base(world,0,0)
        {
            X=250;Y=80;CanMove=true;CanCloseWithEsc=CanCloseWithRightClick=true;selected=TrinsicAudio.ActiveSlot;
            Add(new ResizePic(0xa28){Width=520,Height=530});
            Add(new Label("Saved worlds",false,0x386,432,font:1){X=44,Y=44});
            for(int i=0;i<10;i++)
            {
                Add(new Button(100+i,0x837,0x838,0x837){X=44,Y=86+i*27,ButtonAction=ButtonAction.Activate});
                labels[i]=new Label("",false,0x386,402,font:1){X=70,Y=83+i*27};Add(labels[i]);
            }
            Add(new ResizePic(0xbb8){X=44,Y=370,Width=432,Height=32});
            title=new StbTextBox(1,60,412,false,hue:0x386){X=54,Y=378,Width=412,Height=22,Text=TrinsicAudio.SaveTitles[selected]??""};Add(title);
            Button(1,44,"Save");Button(2,185,"Load");Button(3,326,"Return");
            Add(new Label("F5/F9 use the active slot (*). Select a slot with the arrow.",false,0x386,432,font:1){X=44,Y=470});
            TrinsicSession.Send("SAVES");
            title.SetText(TrinsicAudio.SaveTitles[selected]??"");
        }
        private void Button(int id,int x,string text)=>Add(new NiceButton(x,423,130,25,ButtonAction.Activate,text,hue:0x386,unicode:false,font:1){ButtonParameter=id,IsSelectable=false});
        public override void OnButtonClick(int id)
        {
            if(id>=100 && id<110){selected=id-100;title.SetText(TrinsicAudio.SaveTitles[selected]??"");return;}
            if(id==3){Dispose();return;}
            if(UIManager.GetGump<QuestionGump>()!=null)return;
            int slot=selected;string text=title.Text.Trim();
            if(id==1)
            {
                byte[] bytes=CodePagesEncodingProvider.Instance.GetEncoding(437).GetBytes(text.Length==0?"Ultima Offline 7":text);
                string extra=" "+Convert.ToHexString(bytes);
                void Save(){if(TrinsicSession.Enabled)TrinsicSession.Send("SAVE",slot,0,extra);}
                if(string.IsNullOrEmpty(TrinsicAudio.SaveTitles[slot]))Save();
                else UIManager.Add(new QuestionGump(World,$"Overwrite slot {slot+1}?",yes=>{if(yes)Save();}));
            }
            if(id==2 && !string.IsNullOrEmpty(TrinsicAudio.SaveTitles[slot]))
                UIManager.Add(new QuestionGump(World,$"Load slot {slot+1}? Unsaved progress will be lost.",yes=>{if(yes && TrinsicSession.Enabled)TrinsicSession.Send("LOAD",slot);}));
        }
        public override void Update()
        {
            base.Update();if(!TrinsicSession.Enabled){Dispose();return;}
            for(int i=0;i<10;i++)labels[i].Text=$"{(i==selected?"> ":"  ")}{i+1}{(i==TrinsicAudio.ActiveSlot?"*":" ")}  {(string.IsNullOrEmpty(TrinsicAudio.SaveTitles[i])?"Empty":ShortTitle(TrinsicAudio.SaveTitles[i]))}";
        }
        private static string ShortTitle(string value)=>value.Length>40?value.Substring(0,37)+"...":value;
        public override void Dispose(){if(UIManager.KeyboardFocusControl?.RootParent==this)UIManager.KeyboardFocusControl=null;base.Dispose();}
    }
}
