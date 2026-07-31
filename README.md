# Dikte

Press `Ctrl+Space` and talk. The recording is transcribed by whisper.cpp
on your own machine, a model on OpenRouter cleans it up (dropping the *uh*s, the
restarts, the missing punctuation), and the result lands in your clipboard and
is pasted into whatever window you were typing in. OpenAI and OpenRouter are
there as alternatives for the transcription too.

Runs on KDE Plasma 6 on Wayland, and on Windows 10 and 11. No dependencies
beyond system packages: just the Python standard library and PyQt6.

*[Türkçe README](README.tr.md)*

<p align="center">
  <img src="docs/settings-general.webp" width="820" alt="Dikte settings, General tab">
</p>

|  |  |
|---|---|
| <img src="docs/settings-api.webp" width="410" alt="API and models"> | <img src="docs/settings-cleanup.webp" width="410" alt="Cleanup rules"> |
| <img src="docs/settings-audio-file.webp" width="410" alt="Audio file"> | <img src="docs/settings-history.webp" width="410" alt="History"> |

## Install

### Linux

```sh
sudo pacman -S --needed pipewire-audio wl-clipboard ydotool ffmpeg python-pyqt6
sudo pacman -S --needed whisper-cpp      # local speech to text
sudo pacman -S --needed cuda             # its GPU backend, on an NVIDIA card
systemctl --user enable --now ydotool    # needed for auto-paste

./install.sh                 # or:  ./install.sh "Ctrl+Alt+Space"
dikte                        # the settings window opens on first run
```

`install.sh` adds the `dikte` command, a menu entry, an autostart entry and the
KDE shortcut.

### Windows

```powershell
winget install Python.Python.3.12
winget install Gyan.FFmpeg              # this is what records the microphone
pip install PyQt6

powershell -ExecutionPolicy Bypass -File .\install.ps1
dikte                                   # the settings window opens on first run
```

For local speech to text, download a [whisper.cpp
release](https://github.com/ggml-org/whisper.cpp/releases) and either put its
folder on `PATH` or point Settings → Local whisper at `whisper-server.exe`. The
CUDA build is the one to take on an NVIDIA card. Or skip it and transcribe
through OpenAI or OpenRouter, which needs nothing installed at all.

`install.ps1` adds the `dikte` command, a Start menu entry and an autostart
entry, and checks each dependency on the way. The shortcut is registered by
Dikte itself while it runs, so there is nothing to install for it and nothing to
log out for; `install.ps1 "Ctrl+Alt+Space"` writes a different one into the
settings.

Speech to text runs locally by default, on whisper.cpp. Pick a model under
Settings → API and models and press **Download**: `large-v3-turbo` (1.5 GB) is
the default, and the list runs from `tiny` up to `large-v3`. Models land in
`~/.local/share/dikte/models`, or `%LOCALAPPDATA%\dikte\models` on Windows.
Nothing of the audio leaves the machine, and it costs nothing per dictation.

Cleanup runs on **DeepSeek** (`deepseek-v4-flash`) or **OpenRouter**
(`google/gemini-3.5-flash-lite`), whichever you pick; the same choice also writes
the meeting minutes. It can be switched off, in which case the raw transcript is
pasted. Transcription can also be moved to **OpenAI** or **OpenRouter** under the
same tab, on a machine that would rather not run a model itself. The keys fall
back to `OPENAI_API_KEY`, `OPENROUTER_API_KEY` and `DEEPSEEK_API_KEY`, and are
stored in `~/.config/dikte/config.json` at mode 600, or in
`%APPDATA%\dikte\config.json`, which is inside your own profile.

One thing worth knowing about DeepSeek: it thinks unless it is told not to, and
cleanup is not a job worth thinking about. Measured on the example below,
thinking took six times as long for the same sentence, spent 95% of its output
tokens on the reasoning, and sometimes came back with nothing to paste at all.
So Dikte ships DeepSeek's cleanup with **Thinking: Off** and leaves the minutes,
which are worth thinking about, to think.

## Using it

| What | How |
| --- | --- |
| Start / stop recording | `Ctrl+Space`, or click the tray icon |
| Write what I say | the pen, or its shortcut |
| Have the agent do it | the spark |
| Read what was said and answered | the bubbles, or Tray menu → *History…* |
| Stop the recording | press any lobe again |
| Talk to Zeno | its shortcut, tray menu → *Talk to Zeno*, or `dikte zeno` |
| Cancel a recording | Tray menu → *Cancel recording*, or `dikte cancel` |
| Speak a command to an agent | Tray menu → *Ask Claude*, or `dikte ask` |
| Start / end a meeting | Tray menu → *Record a meeting*, or `dikte meeting` |
| Settings | Tray menu → *Settings*, or `dikte settings` |
| Reload after an update | Tray menu → *Restart*, or `dikte restart` |
| Quit | Tray menu → *Quit*, or `dikte quit` |

A small control sits on the edge of the screen, with three lobes. The pen
**writes**: what you say is tidied and put where the cursor is. The spark
**asks**: what you say goes to the agent and the answer comes back in writing.
The bubbles open the **history** — everything either of the other two has done,
in full, as a conversation you can read and copy out of.

The first two are separate buttons rather than one with a mode, because being
wrong about a mode means a note sent to an agent or a question typed into a
document. A lobe costs a few pixels and removes the question.

Press, talk, press: the second press is what ends a recording, and nothing is
listening for you to go quiet. What it hears appears in bubbles beside the
control — the sentence *as you are still saying it*, then what was done with it
— each staying between three and thirty seconds, worked out from how much there
is to read. Across the middle of the screen was tried, over a ribbon that moved
with the voice, and it is the wrong place: something that appears for every
sentence you dictate has no business in the middle of what you are working on.
An edge is where a running commentary belongs. Drag the control anywhere along
that edge. It is under Settings → Character, and turning it off puts everything
back the way it was.

Behind it, an indicator in the screen corner shows a red dot, a live waveform and the
elapsed time, then the stage it is on — while the character is on that corner
strip stays quiet, since two things reporting the same dictation from opposite
corners is one too many. It never takes focus. Pressing
`Ctrl+Space` again while Dikte is still working does nothing; nothing queues up.
A dictation and a command to the agent do wait on each other for the microphone,
which is one device, but for nothing else: each has its own indicator, and the
second one stacks above the first while both are up.

## Talking to it

Press a lobe, say what you want, and press again.

**Press, talk, press.** The first press opens the microphone and it stays open;
the second closes it. Nothing is listening for you to go quiet. Ending a
recording by waiting for silence was built first and taken out: a person hunting
for a word pauses, the recording ends mid-sentence, and the half that was cut is
the half you cared about — while a room with a fan in it never falls quiet at
all. A finger knows when a sentence has finished and nothing else does.

Which lobe you pressed is the whole of how it knows what you meant:

| What you press | What you say | What happens |
| --- | --- | --- |
| the pen | "bugün üç karar aldık" | the sentence is tidied and pasted at the cursor |
| the spark | "takvime perşembe üçe toplantı ekle" | Claude does it, and writes back what it did |
| the bubbles | — | opens the history |

Nothing is read out of the words, and that is deliberate. Dikte used to look at
the opening — "yaz", "not al", "metne dök" meant you wanted the words themselves
and everything else went to the agent. With one button that was the only way to
tell them apart; with three it is a trap, because "yaz bana bir e-posta taslağı"
is a thing you say *to* an assistant and would have been pasted into your
document instead of answered. The mistake a guess makes here cannot be taken
back, so nothing guesses.

Pressing while it is working calls it off — any lobe will do it, because hunting
for the right part of a button to stop something with would be nearly as bad as
having no way to stop it. A recording nobody ever stops is closed after five
minutes rather than left running, and what was said is kept. The shortcut is
under Settings → Shortcut; `dikte zeno` does the same from a terminal.

### The history

The third lobe opens it: everything either of the other two has done, oldest
first, as a conversation. Your request on one side, the answer on the other,
rendered as markdown — headings, lists, tables and fenced code all come out as
they were written. There is a **Copy** on every answer and a **Copy all as
markdown** at the foot of the window, and it can be widened when an answer has a
wide table in it.

It is a window rather than a tooltip because of what is in it. An answer from an
agent is not a line of status text: it is paragraphs, and it is the thing you
actually wanted. It used to appear in a bubble that faded after eleven seconds,
which was the wrong shape for it.

The bubbles beside the control are still there and still fade — they are the
glance, not the record. What is happening, in the corner of your eye, gone in a
few seconds. Nothing is lost when one goes; all of it is behind the third lobe.
The panel is kept between runs, in `history.jsonl` beside the recordings.

**There is no speech.** There was: Piper, a Turkish voice picked by measuring
the fundamental frequency of all three rather than by reading their names, and a
window to hear it in. It was taken out with the third lobe. An answer worth
having is worth being able to read twice, and a spoken one is gone the moment it
finishes. Everything the agent says now arrives in writing, which is also why it
is no longer told to answer in plain sentences: markdown is how an answer should
look when it is read.

## What it does

- **The sentence is read back while it is still being said.** Every second or
  so the audio recorded *so far* goes to the same whisper.cpp server, and what
  comes back replaces the previous guess in the bubble. There is no streaming
  model and no second code path: it works because the machine is far faster than
  the speaking — measured at forty to sixty times real time on an RTX 4060, so
  a sentence in progress is re-read in a fraction of the time it took to say.
  Re-reading the whole thing rather than a window is what lets it improve as
  context arrives, and it is the reason the preview visibly corrects itself
  ("paye tuta" becoming "PyQt" a second later), the way every live captioner
  does. None of that reaches the clipboard: what gets pasted, cleaned up or
  handed to the agent is always the full pass made after you stop. It only runs
  against local whisper, because on a hosted provider every second of talking
  would be a request that costs money and arrives late.
- **Transcription runs on this machine.** whisper.cpp is kept alive as a server
  next to Dikte, on the `/v1/audio/transcriptions` path the hosted providers
  use, which is what makes it one more base URL rather than a second code path:
  dictation, file transcription, subtitles and meetings all go through it
  unchanged. The model is loaded while Dikte starts rather than on the first
  dictation, so a few seconds of speech comes back in about as long as it took
  to say — the loading is the slow part, not the transcribing. Turn that off
  under Settings → Local whisper to keep the graphics memory free.
- **Silence never reaches the model.** Handed near-silence, a transcription model
  invents a sentence instead of returning nothing ("Thanks for watching", or in
  Turkish "Altyazı M.K."). A recording is dropped when nothing rose 10 dB above
  *that recording's own* noise floor for at least 0.3 s, which is also what
  removes steady fan noise however loud, or when its loud end sits below
  -55 dBFS. The indicator reports the level it measured, which is what you
  calibrate the threshold against.
- **Misheard words are repaired.** Speech models fail phonetically on proper
  nouns, so the cleanup model is asked to fix those from context, and to leave
  the word alone when the context does not make the intended one clear. The names
  you list under Cleanup rules go to the transcription model as a hint and to the
  cleanup model as a glossary, which is what lets it recognise "kuber netis":

  ```
  raw    ıı bugün şey kuber netis üzerinde çalışan servisleri güncelledim
         yani sonra grafanada bir panel açtım hani ve pay kut ile arayüzü
         şey bitirdim işte

  result Bugün Kubernetes üzerinde çalışan servisleri güncelledim. Sonra
         Grafana'da bir panel açtım ve PyQt ile arayüzü bitirdim.
  ```
- **A failed cleanup is never silent.** The raw transcript is still pasted so the
  dictation is not lost, but the indicator turns amber with the reason instead of
  looking like a normal run.
- **A dictation can be a command instead.** Its own shortcut sends the
  transcript to Claude Code (`claude -p`) rather than pasting it, and pastes back
  what comes of it: the answer, or a sentence saying what was done. It is the
  session you would have opened yourself, so your skills and connected services
  are there, which is what makes "put that in my calendar on Thursday at three"
  a thing you can say to a window that is not Claude. Codex (`codex exec`) runs
  the same way, and OpenRouter is there as a plain question-and-answer fallback
  for a machine with neither CLI on it. Provider, model, permissions and working
  directory are under Settings → Agent, and commands close together stay in one
  conversation.
- **Meetings** are recorded from the microphone and the speaker output at the
  same time, which settles who said what by the channel a voice arrived on
  instead of guessing at it. The two sides are transcribed separately and
  interleaved into one timestamped transcript, and a second model, configured
  under Settings → Meeting along with its own instruction, turns that into
  minutes: decisions, action items, open questions. They land in
  `~/.local/share/dikte/meetings` (`%LOCALAPPDATA%\dikte\meetings`) and in
  Settings → Minutes. A run that fails
  keeps its recording, and a retry resumes from the transcript it already paid
  for.
- **Audio and video files** run through the same models under Settings → Audio
  file, optionally with `[mm:ss]` timestamps, chunked through ffmpeg when long,
  and saved as `.txt` or as `.srt` subtitles; their cleanup follows its own rules,
  written for subtitles, so the lines keep their place and nothing is shortened.
- **History** of every dictation under Settings → History, with a size limit and
  right-click to delete.
- **Turkish and English interface**, following the system locale by default.

## On KDE, the global shortcut needs one logout

KWin only reads `kglobalshortcutsrc` at startup, so the shortcut `install.sh`
writes will not fire until you log out and back in. Until then, Settings →
Shortcut → **built-in listener** reads `/dev/input` and catches the combination
itself. The difference: it does not swallow the key, so `Ctrl+Space` also reaches
the focused application (some editors will pop up autocomplete). The listener
needs your user in the `input` group: `sudo usermod -aG input $USER`.

None of which applies on Windows, where `RegisterHotKey` is the whole mechanism:
Dikte asks the system for the combination while it runs and has it from the
moment it starts, no logout, and nothing else on the desktop sees the key while
Dikte holds it. The other side of that is that a combination another application
already holds cannot be had at all — Settings → Shortcut says so when that
happens, and another combination is the answer.

## What is different on Windows

- **The microphone comes through ffmpeg**, on its DirectShow input, because
  there is no pw-record. Which means a recording starts about a third of a
  second after the key press: that is what opening a DirectShow device costs,
  and the indicator appearing before the first sample arrives is the visible
  edge of it. Press, pause half a beat, then speak.
- **A meeting needs a loopback device to exist.** Every PipeWire output has a
  `.monitor` source to record from; Windows has one only if the sound card
  offers "Stereo Mix" and somebody switched it on under Sound → Recording, or if
  a virtual cable such as VB-CABLE is installed. Settings → Meeting says so when
  there is none, rather than letting an hour be recorded half empty. Dictation
  needs none of this.
- **The clipboard and the key press are the system's own**, through user32
  rather than through wl-clipboard and ydotool, so there is nothing to install
  and no daemon to keep running. One limit comes with it: a window running as
  administrator only accepts a synthesised key press from an application running
  as administrator too, so auto-paste into one needs Dikte started the same way.
- **The tray icon is drawn rather than themed**, since Windows ships no icon
  theme: a blue microphone waiting, a red dot recording, an amber ring working.

## Layout

```
dikte.py          entry point, tray icon, state machine, IPC
plat.py           what the two platforms do differently, in one place
companion.py      the three-lobed control, and the bubbles beside it
chat.py           the history as a conversation, with markdown answers
history.py        what was asked and what came back, kept between runs
theme.py          one palette, one set of shapes, one stylesheet
conversation.py   the loop from the first press to the answer
live.py           re-reading the audio so far, while it is still being spoken
audio.py          PCM capture: pw-record or ffmpeg, and the device lists
meeting.py        channel split, speaker labelling, cleanup, minutes
assistant.py      running a dictation through Claude Code, Codex or OpenRouter
api.py            transcription on any provider, OpenRouter cleanup (stdlib only)
whispercpp.py     the local whisper.cpp server and its model downloads
worker.py         transcribe → clean up → clipboard → paste
vad.py            deciding whether a recording holds speech at all
filetranscribe.py file transcription: ffmpeg, chunking, timestamps
overlay.py        the corner indicator
icons.py          the tray icon, themed on Linux and drawn on Windows
settings_ui.py    settings window
hotkey.py         the KDE shortcut, the evdev listener, RegisterHotKey
paste.py          the clipboard and the key press, on either platform
i18n.py           the string table
```

On Wayland the indicator is drawn through XWayland, because a Wayland client
cannot place a window in a screen corner; `dikte.py` sets `QT_QPA_PLATFORM=xcb`
for that, and leaves it alone everywhere else.

## License

GPL-3.0, see [LICENSE](LICENSE).
