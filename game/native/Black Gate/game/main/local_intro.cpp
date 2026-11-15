#include "u7port.h"
#include "objref.h"
#include "coord.h"
#include "item.h"
#include "camera.h"
#include "local_session.h"
#include "local_effects.h"
#include "local_intro.h"
#include "u7npc.h"
#include <cstring>
#include <cstdlib>

extern objref AvatarRef;
static bool dreamArrivalPending;
static bool characterCreated;

bool LocalCharacterPending()
{
    return LocalEnabled() && getenv("TRINSIC_READY") && !characterCreated &&
        !dreamArrivalPending && AvatarRef.valid() && !IsOnMap(&AvatarRef);
}

std::string LocalCreateCharacter(int female, const std::string &encoded)
{
    if (!LocalCharacterPending()) return "unavailable";
    if ((female != 0 && female != 1) || encoded.empty() || encoded.size() > 28 || encoded.size()%2)
        return "invalid-character";
    auto digit=[](char c)->int {return c>='0'&&c<='9'?c-'0':c>='A'&&c<='F'?c-'A'+10:c>='a'&&c<='f'?c-'a'+10:-1;};
    std::string name;
    for (size_t i=0;i<encoded.size();i+=2) {
        int hi=digit(encoded[i]),lo=digit(encoded[i+1]);
        if (hi<0 || lo<0) return "invalid-character";
        unsigned char c=(hi<<4)|lo;
        if (c<32 || c==127) return "invalid-character";
        name.push_back(static_cast<char>(c));
    }
    if (name.front()==' ' || name.back()==' ') return "invalid-character";
    // Same native fields and operations as the original LoadGameArgs path.
    auto npc=GetNpcBufferForIbo(&AvatarRef);
    if (!npc) return "unavailable";
    memset(npc->name,0,sizeof npc->name);
    memcpy(npc->name,name.data(),name.size());
    if (female) Npc_setFemale(&AvatarRef); else Npc_setMale(&AvatarRef);
    characterCreated=true;
    return "ok";
}

bool LocalDreamBegin()
{
    // The original arrival runs three westward steps before Iolo greets the
    // Avatar. Start at 1074,2210 so that greeting occurs at the stable entrance,
    // 1071,2210. Keep the original off-map state and every queued Usecode action.
    if (!LocalEnabled() || !AvatarRef.valid() || IsOnMap(&AvatarRef)) return false;
    if (!Item_move(&AvatarRef, Coord(1074), Coord(2210), 0)) return false;
    Item_detach(&AvatarRef);
    PlaceItemOffMap(&AvatarRef);
    gCamera.moveTo(Coord(1074), Coord(2210));
    dreamArrivalPending=true;
    return true;
}

void LocalDreamArrival()
{
    // Observe the native arrival actually putting the Avatar on the map. The
    // stock travel effect is presentation only; no invented spell or mana cost.
    if (!dreamArrivalPending || !AvatarRef.valid() || !IsOnMap(&AvatarRef)) return;
    dreamArrivalPending=false;
    LocalEffectOn("travel",5,AvatarRef.off);
}

extern "C" void ResetLocalIntroGlobals() { dreamArrivalPending=false;characterCreated=false; }
