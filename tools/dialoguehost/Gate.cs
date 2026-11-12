using System.Text.Json;
using Server;
using Server.Network;
using Server.Items;
using UltimaOffline.Entities;

namespace UltimaOffline.Dialogue;

public static partial class CampaignDialogue
{
    private sealed record GateRef(string Id,int Handle,int Shape,int X,int Y);
    private sealed record ActorProgress(int Experience,int Training);
    private sealed record AwardRoster(int SourceOffset,int[] Active,int[] Downed,int[] Returned);
    private sealed class GateAction
    {
        public int Slot { get; set; }
        public int Target { get; set; }
        public int Cursor { get; set; }
        public int LoopRemaining { get; set; } = -1;
        public long Due { get; set; }
        public int OriginPC { get; set; }
        public int[] Program { get; set; } = [];
    }
    private sealed class GateState
    {
        public bool VisibleNpcTalk => true;
        public long Steps { get; set; }
        public long NextTalkStep { get; set; }
        public int TalkSteps { get; set; }
        public bool MayorStartedTalk { get; set; }
        public int[]? OfficeDestination { get; set; }
        public int OfficeSteps { get; set; }
        public bool OfficeArrived { get; set; }
        public bool OfficeWokeFromSleep { get; set; }
        public long NextOfficeStep { get; set; }
        public Queue<Direction> OfficePath { get; set; }=new();
        public SeatSchedule? OfficeSeat { get; set; }
        public uint SeatRandomSeed { get; set; }=0x0BAD0BAD;
        public long? LastClockTicks { get; set; }
        public Dictionary<string,ActorProgress> Progress { get; set; }=new();
        public List<AwardRoster> AwardRosters { get; set; }=new();
        public List<GateAction> Actions { get; set; } = new();
        public List<string> Trace { get; set; } = new();
        public string? Error { get; set; }
    }
    private static readonly Dictionary<int,GateRef> LocalGates=new();
    private static readonly HashSet<int> _witnesses=new();
    private static JsonElement _clues;
    private static JsonElement _coinShape;
    private static GateRef[] _gateCandidates=[];
    private static readonly Dictionary<(int,int),int> ScheduleBeds=new();
    private static string[] ScheduleSeats=[];
    private static int[] _gateBounds=[];
    private static long _initialTime;
    private static int _rate;
    private static int _ticksPerDay;
    private static int _ticksPerMinute;

    private static GateRef GateSource(JsonElement g)
    {
        var p=g.GetProperty("position");
        return new GateRef(g.GetProperty("id").GetString()!,g.GetProperty("handle").GetInt32(),
            g.GetProperty("shape").GetInt32(),p[0].GetInt32(),p[1].GetInt32());
    }
    private static void InstallGate(JsonElement seed,JsonElement manifest)
    {
        if(!seed.TryGetProperty("gate_objects",out var gates) || gates.GetArrayLength()==0) return;
        var roots=manifest.GetProperty("roots").EnumerateObject().Select(k=>k.Value.GetInt32()).ToHashSet();
        if(!new[]{0x40E,0x607,0x609}.All(roots.Contains) || _portraits.GetProperty("14:0").GetInt32()!=64014)
            throw new InvalidDataException("East gate requires the source guard, two lift callbacks and Johnson's portrait.");
        foreach(int slot in new[]{2,13})
            if(roots.Contains(0x400+slot) && _portraits.TryGetProperty($"{slot}:0",out _) &&
               Actor(slot).TryGetProperty("staged_land_id",out _) &&
               (slot!=2 || _portraits.TryGetProperty("2:1",out _))) _witnesses.Add(slot);
        _clues=seed.GetProperty("investigation_items").Clone();
        if(seed.TryGetProperty("runtime_shapes",out var shapes) && shapes.TryGetProperty("644",out var coins)) _coinShape=coins.Clone();
        _gateBounds=seed.GetProperty("gate_query_bounds").EnumerateArray().Select(x=>x.GetInt32()).ToArray();
        if(_gateBounds.Length!=4 || _gateBounds[0]>=_gateBounds[2] || _gateBounds[1]>=_gateBounds[3])
            throw new InvalidDataException("Invalid original gate query bounds.");
        _gateCandidates=seed.GetProperty("gate_search_candidates").EnumerateArray().Select(GateSource).ToArray();
        if(seed.TryGetProperty("schedule_seats",out var seats))
            ScheduleSeats=seats.EnumerateArray().Select(s=>s.GetProperty("id").GetString()!).ToArray();
        if(seed.TryGetProperty("schedule_beds",out var beds))
            foreach(var bed in beds.EnumerateArray())
            {
                var xy=bed.GetProperty("world_xy");
                var key=(xy[0].GetInt32(),xy[1].GetInt32());
                int shape=bed.GetProperty("shape").GetInt32();
                if(shape==1011 || shape==696 && !ScheduleBeds.ContainsKey(key)) ScheduleBeds[key]=shape;
            }
        foreach(var g in gates.EnumerateArray())
        {
            var row=GateSource(g);
            if(!_gateCandidates.Contains(row) || row.Handle!=0x300000+g.GetProperty("archive_offset").GetInt32())
                throw new InvalidDataException("Original gate candidate identity mismatch.");
            LocalGates.Add(row.Handle,row);
        }
        var clock=seed.GetProperty("clock");
        _rate=clock.GetProperty("rate").GetInt32();
        _ticksPerDay=clock.GetProperty("ticks_per_day").GetInt32();
        _ticksPerMinute=clock.GetProperty("ticks_per_minute").GetInt32();
        if(_ticksPerDay!=36000 || _ticksPerMinute!=25 || _rate!=1) throw new InvalidDataException("Unqualified Black Gate clock.");
        _initialTime=checked((long)clock.GetProperty("days").GetInt32()*_ticksPerDay+clock.GetProperty("ticks").GetInt32());
        State.Gate??=new GateState();
        Server.Timer.StartTimer(TimeSpan.FromMilliseconds(100),TimeSpan.FromMilliseconds(100),TickGateWorld);
    }
    private static CampaignGate GateObject(int handle)
    {
        if(!LocalGates.TryGetValue(handle,out var expected) || CampaignEntities.Find(expected.Id) is not CampaignGate obj ||
           obj.Map!=Map.Felucca || obj.X!=expected.X || obj.Y!=expected.Y)
            throw new InvalidDataException($"Missing or moved original gate object {handle}.");
        return obj;
    }
    private static bool GateEffect(Step e,Mobile player,Conversation c,out string? reply)
    {
        reply=null;
        var world=State.Gate!;
        int Arg(int i)=>e.Args[i].GetInt32();
        bool keep=e.Data.GetProperty("expects_value").GetBoolean();
        var party=State.Opening?.Party;
        if(e.Intrinsic==0x21 && Arg(1)==8 && (Arg(0)==Avatar || Arg(0)>Avatar && Arg(0)<0))
        {
            int handle=Arg(0);
            var actor=Actor(handle==Avatar?0:Slot(handle));
            _=OnMap(player,handle) ?? throw new InvalidDataException("Party XP recipient unavailable.");
            string id=actor.GetProperty("id").GetString()!;
            if(!world.Progress.TryGetValue(id,out var previous))
                previous=new ActorProgress(actor.GetProperty("experience").GetInt32(),actor.GetProperty("training").GetInt32());
            if(previous.Experience is <0 or >999999 || previous.Training is <0 or >255)
                throw new InvalidDataException("Invalid source experience or training state.");
            int delta=unchecked((short)Arg(2));
            int experience=Math.Min(999999,previous.Experience+(Math.Max(0,(int)delta)>>1));
            int training=previous.Training;
            for(int threshold=100; threshold<=experience;threshold*=2)
                if(threshold>previous.Experience) training=Math.Min(255,training+3);
            world.Progress[id]=new ActorProgress(experience,training);
            world.Trace.Add($"{world.Steps} experience {handle} {previous.Experience} {experience} {previous.Training} {training}");
            if(keep) reply="1";
            return true;
        }
        if(c.Function==0x040C && e.Data.GetProperty("function_id").GetInt32()==0x0884 && e.Intrinsic==0x2C && keep &&
           e.Args.EnumerateArray().Select(v=>v.GetInt32()).ToArray() is [100,644,-359,-359,1])
        {
            if(party==null || _coinShape.ValueKind!=JsonValueKind.Object ||
                _coinShape.GetProperty("uo_item_id").GetInt32()!=0xEED)
                throw new InvalidDataException("Source currency mapping or party inventory unavailable.");
            string rewardId=$"{State.Build}:0884:0203:{e.Data.GetProperty("source_offset").GetInt32()}";
            if(world.Trace.Any(t=>t.Contains($" coins {rewardId} ",StringComparison.Ordinal)))
                throw new InvalidDataException("Report reward was previously issued without a matching continuation.");
            var coins=new CampaignRewardCoins(rewardId,100);
            try
            {
                foreach(int handle in party)
                {
                    var owner=OnMap(player,handle) ?? throw new InvalidDataException("Unstaged reward recipient.");
                    // DOS TryToPlaceItem searches slot 1, slot 2, then slot 0 for
                    // currency with the default ready record. Slot 0 holds the pack.
                    bool equipped=false;
                    if(_coinShape.TryGetProperty("ready",out var ready))
                    {
                        if(ready.GetProperty("slot").GetInt32()!=0)
                            throw new InvalidDataException("Unqualified currency ready slot.");
                        foreach(var layer in new[]{Layer.OneHanded,Layer.TwoHanded})
                        {
                            coins.Layer=layer;
                            if(owner.EquipItem(coins)) { equipped=true; break; }
                        }
                    }
                    if(!equipped)
                    {
                        coins.Layer=Layer.Invalid;
                        if(owner.Backpack is not { } pack || !pack.TryDropItem(owner,coins,false)) continue;
                    }
                    if(coins.Deleted || (equipped ? coins.Parent!=owner : coins.Parent!=owner.Backpack))
                        throw new InvalidDataException("Reward failed destination ownership check.");
                    world.Trace.Add($"{world.Steps} coins {rewardId} {handle} {coins.Serial.Value} {coins.Amount}");
                    reply=JsonSerializer.Serialize(new[]{handle}); return true;
                }
                reply="0"; return true;
            }
            finally { if(!coins.Deleted && coins.Parent==null) coins.Delete(); }
        }
        if(c.Function==0x040C && e.Data.GetProperty("function_id").GetInt32()==0x0886 &&
           e.Intrinsic==0x10 && keep && Arg(0)==1 && Arg(1)==8 && State.Opening!=null)
        {
            reply=JsonSerializer.Serialize(Roll(State.Opening,1,8)); return true;
        }
        if(c.Function==0x0402 && party!=null)
        {
            if(e.Intrinsic==0x88 && keep && Arg(1)==6) { reply=State.Opening!.ContainsMember(Arg(0))?"1":"0"; return true; }
            if(!keep && e.Intrinsic is 0x1E or 0x1F && Arg(0)==-2)
            {
                var spark=RequireMobile(2);
                if(e.Intrinsic==0x1E && State.Opening!.Join(-2))
                {
                    spark.Combatant=null;
                    State.Work[spark.SourceId]=new WorkSchedule(31,1);
                }
                if(e.Intrinsic==0x1F && State.Opening!.Leave(-2)) State.Work[spark.SourceId]=new WorkSchedule(12,1);
                return true;
            }
            if(e.Intrinsic==0x28 && keep && Arg(0)==-357 && Arg(1)==641 && Arg(2)==253 && Arg(3)==-359)
            {
                var members=party.Select(handle=>OnMap(player,handle) ??
                    throw new InvalidDataException($"Missing party member {handle} during item count.")).ToHashSet();
                var sourceIds=new HashSet<string>();
                foreach(int handle in party)
                {
                    var actor=Actor(handle==Avatar?0:Slot(handle));
                    foreach(var held in actor.GetProperty("inventory").EnumerateArray().Where(i=>i.GetProperty("shape").GetInt32()==641))
                    {
                        var raw=Convert.FromHexString(held.GetProperty("payload_hex").GetString()!);
                        if(raw.Length!=6) throw new InvalidDataException("Unexpected original key record length.");
                        if(raw[5]==253) sourceIds.Add(held.GetProperty("id").GetString()!);
                    }
                }
                foreach(var clue in _clues.EnumerateArray().Where(i=>i.GetProperty("shape").GetInt32()==641 &&
                    i.GetProperty("quality_byte").GetInt32()==253)) sourceIds.Add(clue.GetProperty("id").GetString()!);
                int count=0;
                foreach(string id in sourceIds)
                {
                    if(CampaignEntities.Find(id) is not CampaignInvestigationItem key || key.SourceShape!=641 || key.SourceQuality!=253)
                        throw new InvalidDataException($"Missing matching original party item {id}.");
                    if(key.RootParent is Mobile owner && members.Contains(owner) &&
                       (key.Parent==owner || owner.Backpack!=null && key.IsChildOf(owner.Backpack))) count++;
                }
                reply=JsonSerializer.Serialize(count); return true;
            }
        }
        if(c.Function==0x040D && e.Intrinsic==0x1D && !keep && Arg(0)==-13 && Arg(1)==16)
        {
            var actor=RequireMobile(13);
            State.Work[actor.SourceId]=new WorkSchedule(16,1); return true;
        }
        if(c.Function is not (0x040E or 0x040D)) return false;
        switch(e.Intrinsic)
        {
            case 0x3B when keep:
            {
                long ticks=checked(_initialTime+world.Steps*_rate);
                int hour=(int)((ticks%_ticksPerDay)/(_ticksPerMinute*60));
                int phase=hour/3;
                world.LastClockTicks=ticks;
                reply=JsonSerializer.Serialize(phase); return true;
            }
            case 0x19 when keep && ((Arg(0)==-14 && Arg(1)==-16) || (Arg(0)==-16 && Arg(1)==-14)):
            {
                static (int X,int Y,int Z) Place(int slot)
                {
                    var rec=Actor(slot);
                    if(IsRemoved(rec)) throw new InvalidDataException("Missing original actor in distance query.");
                    if(CampaignEntities.Find(rec.GetProperty("id").GetString()!) is Mobile mobile)
                        return (mobile.X,mobile.Y,mobile.Z);
                    var p=rec.GetProperty("source_position"); return(p[0].GetInt32(),p[1].GetInt32(),4*p[2].GetInt32());
                }
                // Both source human shapes have 1x1 footprints (TFA byte2=0).
                var u=Place(14); var v=Place(16);
                if(u.Z!=v.Z) throw new InvalidDataException("Non-level Johnson/Klog distance needs source height adjustment.");
                reply=JsonSerializer.Serialize(Math.Max(WorldDelta(u.X,v.X),WorldDelta(u.Y,v.Y))); return true;
            }
            case 0x35 when keep && Arg(0)==Avatar && Arg(1) is 271 or 272 or 276 or 277 && Arg(2)==25 && Arg(3)==0:
            {
                if(player.Map!=Map.Felucca || player.X<_gateBounds[0] || player.Y<_gateBounds[1] ||
                    player.X>=_gateBounds[2] || player.Y>=_gateBounds[3]) throw new InvalidDataException("Gate query exceeds the compiled source region.");
                var handles=new List<int>();
                foreach(var obj in _gateCandidates.Where(g=>g.Shape==Arg(1) && WorldDelta(g.X,player.X)<=25 && WorldDelta(g.Y,player.Y)<=25))
                {
                    _=GateObject(obj.Handle);
                    handles.Add(obj.Handle);
                }
                if(handles.Count>1) throw new InvalidDataException("Multiple same-shape gates need a source-ordered spatial query.");
                reply=JsonSerializer.Serialize(handles); return true;
            }
            case 0x42 when keep:
                reply=JsonSerializer.Serialize(GateObject(Arg(0)).SourceLift); return true;
            case 0x01:
            {
                int target=Arg(0);
                _=GateObject(target);
                int[] list=e.Args[1].EnumerateArray().Select(v=>v.GetInt32()).ToArray();
                // Validate the whole list before cancelling an existing action.
                bool winding=list is [70,1,70,2,70,3] or [70,2,70,3] or [70,3] or [70,2,70,1,70,0];
                bool moving=list is [88,32,85,0x607,70,0,11,-7,3] or [35,88,32,85,0x607,70,1,11,-7,2]
                    or [88,32,85,0x607,70,2,11,-7,1] or [88,32,85,0x607,70,2]
                    or [88,32,85,0x609,70,3,11,-7,3];
                var shape=LocalGates[target].Shape;
                if(!(winding && shape is 276 or 277 || moving && shape is 271 or 272))
                    throw new InvalidDataException("Unqualified gate action array: "+e.Args[1].GetRawText());
                if(list[0]!=35) world.Actions.RemoveAll(j=>j.Target==target && j.Program[0]!=35);
                int slot=Enumerable.Range(1,89).FirstOrDefault(i=>world.Actions.All(j=>j.Slot!=i));
                if(slot!=0) world.Actions.Add(new GateAction {Slot=slot,Target=target,Program=list,Due=world.Steps+1,
                    OriginPC=e.Data.GetProperty("pc").GetInt32()});
                if(keep) reply=JsonSerializer.Serialize(slot);
                return true;
            }
            default: return false;
        }
    }
    private static void LiftCallback(CampaignGate item,GateAction j,int function)
    {
        using var vm=new DialogueMachine(_source,function,2,j.Target);
        var get=vm.Next(null);
        if(get.Status!="effect" || get.Kind!="intrinsic" || get.Intrinsic!=0x42 || get.Args[0].GetInt32()!=j.Target)
            throw new InvalidDataException("Missing original gate lift read.");
        int old=item.SourceLift;
        var set=vm.Next(JsonSerializer.Serialize(old));
        if(set.Status!="effect" || set.Kind!="intrinsic" || set.Intrinsic!=0x43 || set.Args[0].GetInt32()!=j.Target ||
            set.Args[1].GetInt32()!=old+(function==0x0607?1:-1) || vm.Next(null).Status!="completed")
            throw new InvalidDataException("Unqualified generated gate lift callback.");
        item.SetSourceState(item.SourceFrame,set.Args[1].GetInt32());
        State.Gate!.Trace.Add($"{State.Gate.Steps} lift {item.SourceId} {function:X4} {old} {item.SourceLift}");
    }
    private static void AdvanceGate(GateAction j)
    {
        var w=State.Gate!;
        var item=GateObject(j.Target);
        int[] a=j.Program;
        for(int i=0;i<3;i++)
        {
            int pc=j.Cursor,cmd=a[pc++];
            switch(cmd)
            {
                case 35: break; // SCRIPT_NO_HALT was applied when the job entered the original queue.
                case 88:
                    pc++; // original SFX 32; native stock portcullis opening/closing sound
                    Effects.PlaySound(item.Location,item.Map,a[pc+1]==0x0607?0xF0:0xEF);
                    break;
                case 85: LiftCallback(item,j,a[pc++]); break;
                case 70: item.SetSourceState(a[pc++],item.SourceLift); break;
                case 11:
                    pc++; // -7 bytes in the packed DOS script jumps to SFX
                    if(j.LoopRemaining<0) j.LoopRemaining=a[pc]; pc++;
                    if(j.LoopRemaining>0) { j.LoopRemaining--;j.Cursor=Array.IndexOf(a,88);continue; }
                    break;
                default: throw new InvalidDataException($"Unsupported original gate opcode {cmd}.");
            }
            j.Cursor=pc; j.Due=w.Steps+1;
            if(pc>=a.Length) w.Actions.Remove(j);
            return;
        }
        throw new InvalidDataException("Gate loop failed to yield.");
    }
    private static int SourceHits(OpeningState roster,int handle) =>
        roster.HitPoints.TryGetValue(handle,out var hp) ? hp : Actor(handle==Avatar?0:Slot(handle)).GetProperty("hit_points").GetInt32();

    private static bool PartyUnconscious(Mobile player,OpeningState roster,int handle)
    {
        var row=Actor(handle==Avatar?0:Slot(handle));
        var mobile=OnMap(player,handle);
        return mobile==null || !mobile.Alive || mobile.Paralyzed || SourceHits(roster,handle)<=0 ||
            Flag(row,1)!=0 || Flag(row,7)!=0 || Flag(row,4)!=0;
    }

    private static void TickGateWorld()
    {
        var w=State.Gate!;
        var player=NetState.Instances.Select(s=>s.Mobile).FirstOrDefault(p=>p!=null && p.Player && p.Map==Map.Felucca &&
            (!_openingEnabled || State.Opening?.Owner==p.Serial.Value));
        if(player==null || State.Active.Count>0 || w.Error!=null) return;
        try
        {
            w.Steps++;
            if(State.Opening is { Status:"complete" } roster)
                roster.UpdateFollowers(h=>PartyUnconscious(player,roster,h));
            foreach(var job in w.Actions.Where(j=>j.Due<=w.Steps).OrderBy(j=>j.Slot).ToArray()) AdvanceGate(job);
            if(_openingEnabled && State.Opening?.Status=="complete" && !w.MayorStartedTalk && w.Steps>=w.NextTalkStep)
                ApproachMayor(player,w);
            if(!_openingEnabled || State.Opening?.Status=="complete")
                RunMayorAppointment(player,w,checked(_initialTime+w.Steps*_rate));
        }
        catch(Exception ex)
        {
            w.Error=$"East gate world step {w.Steps}: {ex.Message}";
            Console.WriteLine("[UltimaOfflineGate] "+w.Error); player.SendMessage(0x22,w.Error);
        }
    }
    private static void ApproachMayor(Mobile player,GateState w)
    {
        var npc=RequireMobile(12);
        if(!State.Work.TryGetValue(npc.SourceId,out var schedule) || schedule.Kind!=3) return;
        w.NextTalkStep=w.Steps+Math.Max(1,(npc.ComputeMovementSpeed()+99)/100);
        if(player.Hidden || !npc.Alive || !player.Alive) return;
        int distance=Math.Max(WorldDelta(player.X,npc.X),WorldDelta(player.Y,npc.Y));
        if(distance>75) return;
        if(distance<=3 && npc.InLOS(player))
        {
            if(schedule.State==1) { State.Work[npc.SourceId]=new WorkSchedule(3,2); return; }
            if(schedule.State==2)
            {
                npc.Direction=npc.GetDirectionTo(player); npc.Animate(4,1,1,true,false,0);
                State.Work[npc.SourceId]=new WorkSchedule(3,3); return;
            }
            var c=new Conversation { Actor=npc.SourceId, Function=npc.FunctionId, Event=1, Item=-12, Automatic=true };
            w.MayorStartedTalk=true;
            w.Trace.Add($"{w.Steps} talk {npc.X} {npc.Y} {player.X} {player.Y} {w.TalkSteps}");
            State.Active.Add(player.Serial.Value,c); Advance(player,npc,c,null,0); return;
        }
        var path=new MovementPath(npc,player.Location);
        if(!path.Success || path.Directions.Length>75) return;
        var direction=path.Directions[0];
        npc.Direction=direction;
        if(npc.Move(direction)) w.TalkSteps++;
    }

    private static void RunMayorAppointment(Mobile player,GateState w,long ticks)
    {
        var actor=Actor(12);
        if(!actor.TryGetProperty("schedule",out var timetable)) return;
        var npc=RequireMobile(12);
        int activity=State.Work.TryGetValue(npc.SourceId,out var work) ? work.Kind : actor.GetProperty("activity").GetInt32();
        bool sleeping=Flag(actor,1)!=0 && !w.OfficeWokeFromSleep;
        if(!npc.Alive || npc.Paralyzed || Flag(actor,7)!=0 || Flag(actor,4)!=0 ||
            actor.GetProperty("hit_points").GetInt32()<=0 || (sleeping && activity!=14) ||
            State.Opening?.Party.Contains(-12)==true) return;
        if(ticks%(_ticksPerMinute*15)==0 && activity is 11 or 14 or 16)
        {
            int period=(int)(ticks%_ticksPerDay)/(_ticksPerMinute*180);
            var entries=timetable.EnumerateArray().OrderBy(row=>(period-row.GetProperty("time_slot").GetInt32()+8)%8);
            var row=entries.FirstOrDefault();
            if(row.ValueKind!=JsonValueKind.Object || row.GetProperty("activity").GetInt32()!=16)
            {
                w.OfficeDestination=null;
                w.OfficeSeat=null;
                return;
            }
            var xy=row.GetProperty("world_xy"); int x=xy[0].GetInt32(),y=xy[1].GetInt32();
            if(x<_gateBounds[0] || x>=_gateBounds[2] || y<_gateBounds[1] || y>=_gateBounds[3]) return;
            if(activity!=16 || (w.OfficeDestination==null && !npc.InRange(new Point3D(x,y,0),25)))
            {
                bool resident=InScheduleWindow(player,npc.X,npc.Y);
                if(activity==14)
                {
                    w.OfficeWokeFromSleep=true;
                    if(resident && ScheduleBeds.TryGetValue((npc.X,npc.Y),out int bed))
                    {
                        // WakeUpNpc prefers southwest then south for bed 1011, northeast then east for 696.
                        npc.Direction=bed==1011 ? Direction.Left : Direction.Right;
                        if(!npc.Move(npc.Direction))
                        {
                            npc.Direction=bed==1011 ? Direction.South : Direction.East;
                            npc.Move(npc.Direction);
                        }
                        w.Trace.Add($"{w.Steps} wake {bed} {npc.X} {npc.Y} {npc.Z}");
                    }
                }
                w.OfficeDestination=[x,y];
                w.OfficeArrived=false;
                w.OfficeSeat=null;
                w.OfficeSteps=0;
                w.OfficePath.Clear();
                State.Work[npc.SourceId]=new WorkSchedule(16,0);
                w.Trace.Add($"{w.Steps} appointment {row.GetProperty("offset").GetInt32()} {period} 16 {x} {y}");
                var office=new Point3D(x,y,0);
                // appts.cpp moves a nonresident NPC directly when the destination is outside 23 tiles.
                if(!resident && !player.InRange(office,23) && npc.Map.CanFit(office,16))
                    npc.MoveToWorld(office,npc.Map);
                // Major sit (activity 16) first pushes walk-to-schedule (49).
                // Its child gets the next update; direct nonresident placement is immediate.
                if(npc.Location!=office) w.NextOfficeStep=w.Steps+1;
            }
        }
        if(w.OfficeDestination is not [int ox,int oy] ||
            !State.Work.TryGetValue(npc.SourceId,out var current) || current.Kind!=16) return;
        if(w.OfficeArrived)
        {
            if(ScheduleSeats.Length>0 && InScheduleWindow(player,npc.X,npc.Y))
                RunOfficeSeat(player,npc,w,current);
            return;
        }
        if(w.Steps<w.NextOfficeStep) return;
        var goal=new Point3D(ox,oy,0);
        // ContinueScheduleWalk consumes one route step per logical update.
        w.NextOfficeStep=w.Steps+1;
        if(npc.Location!=goal)
        {
            // WalkToScheduleSchedule tries the target first, then 14,10,6,2-cell intermediate goals.
            bool moved=false;
            Direction? blocked=null;
            if(w.OfficePath.TryDequeue(out var next))
            {
                var dest=npc.Location;
                Server.Movement.Movement.Offset(next,ref dest);
                npc.Direction=next;
                if(InScheduleWindow(player,dest.X,dest.Y) && npc.Move(next)) { w.OfficeSteps++; moved=true; }
                else { w.OfficePath.Clear(); blocked=next; }
            }
            if(!moved && FindOfficeRoute(player,npc,goal,blocked,out var segment) is {} path)
            {
                w.OfficePath=path;
                // ContinueScheduleWalk finishes a segment in state 1 and increments to 2.
                // WalkToScheduleSchedule spends the next update returning to state 1.
                if(w.OfficeSteps>0 && blocked==null) w.NextOfficeStep=w.Steps+2;
                w.Trace.Add($"{w.Steps} office-route {npc.X} {npc.Y} {segment.X} {segment.Y} {path.Count}");
                return;
            }
            if(moved && npc.Location!=goal) return;
            if(!moved && !player.InRange(goal,23) && !player.InRange(npc.Location,23) && npc.Map.CanFit(goal,16))
                npc.MoveToWorld(goal,npc.Map);
            if(npc.Location!=goal && !npc.InRange(goal,5)) return;
        }
        w.OfficeArrived=true;
        w.OfficePath.Clear();
        State.Work[npc.SourceId]=new WorkSchedule(16,1);
        w.Trace.Add($"{w.Steps} office {npc.X} {npc.Y} {w.OfficeSteps}");
    }
}

// Subdivided pieces retain the reward's source identity and native currency behavior.
public sealed class CampaignRewardCoins : Gold
{
    public string SourceReward { get; private set; }="";
    public int SourceShape=>644;
    public bool SourceTemporary=>true;
    public CampaignRewardCoins() : base(1) { }
    public CampaignRewardCoins(string source,int amount) : base(amount) => SourceReward=source;
    public CampaignRewardCoins(Serial serial) : base(serial) { }
    public override bool StackWith(Mobile from,Item dropped,bool playSound) =>
        dropped is CampaignRewardCoins other && other.SourceReward==SourceReward && base.StackWith(from,dropped,playSound);
    public override void OnAfterDuped(Item copy)
    {
        base.OnAfterDuped(copy);
        if(copy is CampaignRewardCoins coins) coins.SourceReward=SourceReward;
    }
    public override void Serialize(IGenericWriter writer) { base.Serialize(writer); writer.Write(0); writer.Write(SourceReward); }
    public override void Deserialize(IGenericReader reader)
    {
        base.Deserialize(reader);
        if(reader.ReadInt()!=0) throw new InvalidDataException("Unrecognized campaign reward version.");
        SourceReward=reader.ReadString();
    }
}
