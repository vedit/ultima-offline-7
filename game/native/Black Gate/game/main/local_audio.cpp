// Presentation preferences; the native sequencer still owns all cue timing.
#include "local_audio.h"
#include "u7port.h"
#include "preload.h"
#include "u7sound.h"
#include "midiplay.h"
#include "plat.h"
#include <atomic>
#include <cstdlib>
#include <map>
#include <sstream>
extern void LocalAdlibRefreshVolume();
extern int LocalAdlibMusicChannels();
static bool local() { static bool enabled = getenv("TRINSIC_PIPE") != nullptr; return enabled; }
static std::atomic<int> musicGain{0}, effectsGain{0}, speechGain{0};
static int musicOn=1,effectsOn=1,speechOn=1,musicVolume=100,effectsVolume=100,speechVolume=100,external=0;
static bool configured=false;
static int rawSfx[SFX_COUNT]={};
static std::map<void*,int> records;
static unsigned cue=0;
static int track=-1;
void LocalAudioRecord(int number,void *buffer) {
    if(!local())return;
    plat_sound_lock();records[buffer]=number;plat_sound_unlock();
}
void LocalAudioSong(void *buffer) {
    if(!local())return;
    auto it=records.find(buffer);track=it==records.end()?-1:it->second;++cue;
}
int LocalAudioMusicGain() {return local()?musicGain.load():100;}
int LocalAudioMusicVolume(int volume) {
    // FM gain is applied to output operators; MT-32 has native MIDI volume.
    return !local() || MusicDevice==MUSIC_DEVICE_ADLIB?volume:volume*musicGain.load()/100;
}
int LocalAudioSfxVolume(int number,int volume) {
    if(!local())return volume;
    if(number>=0 && number<SFX_COUNT)rawSfx[number]=volume;
    return volume*effectsGain.load()/100;
}
extern "C" int LocalAudioSpeechGain() {return local()?speechGain.load():100;}
// Called while the backend holds the native sound lock. Hardware TL=63 still
// leaks a quiet signal; channel output masks give zero gain without stopping notes.
extern "C" int LocalAudioOplMuteMask() {
    if(!local())return 0;
    int music=MusicDevice==MUSIC_DEVICE_ADLIB?LocalAdlibMusicChannels():0;
    return (musicGain.load()==0?music:0) | (effectsGain.load()==0?(0x1ff^music):0);
}
extern "C" int LocalAudioSynthMuted() {return local() && musicGain.load()==0 && effectsGain.load()==0;}
std::string LocalAudioCommand(int m,int e,std::istream &input) {
    int s,mv,ev,sv,x;std::string tail;
    if(!(input>>s>>mv>>ev>>sv>>x) || (input>>tail) || m<0 || m>1 || e<0 || e>1 || s<0 || s>1 || x<0 || x>1 || mv<0 || mv>100 || ev<0 || ev>100 || sv<0 || sv>100)return "invalid";
    // Original switches, including speech suppression, remain native operations.
    if(!configured || m!=musicOn || e!=effectsOn || s!=speechOn)
        if(!SetAudioState(m?AUDIO_ON:AUDIO_OFF,s?AUDIO_ON:AUDIO_OFF,e?AUDIO_ON:AUDIO_OFF))return "unavailable";
    musicOn=m;effectsOn=e;speechOn=s;musicVolume=mv;effectsVolume=ev;speechVolume=sv;external=x;configured=true;
    musicGain=m && !x?mv:0;effectsGain=e?ev:0;speechGain=s?sv:0;
    LocalAudioRefreshMusic();
    if(MusicDevice==2) {plat_sound_lock();LocalAdlibRefreshVolume();plat_sound_unlock();}
    for(int i=0;i<SFX_COUNT;++i)SetSfxVolume(i,rawSfx[i]);
    return "ok";
}
std::string LocalAudioSnapshot() {
    plat_sound_lock();unsigned id=cue;int t=track,playing=SongStopped==0;plat_sound_unlock();
    std::ostringstream out;
    out<<"AU "<<id<<" "<<t<<" "<<playing<<" "<<musicOn<<" "<<effectsOn<<" "<<speechOn<<" "<<musicVolume<<" "<<effectsVolume<<" "<<speechVolume<<" "<<external<<" "<<configured<<"\n";
    return out.str();
}

void LocalAudioLoaded() { configured=false; }
