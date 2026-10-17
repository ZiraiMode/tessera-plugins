#include "voice_assist.h"

#include "esphome/core/hal.h"

namespace esphome::voice_assist {

using tessera::Font;
namespace ui = tessera::ui;

// Icons of Tessera's set: the assistant, listening, thinking, answering, and the assistant that could not help.
static constexpr uint32_t ICON_ASSISTANT = 0xF06A9;   // robot
static constexpr uint32_t ICON_LISTENING = 0xF036C;   // microphone
static constexpr uint32_t ICON_THINKING = 0xF01D8;    // dots-horizontal
static constexpr uint32_t ICON_ANSWERING = 0xF057E;   // volume-high
static constexpr uint32_t ICON_FAILED = 0xF169F;      // robot-confused
// How long a reply or a failure stays on the tile after it was spoken.
static constexpr uint32_t REPLY_SHOWN_MS = 20000;
static bool is_on(switch_::Switch *s) { return s == nullptr || s->state; }

// The tile: the assistant's icon, what it does now, and under it what it heard or answered. A tap asks, or stops.
class AssistTile : public tessera::Tile {
 public:
  explicit AssistTile(VoiceAssist *plugin) : plugin_(plugin) {}

  void create(const tessera::TileContext &c) override {
    width_ = c.width;
    height_ = c.height;
    wide_ = c.columns >= 2 && c.width > c.height * 3 / 2;
    icon_ = ui::label(c.parent, Font::ICON, theme::MUTED);
    lv_obj_set_style_text_align(icon_, LV_TEXT_ALIGN_CENTER, 0);
    status_ = ui::label(c.parent, Font::TITLE, theme::INK);
    detail_ = ui::label(c.parent, Font::BODY, theme::INK_SOFT);
    lv_label_set_long_mode(detail_, LV_LABEL_LONG_DOT);
    if (!wide_) {
      lv_obj_set_style_text_align(status_, LV_TEXT_ALIGN_CENTER, 0);
      lv_obj_set_style_text_align(detail_, LV_TEXT_ALIGN_CENTER, 0);
    }
  }

  void on_tick(uint32_t) override {
    const Phase phase = plugin_->current();
    const bool busy = phase == Phase::PREPARING || phase == Phase::LISTENING ||
                      phase == Phase::THINKING || phase == Phase::ANSWERING;
    const bool failed = plugin_->showing_failure();
    ui::set_text(icon_, ui::icon(plugin_->phase_icon()));
    ui::set_tone(icon_, plugin_->phase_tone(), theme::MUTED);
    std::string status = busy || failed ? plugin_->phase_word() : plugin_->idle_line();
    // Under it: what was heard while it thinks, the reply while and after it answers.
    std::string detail;
    if (phase == Phase::THINKING) detail = plugin_->question();
    else if (phase == Phase::ANSWERING || plugin_->reply_fresh()) detail = plugin_->reply();
    layout(status, detail);
  }

  void on_theme() override {
    ui::set_color(status_, theme::INK);
    ui::set_color(detail_, theme::INK_SOFT);
    on_tick(0);
  }

  void on_tap() override { plugin_->ask(); }

 private:
  // The icon, the status line and as many lines of the detail as fit: beside each other on a wide card, under each
  // other on any other. The status takes the largest of the screen's fonts that fits.
  void layout(const std::string &status, const std::string &detail) {
    const int icon_h = ui::line_height(Font::ICON);
    const int text_w = wide_ ? width_ - icon_h - ui::px(12) : width_;
    Font face = Font::BODY;
    for (Font f : {Font::HEADLINE, Font::TITLE, Font::BODY_LARGE, Font::BODY}) {
      face = f;
      if (ui::text_width(status, f) <= text_w) break;
    }
    ui::set_font(status_, face);
    ui::set_text(status_, status);
    ui::set_text(detail_, detail);
    const int status_h = ui::line_height(face), line_h = ui::line_height(Font::BODY);
    if (wide_) {
      lv_obj_set_pos(icon_, 0, (height_ - icon_h) / 2);
      lv_obj_set_size(icon_, icon_h, icon_h);
      const int lines = detail.empty() ? 0 : std::max(1, std::min(3, (height_ - status_h) / line_h));
      const int top = (height_ - status_h - lines * line_h) / 2;
      lv_obj_set_pos(status_, icon_h + ui::px(12), top);
      lv_obj_set_size(status_, text_w, status_h);
      lv_obj_set_pos(detail_, icon_h + ui::px(12), top + status_h);
      lv_obj_set_size(detail_, text_w, lines ? lines * line_h : 1);
      return;
    }
    const int room = height_ - icon_h - status_h;
    const int lines = detail.empty() || room < line_h ? 0 : std::min(3, room / line_h);
    const int top = std::max(0, (height_ - icon_h - status_h - lines * line_h) / 2);
    lv_obj_set_pos(icon_, 0, top);
    lv_obj_set_size(icon_, width_, icon_h);
    lv_obj_set_pos(status_, 0, top + icon_h);
    lv_obj_set_size(status_, width_, status_h);
    lv_obj_set_pos(detail_, 0, top + icon_h + status_h);
    lv_obj_set_size(detail_, width_, lines ? lines * line_h : 1);
  }

  VoiceAssist *plugin_;
  int width_ = 0, height_ = 0;
  bool wide_ = false;
  lv_obj_t *icon_{}, *status_{}, *detail_{};
};

void VoiceAssist::setup() {
  add_tile("assist", [this]() { return new AssistTile(this); });
  add_bar_item("busy", [this]() {
    tessera::BarItem item;
    const bool fresh_failure = showing_failure();
    if (busy() || phase_ == Phase::PREPARING || phase_ == Phase::LISTENING ||
        phase_ == Phase::THINKING || phase_ == Phase::ANSWERING || fresh_failure) {
      item.shown = true;
      item.icon = phase_icon();
      item.tone = phase_tone();
      item.text = phase_word();
    }
    return item;
  });
  if (wake_phrase_ != nullptr) {
    wake_phrase_->add_on_state_callback([this](size_t) {
      // Even two models with the same spoken phrase are distinct GUI choices.
      if (request_ != Request::NONE && !request_word_.empty()) cancel_request_();
      tessera::refresh();
      sync_wake();
    });
  }
  setup_complete_ = true;
  sync_wake();
}


bool VoiceAssist::settings(tessera::SettingsPage &page) {
  page.icon = "\U000F06A9";
  page.toggle(text("wake_word"), [this] { return wake_word_on_ != nullptr && wake_word_on_->state; },
              [this](bool on) { on ? wake_word_on_->turn_on() : wake_word_on_->turn_off(); });
  if (wake_phrase_ != nullptr && wake_phrase_->size() != 0) {
    std::vector<std::string> options;
    for (size_t i = 0; i < wake_phrase_->size(); ++i) options.emplace_back(wake_phrase_->screen_label_at(i));
    page.choice(text("wake_phrase"), options,
                [this] { auto index = wake_phrase_->active_index(); return index.has_value() ? (int) *index : -1; },
                [this](int index) { wake_phrase_->make_call().set_index((size_t) index).perform(); });
  } else {
    page.info(text("wake_phrase"), [this] { return std::string(text("manual_only")); });
  }
  page.toggle(text("wake_sound"), [this] { return is_on(wake_sound_on_); },
              [this](bool on) { if (wake_sound_on_ != nullptr) on ? wake_sound_on_->turn_on() : wake_sound_on_->turn_off(); });
  page.toggle(text("thinking_sound"), [this] { return is_on(thinking_sound_on_); },
              [this](bool on) {
                if (thinking_sound_on_ != nullptr) on ? thinking_sound_on_->turn_on() : thinking_sound_on_->turn_off();
              });
  page.action(text("ask"), "\U000F06A9", [this] { ask(); }, nullptr,
              [this]() -> std::string { return busy() ? phase_word() : std::string(); })
      .active([this] { return busy(); });
  return true;
}

void VoiceAssist::loop() {
  const bool running = assistant_ != nullptr && assistant_->is_running();
  if (!running && request_ == Request::NONE) {
    stopping_ = false;
    thinking_allowed_ = false;
    stop_sound_();
    if (phase_ != Phase::IDLE && phase_ != Phase::FAILED) phase(Phase::IDLE);
  }
  // A native follow-up turn remains running: do not restart wake inference between turns.
  if (running && !stopping_ && thinking_allowed_ && phase_ == Phase::THINKING &&
      is_on(thinking_sound_on_) && !sound_active_) {
    sounds_.play(thinking_sound_);
    sound_active_ = sounds_.playing();
  }
  if (phase_ == Phase::THINKING && !is_on(thinking_sound_on_)) stop_sound_();
  loop_sound_();
  sync_wake();
  advance_request_();
}

void VoiceAssist::stop_sound_() {
  sounds_.stop();
  if (sound_active_ && !sound_finishing_) {
    // Stop producing samples, but drain only our own speaker input, not the native response.
    speaker_->finish();
    sound_finishing_ = true;
  }
}

void VoiceAssist::loop_sound_() {
  if (!sound_active_) return;
  sounds_.loop();
  if (sounds_.playing()) return;
  if (!sound_finishing_) {
    // Submission (including SoundPlayer's no-progress exit) is not playback completion.
    speaker_->finish();
    sound_finishing_ = true;
    return;
  }
  // Check on a later loop: finish() must also cancel a speaker start still queued in STOPPED.
  if (speaker_->is_stopped()) {
    sound_active_ = false;
    sound_finishing_ = false;
  }
}

void VoiceAssist::phase(Phase p) {
  if (p != Phase::THINKING) stop_sound_();
  if (stopping_ && (p == Phase::LISTENING || p == Phase::THINKING)) return;
  if (p == Phase::THINKING && !thinking_allowed_) return;
  if (p != Phase::THINKING) thinking_allowed_ = p == Phase::LISTENING;
  // HA on_end closes the pipeline's thinking feeder, not necessarily native reply playback.
  // Keep the current busy visual until loop() observes native idle.
  if (p == Phase::IDLE && assistant_ != nullptr && assistant_->is_running()) return;
  // A failure stays visible after the pipeline ends.
  if (p != Phase::IDLE || phase_ != Phase::FAILED) phase_ = p;
  if (p == Phase::LISTENING) {
    heard_.clear();
    answer_.clear();
  }
  tessera::refresh();
}

void VoiceAssist::heard(const std::string &text) {
  heard_ = text;
  tessera::refresh();
}

void VoiceAssist::answer(const std::string &text) {
  // The answer is about to play on the same speaker: a plop that is still going stops here.
  stop_sound_();
  thinking_allowed_ = false;
  answer_ = text;
  answered_at_ = millis();
  phase_ = Phase::ANSWERING;
  tessera::refresh();
}

void VoiceAssist::failed(const std::string &code, const std::string &message) {
  cancel_request_();
  ESP_LOGW("voice_assist", "Assist failed: %s (%s)", code.c_str(), message.c_str());
  answer_ = message.empty() ? code : message;
  answered_at_ = millis();
  phase_ = Phase::FAILED;
  tessera::refresh();
}

bool VoiceAssist::wake_eligible_() const {
  return setup_complete_ && assistant_ != nullptr && assistant_->get_api_connection() != nullptr &&
         wake_word_on_ != nullptr && wake_word_on_->state &&
         wake_phrase_ != nullptr && wake_phrase_->active_index().has_value();
}

void VoiceAssist::sync_wake() {
  if (request_ != Request::NONE &&
      (assistant_ == nullptr || assistant_->get_api_connection() == nullptr ||
       (!request_word_.empty() && (!wake_eligible_() || !wake_phrase_->accepts(request_word_)))))
    cancel_request_();
  if (!setup_complete_ && !wake_start_pending_ && !wake_stop_pending_ &&
      (wake_word_ == nullptr || !wake_word_->is_running())) return;
  if (wake_word_ == nullptr) return;

  const bool wanted = wake_eligible_() && !busy() && !sound_active_;
  const bool running = wake_word_->is_running();
  if (running) wake_start_pending_ = false;
  if (!wanted && (running || wake_start_pending_)) wake_stop_pending_ = true;
  if (wake_stop_pending_) {
    if (running) {
      if (!wake_stop_sent_) {
        wake_word_->stop();
        wake_stop_sent_ = true;
      }
      return;
    }
    // stop() in STOPPED ignores a queued start. Keep shutdown intent until it becomes visible.
    if (wake_start_pending_) return;
    wake_stop_pending_ = false;
    wake_stop_sent_ = false;
  }
  if (wanted && !running && !wake_start_pending_ && wake_word_->is_ready() && !wake_word_->is_failed()) {
    wake_word_->start();
    wake_start_pending_ = true;
  }
}

bool VoiceAssist::accepts_wake_word(const std::string &word) const {
  return wake_eligible_() && !busy() && !sound_active_ && !wake_stop_pending_ && wake_phrase_->accepts(word);
}

void VoiceAssist::begin_request_(const std::string &word) {
  request_word_ = word;
  request_ = Request::STOPPING_WAKE;
  stopping_ = false;
  thinking_allowed_ = false;
  phase_ = Phase::PREPARING;
  heard_.clear();
  answer_.clear();
  sync_wake();
  tessera::refresh();
}

void VoiceAssist::advance_request_() {
  if (request_ == Request::NONE) return;
  if (request_ == Request::STOPPING_WAKE) {
    if (wake_start_pending_ || wake_stop_pending_ || (wake_word_ != nullptr && wake_word_->is_running()) ||
        sound_active_) return;
    if (is_on(wake_sound_on_)) {
      sounds_.play(wake_sound_);
      sound_active_ = sounds_.playing();
      if (sound_active_) {
        request_ = Request::BEEP;
        return;
      }
    }
  }
  if (sound_active_) return;
  // Recheck immediately before capture; no queued request can survive disconnect or a changed wake choice.
  if (assistant_ == nullptr || assistant_->get_api_connection() == nullptr || assistant_->is_running() ||
      (!request_word_.empty() && (!wake_eligible_() || !wake_phrase_->accepts(request_word_)))) {
    cancel_request_();
    return;
  }
  assistant_->set_wake_word(request_word_);  // Empty on tap: do not reuse the previous detected phrase.
  request_word_.clear();
  request_ = Request::NONE;
  assistant_->request_start(false, true);
}

void VoiceAssist::cancel_request_() {
  request_ = Request::NONE;
  request_word_.clear();
  thinking_allowed_ = false;
  stop_sound_();
  if (phase_ != Phase::FAILED) phase_ = Phase::IDLE;
}

void VoiceAssist::wake(const std::string &word) {
  if (accepts_wake_word(word)) begin_request_(word);
}

void VoiceAssist::ask() {
  if (busy()) {
    stop();
    return;
  }
  if (setup_complete_ && assistant_ != nullptr && assistant_->get_api_connection() != nullptr)
    begin_request_("");
}

void VoiceAssist::stop() {
  cancel_request_();
  stopping_ = assistant_ != nullptr && assistant_->is_running();
  if (stopping_) assistant_->request_stop();
  sync_wake();
  tessera::refresh();
}

void VoiceAssist::before_update() {
  setup_complete_ = false;
  stop();
}

bool VoiceAssist::reply_fresh() const {
  return answered_at_ != 0 && millis() - answered_at_ < REPLY_SHOWN_MS;
}

std::string VoiceAssist::idle_line() const {
  if (assistant_ == nullptr || assistant_->get_api_connection() == nullptr) return text("away");
  if (wake_word_on_ != nullptr && wake_word_on_->state && wake_phrase_ != nullptr) {
    auto index = wake_phrase_->active_index();
    if (index.has_value())
      return tessera::fill(text("say_phrase"), "phrase", std::string(wake_phrase_->screen_label_at(*index)));
  }
  return text("tap_to_ask");
}

uint32_t VoiceAssist::phase_icon() const {
  switch (phase_) {
    case Phase::PREPARING: return ICON_ASSISTANT;
    case Phase::LISTENING: return ICON_LISTENING;
    case Phase::THINKING: return ICON_THINKING;
    case Phase::ANSWERING: return ICON_ANSWERING;
    case Phase::FAILED: return showing_failure() ? ICON_FAILED : ICON_ASSISTANT;
    default: return ICON_ASSISTANT;
  }
}

tessera::Tone VoiceAssist::phase_tone() const {
  switch (phase_) {
    case Phase::PREPARING: return tessera::Tone::BUSY;
    case Phase::LISTENING: return tessera::Tone::ACCENT;
    case Phase::THINKING: return tessera::Tone::BUSY;
    case Phase::ANSWERING: return tessera::Tone::ACCENT;
    case Phase::FAILED: return showing_failure() ? tessera::Tone::ALERT : tessera::Tone::NORMAL;
    default: return tessera::Tone::NORMAL;
  }
}

std::string VoiceAssist::phase_word() const {
  // A failure that is no longer fresh is quiet again.
  if (phase_ == Phase::FAILED && !reply_fresh()) return idle_line();
  switch (phase_) {
    case Phase::PREPARING: return text("preparing");
    case Phase::LISTENING: return text("listening");
    case Phase::THINKING: return text("thinking");
    case Phase::ANSWERING: return text("answering");
    case Phase::FAILED: return text("failed");
    default: return idle_line();
  }
}

}  // namespace esphome::voice_assist
