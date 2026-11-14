// SPDX-License-Identifier: BSD-2-Clause
using System;
using System.Linq;
using System.Text;
using ClassicUO.Game.UI.Controls;
using ClassicUO.Game.Managers;
using ClassicUO.Input;
using ClassicUO.Renderer;
using Microsoft.Xna.Framework;

namespace ClassicUO.Game.UI.Gumps
{
    // Content provider for the stock ClassicUO spellbook. Art, page corners,
    // dragging, minimization and sounds are owned by SpellbookGump.
    internal partial class SpellbookGump
    {
        private sealed record TrinsicSpell(int Id, bool Learned, int Casts, int Reagents, string Name);
        private TrinsicSpell[] _trinsicSpells;
        private string[] _trinsicReagents;
        private Action<string,int> _trinsicCommand;
        private int _trinsicSelected;
        private bool _trinsicClosing;
        internal int TrinsicPage => _dataBox.ActivePage;

        internal SpellbookGump(World world,uint serial,string[] snapshot,Action<string,int> command) : this(world)
        {
            LocalSerial=serial;
            _trinsicCommand=command;
            _trinsicSelected=int.Parse(snapshot.First(l=>l.StartsWith("K ")).Split(' ')[2]);
            string Decode(string value)=>CodePagesEncodingProvider.Instance.GetEncoding(437).GetString(Convert.FromHexString(value)).Trim();
            _trinsicSpells=snapshot.Where(l=>l.StartsWith("L ")).Select(l=> {
                var s=l.Split(' ');
                return new TrinsicSpell(int.Parse(s[1]),s[2]=="1",int.Parse(s[3]),int.Parse(s[4]),Decode(s[5]));
            }).OrderBy(s=>s.Id).ToArray();
            _trinsicReagents=snapshot.Where(l=>l.StartsWith("J ")).OrderBy(l=>int.Parse(l.Split(' ')[1]))
                .Select(l=>Decode(l.Split(' ')[2])).Select(n=>n.StartsWith("a ")?n.Substring(2):n).ToArray();
            if(_trinsicSpells.Length!=72 || _trinsicReagents.Length!=8) throw new InvalidOperationException("Incomplete U7 spellbook");
            var position=UIManager.GetGumpCachePosition(serial,out var saved)?saved:new Point(160,120);
            X=position.X; Y=position.Y;
            BuildGump();
        }

        internal void CloseFromSession() { _trinsicClosing=true; Dispose(); }
        private void CloseTrinsicBook()
        {
            if(_trinsicSpells==null || _trinsicClosing) return;
            _trinsicClosing=true;
            _trinsicCommand("DISMISS",0);
        }
        private void TrinsicBookButton(int id)
        {
            if(id==0) { Dispose(); return; }
            if(id>=101 && id<=108) SetActivePage(2+(id-101)/2);
        }
        private static string TrinsicCircle(int circle)=>circle==0?"Cantrips":$"Circle {circle}";
        private void CreateTrinsicBook()
        {
            _dataBox.Clear();
            _dataBox.WantUpdateSize=true;
            var learned=_trinsicSpells.Where(s=>s.Learned).ToArray();
            _maxPage=5+(learned.Length+1)/2;
            // U7's zero circle occupies an extra spread ahead of the eight UO tabs.
            int[] xs={58,93,130,164,227,260,297,332};
            for(int c=1;c<=8;c++)
                _dataBox.Add(new Button(100+c,(ushort)(0x08B0+c),(ushort)(0x08B0+c)) {
                    X=xs[c-1],Y=175,ButtonAction=ButtonAction.Activate
                });
            for(int circle=0;circle<=8;circle++) {
                int page=circle==0?1:2+(circle-1)/2;
                int x=circle==0 || circle%2==1?62:225;
                _dataBox.Add(new Label("Index",false,0x288,font:6){X=x+40,Y=10},page);
                _dataBox.Add(new Label(TrinsicCircle(circle),false,0x288,font:6){X=x,Y=30},page);
                int row=0;
                foreach(var spell in learned.Where(s=>s.Id/8==circle)) {
                    int detail=6+Array.IndexOf(learned,spell)/2;
                    AddTrinsicSpellLink(spell,x,52+15*row++,page,detail);
                }
                if(row==0) _dataBox.Add(new Label("No spells learned",false,0x288,font:9){X=x,Y=54},page);
            }
            _dataBox.Add(new Label("Spellbook",false,0x288,font:6){X=236,Y=30},1);
            _dataBox.Add(new Label("Double-click a spell\nto cast.\n\nSelect a spell to\nread its reagents.",false,0x288,130,9){X=225,Y=60},1);
            for(int i=0;i<learned.Length;i++) {
                var spell=learned[i]; int page=6+i/2,x=i%2==0?62:225;
                _dataBox.Add(new Label(TrinsicCircle(spell.Id/8),false,0x288,font:6){X=i%2==0?87:224,Y=10},page);
                AddTrinsicSpellLink(spell,x,34,page,page);
                string reagents=string.Join("\n",_trinsicReagents.Where((_,bit)=>(spell.Reagents&(1<<bit))!=0));
                _dataBox.Add(new Label(spell.Reagents==0?"No reagents needed":reagents,false,0x288,130,9){X=x,Y=55},page);
            }
            int selected=Array.FindIndex(learned,s=>s.Id==_trinsicSelected);
            // Persist the original bookmark; a brand new book starts at its index.
            _dataBox.ActivePage=0;
            SetActivePage(selected>=0?6+selected/2:1);
        }
        private void AddTrinsicSpellLink(TrinsicSpell spell,int x,int y,int page,int detail)
        {
            var label=new HoveredLabel(spell.Name,false,0x288,0x33,0x288,font:9,maxwidth:130,style:FontStyle.Cropped) {
                X=x,Y=y,CanMove=true,AcceptMouseInput=true
            };
            label.SetTooltip(spell.Name+"\n"+(spell.Reagents==0?"No reagents needed":$"Reagents for {spell.Casts} casts")+"\nDouble-click to cast");
            label.MouseUp+=(s,e)=> {
                if(IsDisposed || e.Button!=MouseButtonType.Left || Mouse.LDragOffset!=Point.Zero) return;
                _trinsicSelected=spell.Id;
                _trinsicCommand("BOOKSELECT",spell.Id);
                _enqueuePage=detail;
            };
            label.MouseDoubleClick+=(s,e)=> {
                if(e.Button!=MouseButtonType.Left) return;
                _enqueuePage=-1;
                _trinsicCommand("BOOKCAST",spell.Id);
                e.Result=true;
            };
            _dataBox.Add(label,page);
        }
    }
}
