"""The loop from being asked to listen to having answered.

    waiting → listening → working → answering → waiting

Dictation is a thing with a beginning and an end that a person supplies: press,
talk, press. This has only the beginning. The instruction ends when the speaking
does, so that edge has to be found rather than given, and everything after it
runs without anybody there to notice it went wrong.

Three rules hold the whole thing together, and each is here because breaking it
is worse than it sounds:

  * One microphone, one owner. A dictation wants it, an instruction wants it,
    a meeting wants it for an hour, and only one of them may have it.
  * What the agent comes back with crosses a thread boundary, and it crosses
    it by signal. A timer started on a worker thread is started on a thread
    with no event loop to run it and never fires at all — which is how every
    answer was lost, silently, until it was measured.
  * Silence ends the instruction, but only after long enough to think. People
    stop mid-sentence to find a word. Cutting at the first gap loses the half of
    the sentence that mattered.
"""

import time

from PyQt6.QtCore import QObject, QTimer, pyqtSignal

import audio
import router
import vad
from i18n import t

# What state it is in, in the order it goes through them.
WAITING = "waiting"        # nothing going on
LISTENING = "listening"    # taking the instruction
WORKING = "working"        # transcribing, deciding, doing
ANSWERING = "answering"    # saying the answer out loud

# How long to wait for the instruction to start before deciding the name was a
# mistake. Long enough to draw breath, short enough not to sit there recording
# a room nobody is talking to.
PATIENCE_SECONDS = 5.0

# Quiet this long ends the instruction. Much longer than the gap that separates
# one utterance from the next, because a person pausing to find a word has not
# finished talking, and an instruction cut off at the first hesitation is one
# that has to be given again.
SETTLE_SECONDS = 1.4

# Nobody dictates a paragraph to an assistant in one go; past this it is a room
# with a television on in it.
LIMIT_SECONDS = 45.0

WATCH_MS = 120


class Conversation(QObject):
    """Owns what happens between the name being heard and the answer being given."""

    state_changed = pyqtSignal(str)
    # What was heard, and what came back. The application puts these in bubbles.
    heard = pyqtSignal(str)
    answered = pyqtSignal(str)
    stage = pyqtSignal(str)
    failed = pyqtSignal(str)
    # Handed back to the application, which owns the clipboard and the agent.
    # This module decides what was meant; it does not reach for anything itself.
    finish_dictation = pyqtSignal(str)
    ask_agent = pyqtSignal(str)
    # The agent runs on a thread of its own, and what it comes back with has
    # to cross back to the one the interface lives on. A signal is the only
    # thing that does that: a timer started on a worker thread is started on
    # a thread with no event loop to run it, and never fires at all. Which is
    # exactly what happened — the answer arrived and nothing was ever told.
    agent_answered = pyqtSignal(str, str)
    agent_failed = pyqtSignal(str)

    def __init__(self, conf, recorder, pipeline, voice, parent=None):
        super().__init__(parent)
        self.conf = conf
        self.recorder = recorder
        self.pipeline = pipeline
        self.voice = voice
        self.state = WAITING
        # Which lobe was pressed for the job in hand.
        self.mode = router.ASK
        # Set while an instruction that began "write this down" is waiting for
        # the words themselves, which are still to be spoken.
        self.pending_dictation = False

        self._watch = QTimer(self)
        self._watch.setInterval(WATCH_MS)
        self._watch.timeout.connect(self._look)
        self._began = 0.0
        self._spoke_at = 0.0
        self._heard_speech = False

        self.pipeline.finished.connect(self._on_finished)
        self.pipeline.failed.connect(self._on_failed)
        self.pipeline.stage.connect(self.stage)
        self.voice.finished.connect(self._on_spoken)
        self.voice.failed.connect(lambda _m: self._on_spoken())

    # ---- state ------------------------------------------------------------

    @property
    def busy(self):
        return self.state != WAITING

    def _set_state(self, state):
        if state != self.state:
            self.state = state
            self.state_changed.emit(state)

    # ---- being called -----------------------------------------------------

    def wake(self, mode=router.ASK):
        """Asked for. Start listening for the instruction.

        `mode` is which of the two was pressed. It is the whole reason the
        control has two lobes: told outright, nothing has to be guessed from
        the words, and the one thing that cannot be recovered from — a note
        sent to the agent, or a question typed into a document — cannot happen.
        """
        if self.busy:
            return False
        self.mode = mode
        if not self.recorder.active:
            self.recorder.start(self.conf["mic_target"], int(LIMIT_SECONDS))
            if not self.recorder.active:
                return False
        self._began = time.monotonic()
        self._spoke_at = 0.0
        self._heard_speech = False
        self._watch.start()
        self._set_state(LISTENING)
        return True

    def cancel(self):
        """Give up on whatever is going on and go back to waiting."""
        self._watch.stop()
        if self.recorder.active:
            self.recorder.cancel()
        self.voice.stop()
        self.pending_dictation = False
        self._set_state(WAITING)

    # ---- finding the end of the instruction -------------------------------

    def _look(self):
        """Watch the level and decide when the speaking has stopped."""
        if self.state != LISTENING:
            return
        pcm, rms = self.recorder.snapshot()
        now = time.monotonic()
        elapsed = now - self._began

        if rms:
            # Two tests, not one. Relative alone — "louder than this recording's
            # own floor" — is met by the microphone's own hiss in a quiet room,
            # because the spread of that hiss is itself more than the margin;
            # measured, that left it recording an empty room indefinitely. So a
            # block also has to clear the absolute floor below which nothing is
            # speech, which is the same pair of tests the finished recording is
            # judged by.
            stats = vad.analyse(rms, _chunk_seconds(),
                                self.conf["speech_margin_db"])
            gate = max(stats["noise_db"] + self.conf["speech_margin_db"],
                       float(self.conf["silence_db"]))
            recent = rms[-max(1, int(0.25 / _chunk_seconds())):]
            loud = any(vad.to_db(value) > gate for value in recent)
            spoken_at_all = not vad.is_silent(
                stats, self.conf["silence_db"], self.conf["speech_margin_db"],
                self.conf["min_voiced_seconds"])
            if loud and spoken_at_all:
                self._heard_speech = True
                self._spoke_at = now

        if not self._heard_speech:
            # Asked for, and then nothing said. Say nothing back: a key
            # pressed by accident should cost a moment and no more.
            if elapsed > PATIENCE_SECONDS:
                self._watch.stop()
                self.recorder.cancel()
                self.pending_dictation = False
                self._set_state(WAITING)
            return

        if now - self._spoke_at >= SETTLE_SECONDS or elapsed >= LIMIT_SECONDS:
            self._watch.stop()
            self._set_state(WORKING)
            self.recorder.stop()

    # ---- what to do with it ------------------------------------------------

    def take(self, wav_path, duration, rms_values):
        """The recording is in. Work out what was meant and set it going.

        Called by the application when the recorder hands over, because the
        recorder is shared with plain dictation and only the application knows
        which of the two asked for this one.
        """
        self._set_state(WORKING)
        # Transcribed by the same chain everything else uses. What it is for is
        # decided afterwards, from the words: routing needs the text, and the
        # text is what the chain exists to produce.
        self.pipeline.run(wav_path, duration, rms_values, ask=False, paste_it=False)

    def _on_finished(self, _raw, text, warning):
        if self.state not in (WORKING, LISTENING):
            return
        said = (text or "").strip()
        if not said:
            self._set_state(WAITING)
            return
        self.heard.emit(said)

        if self.pending_dictation:
            # It was told to write something down and this is the something.
            self.pending_dictation = False
            self._paste(said, warning)
            return

        if self.mode == router.DICTATE:
            # The writing lobe was pressed. The words are the point; nothing is
            # read into them.
            self._paste(said, warning)
            return

        # The asking lobe. The words still get a say in one direction: somebody
        # who presses ask and then says "yaz şunu" meant to write it down, and
        # honouring that costs nothing. The reverse is not allowed — the
        # writing lobe never quietly turns into an instruction to the agent.
        mode, payload = router.route(said, self.conf["dictation_openings"])
        if mode == router.DICTATE:
            if payload:
                self._paste(payload, warning)
            else:
                # "Write this down" and nothing else: the words are still to
                # come, so listen again rather than paste the instruction.
                self.pending_dictation = True
                self.answered.emit(t("Go ahead, I am listening."))
                self._say(t("Go ahead, I am listening."))
            return
        self._ask(payload)

    def _paste(self, text, warning=""):
        """Put the words where the cursor is, which is what was asked for."""
        self.answered.emit(text)
        if warning:
            self.failed.emit(warning)
        self.finish_dictation.emit(text)
        self._set_state(WAITING)

    def _ask(self, question):
        """Hand it to the agent. The answer comes back through _on_answered."""
        self._set_state(WORKING)
        self.ask_agent.emit(question)

    def answer(self, text, warning=""):
        """The agent replied. Say it, show it, and go back to waiting."""
        said = (text or "").strip()
        if said:
            self.answered.emit(said)
        if warning:
            self.failed.emit(warning)
        if said and self._say(said):
            self._set_state(ANSWERING)
            return
        self._set_state(WAITING)

    def _say(self, text):
        return bool(self.voice.say(text))

    def _on_spoken(self):
        if self.state == ANSWERING:
            self._set_state(WAITING)

    def _on_failed(self, message):
        if self.state == WAITING:
            return
        self.pending_dictation = False
        self.failed.emit(message)
        self._set_state(WAITING)


def _chunk_seconds():
    return audio.CHUNK_FRAMES / float(audio.RATE)
