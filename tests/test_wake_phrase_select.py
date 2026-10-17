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
namespace esphome::micro_wake_word {class MicroWakeWord {public:bool running=false;void start(){running=true;}void stop(){running=false;}};}
''',
    "esphome/components/switch/switch.h": r'''
#pragma once
namespace esphome::switch_ {class Switch {public:bool state=true;void turn_on(){state=true;}void turn_off(){state=false;}};}
''',
    "esphome/components/voice_assistant/voice_assistant.h": r'''
#pragma once
namespace esphome::voice_assistant {class VoiceAssistant {public:void *client=nullptr;bool running=false;
 void *get_api_connection()const{return client;} bool is_running()const{return running;}
 void request_stop(){running=false;}void request_start(bool,bool){running=true;}};}
''',
    "esphome/core/hal.h": r'''
#pragma once
#include <cstdint>
inline uint32_t millis(){return 1;}
''',
    "esphome/components/smart_display/plugin_sound.h": r'''
#pragma once
namespace esphome::speaker {class Speaker {};}
namespace tessera {struct Sound {}; class SoundPlayer {public:void set_speaker(esphome::speaker::Speaker*){}bool playing(){return false;}bool playing(Sound){return false;}void play(Sound){}void stop(){}void loop(){}};}
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
 assistant.client=&assistant;plugin.sync_wake();assert(!detector.running);plugin.setup();assert(!detector.running);
 on.state=false;plugin.sync_wake();on.state=true;plugin.sync_wake();assert(!detector.running);
 assistant.client=nullptr;plugin.sync_wake();assistant.client=&assistant;plugin.sync_wake();assert(!detector.running);
 plugin.ask();assert(assistant.running);assert(!plugin.accepts_wake_word("Hey Jarvis"));assistant.request_stop();
 none.make_call().set_index(1).perform();assert(detector.running);assert(plugin.accepts_wake_word("Hey Jarvis"));assert(!plugin.accepts_wake_word("Алиса"));
 assistant.client=nullptr;plugin.sync_wake();assert(!detector.running);assert(!plugin.accepts_wake_word("Hey Jarvis"));
 assistant.client=&assistant;on.state=false;plugin.sync_wake();assert(!detector.running);on.state=true;plugin.sync_wake();assert(detector.running);
 // DATA selection was restored before LATE plugin setup: explicit setup sync must start it.
 micro_wake_word::MicroWakeWord detector2;VoiceAssist startup;startup.set_assistant(&assistant);startup.set_wake_word(&detector2);startup.set_wake_word_on(&on);startup.set_wake_phrase(&none);startup.setup();assert(detector2.running);
}
'''


class ProductionFirmwareTests(unittest.TestCase):
    def test_production_select_and_assistant(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for path, content in STUBS.items():
                target = root / path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(content)
            source = root / "harness.cpp"
            source.write_text(HARNESS)
            executable = root / "harness"
            result = subprocess.run(["g++", "-std=c++20", "-I", str(root), "-I", str(COMPONENT),
                                     str(source), str(COMPONENT / "wake_phrase_select.cpp"),
                                     str(COMPONENT / "voice_assist.cpp"), "-o", str(executable)],
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            result = subprocess.run([str(executable)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)


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
