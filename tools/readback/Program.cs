using System.Reflection;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Text.Json;
using ClassicUO.Assets;
using ClassicUO.Utility;
using Server;

// Load only the isolated profile chosen by the caller. Neither engine runs a game loop.
var output = Console.Out;
Console.SetOut(Console.Error);
var jsonOptions = new JsonSerializerOptions { WriteIndented = true };
try
{
    if (args.Length != 1)
        throw new ArgumentException("Usage: Readback <directory containing terrain.json and map0.mul>");
    string profile = Path.GetFullPath(args[0]);
    using var source = JsonDocument.Parse(File.ReadAllBytes(Path.Combine(profile, "terrain.json")));
    var specification = source.RootElement;
    int width = specification.GetProperty("width").GetInt32();
    int height = specification.GetProperty("height").GetInt32();
    if (width <= 0 || height <= 0 || width % 8 != 0 || height % 8 != 0 || (long)width * height > 65536)
        throw new InvalidDataException("Terrain proof dimensions must be positive multiples of eight, up to 65,536 cells.");

    var expected = new Dictionary<(int x, int y), (int id, int z)>();
    foreach (var cell in specification.GetProperty("cells").EnumerateArray())
    {
        int x = cell.GetProperty("x").GetInt32(), y = cell.GetProperty("y").GetInt32();
        int id = cell.GetProperty("land_id").GetInt32(), z = cell.GetProperty("z").GetInt32();
        if (x < 0 || x >= width || y < 0 || y >= height || id is < 0 or > 0x3fff || z is < -128 or > 127 ||
            !expected.TryAdd((x, y), (id, z)))
            throw new InvalidDataException($"Invalid or duplicate terrain cell at ({x},{y}).");
    }
    if (expected.Count != width * height)
        throw new InvalidDataException("Terrain specification omits cells.");

    int blocks = width * height / 64;
    long mapLength = new FileInfo(Path.Combine(profile, "map0.mul")).Length;
    if (mapLength != blocks * 196L)
        throw new InvalidDataException($"Invalid map0.mul length {mapLength} for {blocks} blocks.");
    ValidateStatics(profile, blocks);

    foreach (string name in new[] { "mapdif0.mul", "mapdifl0.mul", "stadif0.mul", "stadifi0.mul", "stadifl0.mul", "verdata.mul",
                                       "statics0x.mul", "staidx0x.mul" })
        if (File.Exists(Path.Combine(profile, name)))
            throw new InvalidDataException($"Unexpected patch or alternate static resource in terrain proof: {name}.");

    Core.ApplicationAssembly = Assembly.GetExecutingAssembly();
    ServerConfiguration.Load(mocked: true);
    ServerConfiguration.DataDirectories.Clear();
    ServerConfiguration.DataDirectories.Add(profile);
    var server = new TileMatrix(null, 0, 0, width, height);
    if (server.MapStream == null)
        throw new InvalidDataException("ModernUO did not open the terrain map.");

    if (!ClientVersionHelper.IsClientVersionValid("7.0.118.46", out var version))
        throw new InvalidDataException("ClassicUO could not parse the pinned client version.");
    var client = new UOFileManager(version, profile);
    // MapLoader always initializes both facets 0 and 1, even when only map0 is supplied.
    client.Maps.MapsLayouts = $"{width},{height};{width},{height}";
    client.Maps.Load();
    client.Maps.LoadMap(0);
    var clientMap = client.Maps.GetMapFile(0);
    string clientPath = Path.GetFullPath(clientMap.FilePath);
    var serverPath = Path.GetFullPath(server.MapStream.Name);
    int matched = 0, loaderDisagreements = 0;
    var failures = new List<object>();
    for (int by = 0; by < height / 8; ++by)
    for (int bx = 0; bx < width / 8; ++bx)
    {
        ref var index = ref client.Maps.GetIndex(0, bx, by);
        if (!index.IsValid() || index.MapFile.Length < 196 || index.MapAddress > (ulong)(index.MapFile.Length - 196))
            throw new InvalidDataException($"ClassicUO resolved an invalid block at ({bx},{by}).");
        index.MapFile.Seek(checked((long)index.MapAddress), SeekOrigin.Begin);
        var block = index.MapFile.Read<MapBlock>();
        for (int i = 0; i < 64; ++i)
        {
            int x = bx * 8 + i % 8, y = by * 8 + i / 8;
            var land = server.GetLandTile(x, y);
            var c = block.Cells[i];
            var goal = expected[(x, y)];
            if (land.ID != c.TileID || land.Z != c.Z) ++loaderDisagreements;
            if (land.ID == goal.id && land.Z == goal.z && c.TileID == goal.id && c.Z == goal.z)
                ++matched;
            else if (failures.Count < 8)
                failures.Add(new { x, y, expected = new { goal.id, goal.z },
                    modernuo = new { id = land.ID, z = land.Z }, classicuo = new { id = c.TileID, z = c.Z } });
        }
    }
    client.Maps.LoadMap(0, useXFiles: true);
    var alternatePath = Path.GetFullPath(client.Maps.GetMapFile(0).FilePath);
    bool samePath = StringComparer.OrdinalIgnoreCase.Equals(serverPath, clientPath) &&
                    StringComparer.OrdinalIgnoreCase.Equals(clientPath, alternatePath);
    var staticCheck = CheckStaticContents(specification, width, height, server, client);
    var portraitDir = Path.Combine(profile, "portrait");
    var portrait = Directory.Exists(portraitDir) ? ReadPortrait(portraitDir, version) : null;
    bool passed = samePath && matched == expected.Count && staticCheck.matched &&
                  (portrait == null || portrait.status == "passed");
    var report = new {
        schema = 1, status = passed ? "passed" : "failed", width, height,
        cells_checked = expected.Count, cells_matching_both_and_expected = matched,
        cells_with_loader_disagreement = loaderDisagreements,
        modernuo_file = Path.GetFileName(serverPath), classicuo_file = Path.GetFileName(clientPath),
        classicuo_alternate_file = Path.GetFileName(alternatePath), same_effective_file = samePath,
        modernuo_loader = Identify(typeof(TileMatrix)), classicuo_loader = Identify(typeof(ClassicUO.Assets.MapLoader)),
        first_mismatches = failures, portrait, statics = staticCheck
    };
    output.WriteLine(JsonSerializer.Serialize(report, jsonOptions));
    return passed ? 0 : 1;
}
catch (Exception ex)
{
    output.WriteLine(JsonSerializer.Serialize(new { schema = 1, status = "failed", diagnostic = ex.ToString() }, jsonOptions));
    return 1;
}

static object Identify(Type loader)
{
    string assembly = loader.Assembly.Location;
    using var file = File.OpenRead(assembly);
    return new { type = loader.FullName, assembly = Path.GetFileName(assembly),
        sha256 = Convert.ToHexStringLower(SHA256.HashData(file)) };
}

static StaticReadback CheckStaticContents(JsonElement spec, int width, int height, TileMatrix server, UOFileManager client)
{
    var expected = new List<(int x, int y, int id, int z, int hue)>();
    if (spec.TryGetProperty("statics", out var statics))
        foreach (var obj in statics.EnumerateArray())
            expected.Add((obj.GetProperty("x").GetInt32(), obj.GetProperty("y").GetInt32(),
                          obj.GetProperty("id").GetInt32(), obj.GetProperty("z").GetInt32(), obj.GetProperty("hue").GetInt32()));
    var serverTiles = new List<(int x, int y, int id, int z, int hue)>();
    var clientTiles = new List<(int x, int y, int id, int z, int hue)>();
    for (int bx = 0; bx < width / 8; ++bx)
    for (int by = 0; by < height / 8; ++by)
    {
        var data = server.GetStaticBlock(bx, by);
        for (int dx = 0; dx < 8; ++dx)
        for (int dy = 0; dy < 8; ++dy)
            foreach (var item in data[dx][dy])
                serverTiles.Add((8 * bx + dx, 8 * by + dy, item.ID, item.Z, (ushort)item.Hue));
        ref var index = ref client.Maps.GetIndex(0, bx, by);
        if (index.StaticCount == 0) continue;
        if (index.StaticFile == null || index.StaticAddress + 7UL * index.StaticCount > (ulong)index.StaticFile.Length)
            throw new InvalidDataException($"Invalid ClassicUO static block at ({bx},{by}).");
        index.StaticFile.Seek(checked((long)index.StaticAddress), SeekOrigin.Begin);
        for (int i = 0; i < index.StaticCount; ++i)
        {
            var item = index.StaticFile.Read<StaticsBlock>();
            if (item.X > 7 || item.Y > 7) throw new InvalidDataException("Static outside its UO block.");
            clientTiles.Add((bx * 8 + item.X, by * 8 + item.Y, item.Color, item.Z, item.Hue));
        }
    }
    expected.Sort();
    serverTiles.Sort();
    clientTiles.Sort();
    return new StaticReadback(expected.SequenceEqual(serverTiles) && expected.SequenceEqual(clientTiles),
                              expected.Count, serverTiles.Count, clientTiles.Count);
}

static void ValidateStatics(string profile, int blocks)
{
    // ClassicUO clamps counts to 1,024 per block. Reject silent truncation before loading.
    using var index = new BinaryReader(File.OpenRead(Path.Combine(profile, "staidx0.mul")));
    long staticLength = new FileInfo(Path.Combine(profile, "statics0.mul")).Length;
    if (index.BaseStream.Length != 12L * blocks)
        throw new InvalidDataException("staidx0.mul length disagrees with the proof dimensions.");
    for (int block = 0; block < blocks; block++)
    {
        uint offset = index.ReadUInt32(), size = index.ReadUInt32();
        index.ReadUInt32();
        if (offset == uint.MaxValue && (size == 0 || size == uint.MaxValue)) continue;
        if (size % 7 != 0 || size / 7 > 1024 || (long)offset + size > staticLength)
            throw new InvalidDataException($"Invalid or overfull static block {block} (offset {offset}, bytes {size}).");
    }
}

static PortraitReport ReadPortrait(string directory, ClassicUO.Utility.ClientVersion version)
{
    using var metadata = JsonDocument.Parse(File.ReadAllBytes(Path.Combine(directory, "portrait.json")));
    var spec = metadata.RootElement;
    int width = spec.GetProperty("width").GetInt32(), height = spec.GetProperty("height").GetInt32();
    uint index = spec.GetProperty("gump_id").GetUInt32();
    if (width is < 1 or > 1024 || height is < 1 or > 1024 || index > ushort.MaxValue)
        throw new InvalidDataException("Invalid portrait dimensions or Gump index.");
    if (Directory.Exists(Path.Combine(directory, "Gumps")) || File.Exists(Path.Combine(directory, "gump.def")))
        throw new InvalidDataException("Unexpected Gump override in the standalone portrait profile.");
    var manager = new UOFileManager(version, directory);
    manager.Gumps.Load();
    var gump = manager.Gumps.GetGump(index);
    string digest = Convert.ToHexStringLower(SHA256.HashData(MemoryMarshal.AsBytes(gump.Pixels)));
    int opaque = 0;
    foreach (uint pixel in gump.Pixels) if ((pixel >> 24) != 0) ++opaque;
    bool passed = Path.GetFileName(manager.Gumps.File.FilePath).Equals("gumpart.mul", StringComparison.OrdinalIgnoreCase) &&
                  width == gump.Width && height == gump.Height && opaque == spec.GetProperty("opaque_pixels").GetInt32() &&
                  digest == spec.GetProperty("expected_rgba_sha256").GetString();
    return new PortraitReport(passed ? "passed" : "failed", index, gump.Width, gump.Height, gump.Pixels.Length,
                              opaque, digest, Path.GetFileName(manager.Gumps.File.FilePath));
}

record PortraitReport(string status, uint gump_id, int width, int height, int pixels_checked,
                      int opaque_pixels, string rgba_sha256, string classicuo_file);
record StaticReadback(bool matched, int expected_count, int modernuo_count, int classicuo_count);
