// SPDX-License-Identifier: BSD-2-Clause
using System;
using System.IO;
using System.Linq;
using System.Text;
using ClassicUO.Configuration;
using ClassicUO.Game.Managers;
using ClassicUO.Game.UI.Controls;
using ClassicUO.Game.UI.Gumps;
using Microsoft.Xna.Framework.Media;

namespace ClassicUO.Game
{
    internal static class TrinsicAudio
    {
        private static Song song;
        private static int generation, cue = -1, track = -1;
        private static bool playing, available, external;
        private static string playbackKey, acknowledged;
        private static long retry;
        internal static string Acknowledged => acknowledged;
        internal static string Status { get; private set; } = "Waiting for native audio.";
        internal static int ActiveSlot { get; private set; }
        internal static readonly string[] SaveTitles = new string[10];
        internal static bool Typing => UIManager.KeyboardFocusControl is StbTextBox box &&
            (box.RootParent is TrinsicAudioGump || box.RootParent is TrinsicSavesGump);
        internal static void Close()
        {
            Stop(); playbackKey = acknowledged = null; available = false; cue = -1; retry = 0;
        }
        private static void Stop()
        {
            if (song != null) { MediaPlayer.Stop(); song.Dispose(); song = null; }
            external = false;
        }
        internal static void Apply(string[] lines, int gen)
        {
            if (generation != gen) { Close(); generation = gen; }
            var row = lines.FirstOrDefault(l => l.StartsWith("AU "))?.Split(' ');
            available = row?.Length >= 12;
            if (available)
            {
                cue = int.Parse(row[1]); track = int.Parse(row[2]); playing = row[3] == "1";
                acknowledged = row[11] == "1" ? string.Join(" ", row.Skip(4).Take(7)) : null;
            }
            foreach (string line in lines)
            {
                var a = line.Split(' ');
                if (a[0] == "SV") ActiveSlot = int.Parse(a[1]);
                if (a[0] == "SL" && int.TryParse(a[1], out int n) && n >= 0 && n < 10)
                    SaveTitles[n] = a[2] == "-" ? "" : CodePagesEncodingProvider.Instance.GetEncoding(437).GetString(Convert.FromHexString(a[2]));
            }
        }
        internal static bool SetFolder(World world, string folder, out string message)
        {
            try
            {
                folder = folder.Trim().Trim('"');
                if (folder.Length != 0)
                {
                    folder = Path.GetFullPath(folder);
                    if (!Directory.Exists(folder) || !Directory.EnumerateFiles(folder, "*bg.ogg").Any())
                    { message = "Choose the Exult music folder containing files such as 35bg.ogg."; return false; }
                }
                ProfileManager.CurrentProfile.TrinsicExultMusicFolder = folder;
                ProfileManager.CurrentProfile.Save(world, ProfileManager.ProfilePath);
                playbackKey = null; message = folder.Length == 0 ? "Using original synthesized music." : "Local music folder selected.";
                return true;
            }
            catch (Exception e) when (e is IOException || e is ArgumentException || e is UnauthorizedAccessException || e is NotSupportedException)
            { message = "Cannot read that folder: " + e.Message; return false; }
        }
        internal static void Update()
        {
            var p = ProfileManager.CurrentProfile;
            if (!available || p == null) return;
            string folder = p.TrinsicExultMusicFolder ?? "";
            string key = $"{generation}/{cue}/{track}/{playing}/{p.TrinsicMusicEnabled}/{folder}";
            if (key != playbackKey)
            {
                Stop(); playbackKey = key;
                Status = !p.TrinsicMusicEnabled ? "Music off." : !playing ? "Waiting for the next U7 music cue." : "Original synthesized music.";
                if (playing && p.TrinsicMusicEnabled && folder.Length > 0 && track >= 0 && track < 60)
                {
                    string path = Path.Combine(folder, $"{track:00}bg.ogg");
                    try
                    {
                        using (var file = File.OpenRead(path))
                        {
                            byte[] header = new byte[4];
                            if (file.Read(header, 0, 4) != 4 || Encoding.ASCII.GetString(header) != "OggS") throw new IOException("Invalid OGG header");
                        }
                        Client.Game.Audio.StopMusic();
                        song = Song.FromUri("U7 " + track, new Uri(path));
                        MediaPlayer.Volume = Math.Clamp(p.TrinsicMusicVolume, 0, 100) / 100f;
                        MediaPlayer.IsRepeating = true; // Native stop/change events end playback, including special cues.
                        MediaPlayer.Play(song);
                        external = MediaPlayer.State == MediaState.Playing && song.Duration > TimeSpan.Zero;
                        if (!external) throw new IOException("Decoder did not start");
                        Status = $"Exult MT-32 recording: {track:00}bg.ogg";
                    }
                    catch (Exception e) when (e is IOException || e is ArgumentException || e is InvalidOperationException || e is UnauthorizedAccessException || e is DllNotFoundException || e is EntryPointNotFoundException)
                    { Stop(); Status = $"Track {track:00} unavailable; using native music."; }
                }
            }
            if (external) MediaPlayer.Volume = Math.Clamp(p.TrinsicMusicVolume, 0, 100) / 100f;
            int m = p.TrinsicMusicEnabled ? 1 : 0, efx = p.EnableSound ? 1 : 0, s = p.TrinsicSpeechEnabled ? 1 : 0;
            string settings = $"{m} {efx} {s} {Math.Clamp(p.TrinsicMusicVolume,0,100)} {Math.Clamp(p.SoundVolume,0,100)} {Math.Clamp(p.TrinsicSpeechVolume,0,100)} {(external?1:0)}";
            if (settings != acknowledged && Environment.TickCount64 >= retry)
            {
                retry = Environment.TickCount64 + 600;
                TrinsicSession.Send("AUDIO", m, efx, " " + string.Join(" ", settings.Split(' ').Skip(2)));
            }
        }
    }
}
