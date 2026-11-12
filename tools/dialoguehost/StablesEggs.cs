using System.Text.Json;
using Server;

namespace UltimaOffline.Dialogue;

// ModernUO calls HandlesOnMovement entities after committing Mobile.SetLocation.
// This invisible, zero-height "nodraw" item has no collision or use interaction.
public sealed class StablesEggSensor : Item
{
    public string SourceId { get; private set; } = "";
    public sealed override bool HandlesOnMovement => true;
    public StablesEggSensor(string id) : base(1) { SourceId=id; Movable=false; Visible=false; }
    public StablesEggSensor(Serial serial) : base(serial) { }
    public override void OnMovement(Mobile player,Point3D oldLocation) =>
        CampaignDialogue.OnStablesMovement(this,player,oldLocation);
    public override void Serialize(IGenericWriter w) { base.Serialize(w); w.Write(1); w.Write(SourceId); }
    public override void Deserialize(IGenericReader r)
    {
        base.Deserialize(r);
        if(r.ReadInt()!=1) throw new InvalidDataException("Unsupported stables egg sensor.");
        SourceId=r.ReadString();
    }
}

public static partial class CampaignDialogue
{
    private sealed record SourceEgg(string Id,int MemberOffset,int ArchiveOffset,int X,int Y,int Radius);
    private sealed record EggFire(int MemberOffset,int ArchiveOffset,int Radius,uint Player,
        int BeforeX,int BeforeY,int X,int Y,int Z,int Flag,int Before,int After,int Function,int Event,int PC,int SourceOffset,string EffectHash);
    private static readonly Dictionary<string,SourceEgg> StablesEggs = new();

    private static void InstallStablesEggs(JsonElement seed,JsonElement manifest)
    {
        if(!seed.TryGetProperty("eggs",out var eggs)) return;
        foreach(var row in eggs.EnumerateArray())
        {
            if(row.GetProperty("member").GetString()!="u7ireg64" || !row.TryGetProperty("function_id",out var fn) ||
                fn.GetInt32()!=0x06A4) continue;
            int offset=row.GetProperty("offset").GetInt32();
            if(offset is not (2056 or 2489)) continue;
            var expected=offset==2056?(1077,2182,2,263265):(1069,2206,1,263698);
            var p=row.GetProperty("position");
            int x=p[0].GetInt32(), y=p[1].GetInt32(), radius=row.GetProperty("distance").GetInt32(), file=row.GetProperty("archive_offset").GetInt32();
            string id=row.GetProperty("id").GetString()!;
            if((x,y,radius,file)!=expected || p[2].GetInt32()!=0 || row.GetProperty("event").GetInt32()!=3 ||
                row.GetProperty("shape").GetInt32()!=275 || row.GetProperty("kind_id").GetInt32()!=5 ||
                row.GetProperty("criteria").GetInt32()!=2 || !row.GetProperty("once").GetBoolean() ||
                row.GetProperty("hatched").GetBoolean() || row.GetProperty("repeat").GetBoolean() ||
                row.GetProperty("nocturnal").GetBoolean() || row.GetProperty("probability").GetInt32()!=100 ||
                id!=$"ireg:{seed.GetProperty("seed_sha256").GetString()}:u7ireg64:{offset}")
                throw new InvalidDataException($"Unqualified original stables trigger at {offset}.");
            StablesEggs.Add(id,new SourceEgg(id,offset,file,x,y,radius));
        }
        if(StablesEggs.Count==0) return;
        if(!manifest.GetProperty("roots").EnumerateObject().Any(p=>p.Value.GetInt32()==0x06A4))
            throw new InvalidDataException("Stables terrain includes original eggs without compiled 06A4.");
        var art=TileData.ItemTable[1];
        if(art.Impassable || art.Surface || art.Height!=0 || !string.Equals(art.Name,"nodraw",StringComparison.OrdinalIgnoreCase))
            throw new InvalidDataException("Stables sensor carrier is not zero-height nonblocking nodraw art.");
        var saved=World.Items.Values.OfType<StablesEggSensor>().ToDictionary(s=>s.SourceId);
        if(saved.Keys.Any(id=>!StablesEggs.ContainsKey(id)) || State.Hatched.Keys.Any(id=>!StablesEggs.ContainsKey(id)))
            throw new InvalidDataException("Saved stables sensor has no source record.");
        foreach(var egg in StablesEggs.Values)
        {
            if(State.Hatched.ContainsKey(egg.Id))
            {
                if(saved.ContainsKey(egg.Id)) throw new InvalidDataException("One-shot egg has both a receipt and live sensor.");
                continue;
            }
            var pos=new Point3D(egg.X,egg.Y,0);
            if(saved.TryGetValue(egg.Id,out var sensor))
            {
                if(sensor.Map!=Map.Felucca || sensor.Location!=pos || sensor.Visible || sensor.Movable)
                    throw new InvalidDataException("Saved stables sensor differs from the source anchor.");
            }
            else new StablesEggSensor(egg.Id).MoveToWorld(pos,Map.Felucca);
        }
    }
    internal static void OnStablesMovement(StablesEggSensor sensor,Mobile player,Point3D old)
    {
        if (!player.Player || player.NetState==null || player.Map!=sensor.Map || old==player.Location ||
            !StablesEggs.TryGetValue(sensor.SourceId,out var egg) || State.Hatched.ContainsKey(egg.Id)) return;
        if(_openingEnabled && (State.Opening?.Owner!=player.Serial.Value || State.Opening.Status!="complete")) return;
        // Black Gate trigger.cpp maps both criteria 1 and 2 to script opcode
        // 43. Item_isAvatarNear uses maximum XY distance; only teleport eggs
        // compare lifts. Both Usecode triggers occupy Trinsic's exterior map.
        if(WorldDelta(egg.X,player.X)>egg.Radius || WorldDelta(egg.Y,player.Y)>egg.Radius) return;
        try
        {
            using var vm=new DialogueMachine(_source,0x06A4,3,0x200000+egg.MemberOffset);
            Step step=vm.Next(null);
            if(step.Status!="effect" || step.Kind!="flag_write" || step.Data.GetProperty("function_id").GetInt32()!=0x06A4 ||
                step.Data.GetProperty("expects_value").GetBoolean() || step.Args.GetArrayLength()!=2)
                throw new InvalidDataException("Unexpected original stables Usecode effect.");
            int flag=step.Args[0].GetInt32(), value=Bit(step.Args[1]);
            if(flag!=60 || value!=1 || vm.Next(null).Status!="completed")
                throw new InvalidDataException("Unqualified stables flag result or additional effect.");
            var fire=new EggFire(egg.MemberOffset,egg.ArchiveOffset,egg.Radius,player.Serial.Value,
                old.X,old.Y,player.X,player.Y,player.Z,flag,State.Changes.GetValueOrDefault(flag,_flags[flag]),value,0x06A4,3,
                step.Data.GetProperty("pc").GetInt32(),step.Data.GetProperty("source_offset").GetInt32(),step.Signature);
            // All validation precedes the single game-thread world-state commit.
            State.Changes[flag]=value;
            State.Hatched.Add(egg.Id,fire);
            sensor.Delete();
        }
        catch(Exception ex)
        {
            string message=$"Stables trigger {egg.MemberOffset} paused: {ex.Message}";
            Console.WriteLine("[UltimaOfflineDialogue] "+message); player.SendMessage(0x22,message);
        }
    }
}
