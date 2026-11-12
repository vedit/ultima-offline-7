using System.Text.Json;
using Server;
using Server.Items;

namespace UltimaOffline.Entities;

public interface ICampaignEntity { string SourceId { get; } }

// Identity is serialized with the owning ModernUO entity. It does not depend
// on the current parent, location, display name, or reuse of a shard serial.
public sealed class CampaignItem : Item, ICampaignEntity
{
    public string SourceId { get; private set; } = "";
    public CampaignItem(string id, int art) : base(art) => SourceId = id;
    public CampaignItem(Serial serial) : base(serial) { }
    public override void Serialize(IGenericWriter w) { base.Serialize(w); w.Write(0); w.Write(SourceId); }
    public override void Deserialize(IGenericReader r) { base.Deserialize(r); CampaignEntities.ReadVersion(r); SourceId = r.ReadString(); }
}

public sealed class CampaignInvestigationItem : Item, ICampaignEntity
{
    public string SourceId { get; private set; } = "";
    public int SourceShape { get; private set; }
    public int SourceFrame { get; private set; }
    public int SourceQuality { get; private set; }
    public override bool Decays => false;

    public CampaignInvestigationItem(string sourceId, int shape, int frame, int quality, int art) : base(art)
        => (SourceId, SourceShape, SourceFrame, SourceQuality) = (sourceId, shape, frame, quality);
    public CampaignInvestigationItem(Serial serial) : base(serial) { }
    public override bool CanStackWith(Item item) => false;
    public override void OnDoubleClick(Mobile player)
    {
        if (SourceShape is 641 or 797 && CampaignEntities.EstateUsed != null)
            CampaignEntities.EstateUsed(player, this);
        else base.OnDoubleClick(player);
    }

    public override void Serialize(IGenericWriter writer)
    {
        base.Serialize(writer);
        writer.Write(0); writer.Write(SourceId); writer.Write(SourceShape); writer.Write(SourceFrame); writer.Write(SourceQuality);
    }

    public override void Deserialize(IGenericReader reader)
    {
        base.Deserialize(reader);
        CampaignEntities.ReadVersion(reader);
        SourceId = reader.ReadString(); SourceShape = reader.ReadInt(); SourceFrame = reader.ReadInt(); SourceQuality = reader.ReadInt();
    }
}

public sealed class CampaignFixture : Item, ICampaignEntity
{
    public string SourceId { get; private set; } = "";
    public int FunctionId { get; private set; }
    public CampaignFixture(string id, int function, int art) : base(art) =>
        (SourceId, FunctionId, Movable) = (id, function, false);
    public CampaignFixture(Serial serial) : base(serial) { }
    public override void OnDoubleClick(Mobile player)
    {
        if (player.Map == Map && player.InRange(Location, 2) && player.InLOS(this))
            player.SendMessage($"Unimplemented fixture action in Usecode 0x{FunctionId:X4}, event 1, object {SourceId}.");
    }
    public override void Serialize(IGenericWriter w) { base.Serialize(w); w.Write(0); w.Write(SourceId); w.Write(FunctionId); }
    public override void Deserialize(IGenericReader r)
    {
        base.Deserialize(r); CampaignEntities.ReadVersion(r); SourceId = r.ReadString(); FunctionId = r.ReadInt();
    }
}

public sealed class CampaignContainer : Container, ICampaignEntity
{
    public string SourceId { get; private set; } = "";
    public CampaignContainer(string id, int art) : base(art) => SourceId = id;
    public CampaignContainer(Serial serial) : base(serial) { }
    public override void Serialize(IGenericWriter w) { base.Serialize(w); w.Write(0); w.Write(SourceId); }
    public override void Deserialize(IGenericReader r) { base.Deserialize(r); CampaignEntities.ReadVersion(r); SourceId = r.ReadString(); }
}

public sealed class CampaignActor : Mobile, ICampaignEntity
{
    public string SourceId { get; private set; } = "";
    public int FunctionId { get; private set; }
    public CampaignActor(string id, int function) { SourceId = id; FunctionId = function; }
    public CampaignActor(Serial serial) : base(serial) { }
    public override void Serialize(IGenericWriter w) { base.Serialize(w); w.Write(0); w.Write(SourceId); w.Write(FunctionId); }
    public override void Deserialize(IGenericReader r)
    {
        base.Deserialize(r); CampaignEntities.ReadVersion(r); SourceId = r.ReadString(); FunctionId = r.ReadInt();
    }
    public override void OnDoubleClick(Mobile from)
    {
        if (CampaignEntities.ActorUsed != null && (CampaignEntities.CanTalk?.Invoke(from,this)
            ?? (from.Map == Map && from.InRange(Location, 2) && from.InLOS(this))))
            CampaignEntities.ActorUsed(from, this);
        else base.OnDoubleClick(from);
    }
}

public static class CampaignEntities
{
    // A campaign script host may subscribe to the ordinary in-range interaction.
    public static Action<Mobile, CampaignActor>? ActorUsed { get; set; }
    public static Func<Mobile, CampaignActor, bool>? CanTalk { get; set; }
    public static Action<Mobile, Item>? EstateUsed { get; set; }
    private static Registry? _registry;
    private static readonly Dictionary<string, IEntity> ById = new(StringComparer.Ordinal);
    public static IReadOnlyDictionary<string, IEntity> Entries => ById;
    public static IEntity? Find(string id) => ById.TryGetValue(id, out var obj) && !obj.Deleted ? obj : null;
    public static void ReadVersion(IGenericReader r)
    {
        if (r.ReadInt() != 0) throw new InvalidDataException("Unsupported Ultima Offline entity save");
    }

    private sealed class Registry : GenericPersistence
    {
        public string Seed = "";
        public string RegionalDigest = "";
        public Dictionary<string,string> Spawns = new(StringComparer.Ordinal);
        public Registry() : base("UltimaOfflineEntities", 10) { }
        public override void Serialize(IGenericWriter w)
        {
            w.Write(1); w.Write(Seed); w.Write(RegionalDigest); w.Write(Spawns.Count);
            foreach (var pair in Spawns.OrderBy(p => p.Key, StringComparer.Ordinal)) { w.Write(pair.Key); w.Write(pair.Value); }
        }
        public override void Deserialize(IGenericReader r)
        {
            int version=r.ReadInt();
            if (version is <0 or >1) throw new InvalidDataException("Unsupported campaign entity registry");
            Seed=r.ReadString(); RegionalDigest=version==1?r.ReadString():""; int count=r.ReadInt();
            if (count < 0 || count > 1_000_000) throw new InvalidDataException("Invalid campaign spawn count");
            for (int i = 0; i < count; ++i) Spawns.Add(r.ReadString(), r.ReadString());
        }
    }

    public static void Configure()
    {
        if (ServerConfiguration.GetSetting("ultimaOffline.privateFacet", false)) _registry = new Registry();
    }

    public static void Initialize()
    {
        if (_registry == null) return;
        string dir = Path.Combine(Core.BaseDirectory, "Campaign");
        using var actorDoc = JsonDocument.Parse(File.ReadAllBytes(Path.Combine(dir, "actor.json")));
        using var itemsDoc = JsonDocument.Parse(File.ReadAllBytes(Path.Combine(dir, "container.json")));
        var actor = actorDoc.RootElement;
        var inventory = itemsDoc.RootElement;
        string seed = Str(actor,"seed_sha256");
        if (seed.Length != 64 || Str(inventory, "seed_sha256") != seed || Str(actor,"name") != "Finnigan" ||
            Int(actor,"function_id") != 0x40C || Int(actor,"npc_slot") != 12 || Str(inventory,"member") != "u7ireg64")
            throw new InvalidDataException("Mismatched or unqualified campaign actor and inventory inputs");
        foreach (var entity in World.Items.Values.Cast<IEntity>().Concat(World.Mobiles.Values))
            if (entity is ICampaignEntity known) ById.Add(known.SourceId, entity);
        string regionalFile=Path.Combine(dir,"world-live.json");
        byte[]? regional=File.Exists(regionalFile)?File.ReadAllBytes(regionalFile):null;
        string regionalDigest=regional==null?"":Convert.ToHexStringLower(System.Security.Cryptography.SHA256.HashData(regional));
        if (_registry.Seed != "")
        {
            if (_registry.Seed != seed) throw new InvalidDataException("Campaign seed differs from saved world");
            if (_registry.RegionalDigest!=regionalDigest)
                throw new InvalidDataException("Regional import differs from the saved campaign");
            return; // Even an empty world can be a legitimate saved result of deletions.
        }
        if (ById.Count != 0) throw new InvalidDataException("Saved entities found without their seed registry");
        var records = inventory.GetProperty("objects").EnumerateArray().ToArray();
        var seen = new HashSet<string>();
        string prefix = $"ireg:{seed}:u7ireg64:";
        foreach (var item in records)
        {
            string id = Str(item, "id"), edge = Str(item, "edge");
            string? parent = item.GetProperty("parent").GetString();
            if (id != prefix + Int(item,"offset") || seen.Contains(id) ||
                (edge == "world" ? parent != null : parent == null || !seen.Contains(parent)) ||
                edge is not ("world" or "inventory" or "barge_member"))
                throw new InvalidDataException($"Invalid campaign object path or order at {id}");
            Presentation(Int(item,"shape"), Int(item,"frame"));
            seen.Add(id);
        }
        var position = actor.GetProperty("source_position");
        if (Str(actor,"id") != $"npc:{seed}:npc.dat:12" || records.Length == 0 ||
            records[0].GetProperty("world_xy").GetArrayLength() != 2 || Str(records[0],"kind") != "barge")
            throw new InvalidDataException("Invalid Finnigan binding or missing barge anchor");
        CheckMap(position[0].GetInt32(), position[1].GetInt32(), false);
        var anchor = records[0].GetProperty("world_xy");
        foreach (var item in records.Where(i => Str(i,"edge") != "inventory"))
        {
            var raw = item.GetProperty("raw_xy");
            CheckMap((anchor[0].GetInt32() & ~255) + raw[0].GetInt32(),
                     (anchor[1].GetInt32() & ~255) + raw[1].GetInt32(), true);
        }
        var storyFile = Path.Combine(dir, "story-seed.json");
        if (File.Exists(storyFile))
        {
            using var storyDoc = JsonDocument.Parse(File.ReadAllBytes(storyFile));
            var story = storyDoc.RootElement;
            if (Str(story, "seed_sha256") != seed) throw new InvalidDataException("Mismatched story seed");
            foreach (var slot in story.GetProperty("walking_actor_slots").EnumerateArray())
            {
                var source = story.GetProperty("actors").GetProperty(slot.GetInt32().ToString());
                var xy = source.GetProperty("source_position");
                if (Int(source, "npc_slot") == 0 || Int(source,"staged_land_id") !=
                    Map.Felucca.Tiles.GetLandTile(xy[0].GetInt32(), xy[1].GetInt32()).ID)
                    throw new InvalidDataException("Story actor anchor disagrees with the private facet");
                PlaceActor(source);
            }
            if (story.TryGetProperty("investigation_items", out var clues))
            {
                foreach (var clue in clues.EnumerateArray())
                {
                    var xy = clue.GetProperty("world_xy");
                    var location = new Point3D(xy[0].GetInt32(), xy[1].GetInt32(), Int(clue, "lift") * 4);
                    string id = Str(clue, "id");
                    string member = clue.TryGetProperty("member", out var clueMember) ? clueMember.GetString()! : "u7ireg64";
                    if (id != $"ireg:{seed}:{member}:{Int(clue, "offset")}" || Str(clue, "edge") != "world" ||
                        Map.Felucca.Tiles.GetLandTile(location.X, location.Y).ID != Int(clue, "staged_land_id"))
                        throw new InvalidDataException($"Unqualified investigation item anchor for {id}");
                    var item = new CampaignInvestigationItem(id, Int(clue, "shape"), Int(clue, "frame"),
                        Int(clue, "quality_byte"), Int(clue, "uo_art"))
                    {
                        Name = Str(clue, "display_name"), Movable = clue.GetProperty("movable").GetBoolean(), Stackable = false
                    };
                    item.MoveToWorld(location, Map.Felucca);
                    ById.Add(id, item);
                }
            }
            if (story.TryGetProperty("schedule_seats",out var seats))
                foreach(var seat in seats.EnumerateArray())
                {
                    var xy=seat.GetProperty("sitting_xy");
                    int shape=Int(seat,"shape"), art=Int(seat,"art");
                    if(shape is not (873 or 292) || art is <0xB2E or >0xB31 || TileData.ItemTable[art].Height!=1)
                        throw new InvalidDataException("Invalid native chair placement");
                    var item=new CampaignInvestigationItem(Str(seat,"id"),shape,Int(seat,"frame"),Int(seat,"quality_byte"),art)
                    { Name=shape==873?"chair":"seat", Movable=seat.GetProperty("movable").GetBoolean() };
                    // ClassicUO seats an idle human on the same tile as the chair graphic.
                    item.MoveToWorld(new Point3D(xy[0].GetInt32(),xy[1].GetInt32(),Int(seat,"lift")*4),Map.Felucca);
                    ById.Add(item.SourceId,item);
                }
            if (story.TryGetProperty("town_fences",out var fences))
                foreach(var fence in fences.EnumerateArray())
                {
                    int art=Int(fence,"art");
                    var data=TileData.ItemTable[art];
                    if(data.Height!=8 || (data.Flags & TileFlag.Impassable)==0)
                        throw new InvalidDataException("Fence collision does not match the source's two lifts.");
                    var xy=fence.GetProperty("world_xy");
                    var size=fence.GetProperty("footprint");
                    var pos=new Point3D(xy[0].GetInt32(),xy[1].GetInt32(),Int(fence,"lift")*4);
                    var entity=new CampaignScenery(Str(fence,"id"),art,"fence",Int(fence,"frame"),
                        size[0].GetInt32(),size[1].GetInt32(),pos);
                    ById.Add(entity.SourceId,entity);
                }
            if (story.TryGetProperty("gate_objects", out var gates))
            {
                foreach (var gate in gates.EnumerateArray())
                {
                    var xyz = gate.GetProperty("position");
                    var gateAnchor = new Point3D(xyz[0].GetInt32(), xyz[1].GetInt32(), xyz[2].GetInt32() * 4);
                    var extent = gate.GetProperty("footprint");
                    if (Map.Felucca.Tiles.GetLandTile(gateAnchor.X, gateAnchor.Y).ID != Int(gate, "staged_land_id"))
                        throw new InvalidDataException("Source gate anchor differs from published terrain");
                    var entity = new CampaignGate(Str(gate, "id"), Int(gate, "uo_art"), Str(gate, "uo_name"),
                        Int(gate, "frame"), extent[0].GetInt32(), extent[1].GetInt32(), gateAnchor);
                    ById.Add(entity.SourceId, entity);
                }
            }
            if (story.TryGetProperty("interactive_fixed", out var fixtures))
            {
                foreach (var source in fixtures.EnumerateArray())
                {
                    var location = new Point3D(Int(source, "x"), Int(source, "y"), Int(source, "lift") * 4);
                    var material = source.GetProperty("material");
                    if (Map.Felucca.Tiles.GetLandTile(location.X, location.Y).ID != Int(source, "staged_land_id"))
                        throw new InvalidDataException("Original fixed object has no matching terrain");
                    var item = new CampaignFixture(Str(source, "id"), Int(source, "function_id"), Int(material, "id"))
                        { Name = Str(material, "name") };
                    item.MoveToWorld(location, Map.Felucca);
                    ById.Add(item.SourceId, item);
                }
            }
            if (story.TryGetProperty("investigation_chests", out var trees))
                foreach (var tree in trees.EnumerateArray()) PlaceChest(tree);
        }
        else PlaceActor(actor);
        foreach (var item in records)
        {
            string id = Str(item,"id"), edge = Str(item,"edge");
            var (art, name) = Presentation(Int(item,"shape"), Int(item,"frame"));
            Item obj = Str(item,"kind") == "container" ? new CampaignContainer(id,art) : new CampaignItem(id,art);
            obj.Name = name;
            obj.Stackable = false; // Identical source instances must stay individually addressable.
            obj.Movable = edge == "inventory";
            var xy = item.GetProperty("raw_xy");
            int x = xy[0].GetInt32(), y = xy[1].GetInt32(), z = Int(item,"lift") * 4;
            if (edge == "inventory")
            {
                var parent = (CampaignContainer)ById[Str(item,"parent")];
                parent.AddItem(obj); obj.Location = new Point3D(x, y, z);
            }
            else
            {
                // Ship components retain their world anchors instead of being hidden in an inventory.
                obj.MoveToWorld(new Point3D((anchor[0].GetInt32() & ~255) + x,
                                           (anchor[1].GetInt32() & ~255) + y, z), Map.Felucca);
                if (Str(item,"kind") == "barge") obj.Visible = false;
            }
            ById.Add(id, obj);
        }
        if (regional!=null) RegionalObjects.Import(regional,seed,ById);
        _registry.Seed = seed;
        _registry.RegionalDigest=regionalDigest;
    }

    private static void PlaceChest(JsonElement tree)
    {
        var objects = tree.GetProperty("objects");
        var origin = objects[0];
        var pos = origin.GetProperty("world_xy");
        if (Int(origin,"shape") != 522 || Str(origin,"id") != Str(tree,"id") ||
            Map.Felucca.Tiles.GetLandTile(pos[0].GetInt32(),pos[1].GetInt32()).ID != Int(tree,"staged_land_id"))
            throw new InvalidDataException("Invalid investigation chest placement");
        var chest = new CampaignChest(Str(origin,"id"),Int(origin,"quality_byte"),Int(origin,"uo_art"));
        chest.SetLockShape(522);
        chest.MoveToWorld(new Point3D(pos[0].GetInt32(),pos[1].GetInt32(),Int(origin,"lift")*4), Map.Felucca);
        ById.Add(chest.SourceId,chest);
        for (int i=1; i<objects.GetArrayLength(); i++)
        {
            var source = objects[i];
            if (Str(source,"parent") != chest.SourceId || Str(source,"edge") != "inventory")
                throw new InvalidDataException("Unqualified nested quest chest content");
            var item = new CampaignInvestigationItem(Str(source,"id"),Int(source,"shape"),Int(source,"frame"),
                Int(source,"quality_byte"),Int(source,"uo_art")) { Amount=Int(source,"amount"), Movable=true };
            var xy = source.GetProperty("gump_xy");
            chest.AddItem(item);
            item.Location = new Point3D(xy[0].GetInt32(),xy[1].GetInt32(),Int(source,"lift")*4);
            ById.Add(item.SourceId,item);
        }
    }

    private static void PlaceActor(JsonElement actor)
    {
        var pos = actor.GetProperty("source_position");
        int body = Int(actor, "shape") switch
        {
            465 or 319 or 451 or 720 or 318 or 489 or 445 or 462 or 455 => 0x190,
            452 => 0x191,
            _ => throw new InvalidDataException("No walking-area body mapping for this source actor")
        };
        var npc = new CampaignActor(Str(actor, "id"), Int(actor, "function_id"))
        { Name = Str(actor, "name"), Body = body, Hue = 0x83EA, Blessed = true };
        npc.MoveToWorld(new Point3D(pos[0].GetInt32(), pos[1].GetInt32(), pos[2].GetInt32() * 4), Map.Felucca);
        ById.Add(npc.SourceId, npc);
    }

    private static void CheckMap(int x, int y, bool water)
    {
        if (x < 0 || y < 0 || x >= Map.Felucca.Width || y >= Map.Felucca.Height)
            throw new InvalidDataException("Campaign anchor outside private facet");
        int land = Map.Felucca.Tiles.GetLandTile(x,y).ID;
        if (water ? land is < 168 or > 171 : land is not (3 or 4 or 5 or 6 or 1001 or 1002 or 1003 or 1004))
            throw new InvalidDataException($"Missing qualified {(water ? "water" : "ground")} at ({x},{y})");
    }

    // Called on the shard game thread. Event keys survive restart and deletion.
    public static Item? SpawnOnce(string eventKey, int art, Point3D location)
    {
        if (_registry == null || _registry.Seed == "" || string.IsNullOrWhiteSpace(eventKey))
            throw new InvalidOperationException("No active campaign or event key");
        if (_registry.Spawns.TryGetValue(eventKey, out string? existing)) return Find(existing) as Item;
        string id = "runtime:" + Guid.NewGuid().ToString("N");
        var entity = new CampaignItem(id,art);
        entity.MoveToWorld(location, Map.Felucca);
        ById.Add(id,entity); _registry.Spawns.Add(eventKey,id);
        return entity;
    }

    static string Str(JsonElement obj, string key) => obj.GetProperty(key).GetString() ?? throw new InvalidDataException(key);
    static int Int(JsonElement obj, string key) => obj.GetProperty(key).GetInt32();
    static (int,string) Presentation(int shape,int frame) => shape switch
    {
        961 => (1, "barge anchor"), 791 or 1017 or 700 => (0x04A2, "ship planking"),
        775 => (0x07C9, "ship rail"), 405 => (0x0E3C, "ship's hold"),
        810 => (0x14E0, "bucket"), 804 => (0x0E3D, "crate"),
        677 => (0x1039, "sack of wheat"), 377 when frame is 12 or 13 => (0x09F2, "food"),
        _ => throw new InvalidDataException($"Unsupported Trinsic entity shape/frame {shape}/{frame}")
    };
}
