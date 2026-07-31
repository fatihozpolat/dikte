"""Waking Dikte by saying its name, without running speech recognition to do it.

Whisper could do this — hand it every couple of seconds of audio and look for
the phrase — but that is a transcription engine kept busy all day to answer one
yes-or-no question, and it needs the graphics card awake to do it.

What Siri does instead is take mel-band energies off the microphone and run them
through a small network trained on that one phrase; no recognition, just a
pattern. The network is the part that cannot be had here: there is none trained
on "Hey Zeno" and nothing to train one with. So this is the method that came
before the networks, and the one that is still right when there is exactly one
speaker to recognise — which is the case, since the person who set the phrase is
the only person who will ever say it. The phrase is recorded a few times, its
mel-cepstral shape is kept, and what the microphone hears is compared against
those recordings by dynamic time warping, which is what allows a match when the
same words are said faster or slower than they were recorded.

The expensive part runs once per utterance, not once per frame. Energy alone
decides where an utterance begins and ends — a comparison per block, and no
arithmetic at all in a quiet room — and only what falls between those two points,
and only if it lasts about as long as the phrase does, is ever turned into
features and compared. A second of speech costs about nine milliseconds of that
work, which is what makes an always-open microphone affordable at all.

What it is not is as good as the trained thing. It knows one voice, saying one
phrase, in the room it was recorded in; move any of those and it gets worse.
That is the trade for needing no model, no account and no network.

It also wants the name on its own. Saying "Zeno, put that in my calendar" in one
breath does not wake it, and that is measured rather than assumed: matching the
name against the front of a longer utterance was tried, with the warp free to
end early and the path length carried along to score it honestly, and speech
that was not the name scored *better* than the name followed by an instruction
did. No threshold separates them, so there is no setting that would have fixed
it. Say the name, wait for it to light up, then speak — which is the interaction
every assistant of this kind actually has, for the same reason.
"""

import cmath
import json
import math
import os
import subprocess
import threading

from PyQt6.QtCore import QObject, pyqtSignal

import audio
import plat

# --- how the sound is turned into a shape ---------------------------------

# Halved from the recording rate: speech that matters to a wake word lives well
# under 4 kHz, and every sample dropped is a sample not paid for.
FEATURE_RATE = 8000
DECIMATION = audio.RATE // FEATURE_RATE

FRAME = 256                 # 32 ms, long enough to hold a pitch period
HOP = 128                   # 16 ms
MEL_BANDS = 20
MEL_LOW = 100.0
MEL_HIGH = 3800.0
CEPSTRA = 12                # c1..c12; c0 is loudness and is deliberately dropped

# --- how an utterance is found --------------------------------------------

BLOCK = audio.CHUNK_FRAMES              # 1024 frames, 64 ms at 16 kHz
BLOCK_SECONDS = BLOCK / float(audio.RATE)
SPEECH_MARGIN_DB = 9.0                  # above the room's own floor
TAIL_SECONDS = 0.32                     # quiet this long ends the utterance
PREROLL_SECONDS = 0.20                  # kept from before it began
MIN_SECONDS = 0.35
MAX_SECONDS = 2.5
# Long enough that one "Hey Zeno" cannot start two dictations, short enough not
# to swallow a second, deliberate try.
REFRACTORY_SECONDS = 1.5

# How much of the shortest recording an utterance has to be worth before it is
# compared at all. Below this there is not enough of it to hold the name.
MIN_COVERAGE = 0.6

# Only the front of an utterance is compared against the recordings.
#
# Not merely to save work. The mean taken off the cepstrum is taken over
# whatever is handed in, so the same name comes out shifted differently
# depending on what was said after it: measured over "Zeno" it is one thing,
# and over "Zeno, put that in my calendar" it is another, and the second scored
# five times worse than the first for acoustically identical audio. Looking at a
# fixed span from the start makes the two comparable again.
HEAD_SECONDS = 1.6

TEMPLATE_VERSION = 1


def _twiddles(size):
    return [cmath.exp(-2j * math.pi * k / size) for k in range(size // 2)]


_TWIDDLES = _twiddles(FRAME)
_WINDOW = [0.54 - 0.46 * math.cos(2 * math.pi * i / (FRAME - 1)) for i in range(FRAME)]


def _fft(values):
    """Radix-2, in place, on a copy. The twiddles are worked out once."""
    n = len(values)
    data = list(values)
    j = 0
    for i in range(1, n):
        bit = n >> 1
        while j & bit:
            j ^= bit
            bit >>= 1
        j |= bit
        if i < j:
            data[i], data[j] = data[j], data[i]
    size = 2
    while size <= n:
        step = n // size
        half = size // 2
        for start in range(0, n, size):
            k = 0
            for i in range(start, start + half):
                turn = _TWIDDLES[k] * data[i + half]
                data[i + half] = data[i] - turn
                data[i] = data[i] + turn
                k += step
        size <<= 1
    return data


def _hz_to_mel(hz):
    return 2595.0 * math.log10(1.0 + hz / 700.0)


def _mel_to_hz(mel):
    return 700.0 * (10.0 ** (mel / 2595.0) - 1.0)


def _filterbank():
    """Triangular filters, as (first bin, weights) so the empty bins cost nothing."""
    bins = FRAME // 2 + 1
    edges = [_mel_to_hz(_hz_to_mel(MEL_LOW)
                        + (_hz_to_mel(MEL_HIGH) - _hz_to_mel(MEL_LOW)) * i
                        / (MEL_BANDS + 1))
             for i in range(MEL_BANDS + 2)]
    positions = [edge * FRAME / FEATURE_RATE for edge in edges]
    filters = []
    for band in range(MEL_BANDS):
        low, middle, high = positions[band], positions[band + 1], positions[band + 2]
        first = max(0, int(math.floor(low)))
        last = min(bins - 1, int(math.ceil(high)))
        weights = []
        for index in range(first, last + 1):
            if index < low or index > high:
                weights.append(0.0)
            elif index <= middle:
                weights.append((index - low) / (middle - low) if middle > low else 0.0)
            else:
                weights.append((high - index) / (high - middle) if high > middle else 0.0)
        filters.append((first, weights))
    return filters


_FILTERS = _filterbank()

# DCT-II, worked out once rather than per frame.
_DCT = [[math.cos(math.pi * (k + 1) * (2 * b + 1) / (2 * MEL_BANDS))
         for b in range(MEL_BANDS)] for k in range(CEPSTRA)]


def decimate(samples):
    """16 kHz to 8 kHz, averaging each pair.

    Averaging rather than dropping every other sample: it is a crude low-pass,
    but a crude one is the difference between folding the top of the band back
    over the speech and not.
    """
    return [(samples[i] + samples[i + 1]) * 0.5
            for i in range(0, len(samples) - 1, DECIMATION)]


TARGET_RMS = 2000.0     # in sample units, well clear of the log floor below
LOG_FLOOR = 1e-6


def _normalise(signal):
    """Bring an utterance to a standard loudness before anything is measured.

    Taking the mean off the cepstrum should already make loudness irrelevant —
    quartering the amplitude subtracts the same constant from every mel band,
    and a constant across bands lands entirely in the coefficient that is
    dropped. It only works while the log is a log: near the floor it flattens
    out, quiet bands stop moving with the signal, and the offset stops being a
    constant. Setting the level first is what keeps the arithmetic in the part
    of the curve where the theory holds.
    """
    if not signal:
        return signal
    total = 0.0
    for sample in signal:
        total += sample * sample
    rms = math.sqrt(total / len(signal))
    if rms < 1e-6:
        return signal
    gain = TARGET_RMS / rms
    return [sample * gain for sample in signal]


def features(samples):
    """Mel-cepstral coefficients for 16 kHz signed samples: a list per frame.

    The mean of each coefficient is taken off at the end. That is what stops the
    microphone, the room and the distance from the mouth being part of what is
    matched, since all three shift the cepstrum by roughly a constant.
    """
    signal = _normalise(decimate(samples))
    rows = []
    for start in range(0, len(signal) - FRAME + 1, HOP):
        frame = [signal[start + i] * _WINDOW[i] for i in range(FRAME)]
        spectrum = _fft(frame)
        power = [abs(spectrum[i]) ** 2 for i in range(FRAME // 2 + 1)]
        energies = []
        for first, weights in _FILTERS:
            total = 0.0
            for offset, weight in enumerate(weights):
                if weight:
                    total += power[first + offset] * weight
            energies.append(math.log(total + LOG_FLOOR))
        rows.append([sum(energies[b] * _DCT[k][b] for b in range(MEL_BANDS))
                     for k in range(CEPSTRA)])
    if not rows:
        return []
    means = [sum(row[k] for row in rows) / len(rows) for k in range(CEPSTRA)]
    return [[row[k] - means[k] for k in range(CEPSTRA)] for row in rows]


# --- comparing two shapes -------------------------------------------------

def distance(left, right):
    """Dynamic time warping, normalised by the length of the path it took.

    Normalised because otherwise a longer utterance always scores worse than a
    short one, and the number would say more about how long the phrase is than
    about whether it is the phrase.

    The band keeps the path near the diagonal: without it the warp is free to
    stretch one sound over the whole of the other and find a cheap match between
    things that sound nothing alike.
    """
    score, _ = _warp(left, right, open_end=False)
    return score


def prefix_distance(template, heard):
    """The best match of the template against the *beginning* of what was heard.

    Returns (score, frame the match ended on).

    This is what makes "Zeno, put that in my calendar" work. Said in one breath
    it is a single utterance, and a matcher that expects the name on its own
    rejects it for being four times too long. Letting the path end anywhere in
    the heard sequence, instead of forcing it to the last frame, finds the name
    at the front — and where it finished is where the name stopped and the
    instruction began, which is the other thing that has to be known.
    """
    return _warp(template, heard, open_end=True)


def _warp(template, heard, open_end):
    if not template or not heard:
        return float("inf"), 0
    rows, columns = len(template), len(heard)
    if open_end:
        # The path may stop early, so it must be free to start anywhere near the
        # top and the band has to be wide enough to reach a much longer heard
        # sequence. Bounded by the template's own length rather than the
        # difference, or a long instruction would widen the band to no purpose.
        band = max(12, rows)
    else:
        band = max(10, abs(rows - columns) + 10)
    infinity = float("inf")
    previous = [infinity] * (columns + 1)
    steps_before = [0] * (columns + 1)
    previous[0] = 0.0
    # No free entry. The name is looked for at the *start* of what was said,
    # which is where people put it, and letting the path begin anywhere turns
    # this into a search for the name somewhere inside the sentence — which any
    # long enough sentence contains a passable imitation of.
    #
    # The number of steps each path took is carried along beside its cost. It is
    # the only honest divisor: paths reaching different endings are of different
    # lengths, and dividing by anything derived from the endpoint instead makes
    # a longer path look cheaper than a shorter one and the match runs away to
    # the end of the sentence.
    for i in range(1, rows + 1):
        current = [infinity] * (columns + 1)
        steps_now = [0] * (columns + 1)
        low = max(1, i - band)
        high = min(columns, i + band)
        row = template[i - 1]
        for j in range(low, high + 1):
            other = heard[j - 1]
            step = 0.0
            for k in range(CEPSTRA):
                difference = row[k] - other[k]
                step += difference * difference
            step = math.sqrt(step)
            best, taken = previous[j], steps_before[j]
            if previous[j - 1] < best:
                best, taken = previous[j - 1], steps_before[j - 1]
            if current[j - 1] < best:
                best, taken = current[j - 1], steps_now[j - 1]
            current[j] = step + best
            steps_now[j] = taken + 1
        previous, steps_before = current, steps_now
    if not open_end:
        total, taken = previous[columns], steps_before[columns]
        return (total / taken if taken else infinity), columns
    best_score, best_end = infinity, columns
    for j in range(1, columns + 1):
        if previous[j] >= infinity or not steps_before[j]:
            continue
        normalised = previous[j] / steps_before[j]
        if normalised < best_score:
            best_score, best_end = normalised, j
    return best_score, best_end


# --- what was recorded ----------------------------------------------------

class Templates:
    """The recordings of the name, and the score each of them will accept.

    A threshold per recording rather than one for the set. The name can be said
    more than one way — "Zeno", "Hey Zeno" — and those are genuinely different
    sounds; a single threshold worked out across all of them measures how far
    apart the *variants* are, which is a large number, and hands back something
    so loose it accepts most speech. Each recording is judged against its own
    nearest twin instead, which is another saying of the same variant.
    """

    def __init__(self, phrase="", rows=None, threshold=0.0, lengths=None,
                 thresholds=None):
        self.phrase = phrase
        self.rows = rows or []
        self.threshold = threshold          # kept for a note written by an older build
        self.lengths = lengths or []
        self.thresholds = thresholds or []

    @property
    def ready(self):
        return len(self.rows) >= 2 and bool(self.thresholds)

    def mean_length(self):
        return sum(self.lengths) / len(self.lengths) if self.lengths else 0.0

    def long_enough(self, frames):
        """Whether what was heard could contain the name at all.

        Only a floor. There is no ceiling any more: the name is looked for at
        the beginning of what was said, so an utterance that carries a whole
        instruction after it is exactly the case this has to accept.
        """
        shortest = min(self.lengths) if self.lengths else 0
        return frames >= shortest * MIN_COVERAGE

    def score(self, rows):
        """The best distance to any recording. Lower is a better match."""
        found, _ = self.locate(rows)
        return found

    def locate(self, rows):
        """(best ratio, score, frame it ended on) over every recording.

        The ratio is the score against that recording's own threshold, so the
        recordings are comparable with each other even though a short variant
        and a long one accept quite different distances. Below 1 is a match.
        """
        if not rows or not self.rows:
            return float("inf"), float("inf"), 0
        best_ratio, best_score, best_end = float("inf"), float("inf"), 0
        for index, template in enumerate(self.rows):
            limit = self.thresholds[index] if index < len(self.thresholds) else 0.0
            if limit <= 0:
                continue
            found, stop = prefix_distance(template, rows)
            ratio = found / limit
            if ratio < best_ratio:
                best_ratio, best_score, best_end = ratio, found, stop
        return best_ratio, best_score, best_end

    def matches(self, rows, sensitivity=1.0):
        """(heard it, score as a fraction of what would be accepted, end frame)."""
        if not self.ready or not self.long_enough(len(rows)):
            return False, float("inf"), 0
        ratio, _score, end = self.locate(rows)
        return ratio <= sensitivity, ratio, end

    # ---- keeping them ----------------------------------------------------

    def to_dict(self):
        return {"version": TEMPLATE_VERSION, "phrase": self.phrase,
                "threshold": self.threshold, "lengths": self.lengths,
                "thresholds": self.thresholds, "templates": self.rows}

    @classmethod
    def from_dict(cls, data):
        if not isinstance(data, dict) or data.get("version") != TEMPLATE_VERSION:
            return cls()
        return cls(data.get("phrase", ""), data.get("templates") or [],
                   float(data.get("threshold") or 0.0), data.get("lengths") or [],
                   data.get("thresholds") or [])

    def save(self, path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = f"{path}.tmp"
        with open(tmp, "w", encoding="utf-8") as handle:
            json.dump(self.to_dict(), handle)
        os.replace(tmp, path)

    @classmethod
    def load(cls, path):
        try:
            with open(path, encoding="utf-8") as handle:
                return cls.from_dict(json.load(handle))
        except (OSError, ValueError):
            return cls()


ACCEPT_MARGIN = 1.35    # how much worse than its twin a reading may be
ACCEPT_FLOOR = 0.9      # and never tighter than this, however alike two takes were


def calibrate(recordings, phrase=""):
    """Turn a handful of recordings into templates that each know what to accept.

    Every recording is measured against its nearest neighbour among the others —
    which, when the name has been said several ways, is another saying of the
    same way — and told to accept a little worse than that. Somebody who says it
    the same every time gets a tight threshold and somebody who does not gets a
    loose one, which is the right answer in both cases and not one that could be
    guessed from outside.
    """
    rows = [r for r in recordings if r]
    if len(rows) < 2:
        return Templates(phrase, rows, 0.0, [len(r) for r in rows], [])
    thresholds = []
    for index, template in enumerate(rows):
        nearest = min(distance(template, other)
                      for position, other in enumerate(rows) if position != index)
        thresholds.append(max(nearest * ACCEPT_MARGIN, ACCEPT_FLOOR))
    return Templates(phrase, rows, sum(thresholds) / len(thresholds),
                     [len(r) for r in rows], thresholds)


# --- finding an utterance in a stream -------------------------------------

class Segmenter:
    """Where speech begins and ends, from loudness alone.

    The floor follows the room rather than being a number: a fan, a laptop and a
    quiet flat sit at wildly different levels, and an absolute threshold that
    works in one is deaf or permanently triggered in the others. It falls to
    whatever quiet it has heard and creeps back up, so a room that gets noisier
    is followed and a moment of silence does not permanently deafen it.
    """

    def __init__(self, margin_db=SPEECH_MARGIN_DB):
        self.margin = 10 ** (margin_db / 20.0)
        self.floor = None
        self._preroll = []
        self._current = []
        self._quiet = 0.0
        self.speaking = False

    def reset(self):
        self._preroll = []
        self._current = []
        self._quiet = 0.0
        self.speaking = False

    def feed(self, samples, level):
        """Hand it one block. Returns the finished utterance, or None."""
        if self.floor is None:
            self.floor = max(level, 1e-5)
        elif level < self.floor:
            self.floor = level * 0.25 + self.floor * 0.75      # falls quickly
        else:
            self.floor = min(self.floor * 1.0015, level)       # creeps back up

        loud = level > max(self.floor * self.margin, 1e-4)

        if not self.speaking:
            self._preroll.append(samples)
            keep = max(1, int(PREROLL_SECONDS / BLOCK_SECONDS))
            if len(self._preroll) > keep:
                self._preroll.pop(0)
            if loud:
                self.speaking = True
                self._current = list(self._preroll)
                self._preroll = []
                self._quiet = 0.0
            return None

        self._current.append(samples)
        self._quiet = 0.0 if loud else self._quiet + BLOCK_SECONDS
        spoken = len(self._current) * BLOCK_SECONDS
        if self._quiet < TAIL_SECONDS and spoken < MAX_SECONDS + TAIL_SECONDS:
            return None

        blocks, self._current = self._current, []
        self.speaking = False
        self._quiet = 0.0
        utterance = [sample for block in blocks for sample in block]
        seconds = len(utterance) / float(audio.RATE)
        if not MIN_SECONDS <= seconds <= MAX_SECONDS + TAIL_SECONDS:
            return None
        return utterance


def levels(block):
    """RMS of one block of signed samples, 0..1. The only sum a quiet room pays."""
    if not block:
        return 0.0
    total = 0
    for sample in block:
        total += sample * sample
    return math.sqrt(total / len(block)) / 32768.0


# --- the listener ---------------------------------------------------------

class WakeListener(QObject):
    """Holds the microphone open and says when it heard the phrase."""

    woken = pyqtSignal()
    failed = pyqtSignal(str)
    heard = pyqtSignal(float, bool)     # score as a fraction of the limit, accepted

    def __init__(self, conf, templates_path, parent=None):
        super().__init__(parent)
        self.conf = conf
        self.templates_path = templates_path
        self.templates = Templates()
        self._proc = None
        self._thread = None
        self._stop = threading.Event()
        self._paused = False
        self._last = 0.0
        self._clock = 0.0

    @property
    def running(self):
        return self._thread is not None and self._thread.is_alive()

    def reload(self):
        self.templates = Templates.load(self.templates_path)
        return self.templates

    def pause(self, paused):
        """Deaf while Dikte is already recording: what is being dictated is not
        an attempt to wake anything."""
        self._paused = bool(paused)

    def start(self):
        if self.running:
            return True
        self.reload()
        if not self.templates.ready:
            return False
        try:
            command = audio.capture_command(self.conf["mic_target"])
        except audio.AudioError as exc:
            self.failed.emit(str(exc))
            return False
        try:
            self._proc = subprocess.Popen(
                command, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL, bufsize=0, **plat.quiet())
        except OSError as exc:
            self.failed.emit(str(exc))
            return False
        self._stop.clear()
        self._thread = threading.Thread(target=self._listen, daemon=True)
        self._thread.start()
        return True

    def stop(self):
        self._stop.set()
        plat.interrupt(self._proc, timeout=1.5)
        if self._thread:
            self._thread.join(timeout=2)
        self._thread = None
        self._proc = None

    def _listen(self):
        import array
        stdout = self._proc.stdout
        segmenter = Segmenter()
        want = BLOCK * audio.SAMPLE_WIDTH
        try:
            while not self._stop.is_set():
                raw = stdout.read(want)
                if not raw:
                    break
                block = array.array("h")
                block.frombytes(raw[:len(raw) - len(raw) % 2])
                self._clock += BLOCK_SECONDS
                utterance = segmenter.feed(block, levels(block))
                if utterance is None:
                    continue
                if self._paused or self._clock - self._last < REFRACTORY_SECONDS:
                    continue
                self._consider(utterance)
        except (OSError, ValueError):
            pass

    def _consider(self, utterance):
        rows = head_features(utterance)
        if not rows:
            return
        ok, score, _end = self.templates.matches(
            rows, float(self.conf["wake_sensitivity"]))
        self.heard.emit(score, ok)
        if not ok:
            return
        self._last = self._clock
        self.woken.emit()


def head_features(utterance):
    """The features of the front of an utterance, which is where the name is."""
    return features(utterance[:int(HEAD_SECONDS * audio.RATE)])


# --- recording the phrase -------------------------------------------------

WANTED = 4          # how many times it has to be said


class Enroller(QObject):
    """Collects a few sayings of the phrase, through the same path that will
    later listen for it.

    The same path on purpose: the templates have to come from the microphone
    that will be used, cut at the boundaries the segmenter finds, and measured
    by the code that will measure them. Enrolling from a file, or from audio
    trimmed by hand, would produce templates that are subtly not what the
    listener sees and a threshold that is subtly wrong.
    """

    captured = pyqtSignal(int, int)     # how many so far, how many wanted
    finished = pyqtSignal(object)       # Templates
    failed = pyqtSignal(str)

    def __init__(self, conf, phrase, wanted=WANTED, parent=None):
        super().__init__(parent)
        self.conf = conf
        self.phrase = phrase
        self.wanted = wanted
        self._proc = None
        self._thread = None
        self._stop = threading.Event()
        self._rows = []

    @property
    def running(self):
        return self._thread is not None and self._thread.is_alive()

    def start(self):
        if self.running:
            return True
        try:
            command = audio.capture_command(self.conf["mic_target"])
        except audio.AudioError as exc:
            self.failed.emit(str(exc))
            return False
        try:
            self._proc = subprocess.Popen(
                command, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL, bufsize=0, **plat.quiet())
        except OSError as exc:
            self.failed.emit(str(exc))
            return False
        self._rows = []
        self._stop.clear()
        self._thread = threading.Thread(target=self._collect, daemon=True)
        self._thread.start()
        return True

    def stop(self):
        self._stop.set()
        plat.interrupt(self._proc, timeout=1.5)
        if self._thread:
            self._thread.join(timeout=2)
        self._thread = None
        self._proc = None

    def _collect(self):
        import array
        stdout = self._proc.stdout
        segmenter = Segmenter()
        want = BLOCK * audio.SAMPLE_WIDTH
        try:
            while not self._stop.is_set() and len(self._rows) < self.wanted:
                raw = stdout.read(want)
                if not raw:
                    break
                block = array.array("h")
                block.frombytes(raw[:len(raw) - len(raw) % 2])
                utterance = segmenter.feed(block, levels(block))
                if utterance is None:
                    continue
                rows = features(utterance)
                if not rows:
                    continue
                self._rows.append(rows)
                self.captured.emit(len(self._rows), self.wanted)
        except (OSError, ValueError):
            pass
        if self._stop.is_set():
            return
        if len(self._rows) < 2:
            self.failed.emit("")
            return
        self.finished.emit(calibrate(self._rows, self.phrase))
