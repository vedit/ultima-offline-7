using System.Buffers.Binary;
using System.Text.Json;
using Server;
using UltimaOffline.Entities;

namespace UltimaOffline.Dialogue;

public sealed class SwampSensor : Item
{
    public override bool HandlesOnMovement => true;
    public SwampSensor() : base(1) { Visible=false; Movable=false; }
    public SwampSensor(Serial serial) : base(serial) { }
    public override void OnMovement(Mobile actor,Point3D old) => CampaignDialogue.OnSwampMovement(this,actor,old);
    public override void Serialize(IGenericWriter w) { base.Serialize(w); w.Write(0); }
    public override void Deserialize(IGenericReader r)
    {
        base.Deserialize(r);
        if(r.ReadInt()!=0) throw new InvalidDataException("Unsupported field sensor version");
    }
}

public static partial class CampaignDialogue
{
    private sealed record FieldActor(int Slot,int Width,int Height,bool Flies,bool Safe);
    private sealed record Contact(uint Serial,int X,int Y,int FieldX,int FieldY,int Shape,int Roll,bool Boots,bool Flying,bool Immune,bool Poisoned);
    private sealed class SwampState
    {
        public uint RandomSeed { get; set; } = 0x0BAD0BAD;
        public Dictionary<string,bool> Poisoned { get; set; } = new();
        public long Contacts { get; set; }
        public Contact? Last { get; set; }
    }
    private static readonly Dictionary<(int,int),int> Fields = new();
    private static readonly Dictionary<string,FieldActor> _swampActors = new();
    private static string PlayerKey(Mobile actor) => $"player:{actor.Serial.Value}";

    private static bool IsPoisoned(string key,JsonElement row) =>
        State.Swamp.Poisoned.GetValueOrDefault(key,Flag(row,8)!=0);

    private static void ChangePoison(string key,JsonElement row,bool value,bool safe)
    {
        if(value && safe || IsPoisoned(key,row)==value) return;
        State.Swamp.Poisoned[key]=value;
    }

    private static void InstallSwamp(string dir,JsonElement story)
    {
        string file=Path.Combine(dir,"swamp.json");
        if(!File.Exists(file)) return;
        var profile=FileJson(file);
        byte[] raw=File.ReadAllBytes(Path.Combine(dir,"swamp-fields.bin"));
        if(raw.Length%6!=0 || Hash(raw)!=profile.GetProperty("contacts_sha256").GetString() ||
           profile.GetProperty("seed_sha256").GetString()!=story.GetProperty("seed_sha256").GetString())
            throw new InvalidDataException("Field contact index disagrees with the campaign");
        var chunks=new HashSet<(int,int)>();
        foreach(var p in profile.GetProperty("actors").EnumerateObject())
        {
            int slot=int.Parse(p.Name);
            var row=p.Value;
            var info=new FieldActor(slot,row.GetProperty("width").GetInt32(),row.GetProperty("height").GetInt32(),
                row.GetProperty("flies").GetBoolean(),row.GetProperty("poison_safe").GetBoolean());
            _swampActors.Add(Actor(slot).GetProperty("id").GetString()!,info);
        }
        for(int i=0;i<raw.Length;i+=6)
        {
            int x=BinaryPrimitives.ReadUInt16LittleEndian(raw.AsSpan(i));
            int y=BinaryPrimitives.ReadUInt16LittleEndian(raw.AsSpan(i+2));
            int shape=BinaryPrimitives.ReadUInt16LittleEndian(raw.AsSpan(i+4));
            if(x>=3072 || y>=3072 || shape>=1024 || !Fields.TryAdd((x,y),shape))
                throw new InvalidDataException("Invalid or duplicate field coordinate");
            // Source actor footprints extend west and north by at most seven cells.
            for(int bx=x/16;bx<=Math.Min(191,(x+7)/16);bx++)
                for(int by=y/16;by<=Math.Min(191,(y+7)/16);by++) chunks.Add((bx,by));
        }
        var saved=World.Items.Values.OfType<SwampSensor>().ToDictionary(s=>(s.X/16,s.Y/16));
        foreach(var (bx,by) in chunks)
        {
            var pos=new Point3D(16*bx+8,16*by+8,0);
            if(saved.Remove((bx,by),out var sensor))
            {
                if(sensor.Map!=Map.Felucca || sensor.Location!=pos || sensor.Visible || sensor.Movable)
                    throw new InvalidDataException("Invalid saved field sensor");
            }
            else new SwampSensor().MoveToWorld(pos,Map.Felucca);
        }
        if(saved.Count!=0) throw new InvalidDataException("Saved field sensor outside source coverage");
    }

    internal static void OnSwampMovement(SwampSensor sensor,Mobile actor,Point3D old)
    {
        if(actor.Map!=Map.Felucca || !actor.Alive || actor.Z!=0 || old==actor.Location ||
           actor.X/16!=sensor.X/16 || actor.Y/16!=sensor.Y/16) return;
        string? id=actor.Player ? Actor(0).GetProperty("id").GetString() : (actor as CampaignActor)?.SourceId;
        if(id==null || !_swampActors.TryGetValue(id,out var info)) return;
        for(int dy=0;dy<info.Height;dy++)
        for(int dx=0;dx<info.Width;dx++)
        {
            int x=actor.X-dx,y=actor.Y-dy;
            if(!Fields.TryGetValue((x,y),out int shape)) continue;
            if(shape is not (22 or 67 or 334 or 335)) return;
            var state=State.Swamp;
            int roll;
            if(State.Opening is {} opening) roll=Roll(opening,0,99);
            else
            {
                state.RandomSeed=NextSourceRandom(state.RandomSeed);
                roll=(int)((state.RandomSeed>>16)%100);
            }
            bool boots=actor.FindItemOnLayer(Layer.Shoes) is RegionalItem { IsSwampBoots:true };
            bool flying=actor.Flying || info.Flies;
            string key=actor.Player ? PlayerKey(actor) : id;
            var row=Actor(info.Slot);
            if(roll<3 && !boots && !flying && !info.Safe && !IsPoisoned(key,row))
            {
                ChangePoison(key,row,true,false);
                actor.SendMessage("The swamp has poisoned thee.");
            }
            state.Contacts++;
            state.Last=new Contact(actor.Serial.Value,actor.X,actor.Y,x,y,shape,roll,boots,flying,info.Safe,IsPoisoned(key,row));
            return;
        }
    }
}
