#pragma once
#include <stdint.h>
bool LocalEnabled();
int LocalNumber(int low,int high,int step);
short LocalTarget();
bool LocalTargetPosition(int *x,int *y,int *z);
void LocalDisplay(const char *kind);
void LocalDisplayBegin();
short LocalOpenedObject();
int LocalControlInput(int *x,int *y,int left,int top,int width,int height);
bool LocalSpellbookInput(short book,short caster,int8_t *selected);
extern bool LocalControlReleased;
void LocalControlBegin();
void LocalRefusal(int reason);
void LocalPoll(unsigned char *steps);
// Read-only bridge progress while native time advancement/speech owns the turn.
void LocalProgress();
void LocalBeforeStep();
void LocalPartyObservation();
void LocalFreed(short handle);
void LocalSpeak(const char *text, int face);
void LocalBark(short speaker, const char *text);
void LocalPrompt(bool answers);
bool LocalAnswered(bool answers);
void LocalOpened(short object);
bool LocalChestOpen();
void LocalRecovery(short object, int status, int beforeX, int beforeY);


int LocalWireId(short handle);
short LocalDebugResolve(int wireId);
int LocalDebugCapabilities(short handle);
