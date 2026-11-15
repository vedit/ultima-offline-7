using System;
using System.Collections.Generic;
using System.IO;
using ClassicUO.Assets;
using ClassicUO.Utility.Logging;

namespace ClassicUO.Renderer
{
    // Frames are uploaded once, on first use. Drawing only selects an atlas
    // rectangle; no per-frame disk access, texture mutation, or pixel allocation.
    internal sealed class ShimmerAnimation
    {
        private readonly Dictionary<uint, string> paths = new();
        private readonly Dictionary<uint, (SpriteInfo[] frames, ShimmerData data)> animations = new();
        private readonly string subfolder;
        public ShimmerAnimation(string subfolder) { this.subfolder = subfolder; Reload(); }

        public void Reload()
        {
            paths.Clear(); animations.Clear();
            string town = Environment.GetEnvironmentVariable("TRINSIC_TOWN");
            if (string.IsNullOrEmpty(town)) return;
            string folder = Path.Combine(town, subfolder);
            if (!Directory.Exists(folder)) return;
            foreach (string path in Directory.EnumerateFiles(folder, "*.shimmer"))
                if (uint.TryParse(Path.GetFileNameWithoutExtension(path), out uint id)) paths[id] = path;
        }

        public void Load(uint id, ReadOnlySpan<uint> pixels, int width, int height, TextureAtlas atlas)
        {
            if (!paths.Remove(id, out string path)) return;
            try
            {
                var data = new ShimmerData(File.ReadAllBytes(path), width, height);
                var frames = new SpriteInfo[data.Frames];
                for (int f = 0; f < frames.Length; f++)
                    frames[f].Texture = atlas.AddSprite(data.Render(pixels, f), width, height, out frames[f].UV);
                animations[id] = (frames, data);
                Log.Trace($"Shimmer loaded: {subfolder}/{id}, {data.Frames} frames");
            }
            catch (Exception e) when (e is IOException || e is InvalidDataException || e is ArgumentException || e is OverflowException)
            {
                Log.Warn($"Ignoring shimmer {path}: {e.Message}");
            }
        }

        public ref readonly SpriteInfo Get(uint id, in SpriteInfo fallback)
        {
            if (animations.TryGetValue(id, out var animation))
                return ref animation.frames[animation.data.FrameAt(Environment.TickCount64)];
            return ref fallback;
        }
    }
}
