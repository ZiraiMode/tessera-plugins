"""Exercise production C++ with host boundaries, and real native manifest/font validation.

Run with the ESPHome 2026.9.0 runtime; host coverage is not microphone acceptance.
"""
import importlib.util
import json
from pathlib import Path
import os
import subprocess
import sys
import tempfile
import types
import unittest

ROOT = Path(__file__).resolve().parents[1]
COMPONENT = ROOT / "plugins/voice_assist/components/voice_assist"
CORE = Path(os.environ.get(
    "TESSERA_CORE",
    "/home/p1ng2win/orca/workspaces/homeassistant_espscreen/Waveshare-ESP32-S3-Touch-LCD-4B",
))

STUBS = {
    "esphome/core/component.h": r'''
#pragma once
#include <cstdint>
#include <cstddef>
#include <string>
#include <vector>
#include <functional>
#include <optional>
#include <algorithm>
#define ESP_LOGW(...)
namespace esphome { template<class T> using optional = std::optional<T>;
inline std::vector<std::string> trace;
namespace setup_priority { constexpr float DATA=600, LATE=-100; }
class Component { public: virtual void setup() {} virtual void loop() {} virtual float get_setup_priority() const {return 0;} }; }
''',
    "esphome/core/preferences.h": r'''
#pragma once
#include "component.h"
#include <map>
#include <cstring>
namespace esphome {
inline std::map<uint32_t,std::vector<uint8_t>> storage;
class ESPPreferenceObject { public: uint32_t key{}; template<class T> bool save(const T *p) {storage[key] = std::vector<uint8_t>((const uint8_t*)p,(const uint8_t*)p+sizeof(T)); return true;} };
class ESPPreferences {public: virtual ~ESPPreferences()=default;};
inline ESPPreferences *global_preferences{};
}
''',
    "esphome/components/esp32/preferences.h": r'''
#pragma once
#include "esphome/core/preferences.h"
namespace esphome::esp32 {class ESP32Preferences:public ESPPreferences {public: uint32_t nvs_handle=1;};}
''',
    "esphome/core/helpers.h": r'''
#pragma once
#include "component.h"
#include <cstdio>
namespace esphome {
constexpr size_t UINT32_MAX_STR_SIZE=11;
inline size_t uint32_to_str(char (&out)[11],uint32_t key) {return std::sprintf(out,"%u",key);}
inline uint32_t fnv1_hash(const char *s) {uint32_t h=2166136261UL; while(*s) {h*=16777619; h^=(uint8_t)*s++;} return h;}
}
''',
    "nvs.h": r'''
#pragma once
#include "esphome/core/preferences.h"
#include <cstdlib>
constexpr int ESP_OK=0, ESP_ERR_NVS_NOT_FOUND=1;
inline int nvs_get_blob(uint32_t,const char *key,void *out,size_t *length) {
 auto it=esphome::storage.find(std::strtoul(key,nullptr,10));
 if(it==esphome::storage.end()) return ESP_ERR_NVS_NOT_FOUND;
 if(out) {if(*length<it->second.size()) return 2; std::memcpy(out,it->second.data(),it->second.size());}
 *length=it->second.size(); return ESP_OK;
}
''',
    "esphome/components/select/select.h": r'''
#pragma once
#include "esphome/core/preferences.h"
namespace esphome::select {
class Select {public:
 std::vector<std::string> options; std::optional<size_t> index; std::vector<std::function<void(size_t)>> callbacks;
 uint32_t get_preference_hash(){return 42;}
 template<class T> ESPPreferenceObject make_entity_preference(uint32_t version) {return ESPPreferenceObject{42^version};}
 size_t size() const{return options.size();} const char *option_at(size_t i) const{return options[i].c_str();}
 bool has_state()const{return index.has_value();} std::optional<size_t> active_index()const{return index;}
 void publish_state(size_t i){index=i; for(auto &fn:callbacks)fn(i);}
 template<class F>void add_on_state_callback(F fn){callbacks.emplace_back(fn);}
 struct Call {Select *s; size_t index=SIZE_MAX; Call &set_index(size_t i){index=i;return *this;} Call &set_option(const std::string &value){for(size_t i=0;i<s->size();++i)if(s->options[i]==value)index=i;return *this;} void perform(){if(index<s->size())s->control(index);} };
 Call make_call(){return Call{this};}
 protected:virtual void control(size_t)=0;
};}
''',
    "esphome/components/micro_wake_word/streaming_model.h": r'''
#pragma once
#include "esphome/core/component.h"
namespace esphome::micro_wake_word {
class WakeWordModel {public:std::string id,word; bool enabled=true; int writes=0;
 WakeWordModel(std::string id,std::string word):id(id),word(word){}
 bool is_enabled()const{return enabled;} void enable(){enabled=true;++writes;} void disable(){enabled=false;++writes;}
 const std::string &get_id()const{return id;} const std::string &get_wake_word()const{return word;}};
}
''',
    "esphome/components/micro_wake_word/micro_wake_word.h": r'''
#pragma once
#include "streaming_model.h"
// Native boundary: start is queued in STOPPED, where stop deliberately does not cancel it.
namespace esphome::micro_wake_word {class MicroWakeWord {public:
 int state=0, starts=0, stops=0, redundant_starts=0;bool pending_start=false,pending_stop=false,ready=true,failed=false;
 bool is_running()const{return state!=0;}bool is_ready()const{return ready;}bool is_failed()const{return failed;}
 void start(){if(!ready||failed)return;if(is_running()){++redundant_starts;return;}++starts;pending_start=true;pending_stop=false;}
 void stop(){if(state==0)return;++stops;pending_start=false;pending_stop=true;}
 void step(){
  if(pending_start&&state==0){state=1;pending_start=false;return;}
  if(state==1)state=2;
  if(pending_stop&&state==2){state=3;pending_stop=false;return;}
  if(state==3){state=0;trace.emplace_back("wake-stopped");}
 }
};}
''',
    "esphome/components/switch/switch.h": r'''
#pragma once
namespace esphome::switch_ {class Switch {public:bool state=true;void turn_on(){state=true;}void turn_off(){state=false;}};}
''',
    "esphome/components/voice_assistant/voice_assistant.h": r'''
#pragma once
#include "esphome/core/component.h"
namespace esphome::voice_assistant {class VoiceAssistant {public:
 void *client=nullptr;bool running=false,stop_requested=false;int starts=0,stops=0;std::string wake_word;
 void *get_api_connection()const{return client;}bool is_running()const{return running;}
 void set_wake_word(const std::string &word){wake_word=word;}
 void request_stop(){++stops;stop_requested=true;} // Native stop is asynchronous, especially during TTS.
 void request_start(bool continuous,bool silence){if(client&&!running){++starts;running=true;stop_requested=false;trace.emplace_back("capture");}}
};}
''',
    "esphome/core/hal.h": r'''
#pragma once
#include <cstdint>
namespace esphome {inline uint32_t now=1;inline uint32_t millis(){return now;}}
''',
    "esphome/core/defines.h": r'''
#pragma once
#define USE_SPEAKER
''',
    "esphome/components/audio/audio.h": r'''
#pragma once
namespace esphome::audio {struct AudioStreamInfo {AudioStreamInfo(int,int,int){}};}
''',
    "esphome/components/speaker/speaker.h": r'''
#pragma once
#include "esphome/core/component.h"
#include "esphome/components/audio/audio.h"
namespace esphome::speaker {class Speaker {public:
 bool running=false,pending=false,finishing=false;size_t buffered=0,submitted=0,quota=2;
 int finishes=0,plays=0;
 void set_audio_stream_info(audio::AudioStreamInfo){}
 size_t play(const uint8_t*,size_t length,int){
  ++plays;
  if(!running){pending=true;return 0;}
  size_t taken=std::min(quota,length);buffered+=taken;submitted+=taken;
  if(taken)trace.emplace_back("samples");
  return taken;
 }
 void finish(){++finishes;finishing=true;trace.emplace_back("finish");}
 bool is_stopped()const{return !running;}
 void step(bool drain=true){
  if(finishing&&!running){pending=false;finishing=false;return;}
  if(pending){pending=false;running=true;}
  if(running&&drain)buffered=0;
  if(running&&finishing&&buffered==0){running=false;finishing=false;trace.emplace_back("speaker-stopped");}
 }
};}
''',
    "esphome/components/smart_display/plugin_api.h": r'''
#pragma once
#include "esphome/core/component.h"
struct lv_obj_t{};
constexpr int LV_TEXT_ALIGN_CENTER=0,LV_LABEL_LONG_DOT=0;
inline void lv_obj_set_style_text_align(lv_obj_t*,int,int){} inline void lv_label_set_long_mode(lv_obj_t*,int){}
inline void lv_obj_set_pos(lv_obj_t*,int,int){} inline void lv_obj_set_size(lv_obj_t*,int,int){}
namespace esphome::theme {constexpr int MUTED=0,INK=1,INK_SOFT=2;}
namespace tessera {
enum class Font {ICON,TITLE,BODY,HEADLINE,BODY_LARGE}; enum class Tone {ACCENT,BUSY,NORMAL,ALERT};
namespace ui {
inline lv_obj_t *label(lv_obj_t*,Font,int){return nullptr;}inline void set_text(lv_obj_t*,const std::string&){}
inline std::string icon(uint32_t){return "";}inline void set_tone(lv_obj_t*,Tone,int){}inline void set_color(lv_obj_t*,int){}
inline void set_font(lv_obj_t*,Font){}inline int line_height(Font){return 12;}inline int px(int n){return n;}inline int text_width(const std::string&,Font){return 10;}
}
struct TileContext {int width=100,height=100,columns=1;lv_obj_t *parent=nullptr;};
class Tile {public:virtual ~Tile()=default;virtual void create(const TileContext&){}virtual void on_tick(uint32_t){}virtual void on_theme(){}virtual void on_tap(){}};
struct BarItem {bool shown=false;uint32_t icon=0;Tone tone=Tone::NORMAL;std::string text;};
class SettingsPage {public:std::string icon; template<class... A>void toggle(A...){}template<class... A>void choice(A...){}template<class... A>void info(A...){}template<class... A>SettingsPage &action(A...){return *this;}template<class F>SettingsPage &active(F){return *this;}};
class Plugin {public:virtual ~Plugin()=default;virtual bool settings(SettingsPage&){return false;}virtual void before_update(){}const char *text(const char *key)const{return key;}template<class F>void add_tile(const char*,F){}template<class F>void add_bar_item(const char*,F){}};
inline void refresh(){}inline std::string fill(const char*,const char*,const std::string &s){return s;}
}
''',
}

HARNESS = r'''
#include "wake_phrase_select.h"
#include "voice_assist.h"
#include "esphome/components/esp32/preferences.h"
#include "esphome/core/helpers.h"
#include <cassert>
using namespace esphome;
using namespace esphome::voice_assist;
constexpr uint32_t NEW_KEY=42^0x56415001;
esp32::ESP32Preferences manager;
micro_wake_word::WakeWordModel nabu("va_okay_nabu","Okay Nabu"),jarvis("va_hey_jarvis","Hey Jarvis"),alisa("ww_alisa","Алиса");
WakeModelEntry n{&nabu,{1},"Okay Nabu"},j{&jarvis,{2},"Hey Jarvis"},a{&alisa,{3},"Алиса"};
template<class T>void save(uint32_t key,const T &value){ESPPreferenceObject{key}.save(&value);}
void init(WakePhraseSelect &select,const WakeModelEntry *table,size_t count){
 select.set_models(table,count);for(size_t i=0;i<count;++i)select.options.push_back(table[i].model->get_wake_word());select.setup();
}
void reset(){storage.clear();manager.nvs_handle=1;nabu.enabled=jarvis.enabled=alisa.enabled=true;}
void historical(bool x,bool y,bool z){uint8_t values[]={uint8_t(x),uint8_t(y),uint8_t(z)};const char *ids[]={"va_okay_nabu","va_hey_jarvis","va_hey_mycroft"};for(int i=0;i<3;++i)save(fnv1_hash(ids[i]),values[i]);}
int main(){
 global_preferences=&manager;
 WakeModelEntry reordered[]={a,j,n};
 reset();save(42,size_t(1));WakePhraseSelect migrated;init(migrated,reordered,3);assert(*migrated.active_index()==1);assert(jarvis.enabled&&!alisa.enabled&&!nabu.enabled);
 reset();WakePhraseSelect fresh;init(fresh,reordered,3);assert(*fresh.active_index()==0);assert(alisa.enabled&&!jarvis.enabled&&!nabu.enabled);
 WakeModelEntry again[]={n,a,j};WakePhraseSelect reboot;init(reboot,again,3);assert(*reboot.active_index()==1);
 WakeModelEntry without[]={j,n};WakePhraseSelect removed;init(removed,without,2);assert(!removed.active_index());assert(!jarvis.enabled&&!nabu.enabled);
 WakePhraseSelect readded;init(readded,reordered,3);assert(!readded.active_index());assert(!alisa.enabled);
 readded.make_call().set_index(1).perform();assert(jarvis.enabled&&!alisa.enabled&&!nabu.enabled);
 readded.make_call().set_index(99).perform();readded.make_call().set_option("invented").perform();assert(jarvis.enabled&&*readded.active_index()==1);
 int writes=jarvis.writes;readded.make_call().set_index(1).perform();assert(jarvis.writes==writes);
 assert(readded.accepts("Hey Jarvis"));assert(!readded.accepts("Алиса"));
 reset();WakePhraseSelect empty;init(empty,nullptr,0);assert(!empty.active_index());
 reset();save(NEW_KEY,WakeSelection{1,{99}});WakePhraseSelect unknown;init(unknown,reordered,3);assert(!unknown.active_index());assert(!alisa.enabled&&!jarvis.enabled&&!nabu.enabled);
 reset();save(NEW_KEY,uint8_t(1));save(42,size_t(1));WakePhraseSelect corrupt;init(corrupt,reordered,3);assert(!corrupt.active_index());
 reset();save(NEW_KEY,WakeSelection{2,{2}});WakePhraseSelect invalid;init(invalid,reordered,3);assert(!invalid.active_index());
 reset();historical(true,false,false);WakePhraseSelect bools;init(bools,reordered,3);assert(*bools.active_index()==2);
 reset();historical(true,false,false);WakePhraseSelect bool_removed;init(bool_removed,without,1);assert(!bool_removed.active_index());
 reset();save(fnv1_hash("va_okay_nabu"),uint8_t(1));WakePhraseSelect partial;init(partial,reordered,3);assert(!partial.active_index());
 reset();historical(true,true,false);WakePhraseSelect inconsistent;init(inconsistent,reordered,3);assert(!inconsistent.active_index());
 reset();historical(false,false,false);WakePhraseSelect no_true;init(no_true,reordered,3);assert(!no_true.active_index());
 reset();save(fnv1_hash("va_okay_nabu"),uint8_t(2));WakePhraseSelect bad_bool;init(bad_bool,reordered,3);assert(!bad_bool.active_index());
 reset();save(42,uint8_t(1));WakePhraseSelect bad_old;init(bad_old,reordered,3);assert(!bad_old.active_index());
 reset();manager.nvs_handle=0;WakePhraseSelect unavailable;init(unavailable,reordered,3);assert(!unavailable.active_index());
 // Actual production assistant: startup sync, subscription (not generic API connectivity),
 // no-selection toggles/connects, manual request and genuine-word detection gate.
 reset();save(NEW_KEY,WakeSelection{});WakePhraseSelect none;init(none,reordered,3);
 micro_wake_word::MicroWakeWord detector;voice_assistant::VoiceAssistant assistant;switch_::Switch on;
 VoiceAssist plugin;plugin.set_assistant(&assistant);plugin.set_wake_word(&detector);plugin.set_wake_word_on(&on);plugin.set_wake_phrase(&none);
 assistant.client=&assistant;plugin.sync_wake();assert(!detector.is_running());plugin.setup();assert(!detector.is_running());
 on.state=false;plugin.sync_wake();on.state=true;plugin.sync_wake();assert(!detector.is_running());
 assistant.client=nullptr;plugin.sync_wake();assistant.client=&assistant;plugin.sync_wake();assert(!detector.is_running());
 plugin.ask();assert(plugin.busy()&&!assistant.running);plugin.loop();assert(assistant.running);assert(!plugin.accepts_wake_word("Hey Jarvis"));
 assistant.running=false;plugin.loop();
 none.make_call().set_index(1).perform();assert(detector.pending_start);detector.step();detector.step();plugin.loop();
 assert(detector.is_running());assert(plugin.accepts_wake_word("Hey Jarvis"));assert(!plugin.accepts_wake_word("Алиса"));
 assistant.client=nullptr;plugin.sync_wake();detector.step();detector.step();plugin.loop();assert(!detector.is_running());assert(!plugin.accepts_wake_word("Hey Jarvis"));
 assistant.client=&assistant;on.state=false;plugin.sync_wake();assert(!detector.is_running());on.state=true;plugin.sync_wake();detector.step();detector.step();plugin.loop();assert(detector.is_running());
 // DATA selection was restored before LATE plugin setup: explicit setup sync must start it.
 micro_wake_word::MicroWakeWord detector2;VoiceAssist startup;startup.set_assistant(&assistant);startup.set_wake_word(&detector2);startup.set_wake_word_on(&on);startup.set_wake_phrase(&none);startup.setup();assert(detector2.pending_start);
}
'''


LIFECYCLE_HARNESS = r'''
#include "voice_assist.h"
#include "esphome/components/esp32/preferences.h"
#include "esphome/core/hal.h"
#include <cassert>
using namespace esphome;
using namespace esphome::voice_assist;
esp32::ESP32Preferences manager;
struct Fixture {
 micro_wake_word::WakeWordModel alisa{"ww_alisa","Алиса"},jarvis{"va_hey_jarvis","Hey Jarvis"};
 WakeModelEntry models[2]{{&alisa,{1},"Алиса"},{&jarvis,{2},"Hey Jarvis"}};
 WakePhraseSelect selection;
 micro_wake_word::MicroWakeWord detector;
 voice_assistant::VoiceAssistant assistant;
 speaker::Speaker output;
 switch_::Switch wake_on,sound_on,thinking_on;
 VoiceAssist plugin;
 uint8_t beep_bytes[6]{},thinking_bytes[8]{};
 Fixture(bool sound=true,bool selected=true,bool settle=true,bool duplex=false) {
  storage.clear();global_preferences=&manager;now=1;
  if(!selected){WakeSelection none{};ESPPreferenceObject{42^0x56415001}.save(&none);}
  selection.set_models(models,2);selection.options={"Алиса","Hey Jarvis"};selection.setup();
  assistant.client=&assistant;sound_on.state=sound;
  plugin.set_assistant(&assistant);plugin.set_wake_word(&detector);plugin.set_wake_word_on(&wake_on);
  plugin.set_wake_phrase(&selection);plugin.set_speaker(&output);plugin.set_wake_sound_on(&sound_on);
  plugin.set_thinking_sound_on(&thinking_on);
  plugin.set_capture_during_playback(duplex);
  plugin.set_wake_sound(tessera::Sound{beep_bytes,sizeof(beep_bytes),16000,1});
  plugin.set_thinking_sound(tessera::Sound{thinking_bytes,sizeof(thinking_bytes),16000,1});
  plugin.setup();if(settle)pump(4);trace.clear();
 }
 void tick(bool drain=true){now+=10;detector.step();output.step(drain);plugin.loop();}
 void pump(int count,bool drain=true){for(int i=0;i<count;++i)tick(drain);}
 void await_start(bool drain=true){for(int i=0;i<30&&!assistant.running;++i)tick(drain);assert(assistant.running);}
 void await_beep(){for(int i=0;i<30&&output.submitted<sizeof(beep_bytes);++i)tick(false);assert(output.submitted==sizeof(beep_bytes));}
};
size_t event(const char *name){auto it=std::find(trace.begin(),trace.end(),name);assert(it!=trace.end());return it-trace.begin();}
int main(){
 // Production SoundPlayer feeds partial writes; its final submission must not start capture.
 {
  Fixture f;assert(f.detector.is_running());f.plugin.wake("Алиса");assert(f.plugin.busy());
  assert(f.plugin.current()==Phase::PREPARING&&f.plugin.phase_word()=="preparing");
  f.plugin.wake("Алиса");f.plugin.wake("Hey Jarvis");assert(!f.plugin.accepts_wake_word("Алиса"));
  f.await_beep();assert(f.assistant.starts==0&&f.output.finishes==1&&f.output.buffered==6);
  assert(f.plugin.current()==Phase::PREPARING);
  f.pump(3,false);assert(f.assistant.starts==0); // All bytes accepted, still physically draining.
  assert(f.plugin.current()==Phase::PREPARING);
  f.tick();assert(f.assistant.starts==1&&f.assistant.wake_word=="Алиса");
  assert(f.plugin.current()==Phase::PREPARING); // Native STARTING is not microphone readiness.
  f.plugin.phase(Phase::THINKING);assert(f.plugin.current()==Phase::PREPARING);
  assert(event("wake-stopped")<event("samples"));assert(event("samples")<event("finish"));
  assert(event("finish")<event("speaker-stopped"));assert(event("speaker-stopped")<event("capture"));
  int plays=f.output.plays;f.plugin.phase(Phase::LISTENING);f.pump(8);
  assert(f.plugin.current()==Phase::LISTENING&&f.plugin.phase_word()=="listening");
  assert(f.output.plays==plays&&f.assistant.starts==1&&!f.detector.is_running());
 }
 // Sound off adds no speaker work, and a manual request clears the native wake-word field.
 {
  Fixture f(false);f.assistant.wake_word="previous wake";f.plugin.ask();
  assert(f.plugin.current()==Phase::PREPARING);f.await_start();
  assert(f.plugin.current()==Phase::PREPARING);
  f.plugin.phase(Phase::LISTENING);assert(f.plugin.current()==Phase::LISTENING);
  assert(f.assistant.wake_word.empty()&&f.output.plays==0&&f.output.finishes==0);
  f.assistant.running=false;f.pump(5);assert(f.detector.is_running());
  f.plugin.wake("Алиса");f.await_start();assert(f.assistant.starts==2&&f.assistant.wake_word=="Алиса");
  f.assistant.running=false;f.pump(5);f.plugin.ask();f.await_start();
  assert(f.assistant.starts==3&&f.assistant.wake_word.empty());
  assert(f.output.plays==0&&f.output.finishes==0);
 }
 // Every cancellation point (wake shutdown, feeding, drain) forbids a delayed native start.
 for(int reason=0;reason<6;++reason)for(int point=0;point<3;++point){
  Fixture f;f.plugin.wake("Алиса");
  if(point==1){for(int i=0;i<20&&f.output.submitted==0;++i)f.tick(false);assert(f.output.submitted>0);}
  if(point==2)f.await_beep();
  if(reason==0)f.plugin.ask(); // A second tap cancels the pending request, not queues another.
  if(reason==1){f.assistant.client=nullptr;f.plugin.stop();f.plugin.sync_wake();}
  if(reason==2){f.wake_on.state=false;f.plugin.sync_wake();}
  if(reason==3)f.selection.make_call().set_index(1).perform();
  if(reason==4)f.plugin.before_update();
  if(reason==5)f.assistant.client=nullptr; // Also rechecked without relying on YAML delivery.
  f.pump(30);assert(f.assistant.starts==0&&!f.plugin.busy()&&f.detector.redundant_starts==0);
  assert(f.plugin.current()==Phase::IDLE);
  if(reason==1||reason==2||reason==4||reason==5)assert(!f.detector.is_running()&&!f.detector.pending_start);
 }
 // Model/switch changes only cancel wake-origin requests; tap remains available.
 {
  Fixture f;f.plugin.ask();f.await_beep();f.selection.make_call().set_index(1).perform();
  assert(f.plugin.current()==Phase::PREPARING&&f.plugin.phase_word()=="preparing");
  f.wake_on.state=false;f.plugin.sync_wake();f.await_start();
  assert(f.assistant.wake_word.empty()&&f.assistant.starts==1);
  assert(f.plugin.current()==Phase::PREPARING);
  f.plugin.phase(Phase::LISTENING);assert(f.plugin.current()==Phase::LISTENING);
 }
 // Changing model identity cancels even when the two native wake phrases happen to be identical.
 {
  Fixture f;f.jarvis.word="Алиса";f.plugin.wake("Алиса");f.await_beep();
  f.selection.make_call().set_index(1).perform();f.pump(20);assert(f.assistant.starts==0);
 }
 // No selected model: connect/toggles cannot start inference, but a tap still works.
 {
  Fixture f(false,false);assert(!f.detector.is_running()&&f.detector.starts==0);
  f.assistant.client=nullptr;f.plugin.stop();f.assistant.client=&f.assistant;
  f.wake_on.state=false;f.plugin.sync_wake();f.wake_on.state=true;f.plugin.sync_wake();f.pump(5);
  assert(f.detector.starts==0);f.plugin.ask();f.await_start();assert(f.assistant.wake_word.empty());
  f.assistant.running=false;f.pump(5);assert(f.detector.starts==0);
 }
 // on_end is HA pipeline end, not native playback end. Follow-up conversations remain native.
 {
  Fixture f(false);f.plugin.ask();f.await_start();f.plugin.phase(Phase::LISTENING);
  f.plugin.phase(Phase::THINKING);f.pump(2,false);assert(f.output.submitted>0);
  int plays=f.output.plays;f.plugin.answer("response");assert(f.output.finishes==1);
  f.plugin.phase(Phase::IDLE);f.pump(5,false);
  assert(f.plugin.current()==Phase::ANSWERING&&f.plugin.phase_word()=="answering");
  f.plugin.phase(Phase::THINKING); // A late VAD event cannot reopen the completed pipeline's feeder.
  assert(f.plugin.busy()&&!f.detector.is_running()&&f.output.plays==plays);
  assert(f.plugin.current()==Phase::ANSWERING&&f.plugin.reply()=="response");
  f.pump(5);assert(!f.detector.is_running()); // Local sound idle does not imply native idle.
  assert(f.plugin.current()==Phase::ANSWERING); // Still native playback, not the idle wake phrase.
  f.plugin.phase(Phase::LISTENING);f.pump(3); // Native continues directly into another capture.
  assert(f.assistant.starts==1&&!f.detector.is_running()&&f.plugin.busy());
  f.plugin.phase(Phase::IDLE);f.assistant.running=false;f.pump(6);
  assert(f.detector.is_running()&&f.detector.redundant_starts==0);
  assert(f.plugin.current()==Phase::IDLE);
 }
 // Failure, cancel, and no-TTS "nevermind": all stop the thinking feeder and recover repeatedly.
 {
  Fixture f(false);
  for(int outcome=0;outcome<6;++outcome){
   assert(f.detector.is_running());f.plugin.wake("Алиса");f.await_start();
   f.plugin.phase(Phase::LISTENING);f.plugin.phase(Phase::THINKING);
   size_t before=f.output.submitted;for(int i=0;i<10&&f.output.submitted==before;++i)f.tick(false);
   assert(f.output.submitted>before);int plays=f.output.plays;
   if(outcome%3==0){f.plugin.failed("stt-failed","No text");f.plugin.phase(Phase::IDLE);}
   if(outcome%3==1){
    f.plugin.ask();assert(f.assistant.stop_requested);
    f.plugin.phase(Phase::THINKING); // Deferred VAD callback must not restart a cancelled feeder.
   }
   if(outcome%3==2){f.plugin.phase(Phase::IDLE);assert(f.plugin.current()==Phase::THINKING);}
   f.plugin.phase(Phase::THINKING); // Failure/end are also terminal until the next actual listening turn.
   f.pump(5);assert(f.output.plays==plays&&!f.detector.is_running());
   f.assistant.running=false;f.pump(6);
   assert(f.detector.is_running()&&!f.output.running&&f.detector.redundant_starts==0);
   assert(f.plugin.current()==(outcome%3==0?Phase::FAILED:Phase::IDLE));
   assert(f.assistant.starts==outcome+1);
  }
 }
 // Firmware update cancellation also holds wake inference off after an active request becomes idle.
 {
  Fixture f(false);f.plugin.ask();f.await_start();f.plugin.phase(Phase::LISTENING);
  f.plugin.phase(Phase::THINKING);f.pump(2,false);
  f.plugin.before_update();int plays=f.output.plays;assert(f.assistant.stop_requested);
  f.plugin.phase(Phase::THINKING);f.assistant.running=false;f.pump(10);
  assert(f.output.plays==plays&&!f.detector.is_running()&&!f.detector.pending_start&&!f.plugin.busy());
 }
 // Native idle without any HA end callback is also enough to stop thinking and restore wake.
 {
  Fixture f(false);f.plugin.ask();f.await_start();f.plugin.phase(Phase::LISTENING);
  f.plugin.phase(Phase::THINKING);f.pump(2,false);
  int plays=f.output.plays;f.assistant.running=false;f.pump(8);
  assert(f.output.plays==plays&&f.detector.is_running()&&f.plugin.current()==Phase::IDLE);
 }
 // Native MWW start() queues work while is_running()==false; stop() there is a no-op.
 {
  Fixture f(true,true,false);assert(f.detector.pending_start&&!f.detector.is_running());
  f.wake_on.state=false;f.plugin.sync_wake();f.plugin.sync_wake();
  assert(f.detector.stops==0);f.pump(6);
  assert(!f.detector.is_running()&&!f.detector.pending_start&&f.detector.stops==1);
  f.wake_on.state=true;for(int i=0;i<10;++i)f.plugin.sync_wake();assert(f.detector.starts==2);
  f.assistant.client=nullptr;f.plugin.stop();f.pump(6);
  assert(!f.detector.is_running()&&!f.detector.pending_start&&f.detector.stops==2);
  f.assistant.client=&f.assistant;f.plugin.sync_wake();f.pump(6);
  assert(f.detector.is_running()&&f.detector.starts==3&&f.detector.redundant_starts==0);
 }
 {
  Fixture f(true,true,false);f.plugin.ask();f.plugin.loop();
  assert(f.output.plays==0&&f.assistant.starts==0); // Must not mistake queued MWW start for stopped task.
  f.await_beep();assert(f.assistant.starts==0);f.await_start();assert(f.assistant.starts==1);
 }
 // SoundPlayer's real no-progress timeout still finishes its queued speaker and releases capture.
 {
  Fixture f;f.output.quota=0;f.plugin.ask();
  for(int i=0;i<140&&!f.assistant.running;++i)f.tick();
  assert(f.assistant.starts==1&&f.output.submitted==0&&f.output.finishes==1&&!f.output.pending);
 }
}
'''


DUPLEX_HARNESS = LIFECYCLE_HARNESS.split("int main(){", 1)[0] + r'''
int main(){
 // Capture starts without waiting for HA STT_START or the optional cue to drain.
 {
  Fixture f(true,true,true,true);const int detector_starts=f.detector.starts;
  f.plugin.wake("Алиса");f.tick(false);
  assert(f.assistant.starts==1&&f.assistant.running);
  assert(f.assistant.starts==1&&f.assistant.wake_word=="Алиса"&&f.output.plays==0);
  f.plugin.wake("Алиса");assert(f.assistant.starts==1);
  f.plugin.phase(Phase::LISTENING);f.await_beep();
  assert(f.output.buffered==6&&f.output.running&&f.assistant.running);
  int plays=f.output.plays,finishes=f.output.finishes;
  f.plugin.phase(Phase::LISTENING);f.pump(3,false);
  assert(f.output.plays==plays&&f.output.finishes==finishes); // No duplicate cue or premature stop.
  f.plugin.phase(Phase::THINKING);f.pump(3,false);
  assert(f.output.submitted==6); // Thinking cannot replace the still-draining cue.
  f.pump(10);assert(f.output.submitted>6);
  f.plugin.answer("response");f.plugin.phase(Phase::IDLE);f.pump(8);
  assert(f.detector.is_running()&&f.detector.starts==detector_starts&&f.detector.stops==0);
  plays=f.output.plays;
  f.plugin.phase(Phase::LISTENING);f.pump(8);
  assert(f.output.plays==plays); // Native follow-up is not another user-requested cue.
  f.plugin.phase(Phase::IDLE);f.assistant.running=false;f.pump(5);
  assert(f.plugin.accepts_wake_word("Алиса"));
  f.plugin.wake("Алиса");assert(f.assistant.starts==2);
  f.plugin.phase(Phase::LISTENING);f.pump(10);
  assert(f.output.plays>plays&&f.detector.starts==detector_starts&&f.detector.stops==0);
 }
 // Manual capture is equally immediate, clears the previous phrase, and works without a model.
 for(bool selected:{false,true})for(bool sound:{false,true}){
  Fixture f(sound,selected,true,true);f.assistant.wake_word="old";
  f.plugin.ask();f.tick(false);
  assert(f.assistant.starts==1&&f.assistant.running&&f.assistant.wake_word.empty());
  f.plugin.phase(Phase::LISTENING);f.pump(10);
  assert((f.output.submitted!=0)==sound&&f.detector.starts==(selected?1:0));
 }
 // No late cue after cancel, disconnect, error, model change (even same phrase), switch off,
 // update, native idle, or HA end. Exercise both wake and tap pending cues.
 for(bool manual:{false,true})for(int reason=0;reason<9;++reason){
  Fixture f(true,true,true,true);
  if(manual)f.plugin.ask();else f.plugin.wake("Алиса");
  assert(f.assistant.starts==1);
  if(reason==0)f.plugin.stop();
  if(reason==1){f.assistant.client=nullptr;f.plugin.stop();}
  if(reason==2)f.plugin.failed("error","failed");
  if(reason==3){f.jarvis.word="Алиса";f.selection.make_call().set_index(1).perform();}
  if(reason==4){f.wake_on.state=false;f.plugin.sync_wake();}
  if(reason==5)f.plugin.before_update();
  if(reason==6){f.assistant.running=false;f.plugin.loop();}
  if(reason==7)f.plugin.phase(Phase::IDLE);
  if(reason==8)f.assistant.client=nullptr; // Rechecked at LISTENING without a disconnect callback.
  f.plugin.phase(Phase::LISTENING);f.pump(10);
  // Turning wake activation off must not cancel an independent manual request/cue.
  assert((f.output.submitted!=0)==(manual&&reason==4));
  assert(f.assistant.starts==1);
 }
 // Cue emission is not truncated merely because the optional thinking sound is disabled.
 {
  Fixture f(true,true,true,true);f.thinking_on.state=false;f.plugin.wake("Алиса");
  f.plugin.phase(Phase::LISTENING);f.tick(false);f.plugin.phase(Phase::THINKING);
  f.await_beep();assert(f.output.submitted==6);f.pump(10);assert(f.output.submitted==6);
 }
 // An already-draining local sound never delays a new tap's capture. Its cue waits safely,
 // and remains cancellable until that drain ends instead of overwriting the speaker input.
 for(bool cancel:{false,true}){
  Fixture f(true,true,true,true);f.plugin.wake("Алиса");
  f.plugin.phase(Phase::LISTENING);f.await_beep();f.assistant.running=false;
  f.plugin.ask();f.tick(false);
  assert(f.assistant.running&&f.assistant.starts==2);
  f.plugin.phase(Phase::LISTENING);f.pump(3,false);assert(f.output.submitted==6);
  if(cancel)f.selection.make_call().set_index(1).perform();
  f.pump(12);assert(f.output.submitted==(cancel?6:12));
 }
 // Explicit eligibility changes still fence a queued detector start, even in duplex mode.
 {
  Fixture f(true,true,false,true);assert(f.detector.pending_start);
  f.wake_on.state=false;f.plugin.sync_wake();f.wake_on.state=true;f.plugin.sync_wake();
  assert(!f.plugin.accepts_wake_word("Алиса"));f.plugin.wake("Алиса");assert(f.assistant.starts==0);
  f.pump(10);assert(f.detector.is_running()&&f.detector.stops==1&&f.detector.starts==2);
  f.plugin.wake("Алиса");assert(f.assistant.starts==1);
  f.pump(5);assert(f.detector.starts==2&&f.detector.stops==1);
 }
}
'''


class ProductionFirmwareTests(unittest.TestCase):
    def compile_and_run(self, harness):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for path, content in STUBS.items():
                target = root / path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(content)
            sound_header = CORE / "components/smart_display/plugin_sound.h"
            self.assertTrue(sound_header.is_file(), f"Production SoundPlayer required: {sound_header}; set TESSERA_CORE")
            target = root / "esphome/components/smart_display/plugin_sound.h"
            target.write_text(sound_header.read_text())
            source = root / "harness.cpp"
            source.write_text(harness)
            executable = root / "harness"
            result = subprocess.run(["g++", "-std=c++20", "-I", str(root), "-I", str(COMPONENT),
                                     str(source), str(COMPONENT / "wake_phrase_select.cpp"),
                                     str(COMPONENT / "voice_assist.cpp"), "-o", str(executable)],
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            result = subprocess.run([str(executable)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_production_select_and_assistant(self):
        self.compile_and_run(HARNESS)

    def test_production_request_audio_lifecycle(self):
        self.compile_and_run(LIFECYCLE_HARNESS)

    def test_production_duplex_capture_lifecycle(self):
        self.compile_and_run(DUPLEX_HARNESS)


def load_select():
    import esphome.codegen as cg
    from esphome.components import select
    package = types.ModuleType("wake_test_component")
    package.__path__ = [str(COMPONENT)]
    package.voice_assist_ns = cg.esphome_ns.namespace("voice_assist")
    package.WakePhraseSelect = package.voice_assist_ns.class_("WakePhraseSelect", select.Select, cg.Component)
    sys.modules[package.__name__] = package
    spec = importlib.util.spec_from_file_location(package.__name__ + ".select", COMPONENT / "select.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class NativeMetadataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.select = load_select()

    def setUp(self):
        from esphome.core import CORE
        self.old_data = CORE.data
        CORE.data = {}
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.addCleanup(setattr, CORE, "data", self.old_data)

    def model(self, model_id, name, step=10, internal=False):
        from esphome.core import ID
        manifest = {"type": "micro", "model": "model.tflite", "author": "test", "version": 2,
                    "wake_word": name, "trained_languages": ["ru"],
                    "micro": {"feature_step_size": step, "tensor_arena_size": 32000,
                              "probability_cutoff": 0.9, "sliding_window_size": 10,
                              "minimum_esphome_version": "2026.9.0"}}
        folder = self.root / model_id
        folder.mkdir()
        (folder / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        (folder / "model.tflite").write_bytes(b"\x08\x00\x00\x00TFL3\x00\x00\x00\x00")
        return {"id": ID(model_id), "model": {"type": "local", "path": str(folder / "manifest.json")}, "internal": internal}

    def validate(self, models, vad=None, fonts=None):
        from esphome.core import ID
        import esphome.final_validate as fv
        wake = {"models": models}
        if vad is not None:
            wake["vad"] = vad
        class Full(dict):
            def get_path_for_id(self, unused):
                return ["micro_wake_word", "id"]
            def get_config_for_path(self, path):
                return self["micro_wake_word"]
        full = Full(micro_wake_word=wake, font=fonts or [])
        token = fv.full_config.set(full)
        try:
            self.select.final_validate({"id": ID("choice"), "micro_wake_word_id": ID("wake")})
        finally:
            fv.full_config.reset(token)
        from esphome.core import CORE
        return CORE.data["voice_assist"]["wake_models"]["choice"]

    def test_real_local_manifests_and_capture(self):
        rows = self.validate([self.model("alisa", "Алиса"), self.model("jarvis", "Hey Jarvis"),
                              self.model("internal", "Secret", internal=True)], self.model("vad", "vad"))
        self.assertEqual([row["name"] for row in rows], ["Алиса", "Hey Jarvis"])
        self.assertEqual([row["id"] for row in rows], ["alisa", "jarvis"])
        self.assertEqual(rows[0]["label"], "Алиса")
        # Captured IDs/names survive the end of final_validate.full_config's context.
        self.assertEqual(str(rows[0]["model_id"]), "alisa")

    def test_vad_timing_mismatch_names_offender(self):
        import esphome.config_validation as cv
        with self.assertRaisesRegex(cv.Invalid, "vad.*20ms.*10ms"):
            self.validate([self.model("alisa", "Алиса")], self.model("vad", "vad", 20))

    def test_internal_timing_is_still_checked(self):
        import esphome.config_validation as cv
        with self.assertRaisesRegex(cv.Invalid, "hidden"):
            self.validate([self.model("alisa", "Алиса"), self.model("hidden", "Secret", 20, True)])

    def test_empty_is_manual_only(self):
        self.assertEqual(self.validate([], self.model("vad", "vad")), [])

    def test_nonpositive_timing_fails(self):
        import esphome.config_validation as cv
        with self.assertRaisesRegex(cv.Invalid, "nonpositive"):
            self.validate([self.model("zero", "Zero", 0)])

    def test_screen_choice_capacity(self):
        import esphome.config_validation as cv
        models = [self.model(f"model_{index}", f"Word {index}") for index in range(256)]
        with self.assertRaisesRegex(cv.Invalid, "255"):
            self.validate(models)

    def test_collision_with_literal_generated_name(self):
        entries = [{"id": "a", "name": "Same"}, {"id": "b", "name": "Same"},
                   {"id": "c", "name": "Same [a]"}]
        labels = self.select.option_labels(entries)
        self.assertEqual(len(set(labels)), 3)
        self.assertEqual(labels, ["Same [a] [a]", "Same [b]", "Same [a] [c]"])

    def test_real_roboto_cyrillic_glyph_expansion_and_fallback(self):
        from esphome.components import font
        from esphome.core import ID
        # Use the five actual bundled font weights, without expanding a whole alphabet.
        fonts_root = Path(os.environ.get("TESSERA_FONTS", "/home/p1ng2win/orca/workspaces/homeassistant_espscreen/Waveshare-ESP32-S3-Touch-LCD-4B/fonts"))
        configs = []
        weights = {"headline": 500, "watch_value": 500, "label": 700, "sublabel": 400, "sublabel_big": 400}
        for name, weight in weights.items():
            path = fonts_root / f"Roboto-{weight}.ttf"
            self.assertTrue(path.is_file(), f"Tessera bundled font required: {path}; set TESSERA_FONTS")
            file = {"path": str(path), "type": "local"}
            font.FONT_CACHE[file] = path
            configs.append({"id": ID(name), "file": file, "glyphs": [" ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz_0123456789[]"],
                            "extras": [{"file": file, "glyphs": ["!"]}],
                            "glyphsets": [font.DEFAULT_GLYPHSET], "ignore_missing_glyphs": False, "size": 20})
        rows = self.validate([self.model("alisa", "Алиса"), self.model("unsupported", "\U0010ffff"),
                              self.model("extra", "Okay!")], fonts=configs)
        self.assertEqual(rows[0]["label"], "Алиса")
        self.assertEqual(rows[0]["screen_label"], "Алиса")
        self.assertEqual(rows[1]["label"], "\U0010ffff")
        self.assertEqual(rows[1]["screen_label"], "unsupported")
        for config in configs:
            self.assertTrue(set("Алиса").issubset(set("".join(config["glyphs"]))))
            self.assertEqual(len("".join(config["glyphs"])), len(set("".join(config["glyphs"]))))
            self.assertNotIn("!", "".join(config["glyphs"]))  # supplied by extras, never duplicated
            font.validate_font_config(config)


if __name__ == "__main__":
    unittest.main()
