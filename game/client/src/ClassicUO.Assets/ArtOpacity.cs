using System;
using System.IO;
using ClassicUO.Utility.Logging;

namespace ClassicUO.Assets
{
    // Optional row-major alpha for our RGB555 overrides. Retail assets retain
    // their existing decoding. The renderer expects premultiplied RGBA.
    internal static class ArtOpacity
    {
        internal static void Apply(string artPath, Span<uint> pixels)
        {
            string path=Path.ChangeExtension(artPath,".alpha");
            if(!File.Exists(path)) return;
            byte[] alpha;
            try { alpha=File.ReadAllBytes(path); }
            catch(IOException e) { Log.Warn($"could not read {path}: {e.Message}"); return; }
            if(alpha.Length!=pixels.Length) {
                Log.Warn($"{Path.GetFileName(path)} has {alpha.Length} alpha bytes; expected {pixels.Length}");
                return;
            }
            for(int i=0;i<pixels.Length;i++) {
                uint color=pixels[i];
                if(color==0) continue;
                uint a=alpha[i];
                pixels[i]=(a<<24) |
                    ((((color>>16)&255)*a+127)/255<<16) |
                    ((((color>>8)&255)*a+127)/255<<8) |
                    (((color&255)*a+127)/255);
            }
        }
    }
}
