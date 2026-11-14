// Presentation-only observation of committed engine operations.
#include "u7port.h"
#include "local_effects.h"
#include "local_session.h"
#include "objref.h"
#include "item.h"
#include "coord.h"
#include "npcref.h"
#include "type.h"
#include "u7npc.h"
#include "ucvalue.h"
#include "uclist.h"
#include "gtimer.h"
#include "weapons.h"
#include "plat.h"
#include "worldpal.h"
#include "weather.h"
#include "bogus.h"
#include <vector>
#include <deque>
#include <map>
#include <sstream>
#include <cstdlib>

extern objref AvatarRef;
static bool enabled() { const char *v=getenv("TRINSIC_EFFECTS"); return LocalEnabled() && (!v || *v!='0'); }
static std::vector<int> contexts;
static int remoteSpell=-1;
int LocalEffectsSpell() { return contexts.empty() ? -1 : contexts.back(); }
void LocalEffectsPush(int routine) {
    int spell=routine>=1600 && routine<1672 ? routine-1600 : LocalEffectsSpell();
    if(routine==1542) spell=-2; // original fizzle routine
    if(routine==1554) spell=34;
    if(routine==1555) spell=36;
    if(routine==1551) spell=52; // delayed Magic Storm lightning
    contexts.push_back(spell);
}
void LocalEffectsPop() { if(!contexts.empty()) contexts.pop_back(); }
void LocalEffectsBegin(int routine,bool remote) { contexts.clear(); LocalEffectsPush(routine); if(remote && remoteSpell>=0) contexts.back()=remoteSpell; }
void LocalEffectsEnd() { contexts.clear(); }
struct Effect { uint64_t sequence; uint32_t time,tick; std::string kind; int spell,id,x,y,z,detail; };
static std::deque<Effect> effects;
static uint64_t sequence;
struct Missile { int id,type,x,y,z; };
static std::map<unsigned short,Missile> missiles;

void LocalEffectAt(const char *kind,int spell,short object,int x,int y,int z,int detail) {
    if(!enabled() || x<0 || y<0 || x>=3072 || y>=3072) return;
    const int id=LocalWireId(object);
    // Multiple status changes in one native operation (Cure/Restoration) share a burst.
    for(auto it=effects.rbegin();it!=effects.rend() && it->tick==GameTime.ticks;++it)
        if(it->kind==kind && it->spell==spell && it->id==id && it->x==x && it->y==y && it->z==z && it->detail==detail) return;
    if(effects.size()==512) effects.pop_front();
    effects.push_back({++sequence,plat_milliseconds(),GameTime.ticks,kind,spell,id,x,y,z,detail});
}
void LocalEffectOn(const char *kind,int spell,short object,int detail) {
    if(!enabled()) return;
    objref r(object);
    if(!r.valid()) return;
    objref anchor=r;
    // Inventory effects attach to their world owner, not container pixel coordinates.
    for(int n=0;n<16 && !IsOnMap(&anchor);++n) {
        objref owner=Item_getContainer(&anchor);
        if(!owner.valid() || owner==anchor) break;
        anchor=owner;
    }
    if(IsOnMap(&anchor)) LocalEffectAt(kind,spell,anchor.off,Item_getX(anchor),Item_getY(anchor),anchor.z(),detail);
}
void LocalEffectsReset() { effects.clear(); missiles.clear(); contexts.clear(); remoteSpell=-1; }
std::string LocalEffectsSnapshot() {
    std::ostringstream s;
    const uint32_t now=plat_milliseconds();
    while(!effects.empty() && uint32_t(now-effects.front().time)>1800) effects.pop_front();
    s<<"FX "<<sequence<<"\n";
    s<<"FV "<<int(CurrentWeather.type)<<" "<<GameScreen.lightSpellTime<<" "<<GameTime.hold<<" "<<EarthquakeCount<<"\n";
    for(const auto &e:effects) s<<"F "<<e.sequence<<" "<<e.tick<<" "<<e.kind<<" "<<e.spell<<" "<<e.id<<" "<<e.x<<" "<<e.y<<" "<<e.z<<" "<<e.detail<<"\n";
    for(const auto &pair:missiles) { const auto &m=pair.second; s<<"FM "<<m.id<<" "<<m.type<<" "<<m.x<<" "<<m.y<<" "<<m.z<<"\n"; }
    return s.str();
}
int LocalEffectWeaponSpell(int type) {
    switch(type) {case 856:return 18;case 807:return 33;case 78:return 43;case 621:return 58;case 639:return 65;case 399:return 60;case 287:return 70;case 527:return 57;case 80:return 40;case 281:return 24;case 408:return 28;case 424:return 30;case 72:return 31;case 540:return 2;case 280:return 6;case 443:return 22;default:return -1;}
}
void LocalEffectMissile(short object,int weapon,int x8,int y8,int z8,bool active) {
    if(!enabled() || !object || !weapon) return;
    WeaponRecord record; WeaponRecords.read(weapon,&record);
    int type=record.type; // read into our own buffer; never disturb the engine's record cache
    // Original magical ammunition, never ordinary arrows, bolts or thrown equipment.
    if(LocalEffectWeaponSpell(type)<0) return;
    if(!active) { LocalEffectMissileEnd(object);return; }
    missiles[(unsigned short)object]={LocalWireId(object),type,x8,y8,z8};
}
void LocalEffectMissileEnd(short object) { missiles.erase((unsigned short)object); }
void LocalEffectSprite(short object,int x,int y,int shape) {
    if(!enabled() || shape<1024 || shape>1048) return;
    int spell=LocalEffectsSpell();
    // Success is observed through mutations for these; decorative caster sprites
    // must not masquerade as a successful status application.
    if(spell>=0 && spell!=3 && spell!=10 && spell!=16 && spell!=38 && spell!=64) return;
    if(object) LocalEffectOn("sprite",spell,object,shape-1024);
    else LocalEffectAt("sprite",spell,0,x,y,0,shape-1024);
}
LocalEffectActor::LocalEffectActor(short id,int s):object(id),spell(s),hp(-999),status(0),extended(0),invisible(0),identity(LocalWireId(id)) {
    if(!enabled()) return;
    objref r(object);
    if(!r.valid()) return;
    invisible=(Item_getQualityFlags(&r)&QUALITY_INVISIBLE);
    if(r.isNpc()) { auto n=NPCRef(r).buffer(); hp=(int8_t)Item_getHitPoints(&r);status=n->status;extended=n->typeFlagsHigh; }
}
LocalEffectActor::~LocalEffectActor() {
    if(!enabled() || identity!=LocalWireId(object)) return;
    objref r(object);
    if(!r.valid()) return;
    if(invisible!=int((Item_getQualityFlags(&r)&QUALITY_INVISIBLE))) LocalEffectOn((Item_getQualityFlags(&r)&QUALITY_INVISIBLE)?"hide":"reveal",spell,object);
    if(hp==-999 || !r.isNpc()) return;
    auto n=NPCRef(r).buffer(); int added=n->status & ~status, removed=status & ~n->status;
    if(spell>=0 && (int8_t)Item_getHitPoints(&r)>hp) LocalEffectOn("heal",spell,object);
    if(added & NPC_ASLEEP) LocalEffectOn("sleep",spell,object);
    if(added & NPC_CHARMED) LocalEffectOn("charm",spell,object);
    if(added & NPC_CURSED) LocalEffectOn("curse",spell,object);
    if(added & NPC_PARALYZED) LocalEffectOn("paralyze",spell,object);
    if(added & NPC_POISONED) LocalEffectOn("poison",spell,object);
    if(added & NPC_PROTECTED) LocalEffectOn("protect",spell,object);
    if(spell>=0 && (removed & (NPC_POISONED|NPC_PARALYZED))) LocalEffectOn("cure",spell,object);
    if(spell>=0 && (removed & NPC_ASLEEP)) LocalEffectOn("awaken",spell,object);
    if((n->typeFlagsHigh & ~extended)&0x10) LocalEffectOn("might",spell,object);
    if(spell>=0 && (added & NPC_DEAD)) LocalEffectOn("death",spell,object);
}
static int arg(Value *args,int n,int part=1) { return GetListNode(args-n,part)->toInt(); }
static short observedObject(int num,Value *args,short subject) {
    if(!enabled() || (LocalEffectsSpell()<0 && num!=0x0d)) return 0;
    switch(num) {
    case 0x0d:case 0x13:case 0x15:case 0x1d:case 0x21:case 0x25:case 0x3d:case 0x3e:
    case 0x49:case 0x5f:case 0x61:case 0x89:case 0x8a: {short id=GetItemRef(GetListNode(args-1,1)); return id==UC_PARTY || id==UC_ALL ? 0 : id;}
    case 0x26: { objref r(0); GetItemBeingDragged(&r); return r.off; }
    default:return subject;
    }
}
LocalEffectIntrinsic::LocalEffectIntrinsic(int num,Value *a,Value *r,short who):
 number(num),spell(LocalEffectsSpell()),detail(0),object(observedObject(num,a,who)),subject(who),args(a),ret(r),
 shape(-1),frame(-1),quality(-1),x(0),y(0),z(0),onMap(false),actor(object,spell) {
    if(!enabled() || (spell<0 && number!=0x0d)) return;
    objref ref(object);
    if(ref.valid()) {shape=ref.type();frame=ref.frame();quality=Item_getQuality(&ref);x=Item_getX(ref);y=Item_getY(ref);z=ref.z();onMap=IsOnMap(&ref);}
}
LocalEffectIntrinsic::~LocalEffectIntrinsic() {
    if(!enabled() || (spell<0 && number!=0x0d)) return;
    objref r(object);
    const bool valid=r.valid() && actor.identity==LocalWireId(object);
    switch(number) {
    case 0x0d:
        if(valid && shape>=0 && shape!=r.type()) {
            bool wasLight=gItemTypeInfo[shape].light, isLight=gItemTypeInfo[r.type()].light;
            if(wasLight!=isLight) LocalEffectOn(isLight?"ignite":"douse",spell,object);
            else if(spell==17 || spell==56) LocalEffectOn("transform",spell,object);
        } break;
    case 0x13: if(spell==39 && valid && frame!=r.frame()) LocalEffectOn("unlock",spell,object); break;
    case 0x15: if(spell==16 && valid && quality!=Item_getQuality(&r)) LocalEffectOn("disarm",spell,object); break;
    case 0x1d: if(spell==41 || spell==48) LocalEffectOn(spell==41?"dance":"fear",spell,object); break;
    case 0x25: if(onMap && arg(ret+1,1)!=0 && (spell==42 || spell==16)) LocalEffectAt("dispel",spell,0,x,y,z); break;
    case 0x26:
        if(valid && arg(ret+1,1)!=0 && IsOnMap(&r) && (spell==8 || spell==51))
            LocalEffectOn(spell==51?"flamestrike":"create",spell,object);
        break;
    case 0x3e: if(valid && (x!=int(Item_getX(r)) || y!=int(Item_getY(r)))) {
        LocalEffectAt("travel",spell,0,x,y,z);LocalEffectOn("travel",spell,object);
        } break;
    case 0x56: LocalEffectOn("timestop",spell,subject);break;
    case 0x57: LocalEffectOn("light",spell,subject);break;
    case 0x59: LocalEffectOn("tremor",spell,subject);break;
    case 0x5f: LocalEffectOn("mark",spell,object);break;
    case 0x95: remoteSpell=spell;break;
    }
}
