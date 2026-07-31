"""The loop from a button being pressed to the job being done.

    waiting → listening → working → waiting

Press, talk, press. Both edges are given rather than guessed, and that is the
whole design: the second press is the only thing that ends a recording.

Finding the end by listening for silence was built first and then taken out. It
is wrong in both directions and no threshold fixes it. A person hunting for a
word pauses, and the recording ends mid-sentence; a room with a fan in it never
falls quiet, and the recording runs on until a limit stops it. The first is much
the worse of the two, because what was cut off is the half you cared about and
there is no way back to it except to say the whole thing again. A finger knows
when a sentence has finished, and nothing else does.

Which of the two jobs is meant arrives from the button as well. The control has
a lobe for each, so nothing is read out of the words — the mistake that reading
them can make is the one that cannot be taken back.

The answer comes back written, not spoken. There was a voice here once, and it
took the loop through a fifth state while it talked. What replaced it is a
window you can read the answer in twice, which is what an answer worth having
deserves.

One more rule, and it is here because breaking it was silent: what the agent
comes back with crosses a thread boundary, and it crosses it by signal. A timer
started on a worker thread is started on a thread with no event loop to run it,
and never fires at all. That is how every answer was lost, until it was measured.
"""

import time

from PyQt6.QtCore import QObject, QTimer, pyqtSignal

# Which of the two was asked for.
DICTATE = "dictate"
ASK = "ask"

# What state it is in, in the order it goes through them.
WAITING = "waiting"        # nothing going on
LISTENING = "listening"    # taking the instruction, until the next press
WORKING = "working"        # transcribing, and doing whatever was asked

# Nothing here runs on a clock except this: the case where the second press
# never comes, because the window was closed or the press missed. Long enough
# that nobody dictating a paragraph will ever meet it.
LIMIT_SECONDS = 300.0


class Conversation(QObject):
    """Owns what happens between the two presses, and everything after them."""

    state_changed = pyqtSignal(str)
    # What was heard, and what came back. The application shows these.
    heard = pyqtSignal(str)
    answered = pyqtSignal(str)
    stage = pyqtSignal(str)
    failed = pyqtSignal(str)
    # Handed back to the application, which owns the clipboard and the agent.
    # This module decides nothing about either; it decides when.
    finish_dictation = pyqtSignal(str)
    ask_agent = pyqtSignal(str)
    # Emitted from the agent's own thread, and delivered on this one.
    agent_answered = pyqtSignal(str, str)
    agent_failed = pyqtSignal(str)

    def __init__(self, conf, recorder, pipeline, parent=None):
        super().__init__(parent)
        self.conf = conf
        self.recorder = recorder
        self.pipeline = pipeline
        self.state = WAITING
        self.mode = ASK
        self._began = 0.0

        # Not a way of ending a recording; a way of not recording for ever.
        self._limit = QTimer(self)
        self._limit.setSingleShot(True)
        self._limit.timeout.connect(self._out_of_time)

        self.pipeline.finished.connect(self._on_finished)
        self.pipeline.failed.connect(self._on_failed)
        self.pipeline.stage.connect(self.stage)

    # ---- state ------------------------------------------------------------

    @property
    def busy(self):
        return self.state != WAITING

    @property
    def listening(self):
        return self.state == LISTENING

    @property
    def seconds(self):
        return time.monotonic() - self._began if self.state == LISTENING else 0.0

    def _set_state(self, state):
        if state != self.state:
            self.state = state
            self.state_changed.emit(state)

    # ---- the two presses --------------------------------------------------

    def wake(self, mode=ASK):
        """The first press. Start recording, and keep recording."""
        if self.busy:
            return False
        if not self.recorder.active:
            self.recorder.start(self.conf["mic_target"], int(LIMIT_SECONDS))
            if not self.recorder.active:
                return False
        self.mode = mode
        self._began = time.monotonic()
        self._limit.start(int(LIMIT_SECONDS * 1000))
        self._set_state(LISTENING)
        return True

    def finish(self):
        """The second press. Stop recording and get on with it."""
        if self.state != LISTENING:
            return False
        self._limit.stop()
        self._set_state(WORKING)
        self.recorder.stop()
        return True

    def cancel(self):
        """Give up on whatever is going on and go back to waiting."""
        self._limit.stop()
        if self.recorder.active:
            self.recorder.cancel()
        self._set_state(WAITING)

    def _out_of_time(self):
        """The second press never came. Keep what was said rather than lose it."""
        if self.state == LISTENING:
            self.finish()

    # ---- what to do with it ------------------------------------------------

    def take(self, wav_path, duration, rms_values):
        """The recording is in. Set the chain going.

        Called by the application when the recorder hands over, because the
        recorder is shared with plain dictation and only the application knows
        which of the two asked for this one.
        """
        self._set_state(WORKING)
        # Pasting is settled here rather than by the chain: what was said has to
        # be read before anything can be done with it, and in the asking mode it
        # must not be pasted at all.
        self.pipeline.run(wav_path, duration, rms_values, ask=False, paste_it=False)

    def _on_finished(self, _raw, text, warning):
        if self.state not in (WORKING, LISTENING):
            return
        said = (text or "").strip()
        if not said:
            self._set_state(WAITING)
            return
        self.heard.emit(said)
        if self.mode == DICTATE:
            # The writing lobe. The words are the point; nothing is read into
            # them, and none of them can turn this into a question.
            self._paste(said, warning)
            return
        self._ask(said)

    def _paste(self, text, warning=""):
        """Put the words where the cursor is, which is what was asked for."""
        self.answered.emit(text)
        if warning:
            self.failed.emit(warning)
        self.finish_dictation.emit(text)
        self._set_state(WAITING)

    def _ask(self, question):
        """Hand it to the agent. The answer comes back through answer()."""
        self._set_state(WORKING)
        self.ask_agent.emit(question)

    def answer(self, text, warning=""):
        """The agent replied. Show it, and go back to waiting."""
        said = (text or "").strip()
        if said:
            self.answered.emit(said)
        if warning:
            self.failed.emit(warning)
        self._set_state(WAITING)

    def _on_failed(self, message):
        if self.state == WAITING:
            return
        self.failed.emit(message)
        self._set_state(WAITING)
