using System;
using System.Collections.Generic;
using System.Linq;

namespace UltimaOffline.Dialogue;

// PARTY stores two ordered lists. Sleeping members still belong to the party.
public class PartyRoster
{
    public List<int> Party { get; set; } = new() { -356 };
    public List<int> DownedParty { get; set; } = new();

    public bool ContainsMember(int handle) => Party.Contains(handle) || DownedParty.Contains(handle);
    public int[] Query(bool includeDowned) => (includeDowned
        ? Party.AsEnumerable().Reverse().Concat(DownedParty.AsEnumerable().Reverse())
        : Party.AsEnumerable().Reverse()).ToArray();

    public bool Join(int handle)
    {
        if (ContainsMember(handle) || Party.Count >= 8) return false;
        Party.Add(handle);
        return true;
    }

    public bool Leave(int handle) => handle != -356 && (Party.Remove(handle) || DownedParty.Remove(handle));

    // SeparateDownedMembers runs during movement/follow updates. A Usecode
    // roster read between updates must see the previously committed ordering.
    public void UpdateFollowers(Func<int, bool> unconscious)
    {
        var falling = Party.Skip(1).Where(unconscious).ToArray();
        var rising = DownedParty.Where(h => !unconscious(h)).ToArray();
        if (DownedParty.Count + falling.Length > 16 || Party.Count - falling.Length + rising.Length > 8)
            throw new InvalidOperationException("Party transition exceeds the DOS roster capacity.");
        foreach (var handle in falling)
        {
            Party.Remove(handle);
            DownedParty.Add(handle);
        }
        foreach (var handle in rising)
        {
            DownedParty.Remove(handle);
            Party.Add(handle);
        }
    }
}
