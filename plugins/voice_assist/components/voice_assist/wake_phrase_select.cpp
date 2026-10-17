#include "wake_phrase_select.h"

#include "esphome/components/esp32/preferences.h"
#include "esphome/core/helpers.h"
#include <nvs.h>

namespace esphome::voice_assist {
namespace {
constexpr uint32_t SELECTION_VERSION = 0x56415001;
constexpr const char *HISTORICAL_IDS[] = {"va_okay_nabu", "va_hey_jarvis", "va_hey_mycroft"};
}

StoredRead read_stored(uint32_t key, void *out, size_t size) {
  if (global_preferences == nullptr) return StoredRead::INVALID;
  const auto handle = static_cast<esp32::ESP32Preferences *>(global_preferences)->nvs_handle;
  if (handle == 0) return StoredRead::INVALID;
  char name[UINT32_MAX_STR_SIZE];
  uint32_to_str(name, key);
  size_t length = 0;
  auto result = nvs_get_blob(handle, name, nullptr, &length);
  if (result == ESP_ERR_NVS_NOT_FOUND) return StoredRead::MISSING;
  if (result != ESP_OK || length != size) return StoredRead::INVALID;
  result = nvs_get_blob(handle, name, out, &length);
  return result == ESP_OK && length == size ? StoredRead::FOUND : StoredRead::INVALID;
}

void WakePhraseSelect::unselect_() {
  for (size_t i = 0; i < count_; ++i)
    if (models_[i].model->is_enabled()) models_[i].model->disable();
  WakeSelection selection{};
  preference_.save(&selection);
}

void WakePhraseSelect::apply_(size_t index) {
  for (size_t i = 0; i < count_; ++i) {
    auto *model = models_[i].model;
    if (i == index) {
      if (!model->is_enabled()) model->enable();
    } else if (model->is_enabled()) model->disable();
  }
  WakeSelection selection{};
  selection.selected = 1;
  selection.identity = models_[index].identity;
  preference_.save(&selection);
  publish_state(index);
}

void WakePhraseSelect::restore_historical_(size_t index) {
  if (index < 3) {
    for (size_t i = 0; i < count_; ++i) {
      if (models_[i].model->get_id() == HISTORICAL_IDS[index]) {
        apply_(i);
        return;
      }
    }
  }
  unselect_();
}

void WakePhraseSelect::setup() {
  preference_ = make_entity_preference<WakeSelection>(SELECTION_VERSION);
  WakeSelection selection{};
  auto status = read_stored(get_preference_hash() ^ SELECTION_VERSION, &selection, sizeof(selection));
  if (status != StoredRead::MISSING) {
    if (status == StoredRead::FOUND && selection.selected == 1) {
      for (size_t i = 0; i < count_; ++i) {
        if (selection.identity == models_[i].identity) {
          apply_(i);
          return;
        }
      }
    }
    // Missing identities and corrupt records are saved tombstones, not fresh installs.
    unselect_();
    return;
  }

  size_t legacy_index = 0;
  status = read_stored(get_preference_hash(), &legacy_index, sizeof(legacy_index));
  if (status == StoredRead::FOUND) {
    restore_historical_(legacy_index);
    return;
  }
  if (status == StoredRead::INVALID) {
    unselect_();
    return;
  }

  size_t found = 0, enabled = 0, selected = 0;
  for (size_t i = 0; i < 3; ++i) {
    uint8_t value = 0;
    status = read_stored(fnv1_hash(HISTORICAL_IDS[i]), &value, sizeof(value));
    if (status == StoredRead::INVALID || (status == StoredRead::FOUND && value > 1)) {
      unselect_();
      return;
    }
    if (status == StoredRead::FOUND) {
      ++found;
      if (value == 1) { ++enabled; selected = i; }
    }
  }
  if (found == 3 && enabled == 1) restore_historical_(selected);
  else if (found == 0 && count_ != 0) apply_(0);
  else unselect_();
}

void WakePhraseSelect::control(size_t index) {
  if (index < count_) apply_(index);
}

bool WakePhraseSelect::accepts(const std::string &word) const {
  auto index = active_index();
  return index.has_value() && *index < count_ && models_[*index].model->get_wake_word() == word;
}

}  // namespace esphome::voice_assist
