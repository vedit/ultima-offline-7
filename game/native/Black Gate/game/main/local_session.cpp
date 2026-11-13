// Local Steam FORGE session. Only the game thread touches engine state.
#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#include <string>
#include <sstream>
#include <vector>
#include <map>
#include <algorithm>
#include "u7port.h"
#include "objref.h"
#include "coord.h"
#include "item.h"
#include "type.h"
#include "gtimer.h"
#include "camera.h"
#include "u7npc.h"
#include "mainctrl.h"
#include "itemcmd.h"
#include "savegame.h"
#include "use.h"
#include "weight.h"
#include "itemovr1.h"
#include "look.h"
#include "combat.h"
extern void OpenAndLoopItemDialog(objref);
#include "usehook.h"
#include "cast.h"
#include "legalmov.h"
#include "u7ibuf.h"
#include "bogus.h"
#include "itembuf.h"
#include "equip.h"
#include "ready.h"
#include "wihh.h"
#include "keywords.h"
#include "flags.h"
#include "random.h"
#include "plat.h"
#include "local_session.h"

extern objref AvatarRef;
extern "C" uint8_t AvatarDontMove;
static HANDLE channel = INVALID_HANDLE_VALUE;
static int generation = 1, lastSeq, opened, mode, face;
static std::string words, result = "ready", inFlight;
static std::vector<std::string> choices;
static std::map<int, std::string> history;
static bool connected, started;
static bool retired[65536];
// The engine recycles 16-bit offsets while the Avatar travels between regions.
static uint16_t lifetimes[65536];
static int wireId(int handle) {
    return handle && getenv("TRINSIC_TOWN") ? (int(lifetimes[handle])<<16) | handle : handle;
}
void LocalFreed(short handle) {
    if(!LocalEnabled()) return;
    auto id=(uint16_t)handle;
    if(getenv("TRINSIC_TOWN") && lifetimes[id]<8191) ++lifetimes[id];
    else retired[id]=true;
}
void LocalBeforeStep() {
    static bool initialized=false;
    if(!initialized){memset(retired,0,sizeof retired); memset(lifetimes,0,sizeof lifetimes); initialized=true;}
    if(!getenv("TRINSIC_READY") || !LocalEnabled() || started) return;
    while(!started){LocalPoll(nullptr); plat_yield();}
}
static int chosen = -1;
static int inputValue, numberLow, numberHigh, numberStep;
static int deferredUse;
static bool town() { return getenv("TRINSIC_TOWN") != nullptr; }
static unsigned long promptId;
void LocalPartyObservation() {
    if(!getenv("TRINSIC_TRACE")) return;
    static int px=-1,py=-1,pz=-1;
    objref iolo; GetNpcIbo(&iolo,1);
    if(!iolo.valid() || !IsOnMap(&iolo)) return;
    int x=Item_getX(iolo),y=Item_getY(iolo),z=iolo.z();
    if(x!=px || y!=py || z!=pz) {
        fprintf(stderr,"iolo %u %d %d %d\n",GameTime.ticks,x,y,z);
        px=x;py=y;pz=z;
    }
}

bool LocalEnabled() { return getenv("TRINSIC_PIPE") != nullptr; }

static std::string hexText(const std::string &s) {
    static const char digits[] = "0123456789abcdef";
    std::string v;
    for (unsigned char c : s) {v += digits[c >> 4]; v += digits[c & 15];}
    return v;
}

static void reply(const std::string &s) {
    DWORD sent;
    if (!WriteFile(channel,s.data(),static_cast<DWORD>(s.size()),&sent,nullptr)) {
        DisconnectNamedPipe(channel);
        connected = false;
    }
}

static bool presentShape(unsigned type) {
    switch(type) {
    case 873: case 994: case 800: case 522: case 270: case 376: case 432: case 433: return true;
    default: return false;
    }
}

// Portable shapes represented by the room's ClassicUO artwork.
static bool portableShape(int shape) {
    switch(shape) {
    case 178: case 377: case 569: case 574: case 587: case 594: case 595:
    case 599: case 616: case 627: case 628: case 641: case 644: case 701: case 994: return true;
    default: return false;
    }
}

static int wornSlot(objref item) {
    for(int slot=0;slot<12;++slot)
        if(GetItemInSlot(AvatarRef,slot).off==item.off) return slot;
    return -1;
}

struct Row { int id,shape,frame,x,y,z,parent,npc,dir; int amount=1, slot=-1; };
enum { Movable = 1, Container = 2, Usable = 4, Stack = 8 };
static int capabilities(const Row &r) {
    if(r.npc>=0) return 0;
    objref item((short)r.id);
    const auto &type=gItemTypeInfo[r.shape];
    int flags=item.isContainer() ? Container : 0;
    if(type.typeClass==TYPE_CLASS_QUANTITY) flags|=Stack;
    if(type.door || r.shape==211 || r.shape==270 || r.shape==376 || r.shape==641 || r.shape==797 ||
       r.shape==290 || r.shape==291 || r.shape==322 || r.shape==372) flags|=Usable;
    if(!(r.parent==(uint16_t)AvatarRef.off && r.shape==801) &&
       type.typeClass!=TYPE_CLASS_NONE && type.typeClass!=TYPE_CLASS_EGG && type.typeClass!=TYPE_CLASS_BARGE &&
       type.typeClass!=TYPE_CLASS_HUMAN && type.typeClass!=TYPE_CLASS_MONSTER && Item_getWeight(item)!=0)
        flags|=Movable;
    return flags;
}
static bool movable(const Row &r) {
    return town() ? (capabilities(r)&Movable)!=0 : portableShape(r.shape);
}

static std::vector<Row> inspect() {
    std::vector<Row> rows;
    int actorCount=town() ? NpcRecordCount+ExtraNpcRecordCount : 13;
    for(int n=0;n<actorCount;++n) {
        if(!town() && n!=0 && n!=1 && n!=2 && n!=12) continue;
        objref ref; GetNpcIbo(&ref,n);
        if(!ref.valid() || !IsOnMap(&ref)) continue;
        // The stable egg allocates its horse from the extra creature slots.
        if(n>=NpcRecordCount && ref.type()!=727) continue;
        if(town() && (abs(Item_getX(ref).value-Item_getX(AvatarRef).value)>36 || abs(Item_getY(ref).value-Item_getY(AvatarRef).value)>36)) continue;
        rows.push_back({(uint16_t)ref.off,ref.type(),ref.ptr()->typeFrame>>10,Item_getX(ref),Item_getY(ref),ref.z(),0,n,GetNpcBufferForIbo(&ref)->facing()});
    }
    for(objref gear=GetContainedItem(&AvatarRef);gear.valid();gear=gear.next()) {
        rows.push_back({(uint16_t)gear.off,gear.type(),gear.ptr()->typeFrame>>10,0,0,0,(uint16_t)AvatarRef.off,-1,0,Item_getQuantity(&gear),wornSlot(gear)});
        if(gear.type()!=801) continue;
        for(objref item=GetContainedItem(&gear);item.valid();item=item.next())
            rows.push_back({(uint16_t)item.off,item.type(),item.ptr()->typeFrame>>10,0,0,0,(uint16_t)gear.off,-1,0,Item_getQuantity(&item)});
    }
    for(int slot=0; slot<4; ++slot) {
        if(LoadedRegions[slot]==255) continue;
        for(auto &line:ChunkItemLists[slot]) for(short head:line) {
            for(objref r(head); r.valid(); r=r.next()) {
                if(town()) {
                    if(r.isNpc() || abs(Item_getX(r).value-Item_getX(AvatarRef).value)>36 || abs(Item_getY(r).value-Item_getY(AvatarRef).value)>36) continue;
                } else if(!presentShape(r.type()) && !portableShape(r.type())) continue;
                if(!presentShape(r.type()) && (abs(Item_getX(r).value-Item_getX(AvatarRef).value)>36 || abs(Item_getY(r).value-Item_getY(AvatarRef).value)>36)) continue;
                rows.push_back({(uint16_t)r.off,r.type(),r.ptr()->typeFrame>>10,Item_getX(r),Item_getY(r),r.z(),0,-1,0,Item_getQuantity(&r)});
                if(r.type()!=800 && r.type()!=522 && !(town() && r.isContainer())) continue;
                for(objref child=GetContainedItem(&r);child.valid();child=child.next())
                    rows.push_back({(uint16_t)child.off,child.type(),child.ptr()->typeFrame>>10,0,0,0,(uint16_t)r.off,-1,0,Item_getQuantity(&child)});
            }
        }
    }
    // Ancestors of an open nested bag must precede its contents on the wire.
    if(town() && opened) {
        std::vector<objref> chain;
        for(objref c((short)opened);c.valid() && c!=AvatarRef;c=Item_getContainer(&c))
            chain.push_back(c);
        for(auto it=chain.rbegin();it!=chain.rend();++it) {
            if(!it->isContainer()) continue;
            for(objref child=GetContainedItem(&*it);child.valid();child=child.next()) {
                int id=(uint16_t)child.off;
                if(std::none_of(rows.begin(),rows.end(),[&](const Row &r){return r.id==id;}))
                    rows.push_back({id,child.type(),child.ptr()->typeFrame>>10,0,0,0,(uint16_t)it->off,-1,0,Item_getQuantity(&child)});
            }
        }
    }
    rows.erase(std::remove_if(rows.begin(),rows.end(),[](const Row &r){return retired[r.id] || (r.parent && retired[r.parent]);}),rows.end());
    return rows;
}

static bool reachable(objref item) {
    objref owner=GetOuterContainer(item,AvatarRef);
    return owner==AvatarRef || CanAvatarReach(owner,0);
}

static std::string snapshot(int seq,const std::string &outcome) {
    std::ostringstream s;
    s<<"S "<<seq<<" "<<generation<<" "<<GameTime.ticks<<" "<<lastSeq<<" "<<outcome<<" "<<gCamera.getCenterX().value<<" "<<gCamera.getCenterY().value<<" "<<wireId(opened)<<" "<<mode<<" "<<promptId<<" "<<face<<" "<<GetRandomSeed()<<" "<<int(GameFlags.get(60))<<" "<<int(GameFlags.get(72))<<"\n";
    auto avatar=GetNpcBufferForIbo(&AvatarRef);
    s<<"N "<<hexText(std::string(avatar->name,strnlen(avatar->name,sizeof avatar->name)))<<"\n";
    s<<"V "<<int(Npc_getStrength(&AvatarRef))<<" "<<int(Npc_getDexterity(&AvatarRef))<<" "<<int(Npc_getIntelligence(&AvatarRef))<<" "<<int(avatar->hitPoints)<<" "<<int(avatar->mana)<<" "<<int(avatar->magic)<<"\n";
    if(town()) {
        const int weight=DetermineWeightOfContents(AvatarRef);
        s<<"P "<<int((int8_t)Item_getHitPoints(&AvatarRef))<<" "<<int(avatar->combat)<<" "<<avatar->experience
         <<" "<<Npc_getLevel(&AvatarRef)<<" "<<int(avatar->training)<<" "<<(weight+9)/10
         <<" "<<2*int(Npc_getStrength(&AvatarRef))<<" "<<CountHeldItems(0,AvatarRef,644,255,255)
         <<" "<<int(IsAvatarInCombat()!=0)<<" "<<int((avatar->typeFlagsHigh&2)==0)<<" "<<avatar->status
         <<" "<<int(IsFamished(&AvatarRef)||IsHungry(&AvatarRef)||IsStarving(&AvatarRef))<<"\n";
    }
    if(opened) {
        objref owner((short)opened);
        if(owner.isBody()) for(objref child=GetContainedItem(&owner);child.valid();child=child.next()){
            const char *name=GetItemName((uint16_t)child.off);
            s<<"I "<<child.type()<<" "<<int(Item_getQuantity(&child))<<" "<<hexText(name ? name : "item")<<"\n";
        }
    }
    for(const auto &row:inspect()) { s<<"E "<<wireId(row.id)<<" "<<row.shape<<" "<<row.frame<<" "<<row.x<<" "<<row.y<<" "<<row.z<<" "<<wireId(row.parent)<<" "<<row.npc<<" "<<row.dir<<" "<<row.amount<<" "<<row.slot; if(town()) s<<" "<<capabilities(row); s<<"\n"; }
    if(town()) {
        s<<"Q"; for(int flag : {60,61,62,64,66,67,72,90}) s<<" "<<int(GameFlags.get(flag)); s<<"\n";
        if(mode==3) s<<"D "<<numberLow<<" "<<numberHigh<<" "<<numberStep<<"\n";
    }
    s<<"T "<<hexText(words)<<"\n";
    for(auto &choice:choices) s<<"A "<<hexText(choice)<<"\n";
    return s.str();
}

void LocalSpeak(const char *text,int portrait) {
    if(!LocalEnabled()) return;
    face=portrait;
    if(words.size()>4000) words.clear();
    if(!words.empty()) words+=" ";
    words+=text;
}
int LocalNumber(int low,int high,int step) {
    numberLow=low; numberHigh=high; numberStep=std::max(1,step); mode=3; ++promptId;
    while(mode==3){ LocalPoll(nullptr); plat_yield(); }
    words.clear();
    return inputValue;
}
short LocalTarget() {
    mode=4; ++promptId;
    while(mode==4){ LocalPoll(nullptr); plat_yield(); }
    return (short)inputValue;
}
void LocalOpened(short object) { opened=(uint16_t)object; }
bool LocalChestOpen() { return opened!=0; }
static void poll(uint8_t *steps);
void LocalPrompt(bool answers) {
    if(!LocalEnabled()) return;
    ++promptId; mode=answers?2:1; choices.clear(); chosen=-1;
    if(answers) {
        Answer *a=nullptr;
        while(OfferedAnswers.next(&a)) choices.emplace_back(a->text);
    }
    }
bool LocalAnswered(bool answers) {
    if(!LocalEnabled()) return false;
    poll(nullptr);
    if(chosen<0) return false;
    if(answers) snprintf(ChosenAnswer,ANSWER_SIZE,"%s",choices.at(chosen).c_str());
    choices.clear(); words.clear(); mode=0; chosen=-1;
    return true;
}
void LocalRecovery(short object,int status,int x,int y) {
    if(!getenv("TRINSIC_TRACE")) return;
    objref r(object);
    fprintf(stderr,"recovery %u %d %d camera %d %d before %d %d after %d %d\n",GameTime.ticks,(uint16_t)object,status,gCamera.getCenterX().value,gCamera.getCenterY().value,x,y,(int)Item_getX(r),(int)Item_getY(r));
}

static bool accessible(const Row &r) {
    if(!movable(r) || r.npc>=0) return false;
    if(r.parent && r.parent!=(uint16_t)AvatarRef.off) {
        objref parent((short)r.parent);
        bool pack=parent.type()==801 && Item_getContainer(&parent)==AvatarRef;
        if(!pack && (r.parent!=opened || (!town() && parent.type()!=800))) return false;
    }
    return reachable(objref((short)r.id));
}

static int equipSlot(int shape) {
    // Only gear with a matching wearable ClassicUO graphic in this room.
    switch(shape) {
    case 569: case 574: case 587: case 594: case 595: case 599: case 701:
        return ReadyRecords.get(ReadyLookup.get(shape))->slot;
    default: return -1;
    }
}

static void restoreItem(objref item,const Row &r) {
    if(!r.parent) PlaceItemDirect(&item,Coord(r.x),Coord(r.y),r.z);
    else {
        PlaceItemInContainer(&item,objref((short)r.parent));
        if(r.slot>=0) EquipItem(item,AvatarRef,r.slot,0);
    }
}

// Move one selected quantity as a transaction. A split clone remains detached
// until placement succeeds. A failed drop restores the original stack in place.
static std::string transfer(const Row &src,const Row *dst,int requested,int x,int y,int z) {
    if(!accessible(src)) return "unreachable";
    int amount=requested<0?src.amount:requested;
    bool counted=(capabilities(src)&Stack)!=0;
    if(counted && (amount<=0 || amount>src.amount)) return "amount";
    objref original((short)src.id),item=original,target(dst?(short)dst->id:0);
    bool merge=dst && (capabilities(*dst)&Stack);
    if(dst) {
        if(src.id==dst->id) return "same";
        if(merge) {
            if(!counted || !accessible(*dst) || src.shape!=dst->shape ||
               (!HasQuantityFrames(src.shape) && src.frame!=dst->frame)) return "cannotstore";
            amount=std::min(amount,100-dst->amount);
            if(amount<=0)return "stackfull";
        } else {
            if(!(capabilities(*dst)&Container) || GetOuterContainer(target,original)==original) return "cannotstore";
            if(!reachable(target))return "unreachable";
            if(src.parent==dst->id && (!counted || amount==src.amount))return "same";
        }
    } else if(x<0 || y<0 || x>=3072 || y>=3072 || z<0 || z>15) return "unreachable";
    bool split=counted && amount<src.amount;
    if(split) {
        if(!CloneItem(&original)) return "unavailable";
        GetItemBeingDragged(&item);
        Item_setQuantity(item,amount,0);
        Item_setQuantity(original,src.amount-amount,0);
    } else if(!Item_detach(&item))return "unavailable";
    std::string error;
    if(merge) {
        if(!CanStackWith(&target,item))error="cannotstore";
        else {
            objref owner=GetOuterContainer(target,AvatarRef);
            if(!CanCarryWeight(owner,item))error="refused1";
            else {
                Item_setQuantity(target,dst->amount+amount,0);
                ZapDetachedItem(&item);
                return "merged";
            }
        }
    } else if(dst) {
        int code=TryToPlaceItem(target,0,0);
        if(code)error=code==3 && dst->shape!=522?"cannotstore":"refused"+std::to_string(code);
    } else {
        bool placed=CanItemMoveTo(Coord(x),Coord(y),z,item) && PlaceItem(&item,Coord(x),Coord(y),z);
        if(!placed)error="blocked";
        else if(!CanAvatarReach(item,0)){Item_detach(&item);error="unreachable";}
    }
    if(!error.empty()) {
        if(split){ZapDetachedItem(&item);Item_setQuantity(original,src.amount,0);}
        else restoreItem(item,src);
        return error;
    }
    return split?"split-"+std::to_string(wireId((uint16_t)item.off)):"ok";
}

static void poll(uint8_t *steps) {
    if(!LocalEnabled()) return;
    if(steps && deferredUse) {
        const int id=deferredUse;
        deferredUse=0;
        objref item((short)id);
        if(wireId((uint16_t)item.off)==id && item.valid() && reachable(item)) {
            if(Item_canBeOpened(item)) OpenAndLoopItemDialog(item);
            else RunUsable(1,item.off,-1);
        }
    }
    if(channel==INVALID_HANDLE_VALUE) {
        std::string name=getenv("TRINSIC_PIPE");
        if(name.empty() || name.size()>80 || name.find_first_not_of("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-")!=std::string::npos) return;
        name="\\\\.\\pipe\\"+name;
        channel=CreateNamedPipeA(name.c_str(),PIPE_ACCESS_DUPLEX|FILE_FLAG_FIRST_PIPE_INSTANCE,PIPE_TYPE_MESSAGE|PIPE_READMODE_MESSAGE|PIPE_NOWAIT|PIPE_REJECT_REMOTE_CLIENTS,1,131072,1024,0,nullptr);
        if(channel==INVALID_HANDLE_VALUE) return;
    }
    if(!connected) {
        BOOL ok=ConnectNamedPipe(channel,nullptr);
        if(!ok && GetLastError()!=ERROR_PIPE_CONNECTED) return;
        connected=true;
    }
    char buffer[400]; DWORD n=0;
    if(!ReadFile(channel,buffer,sizeof(buffer)-1,&n,nullptr)) {
        if(GetLastError()!=ERROR_NO_DATA) {DisconnectNamedPipe(channel); connected=false;}
        else {DWORD available; if(!PeekNamedPipe(channel,nullptr,0,nullptr,&available,nullptr)){DisconnectNamedPipe(channel);connected=false;}}
        return;
    }
    buffer[n]=0;
    std::istringstream input(buffer);
    int seq,gen,a=0,b=0; std::string op;
    if(!(input>>seq>>gen>>op)) {reply("ERROR syntax\n"); return;}
    input>>a>>b;
    if(op=="SYNC") { reply(snapshot(0,"sync")); return; }
    if(gen!=generation) { reply(snapshot(seq,"stale"));return; }
    if(auto it=history.find(seq);it!=history.end()){reply(snapshot(seq,it->second));return;}
    if(seq!=lastSeq+1){reply(snapshot(seq,"sequence"));return;}
    lastSeq=seq;
    std::string outcome="ok";
    auto rows=inspect();
    auto findRow=[&](int id)->const Row*{for(const auto &r:rows) if(wireId(r.id)==id)return &r;return nullptr;};
    const Row *r=findRow(a),*dst=findRow(b);
    if(r && (op=="USE" || op=="LOOK" || op=="EQUIP" || op=="MOVE" || op=="GROUND")) a=r->id;
    if(dst && (op=="TARGET" || op=="EQUIP" || op=="MOVE")) b=dst->id;
    if(op=="BEGIN" && getenv("TRINSIC_READY")) started=true;
    else if(op=="ANSWER" && mode && a==(int)promptId && b>=0 && (mode==1 ? b==0 : b<(int)choices.size())) chosen=b;
    else if(op=="NUMBER" && mode==3 && a==(int)promptId && b>=numberLow && b<=numberHigh && (b-numberLow)%numberStep==0) { inputValue=b; mode=0; }
    else if(op=="TARGET" && mode==4 && a==(int)promptId && (!b || (dst && reachable(objref((short)b))))) { inputValue=b; mode=0; }
    else if(mode || (opened && !(town() && op=="USE" && r && r->parent==opened && (capabilities(*r)&(Container|Usable))) && op!="CLOSE" && op!="MOVE" && op!="GROUND" && op!="EQUIP" && op!="LOOK" && op!="WAR")) outcome="modal";
    else if(op=="STEP" && steps && a>=0 && a<8 && !AvatarDontMove) {
        int x=Item_getX(AvatarRef),y=Item_getY(AvatarRef);
        static const int keys[]={0x148,0x149,0x14d,0x151,0x150,0x14f,0x14b,0x147};
        ProcessKey(keys[a],0,0,steps);
        if(x==Item_getX(AvatarRef) && y==Item_getY(AvatarRef)) outcome="blocked";
    } else if(op=="TURN" && a>=0 && a<8 && !AvatarDontMove) SetNPCFacing(AvatarRef.off,a);
    else if(op=="USE" && r) {
        objref target((short)a);
        if(town() && r->parent && !reachable(target)) outcome="unreachable";
        else if(town() && opened && r->parent==opened && (capabilities(*r)&(Container|Usable)) && target.type()!=522) {
            deferredUse=wireId(a); opened=0;
        } else if(target.type()==522) outcome=CanAvatarReach(target,0)?"locked":"unreachable";
        else if(r->npc>=0 || target.type()==800 || presentShape(target.type()) || (town() && (capabilities(*r)&(Container|Usable)))) {
            // Modal input can arrive before Use returns. Acknowledge dispatch first.
            history[seq]="using"; while(history.size()>12)history.erase(history.begin()); reply(snapshot(seq,"using"));
            if(town() && r->parent) {
                if(Item_canBeOpened(target)) OpenAndLoopItemDialog(target);
                else RunUsable(1,target.off,-1);
            } else Use(&target,Item_getX(target),Item_getY(target),target.z());
            return;
        } else outcome="invalid";
    } else if(op=="WAR" && town() && (a==0 || a==1)) {
        if(bool(IsAvatarInCombat())!=bool(a)) {
            if(a) BeginCombat(); else BreakOffCombat();
        }
    } else if(op=="LOOK" && r && town()) {
        char name[80]={};
        ProduceItemDisplayName(name,r->shape,(capabilities(*r)&Stack)?r->amount:0,r->frame);
        outcome="name-"+hexText(name);
    } else if(op=="LOOK" && r) {
        const char *name=GetItemName((uint16_t)a);
        if(name && *name) outcome="name-"+hexText(name);
    } else if(op=="EQUIP" && r && dst && dst->npc==0) {
        objref item((short)a);
        int slot=equipSlot(r->shape);
        if(!accessible(*r)) outcome="unreachable";
        else if(slot<0) outcome="notwearable";
        else if(r->slot>=0) outcome="same";
        else {
            // The native game allows a torch in either hand. The UO torch art uses the off hand.
            if(r->shape==595 || r->shape==701) slot=2;
            if(!CanEquipInSlot(item,AvatarRef,slot,0)) outcome="occupied";
            else if(!Item_detach(&item)) outcome="unavailable";
            else if(!CanCarryWeight(AvatarRef,item)) {restoreItem(item,*r);outcome="refused1";}
            else {
                PlaceItemInContainer(&item,AvatarRef);
                if(EquipItem(item,AvatarRef,slot,0)) MarkItemOkayToTake(item);
                else {Item_detach(&item);restoreItem(item,*r);outcome="occupied";}
            }
        }
    } else if(town() && op=="MOVE" && r && dst) {
        int px=-1,py=-1,amount=-1;input>>px>>py>>amount;
        outcome=transfer(*r,dst,amount,0,0,0);
    } else if(town() && op=="GROUND" && r) {
        int y=-1,z=-1,amount=-1;input>>y>>z>>amount;
        outcome=transfer(*r,nullptr,amount,b,y,z);
    } else if(op=="MOVE" && r && movable(*r) && dst && ((town() && (capabilities(*dst)&Container)) || dst->shape==800 || dst->shape==522 || (dst->shape==801 && dst->parent==(uint16_t)AvatarRef.off))) {
        objref item((short)a),target((short)b),from((short)r->parent);
        if(!accessible(*r) || !reachable(target)) outcome="unreachable";
        else if(GetOuterContainer(target,item)==item) outcome="cannotstore";
        else if(from==target) outcome="same";
        else {
            
            if (!Item_detach(&item)) { history[seq]="unavailable"; reply(snapshot(seq,"unavailable")); return; }
            int code=TryToPlaceItem(target,0,0);
            if(code) {
                restoreItem(item,*r);
                outcome=code==3 && dst->shape!=522?"cannotstore":"refused"+std::to_string(code);
            }
        }
    } else if(op=="GROUND" && r && movable(*r)) {
        int y=-1,z=-1; input>>y>>z;
        objref item((short)a), from((short)r->parent);
        if(b<0 || y<0 || b>=3072 || y>=3072 || z<0 || z>15 || !accessible(*r))
            outcome="unreachable";
        else if(!Item_detach(&item)) outcome="unavailable";
        else {
            bool placed=CanItemMoveTo(Coord(b),Coord(y),z,item) && PlaceItem(&item,Coord(b),Coord(y),z);
            if(!placed || !CanAvatarReach(item,0)) {
                if(placed) Item_detach(&item);
                restoreItem(item,*r);
                outcome=placed?"unreachable":"blocked";
            }
        }
    } else if(op=="PREPARE" && getenv("TRINSIC_PREPARE") && !strcmp(getenv("TRINSIC_PREPARE"),"room")) {
        const int placement[][5]={{994,1079,2185,987,2215},{800,962,2221,987,2216},{522,1050,2278,988,2216}};
        for(auto &v:placement) {
            auto it=std::find_if(rows.begin(),rows.end(),[&](const Row &r){return r.shape==v[0] && r.x==v[1] && r.y==v[2];});
            if(it==rows.end()){outcome="missing";break;}
            objref item((short)it->id);
            if(!Item_forceMove(&item,Coord(v[3]),Coord(v[4]),0)){outcome="placement";break;}
        }
    } else if(op=="SAVE") SaveGameFiles.saveGame(0,(char*)"Trinsic local",0);
    else if(op=="LOAD") {
        char title[80]={}; SaveGameFiles.getSaveTitle(0,title);
        if(!*title) outcome="empty";
        else {SaveGameFiles.restoreGame(0);++generation;memset(retired,0,sizeof(retired));memset(lifetimes,0,sizeof lifetimes);history.clear();lastSeq=0;opened=0;words.clear();}
    } else if(op=="CLOSE") opened=0;
    else if(op=="QUIT") {reply(snapshot(seq,"bye"));plat_exit(0);return;}
    else outcome="invalid";
    auto response=snapshot(seq,outcome);
    if(gen==generation){history[seq]=outcome;while(history.size()>12)history.erase(history.begin());}
    reply(response);
}
void LocalPoll(uint8_t *steps){poll(steps);}


