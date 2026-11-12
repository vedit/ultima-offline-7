using System.Text.Json;
using Server;
using Server.Items;

namespace UltimaOffline.Entities;

public interface IRegionalObject : ICampaignEntity
{
    string SourcePayload { get; }
}

public sealed class RegionalItem : Item, IRegionalObject
{
    public string SourceId { get; private set; } = "";
    public string SourcePayload { get; private set; } = "";
    public bool IsSwampBoots
    {
        get
        {
            var bytes=Convert.FromHexString(SourcePayload);
            return bytes.Length==6 && ((bytes[2]|bytes[3]<<8)&1023)==588;
        }
    }
    public override bool Decays => false;
    public RegionalItem(string id,string payload,int art) : base(art) => (SourceId,SourcePayload)=(id,payload);
    public RegionalItem(Serial serial) : base(serial) { }
    public override void Serialize(IGenericWriter w) { base.Serialize(w); w.Write(0); w.Write(SourceId); w.Write(SourcePayload); }
    public override void Deserialize(IGenericReader r)
    {
        base.Deserialize(r); CampaignEntities.ReadVersion(r); SourceId=r.ReadString(); SourcePayload=r.ReadString();
    }
}

public sealed class RegionalContainer : Container, IRegionalObject
{
    public string SourceId { get; private set; } = "";
    public string SourcePayload { get; private set; } = "";
    public override bool Decays => false;
    public RegionalContainer(string id,string payload,int art) : base(art) => (SourceId,SourcePayload)=(id,payload);
    public RegionalContainer(Serial serial) : base(serial) { }
    public override void Serialize(IGenericWriter w) { base.Serialize(w); w.Write(0); w.Write(SourceId); w.Write(SourcePayload); }
    public override void Deserialize(IGenericReader r)
    {
        base.Deserialize(r); CampaignEntities.ReadVersion(r); SourceId=r.ReadString(); SourcePayload=r.ReadString();
    }
}

internal static class RegionalObjects
{
    internal static void Import(byte[] data,string seed,Dictionary<string,IEntity> known)
    {
        using var manifest=JsonDocument.Parse(data);
        var root=manifest.RootElement;
        if (root.GetProperty("schema").GetInt32()!=1 || root.GetProperty("seed_sha256").GetString()!=seed)
            throw new InvalidDataException("Regional object manifest belongs to a different source world.");
        var materials=root.GetProperty("materials");
        var parents=new Dictionary<string,int>(StringComparer.Ordinal);
        var ids=new HashSet<string>(known.Keys,StringComparer.Ordinal);
        var placements=new List<(string Id,string? Parent,string Payload,string Name,int Art,int Weight,Point3D Location,bool Container)>();
        foreach (var row in root.GetProperty("objects").EnumerateArray())
        {
            int N(string name)=>row.GetProperty(name).GetInt32();
            string S(string name)=>row.GetProperty(name).GetString()!;
            string id=S("id"), member=S("member"), payload=S("payload");
            string? parent=row.GetProperty("parent").GetString();
            bool container=S("kind")=="container";
            int shape=N("shape"), frame=N("frame");
            var mat=materials.GetProperty(shape.ToString(System.Globalization.CultureInfo.InvariantCulture));
            var xy=row.GetProperty("xy");
            var loc=new Point3D(xy[0].GetInt32(),xy[1].GetInt32(),N("lift")*4);
            byte[] raw=Convert.FromHexString(payload);
            if (id!=$"ireg:{seed}:{member}:{N("offset")}" || !ids.Add(id) ||
                raw.Length!=(container?12:6) || (raw[2]|raw[3]<<8)!=(shape|frame<<10) ||
                raw[container?9:4]>>4!=N("lift") || (mat.GetProperty("class").GetInt32()==6)!=container)
                throw new InvalidDataException($"Invalid regional record {id}");
            var variants=mat.GetProperty("art");
            var art=variants[(frame&31)%variants.GetArrayLength()];
            int graphic=N("art");
            if (graphic!=art.GetProperty("id").GetInt32() ||
                (ulong)TileData.ItemTable[graphic].Flags!=art.GetProperty("flags").GetUInt64() ||
                TileData.ItemTable[graphic].Height!=art.GetProperty("height").GetInt32())
                throw new InvalidDataException($"Regional art disagrees with ModernUO for {id}");
            if (parent==null)
            {
                int region=Convert.ToInt32(member[6..],16);
                if (member!=$"u7ireg{region:x2}" || region is <0 or >=144 ||
                    loc.X!=region%12*256+raw[0] || loc.Y!=region/12*256+raw[1] ||
                    Map.Felucca.Tiles.GetLandTile(loc.X,loc.Y).ID!=N("land"))
                    throw new InvalidDataException($"Invalid regional world anchor for {id}");
            }
            else
            {
                if (!parents.TryGetValue(parent,out int ordinal) || N("ordinal")!=ordinal ||
                    loc.X!=raw[0] || loc.Y!=raw[1])
                    throw new InvalidDataException($"Regional inventory parent or order differs for {id}");
                parents[parent]=ordinal+1;
            }
            if (container) parents.Add(id,0);
            placements.Add((id,parent,payload,mat.GetProperty("name").GetString()!,graphic,
                mat.GetProperty("weight_tenths").GetInt32(),loc,container));
        }
        foreach (var p in placements)
        {
            Item item=p.Container?new RegionalContainer(p.Id,p.Payload,p.Art):new RegionalItem(p.Id,p.Payload,p.Art);
            item.Name=p.Name; item.Weight=p.Weight/10.0; item.Movable=p.Weight>0; item.Stackable=false;
            if(item is RegionalItem { IsSwampBoots:true }) item.Layer=Layer.Shoes;
            if (p.Parent==null) item.MoveToWorld(p.Location,Map.Felucca);
            else { ((Container)known[p.Parent]).AddItem(item); item.Location=p.Location; }
            known.Add(p.Id,item);
        }
    }
}
