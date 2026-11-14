// Stock UO presentation for matching U7 species. No combat rules live here.
namespace ClassicUO.Game
{
    internal static class TrinsicCreatures
    {
        internal static byte Attack(ushort body) {
            var animations=Client.Game.UO.Animations;
            animations.AnimationExists(body,0); // Resolve lazy MUL/UOP metadata first.
            animations.ConvertBodyIfNeeded(ref body);
            var flags=animations.GetAnimFlags(body);
            if((flags&ClassicUO.Assets.AnimationFlags.CalculateOffsetLowGroupExtended)!=0) return 4;
            return (byte)(((flags&ClassicUO.Assets.AnimationFlags.CalculateOffsetByLowGroup)!=0 ||
                animations.GetAnimType(body)==ClassicUO.Assets.AnimationGroupsType.Animal)?5:4);
        }
        internal static ushort Body(int shape) => shape switch {
            492=>0x00ca, 493=>0x013d, 495=>0x00c9, 496=>0x00d9,
            498=>0x00d0, 499=>0x0008, 500=>0x00d8, 501=>0x004b,
            502=>0x00ed, 504=>0x000c, 505=>0x003c, 511=>0x0016,
            514=>0x001f, 519 or 354=>0x0018, 521 or 523=>0x00ee,
            524=>0x002f, 525=>0x0096, 528=>0x0032, 529=>0x0033,
            530=>0x0034, 532=>0x001e, 533 or 861=>0x0035,
            534=>0x003a, 537=>0x00e1, 661=>0x0027, 706=>0x0030,
            727 or 476 or 796=>0x00c8, 811=>0x00cd, 865=>0x001c,
            970=>0x00cf, _=>0
        };
        internal static string Name(int shape) => shape switch {
            727 or 476 or 796=>"Horse", 521 or 523=>"Rat", _=>"Creature"
        };
    }
}
