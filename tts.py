"""Saying the answer out loud.

Piper does the synthesis: a standalone program with a voice in a file, which is
the same shape as whisper.cpp and ffmpeg, the two things Dikte already leans on.
Nothing is imported into this process, nothing is downloaded at run time, and
nothing is sent anywhere.

The voice is tr_TR-fettah-medium, chosen by measurement rather than by name.
Piper ships three Turkish voices and two of them are called Fahrettin and
Fettah, which are men's names; the fundamental frequency of a sentence
synthesised by each says otherwise. dfki and fahrettin sit at 103 and 102 Hz,
which is a man. fettah sits at 190 Hz with nothing below 166, which is not.
Reading the names would have picked the wrong one.

Speech is queued a sentence at a time rather than an answer at a time. A long
reply then starts being spoken while the rest of it is still being made, and
stopping — because the answer is no longer wanted — takes effect at the end of
the current sentence instead of at the end of the paragraph.
"""

import contextlib
import os
import re
import shutil
import subprocess
import tempfile
import threading
import time
import wave

from PyQt6.QtCore import QObject, pyqtSignal

import plat

BINARY = "piper"
VOICE = "tr_TR-fettah-medium.onnx"

# Where a Windows install puts it, so the setting can stay empty in the common
# case. Linux is expected to have it on PATH like everything else.
WINDOWS_HOMES = (
    os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "piper", "piper"),
    os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "piper"),
)

# Beyond this a spoken answer stops being an answer and becomes a recital. The
# rest is still on the screen, which is the right place for it.
MAX_SPOKEN = 900

_SENTENCE = re.compile(r"(?<=[.!?…:])\s+|\n+")
# Things that read badly out loud: a URL, a code block, a table of numbers.
_CODE_BLOCK = re.compile(r"```.*?```", re.S)
_INLINE_CODE = re.compile(r"`([^`]*)`")
_URL = re.compile(r"https?://\S+")
_MARKDOWN = re.compile(r"[*_#>|]+")


def binary_path(custom=""):
    """The piper to run, or "" when there is none."""
    custom = (custom or "").strip().strip('"')
    if custom:
        if plat.WINDOWS and not os.path.splitext(custom)[1]:
            custom += ".exe"
        return custom if os.path.isfile(custom) else ""
    found = shutil.which(BINARY)
    if found:
        return found
    if plat.WINDOWS:
        for home in WINDOWS_HOMES:
            candidate = os.path.join(home, "piper.exe")
            if os.path.isfile(candidate):
                return candidate
    return ""


def voices_dir(data_dir):
    return os.path.join(str(data_dir), "voices")


def voice_path(data_dir, custom=""):
    """The voice file to speak with, or "" when it is not there."""
    custom = (custom or "").strip().strip('"')
    if custom:
        return custom if os.path.isfile(custom) else ""
    default = os.path.join(voices_dir(data_dir), VOICE)
    return default if os.path.isfile(default) else ""


def ready(data_dir, binary="", voice=""):
    return bool(binary_path(binary)) and bool(voice_path(data_dir, voice))


def speakable(text):
    """The answer with the parts that do not survive being read out taken off.

    A model writing for a screen puts things on it that mean nothing aloud:
    fenced code, links, the punctuation that makes a heading a heading. Read
    literally they are noise; read as they are meant they are a pause.
    """
    text = _CODE_BLOCK.sub(" ", text or "")
    text = _URL.sub(" ", text)
    text = _INLINE_CODE.sub(r"\1", text)
    text = _MARKDOWN.sub(" ", text)
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()


def sentences(text, limit=MAX_SPOKEN):
    """Split into things worth speaking one at a time, and stop at the limit."""
    spoken = speakable(text)
    if not spoken:
        return []
    if len(spoken) > limit:
        spoken = spoken[:limit].rsplit(" ", 1)[0]
    out = []
    for piece in _SENTENCE.split(spoken):
        piece = piece.strip()
        if piece:
            out.append(piece)
    return out


class Voice(QObject):
    """Speaks what it is given, one sentence at a time, and can be cut off."""

    started = pyqtSignal()
    finished = pyqtSignal()
    failed = pyqtSignal(str)
    # One sentence done: what was said, how long it took to make, and how
    # long the sound of it lasts. Nothing needs this to speak; it is what
    # lets a person watch the thing work instead of taking it on trust.
    spoke = pyqtSignal(str, float, float)

    def __init__(self, conf, data_dir, parent=None):
        super().__init__(parent)
        self.conf = conf
        self.data_dir = str(data_dir)
        self._lock = threading.Lock()
        self._queue = []
        self._thread = None
        self._proc = None
        self._run = 0
        self._speaking = False

    @property
    def speaking(self):
        return self._speaking

    def available(self):
        return ready(self.data_dir, self.conf["tts_binary"], self.conf["tts_voice"])

    def say(self, text):
        """Queue an answer. False when nothing will be said."""
        if not self.conf["tts_enabled"]:
            return False
        parts = sentences(text)
        if not parts:
            return False
        if not self.available():
            self.failed.emit("")
            return False
        with self._lock:
            self._queue.extend(parts)
            if self._thread is not None and self._thread.is_alive():
                return True
            self._run += 1
            self._thread = threading.Thread(target=self._speak, args=(self._run,),
                                            daemon=True)
        self._speaking = True
        self.started.emit()
        self._thread.start()
        return True

    def stop(self):
        """Stop now. The sentence being spoken is cut off with it."""
        with self._lock:
            self._run += 1
            self._queue = []
            proc = self._proc
        _stop_playback()
        if proc is not None and proc.poll() is None:
            try:
                proc.kill()
            except OSError:
                pass
        self._speaking = False

    # ---- the thread -------------------------------------------------------

    def _speak(self, run):
        try:
            while True:
                with self._lock:
                    if run != self._run or not self._queue:
                        break
                    sentence = self._queue.pop(0)
                began = time.monotonic()
                path = self._render(sentence, run)
                if path is None:
                    break
                made = time.monotonic() - began
                try:
                    if run == self._run:
                        self.spoke.emit(sentence, made, _seconds(path))
                        _play(path)
                finally:
                    try:
                        os.unlink(path)
                    except OSError:
                        pass
        finally:
            with self._lock:
                done = run == self._run and not self._queue
            self._speaking = False
            if done:
                self.finished.emit()

    def _render(self, sentence, run):
        """One sentence to a WAV file, or None when it could not be made."""
        binary = binary_path(self.conf["tts_binary"])
        voice = voice_path(self.data_dir, self.conf["tts_voice"])
        if not binary or not voice:
            self.failed.emit("")
            return None
        handle, path = tempfile.mkstemp(prefix="dikte-say-", suffix=".wav")
        os.close(handle)
        pitch = self._pitch()
        command = [binary, "-m", voice, "-f", path,
                   "--length_scale", f"{self._length_scale() * pitch:.3f}"]
        try:
            with self._lock:
                if run != self._run:
                    raise _Cancelled()
                self._proc = subprocess.Popen(
                    command, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL, **plat.quiet())
            self._proc.communicate(sentence.encode("utf-8"), timeout=60)
        except _Cancelled:
            os.unlink(path)
            return None
        except (OSError, subprocess.SubprocessError):
            try:
                os.unlink(path)
            except OSError:
                pass
            self.failed.emit("")
            return None
        finally:
            with self._lock:
                self._proc = None
        _repitch(path, pitch)
        if not os.path.exists(path) or os.path.getsize(path) < 64:
            try:
                os.unlink(path)
            except OSError:
                pass
            return None
        return path

    def _length_scale(self):
        """Piper's dial is duration, so it runs the opposite way to speed."""
        speed = float(self.conf["tts_speed"] or 1.0)
        return 1.0 / max(0.5, min(2.0, speed))

    def _pitch(self):
        """How much lighter than recorded to make it. 1.0 is as it was."""
        return max(0.85, min(1.25, float(self.conf["tts_pitch"] or 1.0)))


class _Cancelled(Exception):
    pass


def _repitch(path, factor):
    """Raise the pitch of a rendered sentence by rewriting its sample rate.

    A voice is raised properly by shortening the vocal tract, which moves the
    formants up with the pitch; playing a recording faster does exactly that.
    The usual objection is that it also shortens the sentence — so the sentence
    is generated proportionally longer to begin with, and the two cancel. The
    result has the duration it was asked for, the pitch and formants of a
    lighter voice, and no resampling in it at all: only the number in the
    header changed, and nothing touched a sample.

    Which is why this and not a filter. Stretching time back with a phase
    vocoder would have cost a process per sentence and put an artefact into
    every one of them, to arrive at the same place.
    """
    if abs(factor - 1.0) < 0.005:
        return
    try:
        with contextlib.closing(wave.open(path, "rb")) as source:
            params = source.getparams()
            frames = source.readframes(params.nframes)
        with contextlib.closing(wave.open(path, "wb")) as target:
            target.setnchannels(params.nchannels)
            target.setsampwidth(params.sampwidth)
            target.setframerate(int(round(params.framerate * factor)))
            target.writeframes(frames)
    except (OSError, wave.Error):
        pass       # the sentence is still perfectly sayable at its own pitch


def _seconds(path):
    """How long a rendered WAV lasts, for the sake of saying so."""
    try:
        with contextlib.closing(wave.open(path)) as handle:
            return handle.getnframes() / float(handle.getframerate())
    except (OSError, wave.Error, ZeroDivisionError):
        return 0.0


# --- getting the sound out ------------------------------------------------

def _play(path):
    """Play a WAV file and wait for it to finish.

    winsound is in the standard library and talks to the same audio session
    everything else does, so nothing has to be installed for the assistant to
    have a voice. Elsewhere it is whichever of the usual players is present.
    """
    if plat.WINDOWS:
        import winsound
        try:
            winsound.PlaySound(path, winsound.SND_FILENAME)
        except RuntimeError:
            pass
        return
    for player in ("paplay", "aplay", "ffplay"):
        found = shutil.which(player)
        if not found:
            continue
        command = [found, path]
        if player == "ffplay":
            command = [found, "-nodisp", "-autoexit", "-loglevel", "quiet", path]
        try:
            subprocess.run(command, check=False, timeout=120)
        except (OSError, subprocess.SubprocessError):
            continue
        return


def _stop_playback():
    if not plat.WINDOWS:
        return
    import winsound
    try:
        winsound.PlaySound(None, winsound.SND_PURGE)
    except RuntimeError:
        pass
