using System.Text;
using System.Text.Json;
using Server;
using Server.Network;
using UltimaOffline.Entities;

namespace UltimaOffline.Dialogue;

public static partial class CampaignDialogue
{
    // Positive IDs in this VM namespace represent distinct original objects.
    // Actor literal references remain negative, including UC_AVATAR (-356).
    private const int EggHandle = 0x100001;
    private const int GateHandle = 0x100002;
    private static bool _openingEnabled;
    private static string _eggId = "";
    private static JsonElement _music;
    private static JsonElement _gate;
    private static JsonElement _search;
    private static Mobile? _connectedOwner;

    private sealed class ActionJob
    {
        public int Slot { get; set; }
        public int Target { get; set; }
        public int Due { get; set; }
        public int Cursor { get; set; }
        public int SourcePC { get; set; }
        public bool NoHalt { get; set; }
        public JsonElement Commands { get; set; }
        public Dictionary<int,int> LoopCounters { get; set; } = new();
    }
    private sealed class OpeningState : PartyRoster
    {
        public uint Owner { get; set; }
        public string Egg { get; set; } = "";
        public string Status { get; set; } = "running";
        public string? Error { get; set; }
        public bool Locked { get; set; } = true;
        public int Tick { get; set; }
        public Dictionary<int,sbyte> HitPoints { get; set; } = new();
        public int AvatarFrame { get; set; }
        public bool GateCreated { get; set; }
        public string? GateId { get; set; }
        public int GateFrame { get; set; }
        public bool MusicResume { get; set; }
        public uint RandomSeed { get; set; } = 0x0BAD0BAD;
        public int QuakeUntil { get; set; }
        public Dictionary<int,int> Frames { get; set; } = new();
        public Dictionary<int,int> Facings { get; set; } = new();
        public List<ActionJob> Actions { get; set; } = new();
        public List<string> Trace { get; set; } = new();
    }

    private static void InstallOpening(string dir,JsonElement seed,JsonElement module)
    {
        _openingEnabled=ServerConfiguration.GetSetting("ultimaOffline.openingEgg", false);
        if (!_openingEnabled) return;
        var ids=module.GetProperty("roots").EnumerateObject().Select(p=>p.Value.GetInt32()).ToHashSet();
        if (!new[] {0x0401,0x06AA,0x0618,0x061A,0x06FA}.All(ids.Contains))
            throw new InvalidDataException("Opening module lacks a queued callback.");
        var egg=seed.GetProperty("eggs").EnumerateArray().Single(e=>e.GetProperty("shape").GetInt32()==275 &&
            e.GetProperty("offset").GetInt32()==3501 && e.GetProperty("member").GetString()=="u7ireg64");
        var pos=egg.GetProperty("position");
        if (pos[0].GetInt32()!=1076 || pos[1].GetInt32()!=2214 || pos[2].GetInt32()!=0 ||
            egg.GetProperty("function_id").GetInt32()!=0x401 || egg.GetProperty("event").GetInt32()!=3 ||
            egg.GetProperty("kind_id").GetInt32()!=5 || egg.GetProperty("criteria").GetInt32()!=0 ||
            !egg.GetProperty("once").GetBoolean() || egg.GetProperty("hatched").GetBoolean() ||
            egg.GetProperty("nocturnal").GetBoolean() || egg.GetProperty("repeat").GetBoolean() ||
            egg.GetProperty("probability").GetInt32()!=100) throw new InvalidDataException("Unqualified cached opening egg.");
        _eggId=egg.GetProperty("id").GetString()!;
        var participants=seed.GetProperty("opening_party_slots");
        if (participants.GetArrayLength()!=1 || participants[0].GetInt32()!=0 ||
            Bit(seed.GetProperty("opening_avatar_dont_move"))!=1) throw new InvalidDataException("Opening initial engine state differs.");
        _music=FileJson(Path.Combine(dir,"music.json")).GetProperty("tracks").GetProperty("35");
        _gate=seed.GetProperty("runtime_shapes").GetProperty("157").Clone();
        var nearby=seed.GetProperty("opening_nearby");
        var center=nearby.GetProperty("center");
        if(center[0].GetInt32()!=1076 || center[1].GetInt32()!=2214 ||
            nearby.GetProperty("radius").GetInt32()!=40 || nearby.GetProperty("mask").GetInt32()!=8)
            throw new InvalidDataException("Opening NPC search was compiled for a different query.");
        _search=nearby.GetProperty("slots").Clone();
        if (_music.GetProperty("client_slot").GetInt32() is < 1 or > 255 || _gate.GetProperty("uo_item_id").GetInt32()<=0)
            throw new InvalidDataException("Opening art or music binding is invalid.");
        EventSink.Connected += mob => Server.Timer.StartTimer(TimeSpan.FromMilliseconds(250),()=>Attach(mob));
        EventSink.Disconnected += mob => { if (_connectedOwner==mob) _connectedOwner=null; Visible.Remove(mob.Serial.Value); };
        EventSink.Movement += e => {
            if (e.Mobile.Player && e.Mobile.Map==Map.Felucca && (State.Opening == null ||
                (State.Opening.Owner==e.Mobile.Serial.Value && (State.Opening.Locked || State.Opening.Status=="blocked"))))
                e.Blocked=true;
        };
        Server.Timer.StartTimer(TimeSpan.FromMilliseconds(100),TimeSpan.FromMilliseconds(100),TickOpening);
    }

    private static void Attach(Mobile player)
    {
        if (!player.Player || player.NetState==null || player.Map!=Map.Felucca) return;
        if (State.Opening==null)
        {
            var pos=Actor(0).GetProperty("source_position");
            if(player.X!=pos[0].GetInt32() || player.Y!=pos[1].GetInt32() || player.Z!=pos[2].GetInt32()*4)
            {
                player.SendMessage("Opening egg requires the Avatar's original starting location in a new private world.");
                return;
            }
            var fresh=new OpeningState { Owner=player.Serial.Value, Egg=_eggId };
            State.Opening=fresh; _connectedOwner=player;
            RunOpeningProgram(player,fresh,0x401,3,EggHandle);
            return;
        }
        var o=State.Opening;
        if(o.Owner!=player.Serial.Value || o.Egg!=_eggId) return;
        _connectedOwner=player;
        // A compatible host update may implement the pending opcode. Retry
        // at most once per new connection, from the saved effect/array cursor.
        if (o.Status=="blocked") { o.Status="running"; o.Error=null; }
        if (State.Active.TryGetValue(o.Owner,out var c) && c.Scripted)
            Advance(player,RequireMobile(1),c,null,0);
    }

    private static void RunOpeningProgram(Mobile player,OpeningState o,int id,int ev,int item)
    {
        var actor=RequireMobile(1);
        if(State.Active.ContainsKey(o.Owner)) throw new InvalidDataException("An opening callback collides with an active conversation.");
        var c=new Conversation { Actor=actor.SourceId, Function=id, Event=ev, Item=item, Scripted=true };
        State.Active.Add(o.Owner,c);
        o.Trace.Add($"{o.Tick} call {id:X4} {ev} {item}");
        Advance(player,actor,c,null,0);
    }
    private static void PauseOpening(OpeningState o,string message)
    {
        o.Status="blocked"; o.Error=message;
    }
    private static int FreeSlot(OpeningState o)
    {
        for(int i=1;i<90;i++) if(!o.Actions.Any(a=>a.Slot==i)) return i;
        return 0;
    }
    private static int Roll(OpeningState o,int low,int high)
    {
        // Pinned BG common/random.cpp NextRandom, including the word carry.
        o.RandomSeed=NextSourceRandom(o.RandomSeed);
        return low+(int)((o.RandomSeed>>16)%(uint)(high-low+1));
    }
    private static uint NextSourceRandom(uint seed)
    {
        uint triple=unchecked(seed*3u), sum=(triple>>16)+(seed&0xFFFF);
        return (uint)(ushort)(sum+(sum>>16))<<16 | (ushort)(triple+1);
    }
    private static Mobile? OnMap(Mobile player,int handle) => handle==Avatar?player:
        CampaignEntities.Find(Actor(Slot(handle)).GetProperty("id").GetString()!) as Mobile;
    private static bool OpeningEffect(Step e,Mobile player,out string? reply)
    {
        reply=null;
        var o=State.Opening!;
        var a=e.Args;
        int Arg(int i)=>a[i].GetInt32();
        bool keep=e.Data.GetProperty("expects_value").GetBoolean();
        switch(e.Intrinsic)
        {
            case 0x1B when keep && Arg(0)==Avatar: reply="-356"; return true;
            case 0x11 when keep && Arg(0)==Avatar:
                reply=player.Female?"989":"721"; return true;
            case 0x68 when keep: reply="1"; return true; // supported mouse on the private Windows classic client
            case 0x88 when keep && Arg(0)==Avatar && Arg(1)==16: reply=o.Locked?"1":"0"; return true;
            case 0x88 when keep && Arg(0)==Avatar && Arg(1)==10:
                // No active vehicle is attached to the starting Avatar.
                reply="0"; return true;
            case 0x88 when keep && Arg(0)==Avatar && Arg(1)==25:
                reply="0"; return true; // normal new game's OinkMode is zero; no opening step sets it.
            case 0x35 when keep && Arg(0)==Avatar && Arg(1)==-359 && Arg(2)==40 && Arg(3)==8:
            {
                if (_search.ValueKind!=JsonValueKind.Array || player.X!=1076 || player.Y!=2214)
                    throw new InvalidDataException("The original ordered nearby NPC search is unavailable for this Avatar position.");
                foreach(var row in _actors.EnumerateObject())
                {
                    int slot=row.Value.GetProperty("npc_slot").GetInt32();
                    if(slot==0 || CampaignEntities.Find(row.Value.GetProperty("id").GetString()!) is not Mobile other) continue;
                    var pos=row.Value.GetProperty("source_position");
                    if(other.X!=pos[0].GetInt32() || other.Y!=pos[1].GetInt32() || other.Z!=4*pos[2].GetInt32())
                        throw new InvalidDataException("NPC movement invalidated the compiled DOS object traversal order.");
                }
                var handles=new List<int>();
                foreach(var v in _search.EnumerateArray())
                {
                    int slot=v.GetInt32(), handle=slot==0?Avatar:-slot;
                    var row=Actor(slot); var mob=OnMap(player,handle);
                    var pos=row.GetProperty("source_position");
                    if (!IsRemoved(row) && Flag(row,4)==0 && Flag(row,0)==0 &&
                        (mob==null || (mob.Alive && !mob.Hidden && mob.Map==player.Map)) &&
                        WorldDelta(player.X,mob?.X??pos[0].GetInt32())<=40 && WorldDelta(player.Y,mob?.Y??pos[1].GetInt32())<=40)
                        handles.Add(handle);
                }
                reply=JsonSerializer.Serialize(handles); return true;
            }
            case 0x10 when keep && Arg(0)>=short.MinValue && Arg(1)<=short.MaxValue &&
                Arg(0)<=Arg(1) && Arg(1)-Arg(0)<ushort.MaxValue:
                reply=JsonSerializer.Serialize(Roll(o,Arg(0),Arg(1))); return true;
            case 0 when keep && Arg(0)>0 && Arg(0)<=8:
                reply=JsonSerializer.Serialize(Roll(o,1,Arg(0))); return true;
            case 0x5E when keep:
                reply=JsonSerializer.Serialize(a[0].ValueKind==JsonValueKind.Array?a[0].GetArrayLength():1); return true;
            case 0x3A when keep && (Arg(0)==Avatar || Arg(0)<0 && Arg(0)>Avatar):
                if(Arg(0)!=Avatar) _=Actor(Slot(Arg(0)));
                reply=JsonSerializer.Serialize(Arg(0)); return true;
            case 0x59 when !keep && Arg(0)==18:
                o.QuakeUntil=o.Tick+18;
                player.PlaySound(0x220); // native UO earthquake presentation
                o.Trace.Add($"{o.Tick} earthquake 18"); return true;
            case 0x5C when !keep:
            {
                int target=Arg(0);
                if(target!=Avatar) _=Actor(Slot(target));
                foreach(var old in o.Actions.Where(j=>j.Target==target && !j.NoHalt).ToArray())
                {
                    o.Trace.Add($"{o.Tick} halt {old.Slot} {target} {old.SourcePC:X}"); o.Actions.Remove(old);
                }
                return true;
            }
            case 0x1D when !keep && ((Arg(0)==-11 && Arg(1)==7) || (Arg(0)==-12 && Arg(1)==3)):
            {
                var npc=RequireMobile(Slot(Arg(0))); npc.Combatant=null;
                State.Work[npc.SourceId]=new WorkSchedule(Arg(1),1); return true;
            }
            case 0x8A when !keep && Arg(0)==Avatar && Arg(1)==16:
                o.Locked=false; o.Trace.Add($"{o.Tick} unlock"); return true;
            case 0x2E when !keep && Arg(0)==35 && Arg(1)==0:
                PlayScore(player,o,false); return true;
            case 0x01 or 0x02:
            {
                int target=Arg(0);
                if (target!=Avatar && target!=GateHandle) _=Actor(Slot(target));
                var list=a[1];
                int n=list.GetArrayLength();
                if(n<1 || n>128) throw new InvalidDataException("Bad source action list.");
                int delay=e.Intrinsic==1?1:Math.Max(1,checked(Arg(2)+1));
                bool noHalt=list.EnumerateArray().Any(v=>v.ValueKind==JsonValueKind.Number && v.GetInt32()==35);
                if(!noHalt) o.Actions.RemoveAll(j=>j.Target==target && !j.NoHalt);
                int slot=FreeSlot(o);
                if(slot!=0) o.Actions.Add(new ActionJob {Slot=slot,Target=target,Due=checked(o.Tick+delay),
                    Commands=list.Clone(),SourcePC=e.Data.GetProperty("pc").GetInt32(),NoHalt=noHalt});
                if(keep) reply=JsonSerializer.Serialize(slot);
                return true;
            }
            case 0x24 when keep && Arg(0)==157:
                if (o.GateCreated) throw new InvalidDataException("Duplicate source gate creation.");
                o.GateCreated=true; reply=JsonSerializer.Serialize(GateHandle); return true;
            case 0x6C when !keep && Arg(0)==Avatar && Arg(1)==32:
                o.AvatarFrame=32; return true;
            case 0x18 when keep && Arg(0)==Avatar:
                if(player.Z%4!=0) throw new InvalidDataException("Avatar lift is outside the source transform.");
                reply=JsonSerializer.Serialize(new[]{player.X,player.Y,player.Z/4}); return true;
            case 0x26 when keep && o.GateCreated && o.GateId==null:
            {
                var p=a[0];
                var site=new Point3D(p[0].GetInt32(),p[1].GetInt32(),checked(p[2].GetInt32()*4));
                if (p.GetArrayLength()!=3 || site.X!=1080 || site.Y!=2215 || site.Z!=0)
                    throw new InvalidDataException("Unqualified source gate location.");
                // The original caller has just created the item off-map. Place
                // its one saved play-world entity at the original computed point.
                var entity=CampaignEntities.SpawnOnce(o.Egg+"/06AA:0B",_gate.GetProperty("uo_item_id").GetInt32(),site) as CampaignItem;
                if(entity==null) { reply="0"; return true; }
                entity.Name=_gate.GetProperty("name").GetString();
                entity.Movable=false;
                o.GateId=entity.SourceId; o.Trace.Add($"{o.Tick} gate {site.X} {site.Y} {site.Z}"); reply="1"; return true;
            }
            case 0x70 when !keep:
                // This scene does not start a targeting cursor. A player-driven
                // target cannot be silently admitted to the opening.
                if(player.Target!=null) player.Target.Cancel(player,Server.Targeting.TargetCancelType.Canceled);
                return true;
            case 0x1E when Arg(0)==-1:
            {
                if(keep) throw new InvalidDataException("Unqualified value return from join-party.");
                var iolo=RequireMobile(1);
                if(o.Join(-1))
                {
                    State.Work[iolo.SourceId]=new WorkSchedule(31,1); // WORK_FOLLOW_AVT
                }
                return true;
            }
            default: return false;
        }
    }
    private static void PlayScore(Mobile player,OpeningState o,bool resume)
    {
        int track=_music.GetProperty("client_slot").GetInt32();
        player.NetState.SendPlayMusic((MusicName)track);
        o.MusicResume=resume;
        o.Trace.Add($"{o.Tick} score 35 {track} {(resume?1:0)}");
    }

    private static void TickOpening()
    {
        var o=State.Opening;
        var player=_connectedOwner;
        if(o==null || o.Status!="running" || player?.NetState==null || player.Map!=Map.Felucca || State.Active.ContainsKey(o.Owner)) return;
        try
        {
            o.Tick++;
            foreach(var job in o.Actions.Where(j=>j.Due<=o.Tick).OrderBy(j=>j.Due).ThenBy(j=>j.Slot).ToArray())
            {
                if(!o.Actions.Contains(job)) continue;
                AdvanceJob(player,o,job);
                if(o.Status=="blocked" || State.Active.ContainsKey(o.Owner)) return;
            }
            if(o.Actions.Count==0)
            {
                if(o.Locked || o.GateId==null || CampaignEntities.Find(o.GateId)!=null ||
                    !o.Trace.Any(t=>t.Contains(" call 06FA ")) || !o.Party.Contains(-1) ||
                    new[]{20,59,92}.Any(i=>State.Changes.GetValueOrDefault(i,_flags[i])!=1))
                    throw new InvalidDataException("Opening queue drained before completing the original callback chain.");
                o.Status="complete"; o.Trace.Add($"{o.Tick} complete");
            }
        }
        catch(Exception ex)
        {
            string error=$"Opening paused on source tick {o.Tick}: {ex.Message}";
            PauseOpening(o,error); Console.WriteLine("[UltimaOfflineOpening] "+error); player.SendMessage(0x22,error);
        }
    }
    private static void AdvanceJob(Mobile player,OpeningState o,ActionJob j)
    {
        var cmd=j.Commands;
        var len=cmd.GetArrayLength();
        int pc=j.Cursor;
        int Read()=>cmd[pc++].GetInt32();
        for(int count=0;count<64;count++)
        {
            if(pc>=len) { o.Actions.Remove(j); return; }
            if(cmd[pc].ValueKind==JsonValueKind.String)
            {
                // An empty text operand outside SCRIPT_BARK serializes to
                // two quote bytes. DOS skips that literal without a signal.
                if(cmd[pc].GetString()!="") throw new InvalidDataException("Unqualified action text outside bark.");
                j.Cursor=++pc; j.Due=o.Tick+1; return;
            }
            int start=pc, op=Read();
            switch(op)
            {
                case 35 or 44: break; // SCRIPT_NO_HALT / SCRIPT_FINISH set flags on admission.
                case 82:
                {
                    string bark=cmd[pc++].GetString()!;
                    if (bark.Contains('"') || Encoding.UTF8.GetByteCount(bark)>79)
                        throw new InvalidDataException("Bark exceeds the verified DOS text-buffer profile.");
                    var actor=RequireMobile(Slot(j.Target));
                    actor.Say(bark.AsSpan());
                    o.Trace.Add($"{o.Tick} bark {j.Target} {Hash(Encoding.UTF8.GetBytes(bark))}"); break;
                }
                case 84:
                {
                    int track=Read(), resume=Read();
                    if(track==0 && resume==0) o.MusicResume=false; // DOS keeps the current track
                    else if(track==35 && resume==1) PlayScore(player,o,true);
                    else throw new InvalidDataException("Unmapped scheduled score.");
                    break;
                }
                case 85:
                {
                    int f=Read();
                    if(!((j.Target==Avatar && f is 0x06AA or 0x0401 or 0x061A or 0x06FA) || (j.Target==GateHandle && f==0x0618)))
                        throw new InvalidDataException($"Unqualified opening callback {f:X4} on {j.Target}.");
                    j.Cursor=pc; j.Due=o.Tick+1; RunOpeningProgram(player,o,f,2,j.Target);
                    if(pc>=len) o.Actions.Remove(j);
                    return;
                }
                case 70 or 78 or 80 when j.Target==GateHandle:
                {
                    int value=op==70 ? Read() : o.GateFrame+(op==78 ? 1 : -1);
                    int frames=_gate.GetProperty("source_frames").GetInt32();
                    if(CampaignEntities.Find(o.GateId!) is not Item) throw new InvalidDataException("Missing original summoned gate.");
                    o.GateFrame=(value%frames+frames)%frames;
                    break;
                }
                case 11:
                {
                    int delta=Read(), initial=Read();
                    if(delta!=-1 || start<1 || cmd[start-1].GetInt32() is not (78 or 80)) throw new InvalidDataException("Unsupported action loop.");
                    int left=j.LoopCounters.GetValueOrDefault(start,initial);
                    if(left>0) { j.LoopCounters[start]=left-1; pc=start-1; }
                    continue;
                }
                case 45 when j.Target==GateHandle:
                    var gate=CampaignEntities.Find(o.GateId!) as Item ?? throw new InvalidDataException("Missing gate for delete.");
                    gate.Delete(); break;
                case 83 when j.Target==Avatar:
                {
                    int direction=Read()-48, lift=Read();
                    if(direction!=6 || lift!=0) throw new InvalidDataException("Unsupported original Avatar step.");
                    player.Direction=Direction.West;
                    if(!player.Move(Direction.West)) throw new InvalidDataException("Original westward Avatar step was blocked.");
                    o.Trace.Add($"{o.Tick} step {player.X} {player.Y}"); break;
                }
                case 89:
                {
                    int facing=(Read()-48)&7; o.Facings[j.Target]=facing;
                    var mobile=OnMap(player,j.Target);
                    if(mobile!=null) mobile.Direction=(Direction)facing;
                    break;
                }
                case 97 or 100 or 108 or 109 or 110:
                {
                    o.Frames[j.Target]=op-97;
                    var mobile=OnMap(player,j.Target);
                    // UO human groups: stand, armed stance, and bow. There
                    // is no matching general-purpose UO sitting action.
                    if(mobile!=null && op!=110)
                        mobile.Animate(op switch {97=>4,100=>7,_=>32},1,1,true,false,0);
                    break;
                }
                case 39:
                    int wait=Read(); j.Cursor=pc; j.Due=checked(o.Tick+wait); return;
                default: throw new InvalidDataException($"Unqualified action {op} at source PC {j.SourcePC:X}, array index {start}.");
            }
            j.Cursor=pc;
            if(pc>=len) o.Actions.Remove(j);
            else j.Due=o.Tick+1;
            return;
        }
        throw new InvalidDataException("Original action failed to yield.");
    }
}
