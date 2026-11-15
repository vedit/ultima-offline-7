#pragma once
#include <string>
#include <istream>
void LocalAudioRecord(int track, void *buffer);
void LocalAudioSong(void *buffer); // caller holds the native sound lock
int LocalAudioMusicVolume(int volume);
int LocalAudioSfxVolume(int number, int volume);
void LocalAudioRefreshMusic();
std::string LocalAudioCommand(int music, int effects, std::istream &input);
std::string LocalAudioSnapshot();

void LocalAudioLoaded();
int LocalAudioMusicGain();
