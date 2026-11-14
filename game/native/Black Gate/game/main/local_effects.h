#pragma once
#include <string>
#include <stdint.h>
struct Value;

// Read-only presentation observers. Never call gameplay, RNG or Usecode here.
void LocalEffectsBegin(int routine,bool remote=false);
void LocalEffectsPush(int routine);
void LocalEffectsPop();
void LocalEffectsEnd();
void LocalEffectsReset();
std::string LocalEffectsSnapshot();
int LocalEffectsSpell();
void LocalEffectAt(const char *kind,int spell,short object,int x,int y,int z,int detail=0);
void LocalEffectOn(const char *kind,int spell,short object,int detail=0);
void LocalEffectSprite(short object,int x,int y,int shape);
void LocalEffectMissile(short object,int weapon,int x8,int y8,int z8,bool active);
void LocalEffectMissileEnd(short object);

struct LocalEffectActor {
    short object; int spell, hp, status, extended, invisible, identity;
    LocalEffectActor(short object,int spell);
    ~LocalEffectActor();
};
struct LocalEffectIntrinsic {
    int number,spell,detail; short object,subject; Value *args,*ret;
    int shape,frame,quality,x,y,z; bool onMap;
    LocalEffectActor actor;
    LocalEffectIntrinsic(int number,Value *args,Value *ret,short subject);
    ~LocalEffectIntrinsic();
};

int LocalEffectWeaponSpell(int type);
