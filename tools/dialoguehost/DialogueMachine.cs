using System.Buffers.Binary;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using Server;

namespace UltimaOffline.Dialogue;

internal sealed class DialogueMachine : IDisposable
{
    [DllImport("U7DialogueNative", CallingConvention = CallingConvention.Cdecl)]
    private static extern nint u7_dialog_open(byte[] source, int n, byte[] bridge, int m, int id, int eventId, int item, [Out] byte[] err, int cap);
    [DllImport("U7DialogueNative", CallingConvention = CallingConvention.Cdecl)]
    private static extern int u7_dialog_next(nint d, byte[] reply, int n, [Out] byte[] result, int cap);
    [DllImport("U7DialogueNative", CallingConvention = CallingConvention.Cdecl)]
    private static extern void u7_dialog_close(nint d);

    private nint _vm;
    private byte[] _result = new byte[65536];
    private static readonly byte[] Bridge;
    static DialogueMachine()
    {
        var assembly = typeof(DialogueMachine).Assembly;
        NativeLibrary.SetDllImportResolver(assembly, (name, _, _) => name == "U7DialogueNative"
            ? NativeLibrary.Load(Path.Combine(Core.BaseDirectory, "U7DialogueNative.dll")) : 0);
        using var stream = assembly.GetManifestResourceStream("dialogue-bridge")!;
        using var buffer = new MemoryStream();
        stream.CopyTo(buffer); Bridge = buffer.ToArray();
    }

    internal DialogueMachine(byte[] source, int function, int eventId, int item)
    {
        _vm = u7_dialog_open(source, source.Length, Bridge, Bridge.Length, function, eventId, item, _result, _result.Length);
        if (_vm == 0) throw new InvalidDataException(Error());
    }
    private string Error() => Encoding.UTF8.GetString(_result.AsSpan(0, Math.Max(0, Array.IndexOf(_result, (byte)0))));
    public void Dispose() { if (_vm != 0) { u7_dialog_close(_vm); _vm = 0; } }

    internal Step Next(string? reply)
    {
        byte[] data;
        if (reply == null) data = [(byte)'n'];
        else
        {
            using var value = JsonDocument.Parse(reply);
            if (value.RootElement.ValueKind == JsonValueKind.Number)
            {
                data = new byte[9]; data[0] = (byte)'i';
                BinaryPrimitives.WriteInt64LittleEndian(data.AsSpan(1), value.RootElement.GetInt64());
            }
            else if (value.RootElement.ValueKind == JsonValueKind.String)
                data = Encoding.UTF8.GetBytes("s" + value.RootElement.GetString());
            else if (value.RootElement.ValueKind == JsonValueKind.Array && value.RootElement.GetArrayLength() <= 4096)
            {
                data = new byte[1+8*value.RootElement.GetArrayLength()]; data[0]=(byte)'a';
                int offset = 1;
                foreach (var element in value.RootElement.EnumerateArray())
                {
                    BinaryPrimitives.WriteInt64LittleEndian(data.AsSpan(offset),element.GetInt64());
                    offset += 8;
                }
            }
            else throw new InvalidDataException("Invalid saved host reply.");
        }
        int size = u7_dialog_next(_vm, data, data.Length, _result, _result.Length);
        if (size < 0) throw new InvalidDataException(Error());
        using var doc = JsonDocument.Parse(_result.AsMemory(0,size));
        return new Step(doc.RootElement.Clone(), Convert.ToHexStringLower(SHA256.HashData(_result.AsSpan(0,size))));
    }
}

internal sealed record Step(JsonElement Data, string Signature)
{
    public string Status => Data.GetProperty("status").GetString()!;
    public string Kind => Data.GetProperty("kind").GetString()!;
    public JsonElement Args => Data.GetProperty("args");
    public int Intrinsic => Data.GetProperty("intrinsic").GetInt32();
    public string Location => $"function 0x{Data.GetProperty("function_id").GetInt32():X4}, PC 0x{Data.GetProperty("pc").GetInt32():X}, source byte {Data.GetProperty("source_offset").GetInt32()}";
}
