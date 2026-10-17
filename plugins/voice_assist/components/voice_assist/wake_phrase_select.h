#pragma once

#include <array>
#include "esphome/core/component.h"
#include "esphome/core/preferences.h"
#include "esphome/components/select/select.h"
#include "esphome/components/micro_wake_word/streaming_model.h"

namespace esphome::voice_assist {

struct WakeModelEntry {
  micro_wake_word::WakeWordModel *model;
  std::array<uint8_t, 32> identity;
  const char *screen_label;
};

struct WakeSelection {
  uint8_t selected;
  std::array<uint8_t, 32> identity;
};
static_assert(sizeof(WakeSelection) == 33);

enum class StoredRead { MISSING, FOUND, INVALID };
StoredRead read_stored(uint32_t key, void *out, size_t size);

class WakePhraseSelect : public select::Select, public Component {
 public:
  void setup() override;
  float get_setup_priority() const override { return setup_priority::DATA; }
  void set_models(const WakeModelEntry *models, size_t count) { models_ = models; count_ = count; }
  const char *screen_label_at(size_t index) const { return index < count_ ? models_[index].screen_label : ""; }
  bool accepts(const std::string &word) const;

 protected:
  void control(size_t index) override;
  void apply_(size_t index);
  void unselect_();
  void restore_historical_(size_t index);
  const WakeModelEntry *models_{};
  size_t count_{};
  ESPPreferenceObject preference_;
};

}  // namespace esphome::voice_assist
