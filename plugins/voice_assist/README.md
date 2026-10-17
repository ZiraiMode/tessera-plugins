# Voice assistant

Talk to Home Assistant's Assist from the screen. The screen listens for a wake phrase on its own, and only then sends
what you say to Home Assistant; the answer comes from the screen's speaker.

Speech to text, the conversation and text to speech are whatever your Home Assistant uses for Assist: its own
conversation agent with Whisper and Piper, Home Assistant Cloud, or an AI such as OpenAI or Claude. The screen is a
voice satellite in Home Assistant, in the area you give it.

## What you need

- A screen with a microphone and a speaker: a board that brings them (the reTerminal D1001) or a plugin that does.
- An Assist pipeline in Home Assistant (Settings, Voice assistants) with speech to text and text to speech.

## Set up

1. In Tessera, open **Plugins**, choose **Voice assistant** and tick your screens. Explicitly add at least one wake
   model for each new installation: an optional catalogue preset or a compatible public microWakeWord JSON URL.
   No model is preselected. Install builds once with only your chosen set.
2. In Home Assistant, open the screen's device (Settings, Devices) and choose its Assist pipeline under
   **Assist pipeline**, if it is not the preferred one.
3. Put the tile **Assistant** on a page: it says what the assistant does, and a tap asks a question without the wake
   phrase, or stops one.
4. Optional: add **Assistant** to a page's top bar (Top bar, Add, From plugins). It shows while the assistant listens,
   thinks or answers.

## On the screen

Hold the top bar, then **Settings**, **Plugins**, **Voice assistant**:

- **Wake word**: whether the screen listens for its wake phrase. Off, a tap on the tile still asks.
- **Wake phrase**: switch immediately between the models installed on this screen; no rebuild is needed.
- **Wake sound**: a short sound when the screen starts to listen, after the wake phrase or a tap.
- **Thinking sound**: a soft sound, again and again, while Home Assistant works out the answer.
- **Ask now**: asks a question at once.

The settings are entities of the screen in Home Assistant too ("Wake word", "Wake phrase", "Wake sound", "Thinking
sound"), and the editor shows them in the plugin's details on the screen's Plugins tab. The screen's own **Microphone** switch, on a board that has one,
silences it for the assistant as well.

The wake sound finishes before recording starts. Wake detection pauses while a question or reply is active and
resumes after the native assistant has finished, not merely when Home Assistant finishes generating its answer.
A second tap during the wake sound cancels the pending question.
The tile shows Preparing during startup and the wake sound, and Listening only after the native recording path starts.
On a half-duplex board, speak after the sound has ended, not over it. The core releases completed playback without
waiting for its silent output timeout; another active audio source still owns the speaker until it finishes.

## Manage wake models

In the plugin's build settings, add or remove catalogue models or public HTTPS JSON manifest URLs, then choose
**Apply and update screen**. Editing the draft never downloads or installs a model. Okay Nabu, Hey Jarvis (English)
and Hey Mycroft are optional catalogue presets, not automatically installed models. Other compatible models, such
as Алиса, use the same URL field. Their actual frontend timing must match the plugin's 10ms requirement and VAD;
changing metadata does not make an incompatible model work.

Ordinary upgrades preserve the installed set. After installation, removing all models is allowed: **Manual activation
only** keeps the tile and **Ask now** usable. The standalone ESPHome package also defaults to manual-only.
Adding/removing binaries requires a firmware update; choosing an already-installed Wake phrase does not.

Selection is saved by model ID, not list position. If the selected model is removed, voice activation remains off
until you explicitly choose an available model, even if the old model is later added again. The Wake word switch
keeps its preference but cannot start detection without a selected model and a subscribed Assist client.
Unknown/corrupt saved selection fails closed. Existing stock selection is migrated using historical IDs.

Model names come from native manifests. Duplicate names include IDs. Supported label characters are added to the
existing screen fonts (including Алиса); unavailable characters use an ASCII model ID on-screen only, while Home
Assistant retains the genuine name. Firmware compilation and real recognition remain the compatibility proof;
download limits do not guarantee the chosen model set fits the board.


## The sounds

They are two files in `components/voice_assist/sounds/`: `wake.wav` and `thinking.wav` (the screen plays it again as
soon as it ends, so its length sets the rhythm). Each is a WAV file of 16-bit samples, mono, at 48 kHz like the screen's speaker. A plugin of your
own made from this one can swap them; the build says so when a file is not such a WAV.

## Privacy

The wake phrase is recognised on the screen itself; nothing leaves the screen until it is heard or you tap the tile.
After that the question goes to your Home Assistant and on to whatever speech and conversation services its pipeline
uses.
