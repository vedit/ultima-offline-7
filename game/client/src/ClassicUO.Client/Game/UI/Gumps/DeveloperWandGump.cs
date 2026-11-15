// SPDX-License-Identifier: BSD-2-Clause
using System;
using System.Collections.Generic;
using System.Linq;
using ClassicUO.Assets;
using ClassicUO.Game.Managers;
using ClassicUO.Game.Scenes;
using ClassicUO.Game.UI.Controls;
using ClassicUO.Input;
using ClassicUO.Renderer;
using Microsoft.Xna.Framework;
using SDL3;

namespace ClassicUO.Game.UI.Gumps
{
    internal sealed class DeveloperWandGump : Gump
    {
        private readonly DataBox content;
        private DataBox results;
        private bool catalogShowing;
        private readonly Label status, clock;
        private readonly Dictionary<int,Action> actions=new();
        private readonly Dictionary<string,StbTextBox> fields=new();
        private readonly Dictionary<string,Button> buttons=new();
        private int buttonId=100, resultButtonId=1000, page, mapFilter, alignment=-1;
        private Combobox category, mapped, temperament;
        private TrinsicDebug.Entry selected;
        internal int Tab {get;private set;}
        private static readonly string[] tabs={"Supplies","Items","Creatures","Inspect","Stats","World","Cleanup"};
        internal DeveloperWandGump(World world):base(world,0,0)
        {
            X=100;Y=70;Width=720;Height=590;WantUpdateSize=false;CanMove=true;
            AcceptMouseInput=AcceptKeyboardInput=true;CanCloseWithEsc=CanCloseWithRightClick=true;
            Add(new ResizePic(0x0a28){Width=720,Height=590});
            Add(new Label(TrinsicDebug.WandName,false,0x288,font:6){X=25,Y=16});
            for(int i=0;i<tabs.Length;i++){int n=i;MakeButton(this,tabs[i],25,66+i*34,()=>SelectTab(n),fixedId:i+1);}
            MakeButton(this,"Duplicate",25,330,TrinsicDebug.Duplicate,fixedId:20);
            MakeButton(this,"Target inspect",25,364,TrinsicDebug.Inspect,fixedId:21);
            MakeButton(this,"Close",25,524,Dispose,fixedId:22);
            content=new DataBox(165,62,530,438){WantUpdateSize=false};Add(content);
            clock=new Label("",false,0x288,665,9){X=25,Y=493};Add(clock);
            status=new Label("",false,0x288,515,9){X=165,Y=522};Add(status);
            SelectTab(0);RefreshStatus();
        }
        private Label Label(Control owner,string text,int x,int y,int width=510,ushort hue=0x288)
        {
            var label=new Label(text,false,hue,width,9){X=x,Y=y};owner.Add(label);return label;
        }
        private void MakeButton(Control owner,string text,int x,int y,Action action,int fixedId=0,bool result=false)
        {
            int id=fixedId!=0?fixedId:result?resultButtonId++:buttonId++;
            var button=new Button(id,0x837,0x838,0x837){X=x,Y=y,ButtonAction=ButtonAction.Activate};
            actions[id]=action;buttons[text]=button;owner.Add(button);Label(owner,text,x+24,y+1,Math.Min(480,Width-x-28));
        }
        private StbTextBox Field(string key,string label,int x,int y,int width=85,string value="",bool number=true,Control owner=null)
        {
            owner??=content;Label(owner,label,x,y,160);
            owner.Add(new ResizePic(0xbb8){X=x,Y=y+20,Width=width,Height=27});
            var text=new StbTextBox(9,number?9:64,width-12,false,hue:0x288){X=x+6,Y=y+24,Width=width-12,Height=22,NumbersOnly=number,Text=value};
            fields[key]=text;owner.Add(text);return text;
        }
        private bool Number(string key,out int number,int low=0,int high=int.MaxValue)
        {
            if(fields.TryGetValue(key,out var field) && int.TryParse(field.Text,out number) && number>=low && number<=high)return true;
            number=0;TrinsicDebug.Say($"Enter {low}–{high} for {key}.");return false;
        }
        public override void OnButtonClick(int id)
        {
            if(actions.TryGetValue(id,out var action)){UIManager.KeyboardFocusControl=null;action();}
        }
        internal void SelectTab(int tab)
        {
            TrinsicDebug.CancelTarget();Tab=tab;fields.Clear();content.Clear();selected=null;page=0;catalogShowing=false;
            foreach(int id in actions.Keys.Where(i=>i>=100).ToArray())actions.Remove(id);
            foreach(string name in buttons.Where(p=>p.Value.IsDisposed).Select(p=>p.Key).ToArray())buttons.Remove(name);
            buttonId=100;resultButtonId=1000;
            switch(tab){case 0:Supplies();break;case 1:case 2:Catalog();break;case 3:Inspection();break;case 4:Stats();break;case 5:WorldControls();break;case 6:Cleanup();break;}
        }
        internal void SessionChanged(){if(!IsDisposed)SelectTab(Tab);}
        internal void RefreshStatus(){if(!IsDisposed){status.Text=TrinsicDebug.Message;clock.Text=TrinsicDebug.WorldStatus;}}
        internal void InspectionChanged(){if(Tab is 3 or 4)SelectTab(Tab);}
        internal void CatalogChanged(){if(catalogShowing)CatalogRows();}
        private void Supplies()
        {
            Label(content,"Supplies and spell testing",0,0);
            Label(content,"These are real U7 objects. Casting still uses original\nreagents, mana, learned spells and targeting rules.",0,35);
            MakeButton(content,"Reagent bag: 30 of each",0,100,()=>TrinsicDebug.Command("DBGSUP",0));
            MakeButton(content,"Fully learned spellbook",0,143,()=>TrinsicDebug.Command("DBGSUP",1));
            MakeButton(content,"Refill Avatar HP and mana",0,186,()=>TrinsicDebug.Command("DBGREFILL",(int)World.Player.Serial));
            MakeButton(content,"Refill targeted actor",0,229,TrinsicDebug.Refill);
            MakeButton(content,"Resurrect a native corpse",0,272,TrinsicDebug.Resurrect);
            Label(content,"To test high-circle spells, inspect the Avatar and edit\nnative stats explicitly. This tool never enables free casting.",0,328);
        }
        private void Catalog()
        {
            catalogShowing=true;
            int kind=Tab-1;
            string[] cats=kind==0?new[]{"All","Weapon","Armour","Clothing","Container","Food","Reagent","Tool","Book","Magic","Furniture","Architecture","Other","Internal"}:new[]{"All","Humanoid","Animal","Undead","Monster","Other"};
            Field("Search","Name or shape ID",0,0,200,TrinsicDebug.CatalogKind==kind?TrinsicDebug.CatalogQuery:"",false);
            int initialCategory=TrinsicDebug.CatalogKind==kind?Array.IndexOf(cats,TrinsicDebug.CatalogCategory):0;
            category=new Combobox(210,20,150,cats,Math.Max(0,initialCategory));content.Add(category);
            MakeButton(content,"Search",382,23,Search);
            mapped=new Combobox(0,61,160,new[]{"All artwork","Mapped","Unmapped"},mapFilter);content.Add(mapped);
            mapped.OnOptionSelected+=(s,n)=>{mapFilter=n;page=0;CatalogRows();};
            results=new DataBox(0,102,530,330){WantUpdateSize=false};content.Add(results);
            if(TrinsicDebug.CatalogKind!=kind || (!TrinsicDebug.CatalogComplete && !TrinsicDebug.Loading))Search();else CatalogRows();
        }
        internal void Search()
        {
            selected=null;page=0;
            string[] cats=Tab==1?new[]{"","Weapon","Armour","Clothing","Container","Food","Reagent","Tool","Book","Magic","Furniture","Architecture","Other","Internal"}:new[]{"","Humanoid","Animal","Undead","Monster","Other"};
            TrinsicDebug.Search(Tab-1,cats[Math.Max(0,category.SelectedIndex)],fields["Search"].Text);
        }
        private void CatalogRows()
        {
            results.Clear();foreach(int id in actions.Keys.Where(i=>i>=1000).ToArray())actions.Remove(id);resultButtonId=1000;
            var entries=TrinsicDebug.Catalog.Where(e=>mapFilter==0 || TrinsicDebug.Mapped(e)==(mapFilter==1)).ToArray();
            int pages=Math.Max(1,(entries.Length+7)/8);page=Math.Clamp(page,0,pages-1);
            Label(results,$"{entries.Length} matches{(TrinsicDebug.Loading?$"; loading {TrinsicDebug.Catalog.Count}/{TrinsicDebug.CatalogTotal}":"")}   Page {page+1}/{pages}",0,0);
            for(int i=0;i<8 && page*8+i<entries.Length;i++) {
                var entry=entries[page*8+i];
                string name=entry.Name.Length>37?entry.Name.Substring(0,34)+"...":entry.Name;
                MakeButton(results,$"{name} [{entry.Shape}:{entry.Frame}]",0,27+i*25,()=>{selected=entry;ShowSelection();},result:true);
            }
            MakeButton(results,"Previous",0,238,()=>{page--;CatalogRows();},result:true);
            MakeButton(results,"Next",135,238,()=>{page++;CatalogRows();},result:true);
            if(entries.Length==0)Label(results,TrinsicDebug.Loading?"Searching original U7 data...":"No matches. Try another name or category.",0,55);
            if(selected!=null)SelectionDetails();
        }
        private void ShowSelection(){CatalogRows();}
        private void SelectionDetails()
        {
            Label(results,$"Selected: {selected.Name} ({selected.Shape}:{selected.Frame})",0,274);
            if(!selected.Supported){Label(results,selected.Reason,0,300);return;}
            // Selection opens a dedicated creation panel with room for the unscaled preview.
            MakeButton(results,"Preview and create",0,303,Creation,result:true);
        }
        private void Creation()
        {
            var entry=selected;if(entry==null)return;
            catalogShowing=false;content.Clear();fields.Clear();alignment=-1;
            Label(content,entry.Name,0,0);Label(content,$"Shape {entry.Shape}, frame {entry.Frame} — {entry.Category}",0,25);
            bool creature=Tab==2;
            ushort art=TrinsicDebug.Graphic(entry.Shape,entry.Frame),body=TrinsicTown.MappedBody(entry.Shape);
            content.Add(new DebugArtPreview(creature?body:art,creature){X=270,Y=65,Width=235,Height=220});
            Label(content,(creature?body:art)==0?"UO artwork is currently unmapped.":$"UO {(creature?"body":"art")}: 0x{(creature?body:art):X4}",260,295,250);
            if(creature){
                Label(content,"Temperament",0,70);
                temperament=new Combobox(0,94,205,new[]{"Original temperament","Friendly","Hostile"},0);content.Add(temperament);
                temperament.OnOptionSelected+=(s,n)=>alignment=n==0?-1:n;
                MakeButton(content,"Create at target",0,160,()=>TrinsicDebug.Create(entry,1,false,alignment));
            }else{
                Field("Quantity","Quantity",0,65,90,"1");
                MakeButton(content,"Create in backpack",0,150,()=>{if(Number("Quantity",out int n,1,127))TrinsicDebug.Create(entry,n,true,-1);});
                MakeButton(content,"Create at target",0,194,()=>{if(Number("Quantity",out int n,1,127))TrinsicDebug.Create(entry,n,false,-1);});
            }
            MakeButton(content,"Back to results",0,350,()=>SelectTab(Tab));
        }
        private void Inspection()
        {
            MakeButton(content,"Select target",0,0,TrinsicDebug.Inspect);
            MakeButton(content,"Avatar",185,0,TrinsicDebug.InspectAvatar);
            Label(content,TrinsicDebug.Details,0,40,510);
            MakeButton(content,"Copy details",0,320,()=>{SDL.SDL_SetClipboardText(TrinsicDebug.Details+"\n"+TrinsicDebug.WorldStatus);TrinsicDebug.Say("Inspection details copied.");});
            MakeButton(content,"Edit actor stats",180,320,()=>SelectTab(4));
            MakeButton(content,"Duplicate target",0,367,TrinsicDebug.Duplicate);
        }
        private void Stats()
        {
            MakeButton(content,"Select actor",0,0,TrinsicDebug.Inspect);MakeButton(content,"Avatar",185,0,TrinsicDebug.InspectAvatar);
            var s=TrinsicDebug.Stats;
            if(s==null){Label(content,"Inspect an actor to edit native stats and conditions.",0,48);return;}
            Label(content,$"Actor {s[0]} — effective STR/DEX/INT/Combat: {s[11]}/{s[12]}/{s[13]}/{s[14]}\nLevel {s[15]}   Native maximum HP {s[16]}, mana {s[17]}",0,37);
            string[] keys={"Strength","Dexterity","Intelligence","Combat","Magic","HP","Mana","Experience","Training","Food"};
            for(int i=0;i<keys.Length;i++)Field(keys[i],keys[i],(i%5)*105,90+(i/5)*63,95,s[i+1].ToString());
            MakeButton(content,"Apply stats",0,226,()=>{
                var values=new List<int>();foreach(string key in keys){if(!Number(key,out int value))return;values.Add(value);}
                TrinsicDebug.Command("DBGSET",s[0],0," "+string.Join(" ",values));
            });
            MakeButton(content,"Refill HP / mana",185,226,()=>TrinsicDebug.Command("DBGREFILL",s[0]));
            string[] conditions={"Sleep","Poison","Paralysis","Curse","Protection","Invisible","Might"};
            var condition=new Combobox(0,280,180,conditions,0);content.Add(condition);
            MakeButton(content,"Apply condition",200,283,()=>TrinsicDebug.Command("DBGCOND",s[0],condition.SelectedIndex," 1"));
            MakeButton(content,"Remove",390,283,()=>TrinsicDebug.Command("DBGCOND",s[0],condition.SelectedIndex," 0"));
            Label(content,$"Native status: 0x{s[18]:X}   Extra flags: 0x{s[19]:X}\nLowering maxima clamps HP/mana. XP is an absolute value.\nDead actors require native resurrection; identity and quest flags are read-only.",0,329);
        }
        private void WorldControls()
        {
            Field("Hour","Hour (0–23)",0,0,105,"12");Field("Minute","Minute (0–59)",125,0,105,"0");
            MakeButton(content,"Set time",260,26,()=>{if(Number("Hour",out int h,0,23)&&Number("Minute",out int m,0,59))TrinsicDebug.Command("DBGTIME",h,m);});
            MakeButton(content,"Set noon",0,65,()=>TrinsicDebug.Command("DBGTIME",12,0));
            Label(content,"Changing time updates native NPC schedules; the day is preserved.",0,101);
            var weather=new Combobox(0,143,350,new[]{"Clear","Snow","Rain / thunderstorm","Magic sparkles (native; UO view unavailable)","Fog (native; UO view unavailable)","Overcast (native; UO view unavailable)","Special palette (native; UO view unavailable)"},0,210);content.Add(weather);
            MakeButton(content,"Set weather",365,146,()=>TrinsicDebug.Command("DBGWEATHER",weather.SelectedIndex));
            MakeButton(content,"Teleport Avatar and party",0,214,TrinsicDebug.Teleport);
            MakeButton(content,"Save current world",0,266,()=>TrinsicDebug.Command("DBGSAVE"));
            Label(content,"Save uses the same native slot as F5.\nTime and weather change the original world, not only this panel.\nAdditional global lighting/weather presentation is separate work.",0,321);
        }
        private void Cleanup()
        {
            Label(content,$"Created this session: {TrinsicDebug.NativeCreatedCount}\nLoading a save clears this cleanup registry.",0,0);
            MakeButton(content,"Remove inspected object",0,58,()=>{
                if(TrinsicDebug.Inspected==0){TrinsicDebug.Say("Inspect a created object first.");return;}
                TrinsicDebug.Command("DBGCLEAN",TrinsicDebug.Inspected);
            });
            MakeButton(content,"Remove all created objects",0,100,()=>TrinsicDebug.Command("DBGCLEAN",0));
            Label(content,"Objects carrying untracked possessions are preserved.\nOnly surviving identities created by this tool are eligible.",0,142);
            Label(content,"Recent actions",0,200);
            string history=TrinsicDebug.History;var lines=history.Split('\n');if(lines.Length>9)history=string.Join("\n",lines.TakeLast(9));
            Label(content,history,0,225,515);
            MakeButton(content,"Refresh history",330,199,()=>SelectTab(6));
        }
        internal Point ButtonPoint(string label)
        {
            if(!buttons.TryGetValue(label,out var button) || button.IsDisposed)throw new InvalidOperationException("Missing wand button: "+label);
            return new Point(button.ScreenCoordinateX+8,button.ScreenCoordinateY+8);
        }
        internal Point EntryPoint(int shape,int frame)
        {
            var entries=TrinsicDebug.Catalog.Where(e=>mapFilter==0 || TrinsicDebug.Mapped(e)==(mapFilter==1)).ToArray();
            int index=Array.FindIndex(entries,e=>e.Shape==shape && e.Frame==frame);
            if(index<0)throw new InvalidOperationException($"Missing catalog entry {shape}:{frame}");
            page=index/8;CatalogRows();
            var entry=entries[index];string name=entry.Name.Length>37?entry.Name.Substring(0,34)+"...":entry.Name;
            return ButtonPoint($"{name} [{entry.Shape}:{entry.Frame}]");
        }
        internal void EnterField(string key,string value)
        {
            if(!fields.TryGetValue(key,out var field))throw new InvalidOperationException("Missing wand field "+key);
            field.SetKeyboardFocus();field.Text=value;
        }
        public override void OnKeyboardReturn(int textID,string text)
        {
            if(catalogShowing && fields.ContainsKey("Search")){UIManager.KeyboardFocusControl=null;Search();}
            else base.OnKeyboardReturn(textID,text);
        }
        public override void Dispose(){if(!IsDisposed){if(UIManager.KeyboardFocusControl?.RootParent==this)UIManager.KeyboardFocusControl=null;TrinsicDebug.PanelClosed();}base.Dispose();}
    }

    // Stock animation/art preview: no spawned game object and no native mutation.
    internal sealed class DebugArtPreview : Control
    {
        private readonly ushort graphic;private readonly bool mobile;
        internal DebugArtPreview(ushort graphic,bool mobile){this.graphic=graphic;this.mobile=mobile;WantUpdateSize=false;}
        public override bool AddToRenderLists(RenderLists lists,int x,int y,ref float depth)
        {
            if(graphic==0)return true;
            var texture=Client.Game.UO.Arts.GetArt(0).Texture;Rectangle source=Rectangle.Empty;ushort hue=0;
            if(mobile){
                var animations=Client.Game.UO.Animations;animations.AnimationExists(graphic,0);
                byte group=Client.Game.UO.FileManager.Animations.GetGroupIndex(graphic,animations.GetAnimType(graphic)) switch{
                    AnimationGroups.Low=>(byte)LowAnimationGroup.Stand,AnimationGroups.High=>(byte)HighAnimationGroup.Stand,_=>(byte)PeopleAnimationGroup.Stand};
                var frames=animations.GetAnimationFrames(graphic,group,1,out hue,out _,false);
                if(frames.Length!=0){texture=frames[0].Texture;source=frames[0].UV;}
            }else{ref readonly var art=ref Client.Game.UO.Arts.GetArt(graphic);texture=art.Texture;source=art.UV;}
            if(texture==null || source.IsEmpty)return true;
            float scale=Math.Min(1f,Math.Min(Width/(float)source.Width,Height/(float)source.Height));
            var destination=new Rectangle(x+(Width-(int)(source.Width*scale))/2,y+(Height-(int)(source.Height*scale))/2,(int)(source.Width*scale),(int)(source.Height*scale));
            float layer=depth;var color=ShaderHueTranslator.GetHueVector(hue);
            lists.AddGumpWithAtlas(batch=>{batch.Draw(texture,destination,source,color,layer);return true;});return true;
        }
    }
}
