"""Raw PCM capture with a live level meter.

Dictation records one source, a meeting records two of them at once — the
microphone and what comes out of the speakers — and reads who said what off the
channel a voice arrived on rather than guessing at it. One ffmpeg process reads
both devices and merges them into the two channels of a single stream, which is
the only way the two stay aligned with each other over an hour.

Where the audio comes from is the one thing the two platforms disagree about.
On Linux a dictation comes off pw-record and the devices are PipeWire's, listed
by pactl, where the output being played back has a `.monitor` source of its own.
On Windows everything goes through ffmpeg's DirectShow input, and there is no
monitor: recording the other side of a meeting needs a loopback device that
somebody put there, Stereo Mix or a virtual cable. Both sides of that difference
live in this file, and the rest of Dikte only ever sees (name, description).
"""

import array
import json
import math
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
from i18n import t

RATE = 16000
CHANNELS = 1
SAMPLE_WIDTH = 2  # s16
CHUNK_FRAMES = 1024
CHUNK_BYTES = CHUNK_FRAMES * SAMPLE_WIDTH * CHANNELS
MIN_FRAMES = int(RATE * 0.25)

# DirectShow hands audio over in blocks of whatever size it likes; asking for a
# short one is what keeps the waveform moving with the voice rather than a
# quarter of a second behind it.
DSHOW_BUFFER_MS = 50


class Recorder(QObject):
    """Runs the capture program as a child process and reads raw PCM from its
    stdout."""

    level = pyqtSignal(float)              # 0.0 - 1.0, for the waveform
    stopped = pyqtSignal(str, float, object)  # wav path, duration (s), per-chunk RMS
    failed = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._proc = None
        self._thread = None
        self._buffer = bytearray()
        self._rms = []
        self._log = None
        self._cancelled = False
        self._lock = threading.Lock()

    @property
    def active(self):
        return self._thread is not None and self._thread.is_alive()

    def start(self, target="", max_seconds=300):
        if self.active:
            return
        try:
            cmd = capture_command(target)
        except AudioError as exc:
            self.failed.emit(str(exc))
            return

        try:
            # The capture program keeps talking to stderr for as long as it
            # runs; a pipe nobody drains would eventually block it, so it goes
            # to a file that is read back only when something went wrong.
            self._log = tempfile.TemporaryFile()
            self._proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=self._log,
                stdin=subprocess.DEVNULL, bufsize=0, **plat.quiet()
            )
        except OSError as exc:
            self._drop_log()
            self.failed.emit(t("Could not start recording: {error}", error=exc))
            return

        self._buffer = bytearray()
        self._rms = []
        self._cancelled = False
        self._max_bytes = int(max_seconds * RATE * SAMPLE_WIDTH * CHANNELS)
        self._thread = threading.Thread(target=self._pump, daemon=True)
        self._thread.start()

    def _pump(self):
        stdout = self._proc.stdout
        try:
            while True:
                chunk = stdout.read(CHUNK_BYTES)
                if not chunk:
                    break
                peak, rms = chunk_levels(chunk)
                with self._lock:
                    self._buffer.extend(chunk)
                    self._rms.append(rms)
                    too_long = len(self._buffer) >= self._max_bytes
                self.level.emit(peak)
                if too_long:
                    self._terminate()
                    break
        except (OSError, ValueError):
            pass

    def snapshot(self):
        """(pcm, per-chunk RMS) for everything recorded so far.

        Taken under the same lock the pump thread appends under, so what comes
        back is a whole number of samples and a level list that matches it.
        Nothing is consumed: the recording carries on, and the copy is for
        whoever wants to look at the sentence before it is finished.
        """
        with self._lock:
            return bytes(self._buffer), list(self._rms)

    def _terminate(self):
        plat.interrupt(self._proc, timeout=1.5)

    def _error_tail(self):
        return _tail_of(self._log)

    def _drop_log(self):
        log, self._log = self._log, None
        if log is not None:
            try:
                log.close()
            except OSError:
                pass

    def cancel(self):
        self._cancelled = True
        self._terminate()
        if self._thread:
            self._thread.join(timeout=2)
        self._thread = None
        self._proc = None
        self._drop_log()
        with self._lock:
            self._buffer = bytearray()

    def stop(self):
        """End the recording and write the WAV file."""
        if not self._proc:
            return
        self._terminate()
        if self._thread:
            self._thread.join(timeout=2)
        self._thread = None
        code = self._proc.poll()
        self._proc = None

        with self._lock:
            pcm = bytes(self._buffer)
            rms = list(self._rms)
            self._buffer = bytearray()

        if self._cancelled:
            self._drop_log()
            return

        frames = len(pcm) // (SAMPLE_WIDTH * CHANNELS)
        if frames < MIN_FRAMES:
            # Nothing arrived at all: either it really was a stray keypress, or
            # the device could not be opened and the program said so on its way
            # out. The second reads like the first unless it is looked up.
            tail = self._error_tail() if code else ""
            self._drop_log()
            self.failed.emit(
                t("Could not record: {error}", error=tail) if tail
                else t("Recording too short, speak for at least 0.3 s")
            )
            return
        self._drop_log()

        path = write_wav(pcm)
        self.stopped.emit(path, frames / RATE, rms)


def write_wav(pcm, rate=RATE, channels=CHANNELS, width=SAMPLE_WIDTH):
    fd, path = tempfile.mkstemp(prefix="dikte-", suffix=".wav")
    with open(fd, "wb") as raw, wave.open(raw, "wb") as wav:
        wav.setnchannels(channels)
        wav.setsampwidth(width)
        wav.setframerate(rate)
        wav.writeframes(pcm)
    return path


def write_wav_to(path, pcm, rate=RATE, channels=CHANNELS, width=SAMPLE_WIDTH):
    """The same, into a file that already has a name.

    The live preview writes one of these a second and would otherwise leave a
    trail of temporary files behind a single dictation.
    """
    with open(path, "wb") as raw, wave.open(raw, "wb") as wav:
        wav.setnchannels(channels)
        wav.setsampwidth(width)
        wav.setframerate(rate)
        wav.writeframes(pcm)
    return path


class MeetingRecorder(QObject):
    """Microphone and speaker output into one stereo file: left is you, right is
    everyone else.

    Who said what then needs no guessing at all, because the two voices never
    shared a channel to begin with. The recording is written to disk as it
    arrives rather than held in memory, so length is not a problem and a crash
    costs the tail of the meeting instead of all of it.
    """

    levels = pyqtSignal(float, float)      # mine, theirs
    stopped = pyqtSignal(str, float)       # wav path, duration (s)
    died = pyqtSignal()                    # ffmpeg quit on its own
    failed = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._proc = None
        self._thread = None
        self._wav = None
        self._log = None
        self._path = ""
        self._frames = 0
        self._cancelled = False
        self._stopping = False
        self._lock = threading.Lock()

    @property
    def active(self):
        return self._thread is not None and self._thread.is_alive()

    def start(self, path, mic_target="", system_target="", max_seconds=14400):
        if self.active:
            return
        if not shutil.which("ffmpeg"):
            self.failed.emit(t("ffmpeg not found. Install it to record a meeting."))
            return
        try:
            cmd = meeting_command(mic_target, system_target)
        except AudioError as exc:
            self.failed.emit(str(exc))
            return

        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            self._wav = wave.open(path, "wb")
            self._wav.setnchannels(2)
            self._wav.setsampwidth(SAMPLE_WIDTH)
            self._wav.setframerate(RATE)
            # ffmpeg keeps talking to stderr for as long as it runs; a pipe
            # nobody drains would eventually block it, so it writes to a file.
            self._log = tempfile.TemporaryFile()
            self._proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=self._log,
                stdin=subprocess.DEVNULL, bufsize=0, **plat.quiet()
            )
        except (OSError, wave.Error) as exc:
            self._close_file()
            self._drop_log()
            try:
                os.unlink(path)   # an empty header nobody will ever read
            except OSError:
                pass
            self.failed.emit(t("Could not start recording: {error}", error=exc))
            return

        self._path = path
        self._frames = 0
        self._cancelled = False
        self._stopping = False
        self._max_frames = int(max_seconds * RATE)
        self._thread = threading.Thread(target=self._pump, daemon=True)
        self._thread.start()

    def _pump(self):
        stdout = self._proc.stdout
        block = CHUNK_FRAMES * SAMPLE_WIDTH * 2
        try:
            while True:
                chunk = stdout.read(block)
                if not chunk:
                    break
                mine, theirs = stereo_levels(chunk)
                with self._lock:
                    if self._wav is None:
                        break
                    self._wav.writeframes(chunk)
                    self._frames += len(chunk) // (SAMPLE_WIDTH * 2)
                    too_long = self._frames >= self._max_frames
                self.levels.emit(mine, theirs)
                if too_long:
                    self._terminate()
                    break
        except (OSError, ValueError, wave.Error):
            pass
        # Nobody asked it to end: the sound device went away, or ffmpeg fell
        # over. An hour into a meeting that has to be said out loud rather than
        # discovered afterwards.
        if not self._stopping:
            self.died.emit()

    def _terminate(self):
        self._stopping = True
        plat.interrupt(self._proc, timeout=2)

    def _close_file(self):
        with self._lock:
            wav, self._wav = self._wav, None
        if wav is not None:
            try:
                wav.close()
            except (OSError, wave.Error):
                pass

    def _error_tail(self):
        return _tail_of(self._log)

    def _finish_process(self):
        self._terminate()
        if self._thread:
            self._thread.join(timeout=3)
        self._thread = None
        code = self._proc.poll() if self._proc else 0
        self._proc = None
        self._close_file()
        return code

    def cancel(self):
        self._cancelled = True
        self._finish_process()
        self._drop_log()
        try:
            os.unlink(self._path)
        except OSError:
            pass

    def stop(self):
        if not self._proc:
            return
        # The count is read after the join: the pump thread is still appending
        # the last blocks up to the moment it ends.
        code = self._finish_process()
        frames = self._frames
        if self._cancelled:
            self._drop_log()
            return

        # The recording ends by taking ffmpeg down, and ffmpeg reports being
        # taken down as a failure; only complain when nothing was captured too.
        if frames < MIN_FRAMES:
            tail = self._error_tail()
            self._drop_log()
            try:
                os.unlink(self._path)
            except OSError:
                pass
            self.failed.emit(
                t("Nothing was recorded: {error}", error=tail or f"ffmpeg → {code}")
                if tail or code else t("Recording too short, speak for at least 0.3 s")
            )
            return
        self._drop_log()
        self.stopped.emit(self._path, frames / RATE)

    def _drop_log(self):
        if self._log is not None:
            try:
                self._log.close()
            except OSError:
                pass
            self._log = None


def _tail_of(log):
    """The last thing a child said on its way out, for an error message."""
    if log is None:
        return ""
    try:
        log.seek(0)
        text = log.read().decode("utf-8", "replace").strip()
    except OSError:
        return ""
    lines = [line for line in text.splitlines() if line.strip()]
    return lines[-1] if lines else ""


def chunk_levels(chunk):
    """(peak, rms) in 0..1. Peak drives the waveform, RMS drives the silence check."""
    samples = array.array("h")
    usable = len(chunk) - (len(chunk) % 2)
    if usable <= 0:
        return 0.0, 0.0
    samples.frombytes(chunk[:usable])
    peak = max(abs(min(samples)), abs(max(samples))) / 32768.0
    rms = math.sqrt(sum(s * s for s in samples) / len(samples)) / 32768.0
    return min(1.0, peak), min(1.0, rms)


def stereo_levels(chunk):
    """(left peak, right peak) in 0..1 from interleaved stereo s16."""
    samples = array.array("h")
    usable = len(chunk) - (len(chunk) % 4)
    if usable <= 0:
        return 0.0, 0.0
    samples.frombytes(chunk[:usable])
    left, right = samples[0::2], samples[1::2]
    return _peak(left), _peak(right)


def _peak(samples):
    if not samples:
        return 0.0
    return min(1.0, max(abs(min(samples)), abs(max(samples))) / 32768.0)


class AudioError(Exception):
    """A recording that cannot even be started: no program, no device."""


# --- what to run ----------------------------------------------------------

def capture_command(target=""):
    """The command that writes one channel of raw 16 kHz PCM to its stdout."""
    if plat.WINDOWS:
        if not shutil.which("ffmpeg"):
            raise AudioError(t("ffmpeg not found. Install it to record."))
        return [
            "ffmpeg", "-hide_banner", "-nostdin", "-loglevel", "error",
            *_dshow_input(_resolve_input(target)),
            "-ac", str(CHANNELS), "-ar", str(RATE),
            "-f", "s16le", "-",
        ]

    if not shutil.which("pw-record"):
        raise AudioError(t("pw-record not found. Is pipewire-audio installed?"))
    cmd = [
        "pw-record",
        "--raw",
        f"--rate={RATE}",
        f"--channels={CHANNELS}",
        "--format=s16",
    ]
    if target:
        cmd.append(f"--target={target}")
    cmd.append("-")
    return cmd


def meeting_command(mic_target="", system_target=""):
    """One ffmpeg reading both sides of a meeting into a single stereo stream."""
    merge = (
        "[0:a]aresample={rate}:async=1,aformat=sample_fmts=s16:channel_layouts=mono[m];"
        "[1:a]aresample={rate}:async=1,aformat=sample_fmts=s16:channel_layouts=mono[s];"
        "[m][s]amerge=inputs=2[out]"
    ).format(rate=RATE)

    if plat.WINDOWS:
        mic = _resolve_input(mic_target)
        system = system_target or default_monitor()
        if not system:
            raise AudioError(t(
                "Windows has no ready-made way to record what the speakers are "
                "playing. Turn on “Stereo Mix” in Sound → Recording, or install a "
                "virtual cable such as VB-CABLE, then pick it under "
                "Settings → Meeting."))
        inputs = (_dshow_input(mic, queue=True) + _dshow_input(system, queue=True))
    else:
        system = system_target or default_monitor()
        if not system:
            raise AudioError(t("Could not work out which speaker output to record. "
                               "Pick one in Settings → Meeting."))
        inputs = [
            "-f", "pulse", "-thread_queue_size", "4096", "-i", mic_target or "default",
            "-f", "pulse", "-thread_queue_size", "4096", "-i", system,
        ]

    return [
        "ffmpeg", "-hide_banner", "-nostdin", "-loglevel", "error",
        *inputs,
        "-filter_complex", merge, "-map", "[out]",
        "-f", "s16le", "-ar", str(RATE), "-",
    ]


def _dshow_input(device, queue=False):
    args = ["-f", "dshow", "-audio_buffer_size", str(DSHOW_BUFFER_MS)]
    if queue:
        args += ["-thread_queue_size", "4096"]
    return args + ["-i", f"audio={device}"]


def _resolve_input(target):
    """A DirectShow device name ffmpeg will accept, or an error worth reading.

    DirectShow has no notion of a default microphone the way PipeWire does, so
    an unset setting means the first device on the machine rather than something
    the system would pick.
    """
    target = (target or "").strip()
    if target:
        return target
    devices = [d for d in _audio_devices() if not _is_loopback(d["name"])]
    if not devices:
        devices = _audio_devices()
    if not devices:
        raise AudioError(t(
            "No microphone was found. Plug one in, or check that Windows lets "
            "applications use it: Settings → Privacy → Microphone."))
    return devices[0]["id"]


# --- which devices there are ----------------------------------------------

# Names that mean "whatever is coming out of the speakers". Windows only puts
# one there when the sound card offers it and it has been switched on by hand,
# which is why the list also covers the virtual cables people install instead.
LOOPBACK_HINTS = (
    "stereo mix", "stereomix", "stereo karışım", "stereo karisim",
    "what u hear", "wave out mix", "waveout mix", "rec. playback",
    "cable output", "voicemeeter out", "virtual-audio-capturer",
    "loopback", "mix aufnahme", "mixage stéréo", "mixage stereo",
)

_DEVICE_CACHE = {"at": 0.0, "devices": []}
_DEVICE_TTL = 20.0
_DEVICE_LOCK = threading.Lock()

_LOG_PREFIX = re.compile(r"^\[[^\]]*\]\s?")
_DEVICE_LINE = re.compile(r'^"(.+)"(?:\s*\((audio|video)\))?$')
_ALT_LINE = re.compile(r'^Alternative name\s+"(.+)"$')
_SECTION_LINE = re.compile(r"DirectShow (audio|video) devices")


def _is_loopback(name):
    lowered = name.lower()
    return any(hint in lowered for hint in LOOPBACK_HINTS)


def _parse_dshow(text):
    """[{'id', 'name'}] for the audio devices in ffmpeg's device listing.

    `id` is DirectShow's alternative name when there is one: it is the same
    string after the device is renamed or moved to another port, while the
    friendly name is what the user should be shown and nothing else.
    """
    devices = []
    section = ""
    for raw in text.splitlines():
        line = _LOG_PREFIX.sub("", raw).strip()
        header = _SECTION_LINE.search(line)
        if header:
            section = header.group(1)
            continue
        alt = _ALT_LINE.match(line)
        if alt and devices:
            devices[-1]["id"] = alt.group(1)
            continue
        match = _DEVICE_LINE.match(line)
        if match:
            kind = match.group(2) or section
            if kind == "audio":
                name = match.group(1)
                devices.append({"id": name, "name": name})
            elif kind:
                # A video device: remember that a following "Alternative name"
                # belongs to it, not to the last audio one.
                devices.append({"id": "", "name": "", "skip": True})
    return [d for d in devices if not d.get("skip")]


def _audio_devices(force=False):
    with _DEVICE_LOCK:
        fresh = time.monotonic() - _DEVICE_CACHE["at"] < _DEVICE_TTL
        if not force and fresh:
            return list(_DEVICE_CACHE["devices"])
    devices = _list_dshow()
    with _DEVICE_LOCK:
        _DEVICE_CACHE["at"] = time.monotonic()
        _DEVICE_CACHE["devices"] = devices
    return list(devices)


def _list_dshow():
    if not shutil.which("ffmpeg"):
        return []
    try:
        # There is no device to open, so this always ends in an error; the
        # listing it prints on the way there is the point of the call.
        res = subprocess.run(
            ["ffmpeg", "-hide_banner", "-list_devices", "true", "-f", "dshow",
             "-i", "dummy"],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=15, **plat.quiet()
        )
    except (subprocess.SubprocessError, OSError):
        return []
    return _parse_dshow((res.stderr or "") + (res.stdout or ""))


def warm_devices():
    """Fill the cache before anything needs it.

    Listing DirectShow devices means starting ffmpeg and waiting a quarter of a
    second for it, which is a quarter of a second the first dictation of the
    session should not have to spend before it starts recording.
    """
    if plat.WINDOWS:
        _audio_devices(force=True)


def _sources():
    if not shutil.which("pactl"):
        return []
    try:
        out = subprocess.run(
            ["pactl", "-f", "json", "list", "sources"],
            capture_output=True, text=True, timeout=5, check=True,
        ).stdout
        return json.loads(out)
    except (subprocess.SubprocessError, OSError, json.JSONDecodeError):
        return []


def list_sources():
    """[(name, description)] for every real input source."""
    if plat.WINDOWS:
        return [(d["id"], d["name"]) for d in _audio_devices(force=True)
                if not _is_loopback(d["name"])]
    return [
        (src.get("name", ""), src.get("description") or src.get("name", ""))
        for src in _sources()
        if not src.get("name", "").endswith(".monitor")
    ]


def list_monitors():
    """[(name, description)] for the sources that carry what is being played.

    Recording one is recording whatever is coming out of the speakers, which in
    a meeting is the other participants and nothing of your own microphone. On
    Linux every output has one. On Windows the recognised ones come first and
    the rest of the inputs follow, because a loopback nobody here has heard of
    is still a loopback and should be selectable.
    """
    if plat.WINDOWS:
        devices = _audio_devices(force=True)
        loopbacks = [d for d in devices if _is_loopback(d["name"])]
        others = [d for d in devices if not _is_loopback(d["name"])]
        return [(d["id"], d["name"]) for d in loopbacks + others]
    return [
        (src.get("name", ""), src.get("description") or src.get("name", ""))
        for src in _sources()
        if src.get("name", "").endswith(".monitor")
    ]


def default_monitor():
    """Where the sound being played can be recorded from, or ''."""
    if plat.WINDOWS:
        for device in _audio_devices():
            if _is_loopback(device["name"]):
                return device["id"]
        return ""
    if not shutil.which("pactl"):
        return ""
    try:
        sink = subprocess.run(
            ["pactl", "get-default-sink"],
            capture_output=True, text=True, timeout=5, check=True,
        ).stdout.strip()
    except (subprocess.SubprocessError, OSError):
        return ""
    if not sink:
        return ""
    monitor = f"{sink}.monitor"
    names = {name for name, _ in list_monitors()}
    return monitor if not names or monitor in names else ""
