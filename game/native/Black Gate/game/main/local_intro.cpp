#include "u7port.h"
#include "objref.h"
#include "coord.h"
#include "item.h"
#include "camera.h"
#include "local_session.h"
#include "local_effects.h"
#include "local_intro.h"

extern objref AvatarRef;
static bool dreamArrivalPending;

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

extern "C" void ResetLocalIntroGlobals() { dreamArrivalPending=false; }
