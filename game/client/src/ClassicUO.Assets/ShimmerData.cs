using System;
using System.IO;

namespace ClassicUO.Assets
{
    // Material weights, not replacement artwork: registration and alpha belong
    // to the decoded base sprite. SHM1 files are made from reviewed atlas masks.
    public sealed class ShimmerData
    {
        public readonly int Width, Height, Frames, FrameMilliseconds;
        private readonly byte[] weights, tint;
        private readonly int lift;
        private readonly double minimum, span;

        public ShimmerData(byte[] data, int width, int height)
        {
            using var input = new BinaryReader(new MemoryStream(data));
            if (data.Length < 28 || input.ReadUInt32() != 0x314d4853)
                throw new InvalidDataException("Invalid shimmer header");
            Width = input.ReadInt32(); Height = input.ReadInt32();
            Frames = input.ReadInt32(); FrameMilliseconds = input.ReadInt32();
            lift = input.ReadInt32(); tint = input.ReadBytes(3);
            if (Width != width || Height != height || Width < 1 || Height < 1 ||
                Width > 512 || Height > 512 || Frames < 2 || Frames > 64 ||
                FrameMilliseconds < 50 || FrameMilliseconds > 1000 || lift < 1 || lift > 64 ||
                data.Length != 27 + Width * Height)
                throw new InvalidDataException($"Invalid shimmer dimensions or timing: mask {Width}x{Height}, sprite {width}x{height}, frames {Frames}, ms {FrameMilliseconds}, bytes {data.Length}");
            weights = input.ReadBytes(Width * Height);
            double low = double.MaxValue, high = double.MinValue;
            for (int i = 0; i < weights.Length; i++) if (weights[i] != 0)
            {
                double q = (i % Width) * .35 + (i / Width) * .65;
                low = Math.Min(low, q); high = Math.Max(high, q);
            }
            if (low == double.MaxValue) throw new InvalidDataException("Empty shimmer mask");
            minimum = low; span = Math.Max(1, high - low);
        }

        public int FrameAt(long milliseconds) => (int)((milliseconds / FrameMilliseconds) % Frames);

        public uint[] Render(ReadOnlySpan<uint> source, int frame)
        {
            if (source.Length != weights.Length || frame < 0 || frame >= Frames)
                throw new ArgumentOutOfRangeException(nameof(frame));
            uint[] result = source.ToArray();
            double t = (double)frame / Frames, pulse = Math.Pow(Math.Sin(Math.PI * t), 2);
            for (int i = 0; i < result.Length; i++)
            {
                uint a = source[i] >> 24;
                if (weights[i] == 0 || a == 0) continue;
                double position = ((i % Width) * .35 + (i / Width) * .65 - minimum) / span;
                double strength = pulse * Math.Exp(-Math.Pow((position - t) / .25, 2)) * weights[i] / 255.0;
                uint color = a << 24;
                for (int c = 0; c < 3; c++)
                {
                    // RGB is premultiplied; keep glass and aura transparency intact.
                    uint delta = (uint)Math.Round(strength * lift * tint[c] / 255.0);
                    uint value = Math.Min(a, ((source[i] >> (8 * c)) & 255) + (delta * a + 127) / 255);
                    color |= value << (8 * c);
                }
                result[i] = color;
            }
            return result;
        }
    }
}
