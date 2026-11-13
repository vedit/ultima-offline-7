#pragma once
bool LocalEnabled();
int LocalNumber(int low,int high,int step);
short LocalTarget();
void LocalPoll(unsigned char *steps);
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

