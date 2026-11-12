using Server;

namespace UltimaOffline.Entities;

// Usecode addresses one object. The UO tile engine tests one item per cell.
public class CampaignScenery : Item, ICampaignEntity
{
    public string SourceId { get; private set; } = "";
    public int SourceFrame { get; private set; }
    public int SourceLift => Z / 4;
    private int _width, _height;
    private readonly List<Item> _parts = new();

    public CampaignScenery(string id, int art, string label, int frame, int width, int height, Point3D anchor) : base(art)
    {
        if (width is < 1 or > 8 || height is < 1 or > 8 || anchor.Z % 4 != 0)
            throw new InvalidDataException("Invalid source gate extent");
        SourceId = id;
        Name = label;
        Movable = false;
        SourceFrame = frame;
        _width = width;
        _height = height;
        MoveToWorld(anchor, Map.Felucca);
        for (int i = 1; i < width * height; i++)
        {
            var part = new Item(art) { Name = label, Movable = false };
            part.MoveToWorld(new Point3D(X - i % width, Y - i / width, Z), Map);
            _parts.Add(part);
        }
    }

    public CampaignScenery(Serial serial) : base(serial) { }

    protected void SetComponentState(int frame, int lift)
    {
        if (frame is < 0 or > 3 || lift is < 0 or > 15 || _parts.Count != _width * _height - 1 ||
            _parts.Any(part => part.Deleted || part.Map != Map))
            throw new InvalidDataException($"Invalid gate state or component for {SourceId}");
        SourceFrame = frame;
        Z = lift * 4;
        for (int i = 0; i < _parts.Count; i++)
            _parts[i].Location = new Point3D(X - (i + 1) % _width, Y - (i + 1) / _width, Z);
    }

    public override void OnAfterDelete()
    {
        foreach (var part in _parts) part.Delete();
        base.OnAfterDelete();
    }

    public override void Serialize(IGenericWriter writer)
    {
        base.Serialize(writer);
        writer.Write(0); writer.Write(SourceId); writer.Write(SourceFrame); writer.Write(_width); writer.Write(_height);
        foreach (var part in _parts) writer.Write(part);
    }

    public override void Deserialize(IGenericReader reader)
    {
        base.Deserialize(reader);
        CampaignEntities.ReadVersion(reader);
        SourceId = reader.ReadString(); SourceFrame = reader.ReadInt(); _width = reader.ReadInt(); _height = reader.ReadInt();
        if (_width is < 1 or > 8 || _height is < 1 or > 8)
            throw new InvalidDataException("Invalid saved gate extent");
        for (int i = 1; i < _width * _height; i++)
            _parts.Add(reader.ReadEntity<Item>() ?? throw new InvalidDataException("Missing saved gate component"));
    }
}

public sealed class CampaignGate : CampaignScenery
{
    public CampaignGate(string id,int art,string label,int frame,int width,int height,Point3D anchor)
        : base(id,art,label,frame,width,height,anchor) { }
    public CampaignGate(Serial serial) : base(serial) { }
    public void SetSourceState(int frame,int lift) => SetComponentState(frame,lift);
}
