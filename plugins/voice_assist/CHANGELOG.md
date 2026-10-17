# Changelog

## 0.2.4 - 2026-10-17
- GUI-managed compatible microWakeWord models, optional catalogue presets and public JSON URLs. First installation
  requires an explicit choice; later an empty list allows manual-only activation.
- Wake phrase derives real names from installed models and preserves selection by stable model ID. Removal and
  corrupt preferences fail closed; historical stock selections migrate without depending on the new list order.
- One authoritative Wake phrase select gates detection on a subscribed Assist client; manual Ask remains independent.
- Add only needed model-name glyphs to existing fonts, with an on-screen ASCII ID fallback for unavailable characters.

## 0.2.3 - 2026-10-10
- A new wake sound.

## 0.2.2 - 2026-10-10
- New wake and thinking sounds. The thinking sound plays again as soon as it ends, so its own length sets the rhythm.

## 0.2.1 - 2026-10-10
- Its sounds play through Tessera's own sound player; on a screen whose microphone and speaker share one bus, a sound that cannot play while it listens is left out.

## 0.2.0 - 2026-10-10
- A short sound when the screen starts to listen, and a soft plop again and again while Assist thinks, each with a setting to turn it off (Wake sound, Thinking sound).
- In the top bar and on the tile, a microphone that lights up while it listens, dots in amber while it thinks and a speaker while it answers; the top bar item can show its icon alone.
- Needs the screen's speaker as well.

## 0.1.0 - 2026-10-10
- First version: Home Assistant's Assist on the screen, with a wake phrase recognised on the screen, a tile, a top bar item and two settings.
