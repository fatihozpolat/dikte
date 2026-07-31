"""Reading the sentence back while it is still being spoken.

Dictation is otherwise silent until it ends: you talk, nothing happens, and then
the text appears. That is fine for a line but not for a character sitting on the
screen, which should look like it is listening rather than like it is asleep.

There is no streaming here and no second model. Every second or so the audio
recorded *so far* is sent to the whisper.cpp server already running next to
Dikte, and what comes back replaces the previous guess. That works because the
machine is far faster than the speaking: on the card this was written for the
server runs at forty to sixty times real time, so a sentence in progress is
re-read in a fraction of the time it took to say. The cost of re-reading the
whole thing each time is what keeps it honest — the model sees the entire
sentence, not a window, so the preview improves as context arrives instead of
being stitched together out of fragments.

Two things this is deliberately not:

  * It is not the transcript. What gets pasted, cleaned up or sent to the agent
    is always the full pass made after the recording ends. The preview may say
    something slightly different on the way there, the way every live captioner
    does, and none of that reaches the clipboard.
  * It is not for the hosted providers. On OpenAI or OpenRouter each preview
    would be a request that costs money and arrives late, so this only ever runs
    against the local server.
"""

import os
import tempfile
import threading

from PyQt6.QtCore import QObject, QTimer, pyqtSignal

import api
import audio
import vad
import whispercpp

# How often to look again. Short enough that the text keeps up with the talking,
# long enough that a slower machine is never asked for a second pass before it
# has finished the first — and it is skipped outright while one is in flight, so
# this is a floor rather than a promise.
INTERVAL_MS = 1200

# Below this there is not enough of a sentence to read, and a model handed a
# fragment of a word invents a whole one.
MIN_SECONDS = 1.0

# Past this the preview stops updating. A dictation this long has had all the
# reassurance it needs, and re-reading minutes of audio every second is work the
# machine should not be doing for a bubble nobody is still watching.
MAX_SECONDS = 120.0

CHUNK_SECONDS = audio.CHUNK_FRAMES / float(audio.RATE)


def wanted(conf):
    """Whether a preview should run at all, from the settings alone."""
    return bool(conf["companion_enabled"]
                and conf["companion_live"]
                and conf["transcribe_provider"] == "local")


class LiveTranscriber(QObject):
    """Polls the recorder and reads back what it has heard so far."""

    partial = pyqtSignal(str)

    def __init__(self, conf, recorder, parent=None):
        super().__init__(parent)
        self.conf = conf
        self.recorder = recorder
        self._timer = QTimer(self)
        self._timer.setInterval(INTERVAL_MS)
        self._timer.timeout.connect(self._look)
        self._busy = False
        self._run = 0            # bumped by stop(), so a late answer is dropped
        self._path = ""
        self._last = ""

    @property
    def running(self):
        return self._timer.isActive()

    def start(self):
        """Begin previewing. False when this setup has no business doing it."""
        if not wanted(self.conf):
            return False
        # The server has to be up already. Starting it here would put a model
        # load in front of the first preview and, worse, in front of the
        # recording the user is in the middle of making.
        if not whispercpp.running():
            return False
        self._run += 1
        self._last = ""
        self._timer.start()
        return True

    def stop(self):
        """Stop previewing. Anything still in flight is discarded, not awaited.

        The pass that matters starts the moment the recording ends, and making
        it queue behind a preview nobody will see now would be the one place
        this feature could cost the user time.
        """
        self._run += 1
        self._timer.stop()
        self._drop_file()

    # ---- one look ---------------------------------------------------------

    def _look(self):
        if self._busy:
            return
        pcm, rms = self.recorder.snapshot()
        seconds = len(pcm) / float(audio.RATE * audio.SAMPLE_WIDTH * audio.CHANNELS)
        if seconds < MIN_SECONDS:
            return
        if seconds > MAX_SECONDS:
            self._timer.stop()
            return
        # The same silence test the finished recording gets. Without it the
        # bubble fills up with the stock sentence models invent for a quiet room.
        stats = vad.analyse(rms, CHUNK_SECONDS, self.conf["speech_margin_db"])
        if vad.is_silent(stats, self.conf["silence_db"],
                         self.conf["speech_margin_db"],
                         self.conf["min_voiced_seconds"]):
            return

        self._busy = True
        run = self._run
        threading.Thread(target=self._read, args=(pcm, seconds, run),
                         daemon=True).start()

    def _read(self, pcm, seconds, run):
        try:
            text = self._transcribe(pcm)
        except (api.ApiError, OSError, ValueError):
            # A preview that fails is a preview that does not appear. The real
            # pass will raise the same thing where it can be acted on.
            text = ""
        finally:
            self._busy = False
        if run != self._run or not text:
            return
        if vad.looks_like_hallucination(text, seconds):
            return
        if text != self._last:
            self._last = text
            self.partial.emit(text)

    def _transcribe(self, pcm):
        path = self._temp_file()
        audio.write_wav_to(path, pcm)
        return api.transcribe(
            self.conf.transcribe_target(), path,
            language=self.conf["language"],
            prompt=self.conf["transcribe_prompt"],
        ).strip()

    def _temp_file(self):
        """One file, rewritten each time, rather than one per second."""
        if not self._path:
            handle, self._path = tempfile.mkstemp(prefix="dikte-live-", suffix=".wav")
            os.close(handle)
        return self._path

    def _drop_file(self):
        # Windows will not unlink a file another thread still has open, and a
        # preview can be in flight when the recording ends. Keeping the name on
        # a failure means the next run writes over it instead of leaving one
        # behind for every dictation of the day.
        if not self._path:
            return
        try:
            os.unlink(self._path)
        except OSError:
            return
        self._path = ""
