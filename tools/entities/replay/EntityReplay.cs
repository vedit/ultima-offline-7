using System.Text.Json;
using Server;
using Server.Items;
using UltimaOffline.Entities;

namespace UltimaOffline.EntityTests;

// Only installed in the disposable server used by smoke.py.
public static class EntityReplay
{
    public static void Configure() => EventSink.ServerStarted += Run;
    private static string F(string name) => Path.Combine(Core.BaseDirectory, name);
    private static void Require(bool condition, string message)
    {
        if (!condition) throw new InvalidDataException(message);
    }

    private static void Run()
    {
        try { Replay(); }
        catch (Exception ex)
        {
            File.WriteAllText(F("replay-error.txt"), ex.ToString()); Core.Kill();
        }
    }

    private static void Replay()
    {
        using var doc = JsonDocument.Parse(File.ReadAllBytes(F("Campaign/container.json")));
        var rows = doc.RootElement.GetProperty("objects").EnumerateArray().ToArray();
        string Id(JsonElement row) => row.GetProperty("id").GetString()!;
        Item Lookup(string id) => (Item)(CampaignEntities.Find(id) ?? throw new InvalidDataException($"Missing item {id}"));
        var duplicates = rows.Where(o => o.GetProperty("shape").GetInt32() == 377)
            .GroupBy(o => (o.GetProperty("parent").GetString(), o.GetProperty("payload_hex").GetString()))
            .First(g => g.Count() >= 3).ToArray();
        string moved = Id(duplicates[0]), untouched = Id(duplicates[1]), destroyed = Id(duplicates[2]);
        var crate = (Container)Lookup(duplicates[0].GetProperty("parent").GetString()!);
        var holdRow = rows.Single(r => r.GetProperty("shape").GetInt32() == 405);
        var hold = (Container)Lookup(Id(holdRow));
        var worldAnchor = Lookup(doc.RootElement.GetProperty("root_id").GetString()!);
        var npc = CampaignEntities.Entries.Values.OfType<CampaignActor>().Single(actor => actor.FunctionId == 0x40c);
        Require(npc.Map == Map.Felucca && npc.Name == "Finnigan" && npc.FunctionId == 0x40c &&
                npc.Location == new Point3D(1048,2215,0), "Finnigan source binding changed");
        Require(worldAnchor.Map == Map.Felucca && worldAnchor.Location == new Point3D(1144,2212,0) &&
                hold.Map == Map.Felucca && hold.Location == new Point3D(1142,2210,0), "Ship source anchors changed");
        var movedItem = Lookup(moved);
        bool restarted = File.Exists(F("before.json"));
        if (!restarted)
        {
            Require(movedItem.Parent == crate && Lookup(untouched).Parent == crate && Lookup(destroyed).Parent == crate,
                    "Initial duplicate parents differ from the seed");
            string[] original = crate.Items.OfType<ICampaignEntity>().Select(i => i.SourceId).ToArray();
            string[] expected = rows.Where(o => o.GetProperty("parent").GetString() == ((ICampaignEntity)crate).SourceId)
                .Select(Id).ToArray();
            Require(original.SequenceEqual(expected), "Initial crate order differs from its source record order");
            hold.AddItem(movedItem);
            movedItem.Location = new Point3D(32,45,0);
            Lookup(destroyed).Delete();
        }
        var runtime = CampaignEntities.SpawnOnce("smoke-first-spawn", 0x14E0, worldAnchor.Location);
        Require(runtime is CampaignItem && runtime == CampaignEntities.SpawnOnce("smoke-first-spawn", 0x14E0, worldAnchor.Location),
                "Runtime event produced duplicate items");
        Require(CampaignEntities.Find(destroyed) == null && Lookup(untouched).Parent == crate &&
                movedItem.Parent == hold && movedItem.Location == new Point3D(32,45,0), "Move or deletion lost");
        var observation = new {
            regional=CheckRegional(restarted,hold),
            npc = npc.Serial.Value, root = worldAnchor.Serial.Value, rootX = worldAnchor.X, rootY = worldAnchor.Y,
            hold = hold.Serial.Value, holdX = hold.X, holdY = hold.Y, holdZ = hold.Z,
            moved, movedSerial = movedItem.Serial.Value, movedX = movedItem.X, movedY = movedItem.Y,
            untouched, untouchedSerial = Lookup(untouched).Serial.Value, destroyed,
            runtime = ((CampaignItem)runtime!).SourceId, runtimeSerial = runtime!.Serial.Value,
            holdOrder = hold.Items.OfType<ICampaignEntity>().Select(i => i.SourceId).ToArray(),
            crateOrder = crate.Items.OfType<ICampaignEntity>().Select(i => i.SourceId).ToArray(),
            liveCount = CampaignEntities.Entries.Count(p => !p.Value.Deleted)
        };
        string json = JsonSerializer.Serialize(observation);
        if (restarted)
        {
            Require(File.ReadAllText(F("before.json")) == json, "Restart changed entity membership, serials or order");
            File.WriteAllText(F("after.json"), json);
            Core.Kill();
        }
        else
        {
            File.WriteAllText(F("before.json"), json);
            World.Save();
        }
    }

    private static object? CheckRegional(bool restarted,Container destination)
    {
        string file=F("Campaign/world-live.json");
        if (!File.Exists(file)) return null;
        using var doc=JsonDocument.Parse(File.ReadAllBytes(file));
        var rows=doc.RootElement.GetProperty("objects").EnumerateArray().ToArray();
        string Id(JsonElement r)=>r.GetProperty("id").GetString()!;
        var children=rows.Where(r=>r.GetProperty("parent").ValueKind==JsonValueKind.String)
            .ToLookup(r=>r.GetProperty("parent").GetString()!);
        // Move a filled container, then independently delete an ordinary world item.
        string moved=Id(rows.First(r=>r.GetProperty("parent").ValueKind==JsonValueKind.Null && children.Contains(Id(r))));
        string removed=Id(rows.First(r=>r.GetProperty("kind").GetString()=="simple" &&
            r.GetProperty("parent").ValueKind==JsonValueKind.Null));
        var state=new List<object>();
        foreach (var row in rows)
        {
            string id=Id(row);
            var obj=CampaignEntities.Find(id) as Item;
            if (id==removed && restarted)
            {
                Require(obj==null,"Deleted regional object respawned");
                continue;
            }
            Require(obj is IRegionalObject known && known.SourcePayload==row.GetProperty("payload").GetString()
                && obj.ItemID==row.GetProperty("art").GetInt32(),$"Regional item identity or art differs: {id}");
            var xy=row.GetProperty("xy");
            var expected=new Point3D(xy[0].GetInt32(),xy[1].GetInt32(),row.GetProperty("lift").GetInt32()*4);
            var originalParent=row.GetProperty("parent").GetString();
            if (!restarted || id!=moved)
            {
                var owner=originalParent==null?null:CampaignEntities.Find(originalParent);
                Require(obj!.Map==Map.Felucca && obj.Parent==owner && obj.Location==expected,$"Regional anchor differs: {id}");
            }
            if (obj is Container box)
                Require(box.Items.OfType<IRegionalObject>().Select(i=>i.SourceId).SequenceEqual(children[id].Select(Id)),
                    $"Regional container child order differs: {id}");
            if (id==removed) { obj!.Delete(); continue; }
            if (id==moved)
            {
                if (!restarted) { destination.AddItem(obj!); obj!.Location=new Point3D(33,47,0); }
                Require(obj!.Parent==destination && obj.Location==new Point3D(33,47,0),"Regional transfer failed");
            }
            state.Add(new { id,serial=obj!.Serial.Value, parent=(obj.Parent as Item)?.Serial.Value,x=obj.X,y=obj.Y,z=obj.Z });
        }
        return new { initial_records=rows.Length,restored_live=state.Count,moved,removed,
            inventory_links=children.Sum(g=>g.Count()),containers=rows.Count(r=>r.GetProperty("kind").GetString()=="container"),
            serials_parents_positions_sha256=Convert.ToHexStringLower(System.Security.Cryptography.SHA256.HashData(
                JsonSerializer.SerializeToUtf8Bytes(state))) };
    }
}
