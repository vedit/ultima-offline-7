extern int LocalActiveSave();
extern void LocalSaveWorld();
// Explicit development operations on the original engine. No alternate gameplay rules.
#include "u7port.h"
#include "local_debug.h"
#include "local_session.h"
#include "objref.h"
#include "item.h"
#include "itemovr1.h"
#include "itembuf.h"
#include "coord.h"
#include "type.h"
#include "npcref.h"
#include "u7npc.h"
#include "use.h"
#include "look.h"
#include "u7ibuf.h"
#include "weight.h"
#include "voolook.h"
#include "u7manage.h"
#include "bltshape.h"
#include "weapons.h"
#include "monsters.h"
#include "equip.h"
#include "ready.h"
#include "wihh.h"
#include "legalmov.h"
#include "collide.h"
#include "spell.h"
#include "cast.h"
#include "daze.h"
#include "death.h"
#include "bodies.h"
#include "actutil.h"
#include "sche.h"
#include "party.h"
#include "gtimer.h"
#include "weather.h"
#include "worldpal.h"
#include "savegame.h"
#include <algorithm>
#include <cctype>
#include <cstdlib>
#include <cstring>
#include <map>
#include <set>
#include <vector>
#include <deque>
#include <sstream>

extern objref AvatarRef;
namespace {
std::set<int> made, genericActors;
std::string payload;
std::map<int,std::string> replies;
std::deque<std::string> history;
std::string hex(const std::string &s) { if(s.empty())return "-";static const char digits[]="0123456789abcdef";std::string out;for(unsigned char c:s){out+=digits[c>>4];out+=digits[c&15];}return out; }
bool unhex(const std::string &s,std::string &out) {out.clear();if(s=="-")return true;if(s.size()%2 || s.size()>160)return false;for(size_t i=0;i<s.size();i+=2){auto digit=[](char c){if(c>='0'&&c<='9')return c-'0';c=(char)tolower((unsigned char)c);return c>='a'&&c<='f'?c-'a'+10:-1;};int a=digit(s[i]),b=digit(s[i+1]);if(a<0||b<0)return false;out+=(char)(a*16+b);}return true;}
std::string lower(std::string s){for(char &c:s)c=(char)tolower((unsigned char)c);return s;}
bool word(const std::string &text,const char *value){size_t pos=0,length=strlen(value);while((pos=text.find(value,pos))!=std::string::npos){if((pos==0||!isalnum((unsigned char)text[pos-1]))&&(pos+length==text.size()||!isalnum((unsigned char)text[pos+length])))return true;pos+=length;}return false;}
objref resolve(int id) {if(id<=0 || id>0x1fffffff)return objref(0);short raw=(short)id;if(LocalWireId(raw)!=id)return objref(0);if(made.count(id))return objref(raw);return objref(LocalDebugResolve(id));}
objref pack(){for(objref r=GetContainedItem(&AvatarRef);r.valid();r=r.next())if(r.type()==801)return r;return objref(0);}
bool coordinate(int x,int y,int z){return x>=0&&x<3072&&y>=0&&y<3072&&z>=0&&z<=15;}
bool actorShape(int s){return s>=0&&s<1024&&(ItemTypeClassFlags[gItemTypeInfo[s].typeClass]&CLASS_NPC)!=0;}
// Dedicated body shapes include frame0 during native death animation; food377
// shares ordinary meat frames and only its headless corpse frame is protected.
bool corpseArt(int s,int f){return s==400||s==414||s==778||s==892||s==762||(s==377&&(f&31)==12);}
std::string unsupported(int s,int f=0){int c=gItemTypeInfo[s].typeClass;if(corpseArt(s,f))return "Native corpse artwork; use native death/resurrection";if(actorShape(s))return "Use the creature browser";if(c>=1&&c<=6 || c==8 || c==11)return "";return "Internal, structural or vehicle object";}
std::string name(int s,int f){char text[256]={};ProduceItemDisplayName(text,s,1,f);return *text?text:"Unnamed shape "+std::to_string(s);}
std::string category(int s,const std::string &n,bool creature){std::string l=lower(n);auto has=[&](const char *v){return word(l,v);};if(creature){if(has("skeleton")||has("ghost")||has("liche")||has("zombie"))return "Undead";if(gItemTypeInfo[s].typeClass==TYPE_CLASS_HUMAN)return "Humanoid";if(has("horse")||has("rat")||has("cat")||has("dog")||has("bird")||has("sheep")||has("cow")||has("fox")||has("deer")||has("wolf")||has("bear")||has("rabbit")||has("snake"))return "Animal";return "Monster";}
 if(s==842)return "Reagent";if(gItemTypeInfo[s].typeClass==8||gItemTypeInfo[s].typeClass==11)return "Magic";if(WeaponLookup.get(s))return "Weapon";if(ArmorLookup.get(s))return "Armour";if(ReadyLookup.get(s))return "Clothing";if(gItemTypeInfo[s].typeClass==0||gItemTypeInfo[s].typeClass==14||gItemTypeInfo[s].typeClass==15)return "Architecture";if(!unsupported(s).empty())return "Internal";if(ItemTypeClassFlags[gItemTypeInfo[s].typeClass]&CLASS_CONTENTS)return "Container";if(has("food")||has("bread")||has("meat")||has("wine")||has("ale")||has("fruit")||has("fish"))return "Food";if(has("book")||has("scroll")||has("map"))return "Book";if(has("key")||has("hammer")||has("tongs")||has("torch")||has("bucket")||has("rake")||has("shovel"))return "Tool";if(has("chair")||has("table")||has("bed")||has("desk")||has("bench"))return "Furniture";return "Other";}
struct Entry {int shape,frame;bool creature,supported;std::string category,name,reason;};
std::vector<Entry> catalog;
void loadCatalog(){if(!catalog.empty())return;for(int s=0;s<1024;s++){int count=std::min(64,(int)ShapeManager_getFrameCount(&gShapeManager,s));bool creature=actorShape(s);for(int f=0;f<count;f++){if(s>=150 && gShapeManager.isFrameEmpty(s,f))continue;std::string n=name(s,f),reason=creature?"":unsupported(s,f);catalog.push_back({s,f,creature,reason.empty(),category(s,n,creature),n,reason});}}}
bool validFrame(int s,int f){if(s<0||s>=1024||f<0||f>=64)return false;loadCatalog();return std::any_of(catalog.begin(),catalog.end(),[&](const Entry &e){return e.shape==s&&e.frame==f;});}
void inspect(objref r,std::ostringstream &out){int id=LocalWireId(r.off),npc=r.isNpc()?Item_getNpcNumber(&r):-1;objref owner=IsOnMap(&r)?objref(0):Item_getContainer(&r);const char *display=GetItemName((uint16_t)r.off);out<<"DX "<<id<<" "<<hex(display?display:name(r.type(),r.frame()))<<" "<<r.type()<<" "<<r.frame()<<" "<<(IsOnMap(&r)?int(Item_getX(r)):0)<<" "<<(IsOnMap(&r)?int(Item_getY(r)):0)<<" "<<r.z()<<" "<<LocalWireId(owner.off)<<" "<<int(Item_getQuantity(&r))<<" "<<Item_getWeight(r)<<" "<<int(gItemTypeInfo[r.type()].typeClass)<<" "<<int(Item_getQuality(&r))<<" "<<int(Item_getQualityFlags(&r))<<" "<<LocalDebugCapabilities(r.off)<<" "<<npc<<" "<<made.count(id)<<"\n";
 if(npc>=0){auto n=GetNpcBufferForIbo(&r);out<<"DS "<<id<<" "<<int(n->strength)<<" "<<int(n->dexterity)<<" "<<int(n->intelligence)<<" "<<int(n->combat)<<" "<<int(n->magic)<<" "<<int((int8_t)n->hitPoints)<<" "<<int(n->mana)<<" "<<n->experience<<" "<<int(n->training)<<" "<<int(n->food)<<" "<<int(Npc_getStrength(&r))<<" "<<int(Npc_getDexterity(&r))<<" "<<int(Npc_getIntelligence(&r))<<" "<<int(Npc_getCombat(&r))<<" "<<Npc_getLevel(&r)<<" "<<int(Npc_getStrength(&r))<<" "<<int(n->magic)<<" "<<n->status<<" "<<int(n->typeFlagsHigh)<<"\n";}
 if(gItemTypeInfo[r.type()].typeClass==8){std::string bits;int count=0;for(int i=0;i<72;i++){bool has=DoesSpellbookHaveSpell(&r,i)!=0;bits+=has?'1':'0';count+=has;}out<<"DB "<<id<<" "<<int(GetSpellbookBookmark(&r))<<" "<<count<<" "<<bits<<"\n";}
 if(gItemTypeInfo[r.type()].typeClass==11)out<<"DV "<<id<<" "<<int(r.cellX())<<" "<<int(r.cellY())<<" "<<int(r.region())<<" "<<int(Item_getQuality(&r))<<"\n";
}
bool generic(objref r){return r.isNpc()&&r!=AvatarRef&&!Item_isPartyMember(r)&&(Item_getNpcNumber(&r)>=NpcRecordCount||genericActors.count(LocalWireId(r.off)));}
int records(int shape){return GetItemRecordCount(ItemTypeClassFlags[gItemTypeInfo[shape].typeClass]);}
// Reserve for every possible original equipment roll before consuming randomness.
int creatureRecords(int shape){
    int needed=records(shape)+3;
    MonsterRecord monster;MonsterRecords.read(MonsterLookup.get(shape),&monster);
    if(!monster.equipment)return needed;
    struct Entry {int16_t type;uint8_t chance,count,rest[2];};
    struct List {Entry entries[10];} equipment;
    static_assert(sizeof(List)==60,"Native equipment layout");
    EquipRecords.read(monster.equipment,(EquipmentList*)&equipment);
    for(auto &entry:equipment.entries){
        if(entry.type==0)break;
        if(entry.type<0||entry.type>=1024||!entry.chance)continue;
        int count=gItemTypeInfo[entry.type].typeClass==TYPE_CLASS_QUANTITY?(entry.count+99)/100:std::max(1,int(entry.count));
        needed+=records(entry.type)*std::max(1,count);
        int index=WeaponLookup.get(entry.type);
        if(index){WeaponRecord weapon;WeaponRecords.read(index,&weapon);if(weapon.ammo>=0&&weapon.ammo<1024)needed+=records(weapon.ammo);}
    }
    return needed;
}

struct Tree {objref source;int parent,slot;};
bool tree(objref r,std::vector<Tree> &out,std::set<short> &visited,int depth,int parent,int slot,std::string &why,bool cloning){if(depth>16||out.size()>=512){why="Tree exceeds 16 levels or 512 objects";return false;}if(!visited.insert(r.off).second){why="Container cycle";return false;}if(cloning){if(r.isNpc()){if(parent!=-1||!generic(r)){why="Story actors and party members cannot be duplicated";return false;}if(IsDead(&r)){why="Use native resurrection before duplicating a dead actor";return false;}}else if(!(why=unsupported(r.type(),r.frame())).empty())return false;}
 int index=(int)out.size();out.push_back({r,parent,slot});if(r.isContainer())for(objref c=GetContainedItem(&r);c.valid();c=c.next()){int worn=-1;if(r.isNpc())for(int s=0;s<12;s++)if(GetItemInSlot(r,s).off==c.off){worn=s;if(s==1&&GetItemInSlot(r,2).off==c.off)worn=20;else if(s==6&&GetItemInSlot(r,7).off==c.off)worn=21;break;}if(!tree(c,out,visited,depth+1,index,worn,why,cloning))return false;}return true;}
// Developer-created objects are persistent; native temporary monsters deliberately
// leave non-resurrectable corpses and are removed on death/unload.
void registerTree(objref r,std::ostringstream &out){std::vector<Tree> t;std::set<short> seen;std::string why;tree(r,t,seen,1,-1,-1,why,false);out<<"DN";for(auto &e:t){Item_clearTemporary(&e.source);int id=LocalWireId(e.source.off);made.insert(id);out<<" "<<id;if(e.source.isNpc())genericActors.insert(id);}out<<"\n";inspect(r,out);}
void rollback(std::vector<objref> &created){for(auto it=created.rbegin();it!=created.rend();++it)if(it->valid())Item_delete(&*it);}
bool destination(int d,int &x,int &y,int &z,TypeFrame tf,objref &owner,std::string &why){
    owner=d==-1?pack():d>0?resolve(d):objref(0);
    if(d!=0){
        if(!owner.valid()){why="Destination is stale or unavailable";return false;}
        if(owner.isContainer()){
            if(owner.isNpc()&&IsDead(&owner)){why="Select a living actor inventory";return false;}
            return true;
        }
        const auto &support=gItemTypeInfo[owner.type()];
        if(!IsOnMap(&owner)||!support.solid||!support.height||support.door||support.field){why="Target is neither a container nor a native supporting surface";return false;}
        x=Item_getX(owner);y=Item_getY(owner);z=owner.z()+support.height;
        owner=objref(0);
    }
    if(!coordinate(x,y,z)){why="Coordinates out of range";return false;}
    // Native footprint values are inclusive extents; the box API accepts counts.
    int w=GetFootprintX(tf)+1,h=GetFootprintY(tf)+1,height=std::max(1,int(gItemTypeInfo[tf.type()].height));
    if(IsBoxBlockedAt(x,y,z,w,h,height)||!IsTypeSupportedAt(x,y,z,tf)){why="Destination is blocked or has no native support";return false;}
    return true;
}
bool place(objref &r,objref owner,int x,int y,int z){return owner.valid()?PlaceDraggedInContainer(&r,owner)!=0:PlaceItem(&r,x,y,z)!=0;}
// Copies explicit base attributes only. Queued conditions and AI state start fresh.
void copyStats(objref source,objref copy){
    auto original=GetNpcBufferForIbo(&source);
    struct Attributes {uint8_t strength,dexterity,intelligence,combat,magic,mana,hp,training,food;int32_t experience;uint16_t status;};
    Attributes n={original->strength,original->dexterity,original->intelligence,original->combat,original->magic,original->mana,original->hitPoints,original->training,original->food,original->experience,original->status};
    auto c=GetNpcBufferForIbo(&copy);
    c->strength=n.strength;c->dexterity=n.dexterity;c->intelligence=n.intelligence;c->combat=n.combat;
    c->magic=n.magic;c->mana=n.mana;c->hitPoints=n.hp;c->experience=n.experience;c->training=n.training;c->food=n.food;
    c->setAlignment((n.status>>3)&3);c->setInitialAlignment((n.status>>5)&3);c->status=(c->status&0x78)|(n.status&7);
    c->typeFlagsHigh=0;c->face=0;memset(c->name,0,sizeof c->name);
    Item_setQualityFlags(&copy,Item_getQualityFlags(&copy)&~QUALITY_INVISIBLE);
    Npc_clearTargets(&copy);Npc_setSchedule(&copy,WORK_LOITER);
}
bool copyTree(const std::vector<Tree> &t,std::vector<objref> &created,int x,int y,int z,std::string &why){for(const auto &e:t){objref c(0),source=e.source;if(source.isNpc()){if(!CreateNpc(&c,TypeFrame(source.ptr()->typeFrame),x,y,z)){why="No native creature slots";return false;}Item_detach(&c);copyStats(source,c);}else{if(!CloneItem(&source)){why="Native item allocation failed";return false;}GetItemBeingDragged(&c);}if(!c.valid()){why="Native allocation failed";return false;}created.push_back(c);int cls=gItemTypeInfo[source.type()].typeClass;if(cls==8){ClearSpellbook(&c.off);for(int s=0;s<72;s++)if(DoesSpellbookHaveSpell(&source,s))AddSpellToSpellbook(&c,s);SetSpellbookBookmark(NPCRef(c),GetSpellbookBookmark(&source));}if(cls==11){c.cellX(source.cellX());c.cellY(source.cellY());c.region(source.region());}
 if(e.parent>=0){objref parent=created[e.parent];if(!PlaceDraggedInContainer(&c,parent)){why="Native child placement failed";return false;}}}return true;}
}

bool LocalDebugEnabled(){const char *v=getenv("TRINSIC_DEBUG");return LocalEnabled()&&v&&strcmp(v,"1")==0;}
void LocalDebugFreed(short handle){int id=LocalWireId(handle);made.erase(id);genericActors.erase(id);}
void LocalDebugReset(){made.clear();genericActors.clear();payload.clear();history.clear();replies.clear();}
void LocalDebugReplay(int sequence){auto it=replies.find(sequence);if(it!=replies.end())payload=it->second;}
std::string LocalDebugSnapshot(){if(!LocalDebugEnabled())return "";std::ostringstream s;s<<"DEVCAP 1 "<<GameTime.getHour()<<" "<<GameTime.getMinute()<<" "<<GameTime.days<<" "<<int(CurrentWeather.type)<<" "<<made.size()<<"\n"<<payload;for(auto &h:history)s<<"DH "<<hex(h)<<"\n";return s.str();}
std::string LocalDebugCommand(const std::string &op,int a,int b,std::istream &input,bool idle,int sequence){std::ostringstream out;std::string status="ok",message="Done";out<<"DQ "<<sequence<<"\n";auto fail=[&](const std::string &text,const char *code="invalid"){status=code;message=text;};
 if(!LocalDebugEnabled())fail("Development tools are disabled","disabled");
 else if(op!="DBGCAT"&&op!="DBGINSPECT"&&!idle)fail("Finish the current native interaction first","busy");
 else if(op=="DBGCAT") {std::string c,q,cat,query;input>>c>>q;if(a<0||a>1||b<0||!unhex(c,cat)||!unhex(q,query))fail("Invalid catalog query");else{loadCatalog();std::vector<const Entry*> found;std::set<std::string> categories;std::string needle=lower(query);for(auto &e:catalog){if(e.creature!=(a==1))continue;categories.insert(e.category);if(!cat.empty()&&e.category!=cat)continue;if(!needle.empty()&&lower(e.name).find(needle)==std::string::npos&&std::to_string(e.shape)!=needle)continue;found.push_back(&e);}int pages=std::max(1,(int(found.size())+39)/40);int page=std::min(b,pages-1);out<<"DC "<<found.size()<<" "<<page<<" "<<pages<<" "<<a<<" "<<hex(cat)<<" "<<hex(query)<<"\n";for(auto &category:categories)out<<"DK "<<hex(category)<<"\n";for(int i=page*40;i<std::min(int(found.size()),page*40+40);i++){auto &e=*found[i];out<<"DI "<<e.shape<<" "<<e.frame<<" "<<hex(e.category)<<" "<<hex(e.name)<<" "<<e.supported<<" "<<hex(e.reason)<<"\n";}message=std::to_string(found.size())+" original entries";}}
 else if(op=="DBGINSPECT"){objref r=resolve(a);if(!r.valid())fail("Target is stale or unavailable");else{inspect(r,out);message="Native target inspected";}}
 else if(op=="DBGSUP"){objref owner=pack(),root(0);std::vector<objref> created;if(!owner.valid())fail("Avatar backpack not found");else if(b!=0||a<0||a>1)fail("Unknown supply");else if(ItemFreeCount<(a==0?20:4))fail("Insufficient native item records","blocked");else if(!CreateItem(&root,TypeFrame(a==0?802:761,0)))fail("Allocation failed","blocked");else{created.push_back(root);bool ok=true;if(a==0){for(int f=0;f<8&&ok;f++){objref r(0);ok=CreateItem(&r,TypeFrame(842,f));if(ok){created.push_back(r);Item_setQuantity(r,30,0);Item_setOkayToTake(&r);ok=PlaceDraggedInContainer(&r,root)!=0;}}}else{ClearSpellbook(&root.off);for(int i=0;i<72;i++)AddSpellToSpellbook(&root,i);SetSpellbookBookmark(NPCRef(root),0);}Item_setOkayToTake(&root);if(!ok||!place(root,owner,0,0,0)){rollback(created);fail("Supply placement failed; nothing added","blocked");}else{registerTree(root,out);message=a==0?"Added bag: 30 of each of eight reagents":"Added fully learned U7 spellbook";}}}
 else if(op=="DBGI"){int quantity,d,x,y,z;objref owner(0),r(0);std::string why;if(!(input>>quantity>>d>>x>>y>>z)||!validFrame(a,b)||!unsupported(a,b).empty()||quantity<1||quantity>127||(gItemTypeInfo[a].typeClass!=TYPE_CLASS_QUANTITY&&quantity!=1))fail("Unsupported shape/frame or quantity (stack maximum 127)");else if(!destination(d,x,y,z,TypeFrame(a,b),owner,why))fail(why,"blocked");else if(ItemFreeCount<records(a)||!CreateItem(&r,TypeFrame(a,b)))fail("Insufficient native item records","blocked");else{Item_setOkayToTake(&r);if(Item_hasQuantity(&r))Item_setQuantity(r,quantity,0);if(gItemTypeInfo[a].typeClass==8)ClearSpellbook(&r.off);if(!place(r,owner,x,y,z)){Item_delete(&r);fail("Native placement failed","blocked");}else{registerTree(r,out);message="Created "+name(a,b);}}}
 else if(op=="DBGC"){int align,x,y,z;objref r(0);if(!(input>>align>>x>>y>>z)||!validFrame(a,b)||!actorShape(a)||align< -1||align>2||!coordinate(x,y,z))fail("Invalid creature request");else if(!CanTypeMoveTo(x,y,z,TypeFrame(a,b)))fail("Creature destination is blocked","blocked");else if(ItemFreeCount<creatureRecords(a)||!CreateNpc(&r,TypeFrame(a,b),x,y,z))fail("No native creature slots","blocked");else{RandomizeCreature(r,TypeFrame(a,b));{MonsterRecord original;MonsterRecords.read(MonsterLookup.get(a),&original);auto n=GetNpcBufferForIbo(&r);n->setAlignment(align<0?original.alignment:align);n->setInitialAlignment(align<0?original.alignment:align);n->experience=0;n->training=0;n->food=31;n->face=0;memset(n->name,0,sizeof n->name);}Npc_clearTargets(&r);Npc_setSchedule(&r,WORK_LOITER);registerTree(r,out);message="Created fresh native creature";}}
 else if(op=="DBGDUP"){int x,y,z;objref source=resolve(a),owner(0);std::string why;std::vector<Tree> t;std::set<short> seen;if(!(input>>x>>y>>z)||!source.valid())fail("Source is stale or invalid");else if(!tree(source,t,seen,1,-1,-1,why,true))fail(why,"blocked");else if(source.isNpc()&&b!=0)fail("Creatures must be placed in the world");else if(!destination(b,x,y,z,TypeFrame(source.ptr()->typeFrame),owner,why))fail(why,"blocked");else{int needed=0;for(auto &e:t)needed+=records(e.source.type());if(needed>ItemFreeCount)fail("Insufficient native records for complete duplicate","blocked");else{std::vector<objref> created;if(!copyTree(t,created,x,y,z,why)){rollback(created);fail(why,"blocked");}else{objref copy=created.front();if(!place(copy,owner,x,y,z)){rollback(created);fail("Destination failed; duplicate rolled back","blocked");}else{for(size_t i=0;i<t.size();i++)if(t[i].slot>=0)EquipItem(created[i],created[t[i].parent],(uint8_t)t[i].slot,0);registerTree(copy,out);message="Duplicated "+std::to_string(t.size())+(source.isNpc()?" native objects; creature conditions and AI start fresh":" native objects");}}}}}
 else if(op=="DBGSET"||op=="DBGREFILL"){objref r=resolve(a);if(!r.valid()||!r.isNpc())fail("Target must be a live native actor");else if(IsDead(&r))fail("Use native resurrection for dead actors","blocked");else{auto n=GetNpcBufferForIbo(&r);if(op=="DBGREFILL"){n->hitPoints=(uint8_t)std::min(127,int(Npc_getStrength(&r)));n->mana=n->magic;message="Restored native HP and mana";}else{int s,d,i,c,m,h,ma,x,t,f;if(!(input>>s>>d>>i>>c>>m>>h>>ma>>x>>t>>f)||s<1||s>127||c<1||c>127||d<1||d>30||i<1||i>30||m<0||m>30||h<1||h>127||ma<0||ma>30||x<0||x>999999||t<0||t>255||f<0||f>31)fail("Invalid stat range; no values changed");else{n->strength=s;n->dexterity=d;n->intelligence=i;n->combat=c;n->magic=m;n->hitPoints=std::min(h,s);n->mana=std::min(ma,m);n->experience=x;n->training=t;n->food=f;message="Updated native base stats; HP/mana clamped to maxima";}}inspect(r,out);}}
 else if(op=="DBGCOND"){int on;objref r=resolve(a);if(!(input>>on)||on<0||on>1||b<0||b>6||!r.valid()||!r.isNpc())fail("Invalid actor/condition");else if(IsDead(&r))fail("Use native resurrection first","blocked");else{NPCRef n(r);switch(b){case 0:if(on)PutToSleep(n);else{EndSleep(r);WakeUpNpc(&r);}break;case 1:if(on)ApplyPoison(n);else EndPoison(n);break;case 2:if(on)ApplyParalysis(n);else EndParalysis(n);break;case 3:if(on)ApplyCurse(n);else EndCurse(n);break;case 4:ChangeStatus(&r,on?0:NPC_PROTECTED,on?NPC_PROTECTED:0);break;case 5:if(on)Item_setInvisible(&r);else Item_setQualityFlags(&r,Item_getQualityFlags(&r)&~QUALITY_INVISIBLE);break;case 6:{auto p=GetNpcBufferForIbo(&r);p->typeFlagsHigh=on?p->typeFlagsHigh|0x10:p->typeFlagsHigh&~0x10;break;}}inspect(r,out);message="Applied native condition operation";}}
 else if(op=="DBGRES"){
    objref body=resolve(a);
    if(!body.valid()||!corpseArt(body.type(),body.frame())||!IsOnMap(&body)||GetBodyNpc(body)==0)fail("Select a valid native corpse on the ground");
    else{
        objref who(0);GetNpcIbo(&who,GetBodyNpc(body));
        if(!who.valid()||!IsDead(&who))fail("Corpse does not refer to a dead actor","blocked");
        else{
            objref holder(0);int bodyId=LocalWireId(body.off),x=Item_getX(body),y=Item_getY(body),z=body.z();
            std::vector<Tree> bodyTree;std::set<short> seen;std::string why;
            // Original RefitInventory assumes HUMAN-class actors (isBody()).
            // A MONSTER is treated as a plain container: a loose item is put
            // straight back, and its original refit loop never progresses.
            // Preserve nonhuman contents in a detached native holder while the
            // unchanged native resurrection runs, then transfer them intact.
            bool nonhuman=!who.isBody(),ready=true;
            if(nonhuman&&GetContainedItem(&who).valid()){fail("Dead nonhuman actor already has possessions","blocked");ready=false;}
            else if(!tree(body,bodyTree,seen,1,-1,-1,why,false)){fail(why,"blocked");ready=false;}
            else if(nonhuman&&GetContainedItem(&body).valid()){
                if(ItemFreeCount<records(802)||!CreateItem(&holder,TypeFrame(802,0))){fail("Insufficient native records to preserve corpse possessions","blocked");ready=false;}
                else if(!MoveContents(&body,&holder)){Item_delete(&holder);holder=objref(0);fail("Could not preserve corpse possessions","blocked");ready=false;}
            }
            if(ready){
                bool revived=ResurrectBody(body,x,y,z)!=0;
                if(holder.valid()){
                    objref receiver=revived?who:(LocalWireId(body.off)==bodyId?body:objref(0));
                    if(receiver.valid()&&MoveContents(&holder,&receiver))Item_delete(&holder);
                    else{
                        // Defensive retention: never delete original possessions
                        // if a native operation unexpectedly changes its receiver.
                        if(!place(holder,objref(0),x,y,z))place(holder,AvatarRef,0,0,0);
                        Item_clearTemporary(&holder);made.insert(LocalWireId(holder.off));
                        out<<"DN "<<LocalWireId(holder.off)<<"\n";
                        message="Possessions retained in a recovery bag";
                    }
                }
                if(!revived)fail("Original resurrection refused; possessions retained","blocked");
                else{inspect(who,out);if(message=="Done")message="Original native resurrection succeeded";else message="Original native resurrection succeeded; "+message;}
            }
        }
    }
}
 else if(op=="DBGTIME"){if(a<0||a>23||b<0||b>59)fail("Enter a valid 24-hour time");else{GameTime.ticks=a*TICKS_PER_HOUR+b*TICKS_PER_MINUTE;UpdateNpcSchedules();GameScreen.forceUpdate(0);message="Native clock set; schedules updated";}}
 else if(op=="DBGWEATHER"){if(a<0||a>6)fail("Unknown weather type");else{SetWeather(&CurrentWeather,(uint8_t)a);message="Native weather updated";}}
 else if(op=="DBGTELEPORT"){int z;if(!(input>>z)||!coordinate(a,b,z))fail("Invalid destination");else if(!CanTypeMoveTo(a,b,z,TypeFrame(AvatarRef.ptr()->typeFrame)))fail("Teleport destination is blocked","blocked");else{TeleportParty(a,b,(int8_t)z);message="Teleported Avatar and party";}}
 else if(op=="DBGCLEAN"){std::vector<int> ids;if(a)ids.push_back(a);else ids.assign(made.begin(),made.end());int removed=0,blocked=0,dead=0;for(int id:ids){if(!made.count(id))continue;objref r=resolve(id);if(!r.valid())continue;if(r.isNpc()&&IsDead(&r)){dead++;continue;}std::vector<Tree> t;std::set<short> seen;std::string why;if(!tree(r,t,seen,1,-1,-1,why,false)||std::any_of(t.begin(),t.end(),[](Tree &e){return !made.count(LocalWireId(e.source.off));})){blocked++;continue;}removed+=(int)t.size();for(auto it=t.rbegin();it!=t.rend();++it){objref child=it->source;Item_delete(&child);}}message="Removed "+std::to_string(removed)+" created objects; protected "+std::to_string(blocked)+" containers with untracked contents; "+std::to_string(dead)+" dead actors require native resurrection before cleanup";if(a&&!removed)fail(message,"blocked");}
 else if(op=="DBGSAVE"){LocalSaveWorld();const char *run=getenv("TRINSIC_RUN");message="Saved run "+std::string(run?run:"current").substr(0,128)+" to slot "+std::to_string(LocalActiveSave()+1);}
 else fail("Unknown development operation");
 out<<"DM "<<hex(message)<<"\n";payload=out.str();replies[sequence]=payload;while(replies.size()>128)replies.erase(replies.begin());if(op!="DBGCAT"&&op!="DBGINSPECT"){history.push_back(op+": "+message);if(history.size()>16)history.pop_front();}return status;
}
