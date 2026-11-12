using Server;
using Server.Items;

namespace UltimaOffline.Entities;

public sealed class CampaignChest : Container, ICampaignEntity
{
    public string SourceId { get; private set; } = "";
    public int SourceQuality { get; private set; }
    public int SourceShape { get; private set; } = 522;
    public override bool Decays => false;
    public override bool IsDecoContainer => SourceShape == 522;
    public CampaignChest(string id, int quality, int art) : base(art)
    {
        SourceId = id; SourceQuality = quality; Movable = false;
    }
    public CampaignChest(Serial serial) : base(serial) { }
    public void SetLockShape(int shape)
    {
        if (shape is not (522 or 800)) throw new InvalidDataException("Unsupported chest transformation");
        SourceShape = shape;
        Name = shape == 522 ? "locked chest" : "chest";
    }
    public override void OnDoubleClick(Mobile player)
    {
        if (player.Map != Map || !player.InRange(GetWorldLocation(), 2) || !player.InLOS(this)) return;
        if (SourceShape == 522) CampaignEntities.EstateUsed?.Invoke(player, this);
        else base.OnDoubleClick(player);
    }
    public override void DisplayTo(Mobile player)
    {
        if (SourceShape == 800) base.DisplayTo(player);
    }
    public override void Serialize(IGenericWriter w)
    {
        base.Serialize(w); w.Write(0); w.Write(SourceId); w.Write(SourceQuality); w.Write(SourceShape);
    }
    public override void Deserialize(IGenericReader r)
    {
        base.Deserialize(r); CampaignEntities.ReadVersion(r); SourceId = r.ReadString();
        SourceQuality = r.ReadInt(); SetLockShape(r.ReadInt());
    }
}
