using Server;
using UltimaOffline.Entities;

namespace UltimaOffline.Dialogue;

public static partial class CampaignDialogue
{
    // The non-party branch of schesit.c pushes activity 35 with both parameters -1.
    // Keep its child state, path, and posted script across world saves.
    private sealed class SeatSchedule
    {
        public int State { get; set; }
        public string? SeatId { get; set; }
        public Point3D Target { get; set; }
        public Queue<Direction> Path { get; set; }=new();
        public int Pose { get; set; }
        public long Due { get; set; }
    }

    private static bool SeatAvailable(CampaignInvestigationItem seat,Mobile npc)
    {
        if(seat.Deleted || seat.Map!=npc.Map || seat.Parent!=null) return false;
        foreach(var other in npc.Map.GetMobilesInRange(seat.Location,0))
            if(other!=npc && other.Alive && other.Z==seat.Z) return false;
        return true;
    }

    private static int SeatChoice(GateState w,int count)
    {
        uint seed=NextSourceRandom(State.Opening?.RandomSeed ?? w.SeatRandomSeed);
        if(State.Opening is {} opening) opening.RandomSeed=seed;
        w.SeatRandomSeed=seed;
        return count==0 ? 0 : (int)((seed>>16)%(uint)count);
    }

    private static Point3D SeatAnchor(CampaignInvestigationItem seat)
    {
        var point=seat.Location;
        Server.Movement.Movement.Offset((Direction)(((seat.SourceFrame&3)*2+4)%8),ref point);
        return point;
    }

    private static bool StartSeatPath(Mobile player,CampaignActor npc,GateState w,SeatSchedule child)
    {
        var candidates=ScheduleSeats.Select(id=>CampaignEntities.Find(id)).OfType<CampaignInvestigationItem>()
            .Where(item=>!item.Deleted && item.Map==npc.Map && item.Parent==null && npc.InRange(SeatAnchor(item),12))
            .OrderByDescending(item=>SeatAnchor(item).Y>>4).ThenByDescending(item=>SeatAnchor(item).X>>4).ToArray();
        foreach(int shape in new[]{873,292})
        {
            var seats=candidates.Where(item=>item.SourceShape==shape).ToArray();
            int chosen=SeatChoice(w,seats.Length);
            if(seats.Length==0) continue;
            foreach(var seat in seats.Prepend(seats[chosen]))
            {
                if(!SeatAvailable(seat,npc)) continue;
                var path=FindOfficeRoute(player,npc,seat.Location,null,out _,exactSeat:true);
                if(path==null) continue;
                child.SeatId=seat.SourceId;
                child.Target=seat.Location;
                child.Path=path;
                child.State=5;
                w.Trace.Add($"{w.Steps} chair-route {seat.SourceId} {seat.X} {seat.Y} {path.Count}");
                return true;
            }
        }
        return false;
    }

    private static void RunOfficeSeat(Mobile player,CampaignActor npc,GateState w,WorkSchedule work)
    {
        if(work.State==3) return;
        if(w.OfficeSeat==null)
        {
            if(work.State!=1) return;
            w.OfficeSeat=new SeatSchedule();
            return;
        }
        var child=w.OfficeSeat;
        if(w.Steps<child.Due) return;
        if(child.State==0) { child.State=4; return; }
        if(child.State==4)
        {
            if(StartSeatPath(player,npc,w,child)) return;
            State.Work[npc.SourceId]=new WorkSchedule(11,1);
            w.OfficeSeat=null;
            w.Trace.Add($"{w.Steps} chair-unavailable");
            return;
        }
        var seat=child.SeatId==null ? null : CampaignEntities.Find(child.SeatId) as CampaignInvestigationItem;
        bool available=seat!=null && seat.Location==child.Target && SeatAvailable(seat,npc);
        switch(child.State)
        {
            case 5:
                if(child.Path.TryDequeue(out var step))
                {
                    var next=npc.Location;
                    Server.Movement.Movement.Offset(step,ref next);
                    npc.Direction=step;
                    if((next.X==child.Target.X && next.Y==child.Target.Y && !available) || !npc.Move(step))
                    {
                        // Route::walk tries a reachable remaining waypoint before reporting failure.
                        if(available && FindOfficeRoute(player,npc,child.Target,step,out _,exactSeat:true) is {Count:>0} detour)
                        {
                            child.Path=detour;
                            return;
                        }
                        child.Path.Clear();
                        child.State=-1;
                        State.Work[npc.SourceId]=new WorkSchedule(16,2);
                        w.Trace.Add($"{w.Steps} chair-blocked {child.SeatId} {npc.X} {npc.Y}");
                        return;
                    }
                }
                if(child.Path.Count==0) child.State=6;
                break;
            case 6:
                child.State=available && npc.Location==child.Target ? 9 : 4;
                break;
            case 9:
                if(!available)
                {
                    child.State=-1;
                    State.Work[npc.SourceId]=new WorkSchedule(16,2);
                    break;
                }
                npc.Direction=(Direction)((seat!.SourceFrame&3)*2);
                // The DOS script posts STAND, BEND and SIT, waiting two ticks after each.
                // ClassicUO draws the stationary human through its native chair table.
                child.Pose=1;
                child.Due=w.Steps+2;
                child.State=10;
                break;
            case 10:
                if(child.Pose<3)
                {
                    child.Pose++;
                    child.Due=w.Steps+2;
                    break;
                }
                State.Work[npc.SourceId]=new WorkSchedule(16,2);
                child.State=11;
                break;
            case 11:
                State.Work[npc.SourceId]=new WorkSchedule(16,3);
                w.Trace.Add($"{w.Steps} seated {npc.X} {npc.Y} {npc.Z} {(int)npc.Direction} {child.SeatId}");
                break;
            case -1:
                // ContinueScheduleWalk pops the failed child. The major sit parent switches to loiter.
                State.Work[npc.SourceId]=new WorkSchedule(11,1);
                w.OfficeSeat=null;
                w.Trace.Add($"{w.Steps} chair-loiter {npc.X} {npc.Y}");
                break;
        }
    }
}
