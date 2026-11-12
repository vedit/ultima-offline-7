using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using Server;

namespace UltimaOffline;

public static class UsecodeHost
{
    const int FlagCount = 32768;
    private static readonly byte[] WorldFlags = new byte[FlagCount];
    private static byte[]? _source;
    private static int _function;
    private static string _edition = "";
    private static (int Line, int Offset)[] _locations = [];

    [DllImport("U7LuaHost", CallingConvention = CallingConvention.Cdecl)]
    private static extern int u7_run_v1(byte[] source, int length, int eventId,
        [In, Out] byte[] flags, int flagCount, int budget, [Out] byte[] error, int capacity, out int line);

    // Called by ModernUO's assembly initializer after loading this private facet.
    public static void Initialize()
    {
        string dir = Path.Combine(Core.BaseDirectory, "Campaign");
        NativeLibrary.SetDllImportResolver(typeof(UsecodeHost).Assembly, (name, _, _) =>
            name == "U7LuaHost" ? NativeLibrary.Load(Path.Combine(Core.BaseDirectory, "U7LuaHost.dll")) : 0);
        using var document = JsonDocument.Parse(File.ReadAllBytes(Path.Combine(dir, "script.json")));
        var script = document.RootElement;
        _source = File.ReadAllBytes(Path.Combine(dir, "function.lua"));
        if (Convert.ToHexStringLower(SHA256.HashData(_source)) != script.GetProperty("lua_sha256").GetString())
            throw new InvalidDataException("Usecode source differs from the staged compiler product.");
        _function = script.GetProperty("function_id").GetInt32();
        _edition = File.Exists(Path.Combine(dir, "edition.txt"))
            ? File.ReadAllText(Path.Combine(dir, "edition.txt")).Trim()
            : script.GetProperty("source_sha256").GetString()!;
        _locations = script.GetProperty("source_map").EnumerateArray().Select(row =>
            (row.GetProperty("lua_line").GetInt32(), row.GetProperty("source_offset").GetInt32())).ToArray();
        if (_function != 0x06A4 || _locations.Length == 0)
            throw new InvalidDataException("The flag-host probe requires the compiled function 0x06A4 and source map.");

        var scenarios = new List<object>();
        foreach (var (eventId, before, expected) in new[] { (3, 0, 1), (1, 0, 0), (0, 1, 1) })
        {
            var flags = new byte[FlagCount];
            flags[2] = 1;
            flags[60] = (byte)before;
            var expectedFlags = (byte[])flags.Clone();
            expectedFlags[60] = (byte)expected;
            DispatchInto(_function, eventId, "probe", flags);
            if (!flags.SequenceEqual(expectedFlags)) throw new InvalidDataException("Hosted flag branch diverged.");
            scenarios.Add(new { eventId, before, after = flags[60] });
        }
        // Exercise the same native entry with authored fragments, on isolated state.
        ExpectFailure("return function(e,f) f[1]=1 while true do end end", "budget exhausted");
        ExpectFailure("return function() return os.time() end", "nil");
        ExpectFailure("return function(e,f) f[-1]=1 end", "outside host range");
        var report = new { status = "passed", abi = 1, lua = "5.4.7", function = _function,
            edition = _edition, scenarios, budget_and_api_cases = 3,
            server = typeof(Core).Assembly.GetName().Name, process = Environment.ProcessId,
            converted_gameplay = "not_run" };
        File.WriteAllText(Path.Combine(dir, "host-probe.json"), JsonSerializer.Serialize(report));
    }

    public static void Dispatch(int functionId, int eventId, string sourceObject) =>
        DispatchInto(functionId, eventId, sourceObject, WorldFlags);

    private static void DispatchInto(int functionId, int eventId, string sourceObject, byte[] flags)
    {
        if (_source == null || functionId != _function)
            throw new InvalidOperationException($"Missing compiled function {functionId:X4}, edition {_edition}, event {eventId}, object {sourceObject}.");
        var (status, line, message) = Execute(_source, eventId, flags);
        if (status == 0) return;
        var offset = _locations.Where(location => location.Line <= line)
            .Select(location => (int?)location.Offset).LastOrDefault();
        throw new InvalidOperationException($"Edition {_edition}, function {functionId:X4}, event {eventId}, object {sourceObject}, " +
            $"source byte {offset?.ToString() ?? "unknown"}, function.lua line {line}: {message}");
    }

    private static (int Status, int Line, string Message) Execute(byte[] source, int eventId, byte[] flags)
    {
        var working = (byte[])flags.Clone();
        var error = new byte[512];
        int status = u7_run_v1(source, source.Length, eventId, working, working.Length, 10000,
            error, error.Length, out int line);
        if (status == 0) Array.Copy(working, flags, flags.Length);
        return (status, line, Encoding.UTF8.GetString(error).TrimEnd('\0'));
    }

    private static void ExpectFailure(string source, string expected)
    {
        var flags = new byte[FlagCount];
        var (status, _, message) = Execute(Encoding.UTF8.GetBytes(source), 0, flags);
        if (status == 0 || !message.Contains(expected, StringComparison.Ordinal) || flags[1] != 0)
            throw new InvalidDataException($"Host boundary test failed: {message}");
    }
}
