using System.Text.Json;
using Server;
using Server.Network;
using Server.Gumps;
using Server.Targeting;
using UltimaOffline.Entities;

namespace UltimaOffline.Dialogue;

public static partial class CampaignDialogue
{
    private static readonly Dictionary<string,int> EstateHandles = new(StringComparer.Ordinal);
    private static readonly Dictionary<int,string> EstateIds = new();
    private static bool _estateScroll;

    private static void InstallEstate(JsonElement seed, JsonElement module)
    {
        if (!seed.TryGetProperty("investigation_chests", out var chests) || chests.GetArrayLength() == 0) return;
        var roots = module.GetProperty("roots").EnumerateObject().Select(p => p.Value.GetInt32()).ToHashSet();
        if (!roots.Contains(641) || !roots.Contains(522)) throw new InvalidDataException("Missing original chest or key function");
        _estateScroll = roots.Contains(797);
        void Register(JsonElement obj)
        {
            string id = obj.GetProperty("id").GetString()!;
            int handle = checked(0x300000 + obj.GetProperty("archive_offset").GetInt32());
            EstateHandles.Add(id, handle); EstateIds.Add(handle, id);
        }
        foreach (var obj in seed.GetProperty("investigation_items").EnumerateArray()) Register(obj);
        foreach (var chest in chests.EnumerateArray())
            foreach (var obj in chest.GetProperty("objects").EnumerateArray()) Register(obj);
        CampaignEntities.EstateUsed += UseEstate;
        EventSink.Connected += player => Server.Timer.StartTimer(TimeSpan.FromMilliseconds(300), () =>
        {
            if (State.PendingKeys.TryGetValue(player.Serial.Value, out var key) &&
                CampaignEntities.Find(key) is CampaignInvestigationItem item) UseEstate(player,item);
        });
    }

    private static bool CanUseEstate(Mobile player, Item item) => !item.Deleted && player.Alive &&
        (player.Backpack != null && item.IsChildOf(player.Backpack) || player.Map == item.Map &&
         item.RootParent is not Mobile && player.InRange(item.GetWorldLocation(),2) && player.InLOS(item));

    private static void UseEstate(Mobile player, Item item)
    {
        if (!CanUseEstate(player,item) || item is not ICampaignEntity entity ||
            !EstateHandles.TryGetValue(entity.SourceId,out var handle)) return;
        if (item is CampaignChest chest) RunEstate(player,522,handle,chest);
        else if (item is CampaignInvestigationItem { SourceShape: 797, SourceQuality: 5 } scroll && _estateScroll)
            ReadEstateScroll(player,scroll,handle);
        else if (item is CampaignInvestigationItem { SourceShape: 641 })
        {
            // In the original program, target selection precedes all world effects.
            // Reopening this cursor is safe across a disconnect or process restart.
            using var vm = new DialogueMachine(_source,641,1,handle);
            var cursor = vm.Next(null);
            if (cursor.Status != "effect" || cursor.Kind != "intrinsic" || cursor.Intrinsic != 0x33)
                throw new InvalidDataException("Unexpected original key entry");
            player.Target = new EstateTarget(entity.SourceId);
            State.PendingKeys[player.Serial.Value] = entity.SourceId;
        }
    }

    private sealed class EstateScrollGump : Gump
    {
        public EstateScrollGump(string line) : base(80,80)
        {
            AddPage(0); AddBackground(0,0,390,160,0x242C);
            AddHtml(25,28,338,83,GumpText(line),false,true);
            AddButton(26,116,0xFA5,0xFA7,1); AddLabel(60,114,0,"Close");
        }
    }

    private static void ReadEstateScroll(Mobile player, CampaignInvestigationItem scroll, int handle)
    {
        using var vm = new DialogueMachine(_source,797,1,handle);
        var e = vm.Next(null);
        string? line = null;
        bool display = false;
        try
        {
            for(int step=0;step<16;step++)
            {
                if(e.Status=="completed" && display && line!=null)
                {
                    player.SendGump(new EstateScrollGump(line),singleton:true); return;
                }
                if(e.Status!="effect") throw new InvalidDataException(e.Data.GetRawText());
                string? reply=null;
                if(e.Kind=="say" && display && line==null && e.Args.GetArrayLength()==1) line=e.Args[0].GetString();
                else if(e.Kind=="intrinsic" && e.Intrinsic==0x14 && e.Args[0].GetInt32()==handle)
                    reply=JsonSerializer.Serialize(scroll.SourceQuality);
                else if(e.Kind=="intrinsic" && e.Intrinsic==0x86 && e.Args[0].GetInt32()==14 && e.Args[1].GetInt32()==handle)
                    Effects.PlaySound(player.Location,player.Map,0x55); // Native UO page turn.
                else if(e.Kind=="intrinsic" && e.Intrinsic==0x55 && e.Args[0].GetInt32()==handle) display=true;
                else throw new InvalidDataException("Unqualified source scroll effect");
                e=vm.Next(reply);
            }
            throw new InvalidDataException("Estate scroll exceeded its source effect budget");
        }
        catch(Exception ex)
        {
            var error=$"Estate scroll {scroll.SourceId} at {e.Location}: {ex.Message}";
            player.SendMessage(error); Console.WriteLine(error);
        }
    }

    private sealed class EstateTarget(string key) : Target(2,false,TargetFlags.None)
    {
        protected override void OnTarget(Mobile from, object target)
        {
            if (!State.PendingKeys.Remove(from.Serial.Value,out var pending) || pending != key ||
                CampaignEntities.Find(key) is not Item item || !CanUseEstate(from,item)) return;
            if (target is CampaignChest chest && CanUseEstate(from,chest))
                RunEstate(from,641,EstateHandles[key],chest);
            else from.SendMessage("This source key target has no qualified interaction on this facet.");
        }
        protected override void OnTargetCancel(Mobile from, TargetCancelType reason)
        {
            if (reason != TargetCancelType.Disconnected && State.PendingKeys.GetValueOrDefault(from.Serial.Value) == key)
                State.PendingKeys.Remove(from.Serial.Value);
        }
    }

    private static void RunEstate(Mobile player,int function,int caller,CampaignChest chest)
    {
        int target = EstateHandles[chest.SourceId], shape = chest.SourceShape;
        var effects = new List<Action>();
        using var vm = new DialogueMachine(_source,function,1,caller);
        var e = vm.Next(null);
        try
        {
            for (int i=0; i<64; i++)
            {
                if (e.Status == "completed")
                {
                    foreach (var effect in effects) effect();
                    return;
                }
                if (e.Status != "effect") throw new InvalidDataException(e.Data.GetRawText());
                var args = e.Args;
                int A(int n) => args[n].ValueKind == JsonValueKind.Array ? args[n][0].GetInt32() : args[n].GetInt32();
                string? reply = null;
                if (e.Kind == "flag_write" && A(0)==62)
                {
                    int value=Bit(args[1]); effects.Add(()=>State.Changes[62]=value);
                }
                else if (e.Kind == "intrinsic")
                {
                    switch (e.Intrinsic)
                    {
                        case 0x33: reply=JsonSerializer.Serialize(new[] {target,chest.X,chest.Y,chest.Z/4}); break;
                        case 0x86 when A(0)==27 && A(1)==caller:
                            effects.Add(()=>Effects.PlaySound(player.Location,player.Map,0x1F5)); break;
                        case 0x11 when A(0)==target: reply=JsonSerializer.Serialize(shape); break;
                        case 0x14 when A(0)==caller && EstateIds.TryGetValue(caller,out var key) &&
                                             CampaignEntities.Find(key) is CampaignInvestigationItem k:
                            reply=JsonSerializer.Serialize(k.SourceQuality); break;
                        case 0x14 when A(0)==target: reply=JsonSerializer.Serialize(chest.SourceQuality); break;
                        case 0x40 when A(0)==target || A(0)==Avatar:
                        {
                            string line=args[1].GetString()!; bool onChest=A(0)==target;
                            effects.Add(()=>{ if(onChest) chest.LabelTo(player,line); else player.SendMessage(line); });
                            break;
                        }
                        case 0x0D when A(0)==target && A(1) is 522 or 800:
                        {
                            int next=A(1); shape=next; effects.Add(()=>chest.SetLockShape(next)); break;
                        }
                        case 0x2A when A(0)==target && A(1)==641 && A(3)==-359:
                        {
                            int quality=A(2);
                            var found=CampaignEntities.Entries.Values.OfType<CampaignInvestigationItem>()
                                .Where(k=>!k.Deleted && k.SourceShape==641 && k.SourceQuality==quality && k.IsChildOf(chest)).ToArray();
                            if(found.Length>1) throw new InvalidDataException("Multiple matching estate keys need original ordering");
                            reply=JsonSerializer.Serialize(found.Select(k=>EstateHandles[k.SourceId]).ToArray()); break;
                        }
                        case 0x6E when EstateIds.TryGetValue(A(0),out var contained) &&
                                        CampaignEntities.Find(contained) is Item {Parent: ICampaignEntity container}:
                            reply=JsonSerializer.Serialize(EstateHandles[container.SourceId]); break;
                        case 0x80 when A(0)==target:
                            effects.Add(()=>{ chest.SendRemovePacket(); if(player.NetState is {} ns) chest.SendInfoTo(ns); }); break;
                        default: throw new InvalidDataException($"Unimplemented estate intrinsic {e.Intrinsic:X2}");
                    }
                }
                else throw new InvalidDataException($"Unimplemented estate effect {e.Kind}");
                e=vm.Next(reply);
            }
            throw new InvalidDataException("Estate command budget exceeded");
        }
        catch (Exception ex)
        {
            string error=$"Estate action {function:X4} on {chest.SourceId} at {e.Location}: {ex.Message}";
            Console.WriteLine(error); player.SendMessage(error);
        }
    }
}
