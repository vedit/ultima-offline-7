using System.Security.Cryptography;
using System.Text.Json;
using Server;
using Server.Gumps;
using Server.Network;
using UltimaOffline.Entities;

namespace UltimaOffline.Dialogue;

public static partial class CampaignDialogue
{
    private const int Avatar = -356;
    private const int MaxJournal = 4096;
    private static byte[] _source = [];
    private static int[] _flags = [];
    private static JsonElement _actors;
    private static JsonElement _portraits;
    private static Registry? _registry;
    private static readonly Dictionary<uint, OriginalDialogueGump> Visible = new();

    private sealed record Answer(string EffectHash, string? Reply);
    private sealed class Conversation
    {
        public string Actor { get; set; } = "";
        public int Function { get; set; }
        public int Event { get; set; } = 1;
        public int Item { get; set; } = -12;
        public bool Scripted { get; set; }
        public bool Automatic { get; set; }
        public int Face { get; set; }
        public int Page { get; set; }
        public int FaceSlot { get; set; }
        public List<Answer> History { get; set; } = new();
    }
    private sealed class Saved
    {
        public string Build { get; set; } = "";
        public Dictionary<int,int> Changes { get; set; } = new();
        public Dictionary<string,WorkSchedule> Work { get; set; } = new();
        public Dictionary<uint,Conversation> Active { get; set; } = new();
        public Dictionary<uint,string> PendingKeys { get; set; } = new();
        public OpeningState? Opening { get; set; }
        public GateState? Gate { get; set; }
        public SwampState Swamp { get; set; } = new();
        public Dictionary<string,EggFire> Hatched { get; set; } = new();
    }
    // In the source, UC_SetWorkType resets the selected schedule and enters
    // state 1. These are the persisted fields consumed by work-type reads.
    private sealed record WorkSchedule(int Kind, int State);
    private sealed class Registry : GenericPersistence
    {
        public Saved State = new();
        public Registry() : base("UltimaOfflineDialogue", 10) { }
        public override void Serialize(IGenericWriter w) { w.Write(1); w.Write(JsonSerializer.Serialize(State)); }
        public override void Deserialize(IGenericReader r)
        {
            if (r.ReadInt() != 1) throw new InvalidDataException("Unsupported campaign dialogue save.");
            State = JsonSerializer.Deserialize<Saved>(r.ReadString()) ?? throw new InvalidDataException("Missing dialogue state.");
        }
    }
    public static void Configure()
    {
        if (ServerConfiguration.GetSetting("ultimaOffline.privateFacet", false)) _registry = new Registry();
    }
    private static Saved State => _registry!.State;
    private static string Hash(byte[] bytes) => Convert.ToHexStringLower(SHA256.HashData(bytes));
    private static JsonElement FileJson(string path)
    {
        using var doc = JsonDocument.Parse(File.ReadAllBytes(path));
        return doc.RootElement.Clone();
    }
    public static void Initialize()
    {
        if (_registry == null) return;
        string dir = Path.Combine(Core.BaseDirectory, "Campaign");
        var manifest = FileJson(Path.Combine(dir, "dialogue.json"));
        _source = File.ReadAllBytes(Path.Combine(dir, "dialogue.lua"));
        string compiled = Hash(_source);
        if (manifest.GetProperty("lua_sha256").GetString() != compiled) throw new InvalidDataException("Dialogue module hash mismatch.");
        byte[] seedBytes = File.ReadAllBytes(Path.Combine(dir, "story-seed.json"));
        using var seed = JsonDocument.Parse(seedBytes);
        var root = seed.RootElement;
        if (root.GetProperty("schema").GetInt32() != 1) throw new InvalidDataException("Unsupported story seed format.");
        _flags = root.GetProperty("flags").EnumerateArray().Select(Bit).ToArray();
        _actors = root.GetProperty("actors").Clone();
        var portraitManifest = FileJson(Path.Combine(dir, "portraits.json"));
        if (portraitManifest.GetProperty("schema").GetInt32() != 1) throw new InvalidDataException("Unsupported portrait manifest.");
        _portraits = portraitManifest.GetProperty("frames").Clone();
        foreach (var (face, art) in new[] {(1,64001),(11,64011),(12,64012)})
            if (_portraits.GetProperty($"{face}:0").GetInt32() != art) throw new InvalidDataException("Opening portrait binding mismatch.");
        var actor = FileJson(Path.Combine(dir, "actor.json"));
        if (Actor(12).GetProperty("id").GetString() != actor.GetProperty("id").GetString() || _flags.Length != 837)
            throw new InvalidDataException("Story seed does not match the campaign edition.");
        string build = compiled + ":" + Hash(seedBytes);
        if (State.Build != "" && State.Build != build) throw new InvalidDataException("Dialogue save belongs to another source build.");
        State.Build = build;
        CampaignEntities.CanTalk=CanTalk;
        CampaignEntities.ActorUsed += Begin;
        InstallOpening(dir, root, manifest);
        InstallEstate(root, manifest);
        InstallStablesEggs(root,manifest);
        InstallGate(root,manifest);
        InstallSwamp(dir,root);
    }
    private static int Bit(JsonElement v) => v.ValueKind switch {
        JsonValueKind.True => 1, JsonValueKind.False => 0,
        JsonValueKind.Number when v.TryGetInt32(out int i) && i is 0 or 1 => i,
        _ => throw new InvalidDataException("Expected a binary story field.")
    };
    private static JsonElement Actor(int slot) => _actors.TryGetProperty(slot.ToString(System.Globalization.CultureInfo.InvariantCulture), out var row)
        ? row : throw new InvalidDataException($"No hydrated NPC slot {slot}.");

    private static bool CanTalk(Mobile player,CampaignActor actor)
    {
        if (actor.Deleted || !player.Alive || player.Map!=actor.Map || !player.CanSee(actor) || player.Warmode)
            return false;
        int slot=actor.FunctionId-0x400;
        if (!_actors.TryGetProperty(slot.ToString(System.Globalization.CultureInfo.InvariantCulture),out var row)
            || actor.SourceId!=row.GetProperty("id").GetString()) return false;
        if (State.Opening?.ContainsMember(-slot)==true)
            return player.InRange(actor.Location,2) && player.InLOS(actor);
        // DOS Use skips reach for a nonparty NPC. The original centered camera
        // covers 20 by 12 tiles in either direction. Three source lifts equal 12 UO Z.
        int activity=State.Work.TryGetValue(actor.SourceId,out var work)?work.Kind:row.GetProperty("activity").GetInt32();
        return activity!=0 && actor.Combatant==null && Math.Abs(player.Z-actor.Z)<=12 &&
            Math.Abs(player.X-actor.X)<=20 && Math.Abs(player.Y-actor.Y)<=12 &&
            Utility.InUpdateRange(player.Location,actor.Location);
    }

    private static void Begin(Mobile player, CampaignActor actor)
    {
        if (State.Opening is { } o && o.Owner == player.Serial.Value && State.Active.TryGetValue(o.Owner,out var sc) && sc.Scripted)
        {
            if (sc.Actor==actor.SourceId) Advance(player,actor,sc,null,0);
            return;
        }
        if (_openingEnabled && State.Opening?.Status != "complete") return;
        int slot=actor.FunctionId switch {
            0x040C=>12,0x040E when State.Gate!=null=>14,
            0x0402 when _witnesses.Contains(2)=>2,0x040D when _witnesses.Contains(13)=>13,_=>0
        };
        if (slot==0 || actor.SourceId != Actor(slot).GetProperty("id").GetString()) return;
        var active = State.Active;
        if (!active.TryGetValue(player.Serial.Value, out var c))
            active.Add(player.Serial.Value, c = new Conversation { Actor = actor.SourceId, Function = actor.FunctionId,Item=-slot });
        if (c.Actor != actor.SourceId || c.Function != actor.FunctionId) return;
        Advance(player,actor,c,null,0);
    }
    private static void Advance(Mobile player, CampaignActor actor, Conversation c, string? responseTo, int button,string? numeric=null)
    {
        Step? effect = null;
        try
        {
            using var vm = new DialogueMachine(_source,c.Function,c.Event,c.Item);
            effect = vm.Next(null);
            string lastLine="";
            foreach (var old in c.History)
            {
                if (effect.Signature != old.EffectHash) throw new InvalidDataException("Stored Usecode effect no longer matches at replay.");
                if(effect.Status=="effect" && effect.Kind=="say") lastLine=MessagePages(effect.Args[0].GetString()!)[^1];
                effect = vm.Next(old.Reply);
            }
            if (responseTo != null && responseTo != effect.Signature) return;
            while (true)
            {
                if (effect.Status == "completed")
                {
                    State.Active.Remove(player.Serial.Value); Visible.Remove(player.Serial.Value); return;
                }
                if (effect.Status != "effect") throw new InvalidDataException("Source interpreter stopped: " + effect.Data.GetRawText());
                if (c.History.Count >= MaxJournal) throw new InvalidDataException("Dialogue transcript limit reached.");
                string? reply;
                if(effect.Kind=="intrinsic" && effect.Intrinsic==0x0C && effect.Data.GetProperty("expects_value").GetBoolean() &&
                   effect.Data.GetProperty("function_id").GetInt32()==0x0886)
                {
                    int[] args=effect.Args.EnumerateArray().Select(a=>a.GetInt32()).ToArray();
                    if(args is not [int low,int high,int step,int initial] || step<=0 || low>high || initial<low || initial>high)
                        throw new InvalidDataException("Invalid source numeric slider bounds.");
                    if(responseTo==null || button!=1 || !int.TryParse(numeric,System.Globalization.NumberStyles.Integer,
                       System.Globalization.CultureInfo.InvariantCulture,out int number) || number<low || number>high || (number-low)%step!=0)
                    {
                        var g=new OriginalDialogueGump(actor,c.History.Count,effect.Signature,c.Face,lastLine,args);
                        Visible[player.Serial.Value]=g; player.SendGump(g,singleton:true); return;
                    }
                    reply=JsonSerializer.Serialize(number); responseTo=null; numeric=null;
                }
                else if (effect.Kind is "say" or "choice")
                {
                    var options = effect.Args.EnumerateArray().Select(a => a.GetString()!).ToArray();
                    bool choice = effect.Kind == "choice";
                    if (choice ? options.Length is < 1 or > 128 : options.Length != 1)
                        throw new InvalidDataException("Invalid source dialogue page.");
                    var pages = choice ? Array.Empty<string>() : MessagePages(options[0]);
                    if (!choice && (uint)c.Page >= (uint)pages.Length)
                        throw new InvalidDataException("Saved page is outside the source message.");
                    if (responseTo == null)
                    {
                        var g = new OriginalDialogueGump(actor,c.History.Count,effect.Signature,c.Face,choice,
                            choice ? options : new[] { pages[c.Page] });
                        Visible[player.Serial.Value] = g; player.SendGump(g, singleton:true); return;
                    }
                    if (button < 1 || button > (choice ? options.Length : 1)) return;
                    if (!choice && c.Page + 1 < pages.Length)
                    {
                        c.Page++;
                        responseTo = null;
                        continue;
                    }
                    c.Page = 0;
                    if(!choice) lastLine=pages[^1];
                    reply = choice ? JsonSerializer.Serialize(options[button-1]) : null;
                    responseTo = null;
                }
                else reply = Resolve(effect,player,c);
                c.History.Add(new Answer(effect.Signature,reply));
                effect = vm.Next(reply);
            }
        }
        catch (Exception ex)
        {
            // Retain the journal at the first unresolved effect. Re-entry retries
            // it without repeating any completed world write or selected topic.
            string place = effect?.Data.TryGetProperty("pc", out _) == true ? effect.Location : $"function 0x{c.Function:X4}";
            string message = $"Conversation paused at {place}: {ex.Message}";
            Console.WriteLine("[UltimaOfflineDialogue] " + message);
            if (c.Scripted && State.Opening != null) PauseOpening(State.Opening,message);
            player.SendMessage(0x22, message);
        }
    }
    private static string? Resolve(Step e, Mobile player, Conversation c)
    {
        JsonElement a = e.Args;
        bool wants = e.Data.GetProperty("expects_value").GetBoolean();
        int Arg(int i) => a[i].GetInt32();
        if (e.Kind is "flag_read" or "flag_write")
        {
            int flag = Arg(0);
            if ((uint)flag >= (uint)_flags.Length) throw new InvalidDataException($"Unseeded original flag {flag}.");
            if (e.Kind == "flag_read" && wants) return JsonSerializer.Serialize(State.Changes.GetValueOrDefault(flag,_flags[flag]));
            if (e.Kind == "flag_write" && !wants) { State.Changes[flag] = Bit(a[1]); return null; }
            throw new InvalidDataException("Invalid flag effect shape.");
        }
        if (e.Kind != "intrinsic") throw new InvalidDataException($"Unimplemented source effect {e.Kind}.");
        if (_swampActors.Count!=0 && e.Intrinsic is 0x88 or 0x89 or 0x8A && Arg(1)==8)
        {
            int handle=Arg(0);
            var row=Actor(handle==Avatar ? 0 : Slot(handle));
            var key=handle==Avatar ? PlayerKey(player) : row.GetProperty("id").GetString()!;
            if(e.Intrinsic==0x88) return wants ? JsonSerializer.Serialize(IsPoisoned(key,row)?1:0) : null;
            var actor=_swampActors[row.GetProperty("id").GetString()!];
            ChangePoison(key,row,e.Intrinsic==0x89,actor.Safe);
            return wants ? "0" : null;
        }
        if (State.Opening is { } roster)
        {
            if (wants && e.Intrinsic is 0x23 or 0x8D)
            {
                var members=roster.Query(e.Intrinsic==0x8D);
                if (e.Intrinsic==0x23 && e.Data.GetProperty("function_id").GetInt32()==0x0911 && State.Gate is { } gate)
                    gate.AwardRosters.Add(new AwardRoster(e.Data.GetProperty("source_offset").GetInt32(),
                        roster.Party.ToArray(),roster.DownedParty.ToArray(),members));
                return JsonSerializer.Serialize(members);
            }
            if (wants && e.Intrinsic==0x88 && Arg(1)==6 && roster.ContainsMember(Arg(0))) return "1";
            if ((e.Intrinsic is 0x20 or 0x21) && Arg(1)==3 && roster.ContainsMember(Arg(0)))
            {
                var hp=SourceHits(roster,Arg(0));
                if (e.Intrinsic==0x20) return wants ? JsonSerializer.Serialize(hp) : null;
                roster.HitPoints[Arg(0)]=unchecked((sbyte)(hp+Arg(2)));
                return wants ? "1" : null;
            }
        }
        if (c.Scripted && OpeningEffect(e,player,out var openingReply)) return openingReply;
        if (State.Gate!=null && GateEffect(e,player,c,out var gateReply)) return gateReply;
        switch (e.Intrinsic)
        {
            case 0x03 when !wants:
            {
                int slot = Slot(Arg(0)), frame = Arg(1);
                if (!_portraits.TryGetProperty($"{slot}:{frame}",out var portrait))
                    throw new InvalidDataException($"Unstaged source portrait {slot} frame {frame}.");
                c.Face = portrait.GetInt32(); c.FaceSlot = slot; return null;
            }
            case 0x04 when !wants:
                if (c.FaceSlot == Slot(Arg(0))) { c.Face = 0; c.FaceSlot = 0; }
                return null;
            case 0x5A when wants: return player.Female ? "1" : "0";
            case 0x22 when wants: return "-356";
            case 0x1B when wants:
            {
                int handle = Arg(0);
                if (handle == Avatar) return "-356";
                var row = Actor(Slot(handle));
                return IsRemoved(row) ? "0" : JsonSerializer.Serialize(handle);
            }
            case 0x27 when wants:
            {
                int handle = Arg(0);
                string name = handle == Avatar ? player.Name : Actor(Slot(handle)).GetProperty("name").GetString()!;
                return JsonSerializer.Serialize(name);
            }
            case 0x2F when wants:
            {
                if (Arg(0) == 0) return "0";
                var row = Actor(Slot(Arg(0)));
                var mob = CampaignEntities.Find(row.GetProperty("id").GetString()!) as Mobile;
                if (IsRemoved(row) || (mob != null && mob.Map != player.Map)) return "0";
                var pos = row.GetProperty("source_position");
                int x = mob?.X ?? pos[0].GetInt32(), y = mob?.Y ?? pos[1].GetInt32();
                if (WorldDelta(x,player.X)>20 || WorldDelta(y,player.Y)>12) return "0";
                if (mob == null) throw new InvalidDataException("Nearby source actor missing from active facet.");
                bool conscious = State.Opening is { } rosterState && rosterState.ContainsMember(Arg(0))
                    ? !PartyUnconscious(player,rosterState,Arg(0))
                    : Bit(row.GetProperty("can_act")) == 1 && mob.Alive && !mob.Paralyzed;
                return conscious && !mob.Hidden && Flag(row,0)==0 ? "1" : "0";
            }
            case 0x88 when wants:
            {
                var row = Actor(Slot(Arg(0)));
                if (IsRemoved(row)) throw new InvalidDataException("Source item flag requested for removed actor.");
                return JsonSerializer.Serialize(Flag(row,Arg(1)));
            }
            case 0x1C when wants:
            {
                var row = Actor(Slot(Arg(0)));
                return JsonSerializer.Serialize(State.Work.TryGetValue(row.GetProperty("id").GetString()!,out var work)
                    ? work.Kind : row.GetProperty("activity").GetInt32());
            }
            case 0x5C when !wants && Arg(0) == -12:
                // The opening starts from an empty native action queue. Lists
                // carrying SCRIPT_NO_HALT survive ordinary cancellation.
                RequireMobile(12);
                State.Opening?.Actions.RemoveAll(job=>job.Target==-12 && !job.NoHalt);
                return null;
            case 0x1D when !wants && Arg(0) == -12 && Arg(1) == 11:
            {
                var npc = RequireMobile(12);
                npc.Combatant = null;
                State.Work[npc.SourceId] = new WorkSchedule(11,1);
                return null;
            }
            default: throw new InvalidDataException($"Unimplemented original intrinsic 0x{e.Intrinsic:X2}, args {a.GetRawText()}.");
        }
    }
    private static CampaignActor RequireMobile(int slot) =>
        CampaignEntities.Find(Actor(slot).GetProperty("id").GetString()!) as CampaignActor ??
        throw new InvalidDataException($"Expected source actor {slot} on the private facet.");
    private static int Slot(int handle) => handle < 0 && handle > Avatar ? -handle
        : throw new InvalidDataException($"Unsupported source NPC reference {handle}.");
    private static int Flag(JsonElement row,int index) => Bit(row.GetProperty("item_flags").GetProperty(index.ToString(System.Globalization.CultureInfo.InvariantCulture)));
    private static bool IsRemoved(JsonElement row) => row.TryGetProperty("staged_land_id",out _) &&
        CampaignEntities.Find(row.GetProperty("id").GetString()!) == null;
    private static int WorldDelta(int a,int b)
    {
        int d = Math.Abs(a-b) % 3072; return Math.Min(d,3072-d);
    }

    private static string[] MessagePages(string raw)
    {
        // DOS FarString::scan treats '*' as a page boundary. The final one waits
        // on the last visible page. A new host button advances the durable page index.
        string[] pages = raw.Split('*');
        return raw.EndsWith('*') ? pages[..^1] : pages;
    }

    // ClassicUO starts a tag at '<' but displays ordinary quotes, apostrophes,
    // ampersands and Unicode verbatim. Web-style entities are shown as text.
    private static string GumpText(string text) => text.Replace("<","&lt;",StringComparison.Ordinal);

    private sealed class OriginalDialogueGump : Gump
    {
        private readonly CampaignActor _actor;
        private readonly int _count;
        private readonly string _signature;
        private readonly bool _number;
        public OriginalDialogueGump(CampaignActor actor,int count,string sig,int face,string question,int[] bounds) : base(50,50)
        {
            _actor=actor; _count=count; _signature=sig; _number=true;
            AddPage(0); AddBackground(0,0,500,230,0x242C);
            if(face!=0) AddImage(20,30,face);
            int x=face==0?22:110;
            AddHtml(x,20,468-x,85,DisplayLine(question),false,true);
            AddLabel(x,110,0,$"{bounds[0]} to {bounds[1]} in steps of {bounds[2]}");
            AddBackground(x,138,100,32,0xBB8);
            AddTextEntry(x+5,142,90,25,0,0,bounds[3].ToString(System.Globalization.CultureInfo.InvariantCulture));
            AddButton(x,182,0xFA5,0xFA7,1); AddLabel(x+34,180,0,"Answer");
        }
        public OriginalDialogueGump(CampaignActor actor,int count,string sig,int face,bool choice,string[] texts) : base(50,50)
        {
            _actor=actor; _count=count; _signature=sig;
            AddPage(0);
            AddBackground(0,0,500,230,0x242C);
            if(face != 0) AddImage(20,30,face);
            int x = face == 0 ? 22 : 110;
            if (!choice)
            {
                AddHtml(x,24,468-x,140,DisplayLine(texts[0]),false,true);
                AddButton(x,182,0xFA5,0xFA7,1);
                AddLabel(x+34,180,0,"Continue");
            }
            else
            {
                const int pageSize = 5;
                for (int i=0;i<texts.Length;i++)
                {
                    int index = i % pageSize, page = i / pageSize + 1;
                    if (index == 0)
                    {
                        AddPage(page);
                        if (page>1) AddButton(x,185,0xFAE,0xFB0,0,GumpButtonType.Page,page-1);
                        if (i+pageSize<texts.Length) AddButton(440,185,0xFA5,0xFA7,0,GumpButtonType.Page,page+1);
                    }
                    int y = 25+index*30;
                    AddButton(x,y,0xFA5,0xFA7,i+1);
                    AddHtml(x+36,y,448-x,27,GumpText(texts[i]));
                }
            }
        }
        private static string DisplayLine(string raw)
        {
            var line = new System.Text.StringBuilder();
            for (int i = 0; i < raw.Length; i++)
            {
                char c = raw[i];
                if (c == '^' && i + 1 < raw.Length)
                    c = char.ToUpperInvariant(raw[++i]);
                line.Append(c == '\t' ? ' ' : c);
            }
            return GumpText(line.ToString());
        }
        public override void OnResponse(NetState sender,in RelayInfo info)
        {
            var player=sender.Mobile;
            if (player == null || !Visible.TryGetValue(player.Serial.Value,out var current) || current != this) return;
            Visible.Remove(player.Serial.Value);
            if (info.ButtonID==0 || _actor.Deleted || _actor.Map != player.Map ||
                !State.Active.TryGetValue(player.Serial.Value,out var c) ||
                (!c.Scripted && (c.Automatic ? !player.InRange(_actor.Location,3) || !player.InLOS(_actor)
                                             : !CanTalk(player,_actor))) ||
                c.Actor!=_actor.SourceId || c.History.Count!=_count) return;
            Advance(player,_actor,c,_signature,info.ButtonID,_number?info.GetTextEntry(0):null);
        }
    }
}
