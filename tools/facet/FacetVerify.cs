using System.Reflection;
using System.Buffers.Binary;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Text.Json;
using ClassicUO.Assets;
using ClassicUO.Utility;
using Server;

// Read the configured slot using the same libraries as the desktop server and client.
var output = Console.Out;
Console.SetOut(Console.Error);
try
{
    if (args is ["--portrait", var assets, var report])
    {
        using var metadata = JsonDocument.Parse(File.ReadAllBytes(report));
        if (!ClientVersionHelper.IsClientVersionValid("7.0.118.46", out var profileVersion))
            throw new InvalidDataException("Unknown client version");
        var gumpManager = new UOFileManager(profileVersion, Path.GetFullPath(assets));
        output.WriteLine(JsonSerializer.Serialize(ReadPortrait(gumpManager, metadata.RootElement)));
        return 0;
    }
    string root = Path.GetFullPath(args.Single());
    JsonElement Read(string path) => JsonDocument.Parse(File.ReadAllBytes(Path.Combine(root, path))).RootElement;
    var facet = Read("facet.json");
    var sample = Read("sample.json");
    var client = Read("client/settings.json");
    var server = Read("server/Configuration/modernuo.json");
    var slot = Read("server/Data/map-definitions.json").EnumerateArray().Single(e => e.GetProperty("index").GetInt32() == 0);
    int width = slot.GetProperty("width").GetInt32(), height = slot.GetProperty("height").GetInt32();
    if (width != 7168 || height != 4096 || slot.GetProperty("id").GetInt32() != 0 || slot.GetProperty("fileIndex").GetInt32() != 0)
        throw new InvalidDataException("Server slot zero has incorrect dimensions or identity.");
    Core.ApplicationAssembly = Assembly.GetExecutingAssembly();
    ServerConfiguration.Load(mocked: true);
    ServerConfiguration.DataDirectories.Clear();
    foreach (var path in server.GetProperty("dataDirectories").EnumerateArray())
        ServerConfiguration.DataDirectories.Add(path.GetString()!);
    var matrix = new TileMatrix(null, 0, 0, width, height);
    if (!ClientVersionHelper.IsClientVersionValid(client.GetProperty("clientversion").GetString(), out var version))
        throw new InvalidDataException("Invalid ClassicUO version");
    string data = client.GetProperty("ultimaonlinedirectory").GetString()!;
    var manager = new UOFileManager(version, data);
    manager.Maps.MapsLayouts = client.GetProperty("maps_layouts").GetString();
    manager.Maps.Load();
    manager.Maps.LoadMap(0);
    var map = manager.Maps.GetMapFile(0);
    if (matrix.MapStream == null || !StringComparer.OrdinalIgnoreCase.Equals(matrix.MapStream.Name, map.FilePath) ||
        !StringComparer.OrdinalIgnoreCase.Equals(map.FilePath, Path.Combine(root, "assets", "map0.mul")) ||
        manager.Maps.MapBlocksSize[0,0] * 8 != width || manager.Maps.MapBlocksSize[0,1] * 8 != height)
        throw new InvalidDataException("The client and server resolved different slot-zero resources or dimensions.");
    int ox = sample.GetProperty("source_origin")[0].GetInt32(), oy = sample.GetProperty("source_origin")[1].GetInt32();
    var checks = new Dictionary<(int x, int y), (int id, int z)>();
    foreach (var c in sample.GetProperty("cells").EnumerateArray())
        checks.Add((ox + c.GetProperty("x").GetInt32(), oy + c.GetProperty("y").GetInt32()),
                   (c.GetProperty("land_id").GetInt32(), c.GetProperty("z").GetInt32()));
    int converted = checks.Count;
    bool expanded = facet.TryGetProperty("world_geometry",out var geometry);
    var questBlocks = checks.Keys.Select(p => (p.x >> 3,p.y >> 3)).ToHashSet();
    var padding = new (int x, int y)[]{ (0,0), (width-1,height-1), (3071,3071), (3072,3071),
        (3071,3072), (ox-1,oy), (ox,oy-1), (ox + sample.GetProperty("width").GetInt32(),oy),
        (ox, oy + sample.GetProperty("height").GetInt32()) };
    foreach (var (x,y) in padding)
        if (x >= 0 && x < width && y >= 0 && y < height && (!expanded || x>=3072 || y>=3072))
            checks.TryAdd((x,y), (facet.GetProperty("pad_land_id").GetInt32(),0));
    foreach (var ((x,y), (id,z)) in checks)
    {
        var st = matrix.GetLandTile(x,y);
        ref var index = ref manager.Maps.GetIndex(0, x >> 3,y >> 3);
        index.MapFile.Seek((long)index.MapAddress, SeekOrigin.Begin);
        var cell = index.MapFile.Read<MapBlock>().Cells[((y & 7) << 3) + (x & 7)];
        if (cell.TileID != id || cell.Z != z || st.ID != id || st.Z != z)
            throw new InvalidDataException($"Slot-zero land mismatch at ({x},{y}).");
    }
    var expected = new List<string>(); var fromClient = new List<string>(); var fromServer = new List<string>();
    string Key(int x, int y, int id, int z, int hue) => $"{x},{y},{id},{z},{hue}";
    if (sample.TryGetProperty("statics", out var items))
        foreach (var item in items.EnumerateArray())
            expected.Add(Key(ox + item.GetProperty("x").GetInt32(), oy + item.GetProperty("y").GetInt32(),
                item.GetProperty("id").GetInt32(), item.GetProperty("z").GetInt32(), item.GetProperty("hue").GetInt32()));
    foreach (var (bx,by) in checks.Keys.Select(p => (p.x >> 3, p.y >> 3)).Distinct())
    {
        var statics = matrix.GetStaticBlock(bx, by);
        for (int x=0; x<8; x++) for (int y=0; y<8; y++)
            foreach (var tile in statics[x][y])
                fromServer.Add(Key(bx * 8 + x, by * 8 + y, tile.ID, tile.Z, tile.Hue));
        ref var index = ref manager.Maps.GetIndex(0, bx, by);
        index.StaticFile.Seek((long)index.StaticAddress, SeekOrigin.Begin);
        for (int n=0; n<index.StaticCount; n++)
        {
            var tile = index.StaticFile.Read<StaticsBlock>();
            fromClient.Add(Key(bx * 8 + tile.X, by * 8 + tile.Y, tile.Color, tile.Z, tile.Hue));
        }
    }
    expected.Sort(StringComparer.Ordinal); fromClient.Sort(StringComparer.Ordinal); fromServer.Sort(StringComparer.Ordinal);
    if (!fromClient.SequenceEqual(expected) || !fromServer.SequenceEqual(expected))
        throw new InvalidDataException($"Slot-zero static disagreement (expected {expected.Count}, client {fromClient.Count}, server {fromServer.Count}).");
    manager.Maps.LoadMap(0, true);
    if (!StringComparer.OrdinalIgnoreCase.Equals(manager.Maps.GetMapFile(0).FilePath, map.FilePath))
        throw new InvalidDataException("ClassicUO alternate map shadows the generated facet.");
    object? portrait = facet.TryGetProperty("portrait", out var spec) && spec.ValueKind == JsonValueKind.Object
        ? ReadPortrait(manager, spec) : null;
    var companions = portrait != null && spec.TryGetProperty("companions", out var faces)
        ? faces.EnumerateArray().Select(face => ReadPortrait(manager, face)).ToArray() : Array.Empty<object>();
    object? music = null;
    if (facet.TryGetProperty("music", out var score) && score.ValueKind == JsonValueKind.Object)
    {
        var cue = score.GetProperty("tracks").GetProperty("35");
        int index = cue.GetProperty("client_slot").GetInt32();
        string file = cue.GetProperty("path").GetString()!;
        manager.Sounds.Load();
        if (!manager.Sounds.TryGetMusicData(index, out var name, out var loop) || name != Path.GetFileName(file) ||
            loop != cue.GetProperty("repeat").GetBoolean() || Convert.ToHexStringLower(
                SHA256.HashData(File.ReadAllBytes(Path.Combine(data, file)))) != cue.GetProperty("sha256").GetString())
            throw new InvalidDataException("ClassicUO resolved different opening music.");
        music = new { status="passed", original_track=35, client_slot=index, filename=name, loop };
    }
    object? world = expanded ? ReadWorld(root,geometry,facet.GetProperty("pad_land_id").GetInt32(),questBlocks,matrix,manager) : null;
    string livePath=Path.Combine(root,"server","Campaign","world-live.json");
    object? regional=null;
    if (File.Exists(livePath))
    {
        using var live=JsonDocument.Parse(File.ReadAllBytes(livePath));
        manager.Arts.Load();
        var decoded=new SortedDictionary<int,object>();
        int count=0;
        foreach(var row in live.RootElement.GetProperty("objects").EnumerateArray())
        {
            ++count;
            int id=row.GetProperty("art").GetInt32();
            if (decoded.ContainsKey(id)) continue;
            var art=manager.Arts.GetArt((uint)(0x4000+id));
            int opaque=0;
            foreach(uint pixel in art.Pixels) if ((pixel>>24)!=0) ++opaque;
            if (art.Width<=0 || art.Height<=0 || art.Pixels.Length!=art.Width*art.Height || opaque==0)
                throw new InvalidDataException($"Regional world item {id:x4} has no native graphic.");
            decoded.Add(id,new { width=art.Width,height=art.Height,opaque,
                rgba_sha256=Convert.ToHexStringLower(SHA256.HashData(MemoryMarshal.AsBytes(art.Pixels))) });
        }
        regional=new { records=count,graphics=decoded };
    }
    object? shores = null;
    if(facet.TryGetProperty("shore_art",out var shore))
    {
        if(regional==null) manager.Arts.Load();
        manager.TileData.Load();
        manager.Hues.Load();
        if(manager.Arts.File is not ClassicUO.IO.UOFileUop archive ||
           !StringComparer.OrdinalIgnoreCase.Equals(Path.GetFullPath(archive.FilePath),Path.Combine(data,"artLegacyMUL.uop")))
            throw new InvalidDataException("ClassicUO did not select the private shore archive");
        int frames=0;
        foreach(var row in Read("world-reference/shore-art.json").GetProperty("frames").EnumerateArray())
        {
            int id=row.GetProperty("slot").GetInt32();
            string name=row.GetProperty("name").GetString()!;
            ulong key=ClassicUO.IO.UOFileUop.CreateHash($"build/artlegacymul/{id:D8}.tga");
            var native=manager.TileData.LandData[id];
            var serverTile=Server.TileData.LandTable[id];
            if(!archive.TryGetUOPData(key,out var entry) || entry.Length!=2024 ||
               native.Flags!=0 || native.TexID!=0 || native.Name!=name || serverTile.Flags!=0 ||
               serverTile.Name!=name || manager.Hues.GetRadarColorData(id)!=row.GetProperty("radar").GetInt32())
                throw new InvalidDataException($"Wrong shore art, tile metadata or radar color at {id:x4}");
            var art=manager.Arts.GetArt((uint)id);
            if(art.Width!=44 || art.Height!=44 || art.Pixels.Length!=44*44 ||
               Convert.ToHexStringLower(SHA256.HashData(MemoryMarshal.AsBytes(art.Pixels)))!=row.GetProperty("rgba_sha256").GetString())
                throw new InvalidDataException($"Wrong decoded shore pixels at {id:x4}");
            frames++;
        }
        if(frames!=shore.GetProperty("frames").GetInt32()) throw new InvalidDataException("Incomplete shore art readback");
        shores=new { status="passed",frames,opaque_pixels=frames*1012,walkable_tiles=frames,radar_colors=frames };
    }
    object? fences=null;
    var seedPath=Path.Combine(root,"server","Campaign","story-seed.json");
    if(File.Exists(seedPath) && Read("server/Campaign/story-seed.json").TryGetProperty("fence_art",out var donors))
    {
        if(regional==null && shores==null) manager.Arts.Load();
        if(shores==null) manager.TileData.Load();
        var results=new SortedDictionary<int,object>();
        foreach(var pair in donors.EnumerateObject())
        {
            int id=int.Parse(pair.Name), stock=pair.Value.GetInt32();
            var a=manager.Arts.GetArt((uint)(0x4000+id));
            var b=manager.Arts.GetArt((uint)(0x4000+stock));
            var clientTile=manager.TileData.StaticData[id];
            var serverTile=Server.TileData.ItemTable[id];
            if(a.Width<=0 || a.Height<=0 || a.Width!=b.Width || a.Height!=b.Height ||
                a.Pixels.Length!=a.Width*a.Height || !a.Pixels.SequenceEqual(b.Pixels) ||
                clientTile.Height!=8 || serverTile.Height!=8 || ((ulong)clientTile.Flags&0x40)==0 ||
                ((ulong)serverTile.Flags&0x40)==0 || manager.TileData.StaticData[stock].Height!=6)
                throw new InvalidDataException($"Fence art or collision mismatch at {id:x4}.");
            results[id]=new { donor=stock,pixels=a.Pixels.Length,height=clientTile.Height };
        }
        fences=results;
    }
    output.WriteLine(JsonSerializer.Serialize(new { status="passed", width, height, slot=0,
        converted_tiles=converted+(expanded ? geometry.TryGetProperty("additional_land_cells",out var cells)
            ? cells.GetInt32() : 64*geometry.GetProperty("additional_land_blocks").GetInt32() : 0),
        padding_tiles=checks.Count-converted, statics=expected.Count+(expanded ? geometry.GetProperty("additional_static_components").GetInt32() : 0),
        world_geometry=world,regional_items=regional,shore_art=shores,fence_art=fences,
        client_effective_map=map.FilePath, server_effective_map=matrix.MapStream.Name, portrait, companions, music }));
    return 0;
}
catch (Exception exc)
{
    output.WriteLine(JsonSerializer.Serialize(new { status="failed", diagnostic=exc.ToString() }));
    return 1;
}

static object ReadWorld(string root, JsonElement geometry, int pad, HashSet<(int,int)> quest,
                        TileMatrix matrix,UOFileManager manager)
{
    string dir = Path.Combine(root,"world-reference");
    byte[] landIndex = File.ReadAllBytes(Path.Combine(dir,"land.idx"));
    byte[] pool = File.ReadAllBytes(Path.Combine(dir,"land.mul"));
    byte[] staticIndex = File.ReadAllBytes(Path.Combine(dir,"staidx0.mul"));
    byte[] raw = File.ReadAllBytes(Path.Combine(dir,"statics0.mul"));
    if (landIndex.Length!=384*384*4 || staticIndex.Length!=384*384*12 || pool.Length%196!=0)
        throw new InvalidDataException("Invalid whole-world reference dimensions");
    int landCount=0, omitted=0, staticsCount=0, mixed=0, mixedPadding=0;
    for (int bx=0;bx<384;bx++)
    for (int by=0;by<384;by++)
    {
        if (quest.Contains((bx,by))) continue;
        int i=bx*384+by;
        int slot=BinaryPrimitives.ReadInt32LittleEndian(landIndex.AsSpan(4*i));
        if (slot < -1 || slot>=pool.Length/196) throw new InvalidDataException("Invalid reference land slot");
        var serverLand=matrix.GetLandBlock(bx,by);
        ref var ci=ref manager.Maps.GetIndex(0,bx,by);
        ci.MapFile.Seek((long)ci.MapAddress,SeekOrigin.Begin);
        var land=ci.MapFile.Read<MapBlock>();
        int padding=0;
        for(int n=0;n<64;n++)
        {
            int p=slot*196+4+3*n;
            int id=slot<0 ? pad : BinaryPrimitives.ReadUInt16LittleEndian(pool.AsSpan(p));
            int z=slot<0 ? 0 : unchecked((sbyte)pool[p+2]);
            if(id==pad) padding++;
            if(land.Cells[n].TileID!=id || land.Cells[n].Z!=z || serverLand[n].ID!=id || serverLand[n].Z!=z)
                throw new InvalidDataException($"World land mismatch at {bx*8+n%8},{by*8+n/8}");
        }
        if(slot<0) omitted++; else landCount++;
        if(slot>=0 && padding>0) { mixed++; mixedPadding+=padding; }
        int offset=BinaryPrimitives.ReadInt32LittleEndian(staticIndex.AsSpan(i*12));
        int bytes=BinaryPrimitives.ReadInt32LittleEndian(staticIndex.AsSpan(i*12+4));
        int count=slot<0 ? 0 : bytes/7;
        var server=matrix.GetStaticBlock(bx,by);
        int serverCount=0;
        foreach(var column in server) foreach(var cell in column) serverCount+=cell.Length;
        if(ci.StaticCount>0) ci.StaticFile.Seek((long)ci.StaticAddress,SeekOrigin.Begin);
        var expected=new List<(int,int,int,int,int)>(count);
        var observed=new List<(int,int,int,int,int)>(count);
        for(int n=0;n<count;n++)
        {
            int p=offset+7*n;
            int id=BinaryPrimitives.ReadUInt16LittleEndian(raw.AsSpan(p)),x=raw[p+2],y=raw[p+3],
                z=unchecked((sbyte)raw[p+4]),hue=BinaryPrimitives.ReadUInt16LittleEndian(raw.AsSpan(p+5));
            if(land.Cells[y*8+x].TileID==pad) continue;
            if(expected.Count>=ci.StaticCount) throw new InvalidDataException($"Missing client fixture at {bx},{by}");
            var tile=ci.StaticFile.Read<StaticsBlock>();
            if(tile.Color!=id || tile.X!=x || tile.Y!=y || tile.Z!=z || tile.Hue!=hue)
                throw new InvalidDataException($"World static mismatch at {bx},{by} ordinal {n}");
            expected.Add((x,y,id,z,hue));
        }
        if(ci.StaticCount!=expected.Count || serverCount!=expected.Count)
            throw new InvalidDataException($"Wrong fixture count at {bx},{by}");
        for(int x=0;x<8;x++) for(int y=0;y<8;y++)
            foreach(var tile in server[x][y]) observed.Add((x,y,tile.ID,tile.Z,tile.Hue));
        expected.Sort(); observed.Sort();
        if(!expected.SequenceEqual(observed)) throw new InvalidDataException($"World server fixture mismatch at {bx},{by}");
        staticsCount+=expected.Count;
    }
    if(landCount!=geometry.GetProperty("additional_land_blocks").GetInt32() ||
       (geometry.TryGetProperty("mixed_blocks",out var mb) && (mb.GetInt32()!=mixed ||
        mixedPadding!=geometry.GetProperty("mixed_block_padding_cells").GetInt32() ||
        landCount*64-mixedPadding!=geometry.GetProperty("additional_land_cells").GetInt32())) ||
       omitted!=geometry.GetProperty("unresolved_blocks").GetInt32() ||
       quest.Count!=geometry.GetProperty("quest_patch_blocks").GetInt32() ||
       staticsCount!=geometry.GetProperty("additional_static_components").GetInt32())
        throw new InvalidDataException("World geometry totals disagree with the published facet");
    return new { status="passed",additional_blocks=landCount,unresolved_block_padding=omitted,
                 mixed_blocks=mixed,mixed_padding_cells=mixedPadding,mapped_cells=landCount*64-mixedPadding,
                 checked_statics=staticsCount,quest_blocks=quest.Count };
}

static object ReadPortrait(UOFileManager manager, JsonElement spec)
{
    uint id = spec.GetProperty("gump_id").GetUInt32();
    manager.Gumps.Load();
    string member = $"build/gumpartlegacymul/{id:D8}.tga";
    ulong key = ClassicUO.IO.UOFileUop.CreateHash(member);
    string expectedFile = Path.Combine(manager.BasePath, "gumpartLegacyMUL.uop");
    int face = spec.GetProperty("shape").GetInt32();
    int frame = spec.GetProperty("frame").GetInt32();
    if (face is < 0 or >= 1024 || id != (frame == 0 ? 64000 + face : (face, frame) == (2, 1) ? 64102 : -1)
        || manager.Gumps.File is not ClassicUO.IO.UOFileUop uop ||
        !StringComparer.OrdinalIgnoreCase.Equals(Path.GetFullPath(expectedFile), Path.GetFullPath(uop.FilePath)) ||
        !uop.TryGetUOPData(key, out var entry) || entry.Length <= 0 ||
        key.ToString("x16") != spec.GetProperty("member_hash").GetString())
        throw new InvalidDataException("ClassicUO did not resolve the private Gump archive member.");
    var gump = manager.Gumps.GetGump(id);
    string digest = Convert.ToHexStringLower(SHA256.HashData(MemoryMarshal.AsBytes(gump.Pixels)));
    int opaque = 0;
    foreach (uint pixel in gump.Pixels) if ((pixel >> 24) != 0) ++opaque;
    if (gump.Width != spec.GetProperty("width").GetInt32() || gump.Height != spec.GetProperty("height").GetInt32() ||
        opaque != spec.GetProperty("opaque_pixels").GetInt32() || digest != spec.GetProperty("expected_rgba_sha256").GetString())
        throw new InvalidDataException("ClassicUO decoded different portrait pixels.");
    return new { status="passed", gump_id=id, width=gump.Width, height=gump.Height, pixels_checked=gump.Pixels.Length,
        opaque_pixels=opaque, rgba_sha256=digest, archive=uop.FilePath, member_hash=key.ToString("x16") };
}
