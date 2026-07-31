# Dikte

Say **Zeno**, or press `Ctrl+Space`, and talk. The recording is transcribed by whisper.cpp
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
| Talk to Zeno | say its name, tray menu → *Talk to Zeno*, or `dikte zeno` |
| Stop it talking | click the sphere |
| Cancel a recording | Tray menu → *Cancel recording*, or `dikte cancel` |
| Speak a command to an agent | Tray menu → *Ask Claude*, or `dikte ask` |
| Start / end a meeting | Tray menu → *Record a meeting*, or `dikte meeting` |
| Settings | Tray menu → *Settings*, or `dikte settings` |
| Reload after an update | Tray menu → *Restart*, or `dikte restart` |
| Quit | Tray menu → *Quit*, or `dikte quit` |

A sphere sits on the edge of the screen and is what you talk to: it lights up
and swells with your voice while you speak, writes the sentence in a bubble
beside it *as you are still saying it*, and then says what it did with it — the
text it pasted, or the agent's answer. Bubbles stay between three and thirty
seconds, worked out from how much there is to read. Drag it anywhere along the
edge; click it instead of pressing the shortcut. It is under Settings → Character,
along with its size, its side and how long the bubbles last, and turning it off
puts everything back the way it was.

Behind it, an indicator in the screen corner shows a red dot, a live waveform and the
elapsed time, then the stage it is on — while the character is on that corner
strip stays quiet, since two things reporting the same dictation from opposite
corners is one too many. It never takes focus. Pressing
`Ctrl+Space` again while Dikte is still working does nothing; nothing queues up.
A dictation and a command to the agent do wait on each other for the microphone,
which is one device, but for nothing else: each has its own indicator, and the
second one stacks above the first while both are up.

## Talking to it

Say its name — **Zeno** — wait for the sphere to light up, then say what you
want. It works out which of two things you meant:

| What you say | What happens |
| --- | --- |
| "Zeno" … "yaz, bugün üç karar aldık" | the sentence is tidied and pasted at the cursor |
| "Zeno" … "takvime perşembe üçe toplantı ekle" | Claude does it, and says what it did |

The opening decides. "Yaz", "not al", "metne dök", "write this down" and their
neighbours mean you want the words themselves; everything else goes to the
agent. Only the opening is looked at, which is what keeps "sonra sana yazarım"
out of your clipboard. The list is in Settings → Shortcut and can be added to.

The answer is spoken, and also appears in a bubble. Turn the voice off and only
the bubble is left. When it is on, the agent is told it is being listened to
rather than read, so it answers in a sentence instead of in headings and bullet
points.

You do not have to say the name at all: the tray menu and `dikte zeno` start the same conversation, which is also the only way in until the name has been recorded in your voice, and the answer in a room where saying a name out loud is not on. Clicking the sphere while it is talking or working calls it off.

Waking it needs the name on its own, with a pause after it. "Zeno, put that in
my calendar" said in one breath does not work, and that was measured rather than
assumed — see the note under **Hearing its name** below.

### Hearing its name

There is no model here and nothing running in the cloud. The name is recorded
four times in your own voice under Settings → Shortcut → *Record the phrase*,
its mel-cepstral shape is kept, and what the microphone hears is compared
against those recordings by dynamic time warping — the method that came before
the trained networks, and the one that is still right when there is exactly one
speaker to recognise.

Energy alone decides where an utterance starts and ends, so a quiet room costs
one comparison per block and no arithmetic at all; only what falls between those
two points is turned into features, at about nine milliseconds a second of
speech. Holding the microphone open does not stop anything else using it — two
captures of one device were checked to coexist — but Windows will show its
microphone indicator for as long as Dikte runs, which is the honest sign that
something is listening. It is off until you turn it on.

What it costs you is that it knows *your* voice saying it, in the room you
recorded it in, and not much else. On synthesised speech the name alone scored
0.73 and 0.78 against a limit of 1.0, and the nearest of six decoys — including
"Zeynep" and "Hey dostum" — scored 2.12. A real voice varies more than a
synthesiser does.

Saying the name and the instruction in one breath was built, fixed twice, and
then removed: matching the name against the front of a longer utterance let
speech that was *not* the name score better than the name followed by an
instruction, so no threshold separated them and there was nothing to tune. The
code that promised it is gone rather than left in looking like it works.

### Its voice

Piper, standing next to whisper.cpp and ffmpeg: a program with a voice in a
file, nothing imported into Dikte, nothing downloaded at run time, nothing sent
anywhere. Install it and put the voice next to the models:

```powershell
# piper.exe from https://github.com/rhasspy/piper/releases
#   -> %LOCALAPPDATA%\Programs\piper\
# tr_TR-fettah-medium.onnx and .onnx.json from
#   https://huggingface.co/rhasspy/piper-voices/tree/main/tr/tr_TR
#   -> %LOCALAPPDATA%\dikte\voices\
```

Settings → Shortcut → Its voice → **Try the voice…** opens a window to hear it
in, and to watch it work. What is *said* is not what is written — code, links
and markdown are taken off first, because read literally they are noise — and
it is said one sentence at a time, so a long answer starts before the rest of
it has been made. Both are shown as they happen, with the time each sentence
took to make against the time it lasts. On the card this was written for that
settles at about seven times real time, which is the number that decides
whether an answer sounds immediate or arrives in pieces.

The voice is `tr_TR-fettah-medium`, and it was chosen by measurement rather than
by name. Piper ships three Turkish voices, two of them called Fahrettin and
Fettah, which are men's names. The fundamental frequency of a sentence from each
says otherwise: dfki and fahrettin sit at 103 and 102 Hz, and fettah sits at 190
with nothing below 166. Reading the names would have picked a man.

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
companion.py      the sphere on the edge of the screen, and its bubbles
wake.py           hearing its name, on mel-cepstra and time warping
conversation.py   the loop from the name being said to the answer being given
router.py         whether the words were wanted, or something done with them
tts.py            saying the answer out loud, through Piper
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
