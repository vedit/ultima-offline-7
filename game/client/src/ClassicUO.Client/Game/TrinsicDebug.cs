// SPDX-License-Identifier: BSD-2-Clause
using System;
using System.Collections.Generic;
using System.Globalization;
using System.Linq;
using System.Text;
using ClassicUO.Game.Data;
using ClassicUO.Game.GameObjects;
using ClassicUO.Game.Managers;
using ClassicUO.Game.UI.Controls;
using ClassicUO.Game.UI.Gumps;
using Microsoft.Xna.Framework;

namespace ClassicUO.Game
{
    // A development view and command adapter; the native engine owns every mutation.
    internal static class TrinsicDebug
    {
        internal const uint WandSerial=0x7fff0002;
        internal const string WandName="Developer's Wand";
        internal sealed record Entry(int Shape,int Frame,string Category,string Name,bool Supported,string Reason);
        internal static World World { get; private set; }
        internal static bool Enabled { get; private set; }
        internal static string Message { get; private set; }="Ready.";
        internal static string WorldStatus { get; private set; }="";
        internal static string Details { get; private set; }="Select Inspect, then an object or actor.";
        internal static string History { get; private set; }="";
        internal static int Inspected { get; private set; }
        internal static int[] Stats { get; private set; }
        internal static int[] Created { get; private set; }=Array.Empty<int>();
        internal static int NativeCreatedCount { get; private set; }
        internal static string LastOutcome { get; set; }="";
        internal static readonly List<Entry> Catalog=new();
        internal static string[] Categories { get; private set; }=Array.Empty<string>();
        internal static int CatalogKind { get; private set; }
        internal static string CatalogQuery { get; private set; }="";
        internal static string CatalogCategory { get; private set; }="";
        internal static int CatalogTotal { get; private set; }
        internal static bool Loading { get; private set; }
        internal static bool CatalogComplete { get; private set; }
        internal static bool Targeting => targetOwned || nextTarget!=null;
        internal static bool Typing => UIManager.KeyboardFocusControl is StbTextBox box && box.RootParent is DeveloperWandGump;
        private static int generation=-1, requestedPage=-1, nextPage=-1;
        private static uint cursor=0x7fff1000;
        private static bool targetOwned;
        private static Action nextTarget;
        private static long catalogDeadline;
        private static string response="";
        private static DeveloperWandGump panel;
        private static readonly Encoding textEncoding=CodePagesEncodingProvider.Instance.GetEncoding(437);
        internal static string Decode(string s)=>s=="-"?"":textEncoding.GetString(Convert.FromHexString(s));
        internal static string Encode(string s)=>string.IsNullOrWhiteSpace(s)?"-":Convert.ToHexString(textEncoding.GetBytes(s.Trim()));
        internal static void Close()
        {
            CancelTarget();panel?.Dispose();panel=null;Enabled=false;Loading=false;
            nextPage=requestedPage=-1;generation=-1;response="";Catalog.Clear();CatalogComplete=false;Stats=null;Inspected=0;
        }
        internal static void Disconnected() {CancelTarget();Loading=false;nextPage=requestedPage=-1;}
        internal static void PanelClosed() {CancelTarget();Loading=false;nextPage=requestedPage=-1;panel=null;}
        internal static void CancelTarget()
        {
            bool owned=targetOwned;targetOwned=false;nextTarget=null;
            if(owned && World?.TargetManager.IsTargeting==true) World.TargetManager.Reset();
        }
        internal static void Say(string text) {Message=text;panel?.RefreshStatus();}
        internal static void Open(World world)
        {
            if(!Enabled)return;
            World=world;
            if(panel==null || panel.IsDisposed) {panel=new DeveloperWandGump(world);UIManager.Add(panel);}
            else UIManager.MakeTopMostGump(panel);
        }
        internal static void Apply(World world,string[] lines,int gen,uint backpack)
        {
            World=world;
            string cap=lines.FirstOrDefault(l=>l.StartsWith("DEVCAP "));
            Enabled=cap!=null && cap.Split(' ')[1]=="1";
            if(!Enabled) {if(panel!=null)Close();if(world.Items.Get(WandSerial)!=null)world.RemoveItem(WandSerial,true);return;}
            if(generation!=gen) {CancelTarget();generation=gen;response="";Inspected=0;Stats=null;Created=Array.Empty<int>();Catalog.Clear();CatalogComplete=false;Loading=false;nextPage=requestedPage=-1;panel?.SessionChanged();}
            string[] h=lines[0].Split(' ');
            if(h.Length>9 && h[9]!="0") CancelTarget();
            if(requestedPage>=0 && h[1]!="0" && h[5]!="ok" && h[5]!="sync") {
                Loading=false;requestedPage=nextPage=-1;Say("Catalog request: "+h[5]+". Search again when the interaction finishes.");
            }
            string[] c=cap.Split(' ');
            NativeCreatedCount=int.Parse(c[6]);
            WorldStatus=$"Day {c[4]}   {int.Parse(c[2]):00}:{int.Parse(c[3]):00}   Weather {c[5]}   Created this session: {c[6]}";
            var owner=world.Items.Get(backpack);
            if(owner!=null) {
                var wand=world.GetOrCreateItem(WandSerial);
                if(wand.Container!=backpack) {
                    world.RemoveItemFromContainer(wand);owner.PushToBack(wand);wand.Container=backpack;
                    wand.Graphic=0x0df2;wand.Hue=0;wand.Amount=1;wand.Layer=Layer.Invalid;wand.X=25;wand.Y=75;
                    UIManager.GetGump<ContainerGump>(backpack)?.RequestUpdateContents();
                }
            }
            string data=string.Join("\n",lines.Where(l=>l.StartsWith("DM ")||l.StartsWith("DC ")||l.StartsWith("DI ")||l.StartsWith("DK ")||l.StartsWith("DX ")||l.StartsWith("DS ")||l.StartsWith("DN ")||l.StartsWith("DH ")));
            if(data!=response) {response=data;ReadResponse(data.Split('\n'));}
            panel?.RefreshStatus();
        }
        private static void ReadResponse(string[] lines)
        {
            string Find(string prefix)=>lines.FirstOrDefault(l=>l.StartsWith(prefix));
            if(Find("DM ") is string dm) Message=Decode(dm.Substring(3));
            History=string.Join("\n",lines.Where(l=>l.StartsWith("DH ")).Select(l=>Decode(l.Substring(3))));
            if(Find("DN ") is string dn) Created=dn.Length>3?dn.Substring(3).Split(' ',StringSplitOptions.RemoveEmptyEntries).Select(int.Parse).ToArray():Array.Empty<int>();
            if(Find("DX ") is string dx) {
                var x=dx.Split(' ');Inspected=int.Parse(x[1]);
                ushort graphic=Graphic(int.Parse(x[3]),int.Parse(x[4]));
                ushort body=TrinsicTown.MappedBody(int.Parse(x[3]));
                Details=$"{Decode(x[2])}\nNative ID: {x[1]}   Shape/frame: {x[3]}/{x[4]}\nPosition: {x[5]}, {x[6]}, lift {x[7]}\nOwner/container: {x[8]}   Quantity: {x[9]}   Weight: {x[10]}\nClass: {x[11]}   Quality: {x[12]}\nNative flags: {x[13]}   Capabilities: {x[14]}\nNPC number: {x[15]}   Created this session: {(x[16]=="1"?"Yes":"No")}\nUO art: {(graphic==0?"unmapped":$"0x{graphic:X4}")}   Body: {(body==0?"unmapped":$"0x{body:X4}")}";
                Stats=Find("DS ") is string ds?ds.Substring(3).Split(' ').Select(int.Parse).ToArray():null;
                if(Stats!=null)Details+=$"\nBase STR/DEX/INT/Combat: {Stats[1]}/{Stats[2]}/{Stats[3]}/{Stats[4]}\nEffective STR/DEX/INT/Combat: {Stats[11]}/{Stats[12]}/{Stats[13]}/{Stats[14]}\nHP: {Stats[6]}/{Stats[16]}   Mana: {Stats[7]}/{Stats[17]}   Level: {Stats[15]}";
                panel?.InspectionChanged();
            }
            if(Find("DC ") is string dc && Loading) {
                var c=dc.Split(' ');int page=int.Parse(c[2]);
                bool matching=c.Length<7 || (int.Parse(c[4])==CatalogKind && Decode(c[5])==CatalogCategory && Decode(c[6])==CatalogQuery);
                if(matching && page==requestedPage) {
                    CatalogTotal=int.Parse(c[1]);
                    foreach(var row in lines.Where(l=>l.StartsWith("DI "))) {
                        var r=row.Split(' ');Catalog.Add(new(int.Parse(r[1]),int.Parse(r[2]),Decode(r[3]),Decode(r[4]),r[5]=="1",Decode(r[6])));
                    }
                    Categories=lines.Where(l=>l.StartsWith("DK ")).Select(l=>Decode(l.Substring(3))).ToArray();
                    nextPage=page+1<int.Parse(c[3])?page+1:-1;Loading=nextPage>=0;CatalogComplete=!Loading;requestedPage=-1;
                    panel?.CatalogChanged();
                }
            }
        }
        internal static ushort Graphic(int shape,int frame)=>TrinsicTown.Graphic(shape,frame,0,0,0,false);
        internal static bool Mapped(Entry entry)=>CatalogKind==1?TrinsicTown.MappedBody(entry.Shape)!=0:Graphic(entry.Shape,entry.Frame)!=0;
        internal static void Search(int kind,string category,string query)
        {
            CatalogKind=kind;CatalogCategory=category;CatalogQuery=query.Trim();Catalog.Clear();CatalogTotal=0;
            nextPage=0;requestedPage=-1;Loading=true;CatalogComplete=false;panel?.CatalogChanged();
        }
        internal static void Update()
        {
            if(!Enabled || panel==null || panel.IsDisposed)return;
            if(nextTarget!=null){var pending=nextTarget;nextTarget=null;pending();}
            if(requestedPage>=0 && Environment.TickCount64>catalogDeadline){Loading=false;requestedPage=nextPage=-1;Say("Catalog request timed out. Search again.");}
            if(Loading && requestedPage<0 && nextPage>=0) {
                requestedPage=nextPage;nextPage=-1;
                catalogDeadline=Environment.TickCount64+5000;
                TrinsicSession.Send("DBGCAT",CatalogKind,requestedPage,$" {Encode(CatalogCategory)} {Encode(CatalogQuery)}");
            }
        }
        internal static void Command(string op,int a=0,int b=0,string extra="")
        {
            if(!Enabled)return;
            UIManager.KeyboardFocusControl=null;
            // A mutation supersedes catalog paging, so its reply cannot be hidden by a queued page.
            Loading=false;nextPage=requestedPage=-1;
            TrinsicSession.Send(op,a,b,extra);
        }
        private static void Target(string instruction,Action<GameObject> selected)
        {
            if(!Enabled || World==null)return;
            if(World.TargetManager.IsTargeting && !targetOwned) {Say("Finish or cancel the current U7 target first.");return;}
            string[] h=TrinsicSession.Header.Split(' ');
            if(h[9]!="0") {Say("Finish the current U7 interaction first.");return;}
            CancelTarget();UIManager.KeyboardFocusControl=null;Say(instruction);targetOwned=true;
            uint token=++cursor;
            World.TargetManager.SetTargeting(target=> {
                if(!targetOwned || token!=cursor)return;
                targetOwned=false;
                if(target==null) {Say("Target cancelled.");return;}
                if(target is Entity e && (e.Serial & 0x20000000u)!=0) {Say("Presentation-only objects cannot be targeted.");return;}
                selected(target);
            },token,TargetType.Neutral);
        }
        private static int Id(GameObject obj)=>obj is Entity e?(int)(e.Serial&0x1fffffff):0;
        private static (int destination,int x,int y,int z) Destination(GameObject target)
        {
            // Resolve containers, actor inventories and supporting surfaces in the
            // native engine. Their rendered anchors/lifts may have art offsets.
            if(target is Entity)return (Id(target),0,0,0);
            Point p=TrinsicTown.Compact?TrinsicTown.NativeGround(target.X,target.Y):new Point(target.X,target.Y);
            return (0,p.X,p.Y,Math.Clamp(target.Z/4,0,15));
        }
        internal static void Inspect()=>Target("Select an object or actor to inspect.",t=> {if(Id(t)!=0)Command("DBGINSPECT",Id(t));else Say("Select a native object or actor.");});
        internal static void InspectAvatar()=>Command("DBGINSPECT",(int)World.Player.Serial);
        internal static void Duplicate()=>Target("Duplicate: select the source object or generic creature.",source=> {
            int id=Id(source);if(id==0){Say("Select a native object or creature.");return;}
            nextTarget=()=>Target("Duplicate: select the destination ground, surface or container.",destination=> {
                var d=Destination(destination);Command("DBGDUP",id,d.destination,$" {d.x} {d.y} {d.z}");
            });
        });
        internal static void Create(Entry entry,int quantity,bool pack,int alignment)
        {
            if(!entry.Supported){Say(entry.Reason);return;}
            if(CatalogKind==0 && pack) {Command("DBGI",entry.Shape,entry.Frame,$" {quantity} -1 0 0 0");return;}
            bool creature=CatalogKind==1;
            Target("Select a destination for "+entry.Name+".",target=> {
                var d=Destination(target);
                if(creature && d.destination!=0){Say("Select ground for the creature, rather than an object or actor.");return;}
                Command(creature?"DBGC":"DBGI",entry.Shape,entry.Frame,creature?$" {alignment} {d.x} {d.y} {d.z}":$" {quantity} {d.destination} {d.x} {d.y} {d.z}");
            });
        }
        internal static void Teleport()=>Target("Select a world destination for the Avatar and party.",t=> {
            var d=Destination(t);if(d.destination!=0){Say("Choose ground for the party destination.");return;}Command("DBGTELEPORT",d.x,d.y,$" {d.z}");
        });
        internal static void Resurrect()=>Target("Select the native corpse to resurrect.",t=>{if(Id(t)!=0)Command("DBGRES",Id(t));else Say("Select a corpse.");});
        internal static void Refill()=>Target("Select an actor to refill HP and mana.",t=>{if(Id(t)!=0)Command("DBGREFILL",Id(t));else Say("Select an actor.");});
    }
}
