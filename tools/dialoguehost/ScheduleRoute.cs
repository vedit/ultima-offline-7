using Server;
using Move = Server.Movement.Movement;

namespace UltimaOffline.Dialogue;

public static partial class CampaignDialogue
{
    private static bool InScheduleWindow(Mobile player,int x,int y) =>
        (x-(player.X&~15)+32+3072)%3072<80 && (y-(player.Y&~15)+32+3072)%3072<80;

    private sealed record RouteNode(Point3D Previous,Direction Direction,int Steps);

    // StartPath tries the full destination, then 14,10,6,2-tile segments in that order.
    // The stock UO path search only examines a 38-tile square centered between the endpoints.
    // Reuse the live UO collision check for each step throughout the original 80-tile window.
    private static Queue<Direction>? FindOfficeRoute(Mobile player,Mobile npc,Point3D office,
        Direction? blocked,out Point3D segment,bool exactSeat=false)
    {
        var start=npc.Location;
        var goals=new List<Point3D>();
        segment=office;
        if(exactSeat && start==office) return new Queue<Direction>();
        foreach(int limit in exactSeat ? new[]{100} : new[]{150,14,10,6,2})
        {
            var point=new Point3D(start.X+Math.Clamp(office.X-start.X,-limit,limit),
                start.Y+Math.Clamp(office.Y-start.Y,-limit,limit),office.Z);
            if(point!=start && (!exactSeat || point==office) && InScheduleWindow(player,point.X,point.Y) && !goals.Contains(point))
                goals.Add(point);
        }
        if(goals.Count==0) return null;
        int Distance(Point3D p) => Math.Max(Math.Abs(p.X-goals[0].X),Math.Abs(p.Y-goals[0].Y));
        var nodes=new Dictionary<Point3D,RouteNode> { [start]=new(start,0,0) };
        var queue=new PriorityQueue<Point3D,(int Cost,int Remaining,int Order)>();
        int order=0;
        queue.Enqueue(start,(Distance(start),Distance(start),order++));
        while(queue.TryDequeue(out var here,out var rank))
        {
            int depth=nodes[here].Steps;
            if(rank.Cost!=depth+rank.Remaining) continue;
            if(here==goals[0]) break;
            if(depth==(exactSeat ? 100 : 150)) continue;
            for(int i=0;i<8;i++)
            {
                var direction=(Direction)i;
                if(here==start && direction==blocked) continue;
                int x=here.X,y=here.Y;
                Move.Offset(direction,ref x,ref y);
                if(!InScheduleWindow(player,x,y) || !Move.CheckMovement(npc,npc.Map,here,direction,out int z))
                    continue;
                var next=new Point3D(x,y,z);
                if(nodes.TryGetValue(next,out var old) && old.Steps<=depth+1) continue;
                nodes[next]=new(here,direction,depth+1);
                int remaining=Distance(next);
                queue.Enqueue(next,(depth+1+remaining,remaining,order++));
            }
        }
        foreach(var goal in goals)
        {
            if(!nodes.ContainsKey(goal)) continue;
            var directions=new Stack<Direction>();
            for(var p=goal;p!=start;p=nodes[p].Previous) directions.Push(nodes[p].Direction);
            segment=goal;
            return new Queue<Direction>(directions);
        }
        return null;
    }
}
