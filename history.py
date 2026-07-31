"""Everything that was asked, and everything that came back.

The application already kept a history: worker.py has written a row per
dictation into `history.jsonl` for as long as there has been a worker. What was
missing was somewhere to *read* it as a conversation — a request and the answer
to it, in order, in full. That is what this is.

One file, not two. A second store for "chat" turns would have meant two things
that both call themselves the history, disagreeing about the same dictation the
first time one of them was written to and the other was not. So this reads the
rows that are already there, normalises the two shapes they come in, and appends
in the same shape.

A turn that is still waiting for its answer is held in memory and never written.
That is deliberate: an unanswered question is not worth keeping, and if the
application stops between the asking and the answering there is nothing there to
be resumed. The panel shows it because it is happening; the file gets it once
there is something to get.
"""

import json
import time
import uuid

from PyQt6.QtCore import QObject, pyqtSignal

import config as cfg

# What the turn was for. The same two words the control uses, on purpose.
DICTATE = "dictate"
ASK = "ask"

# What has become of it.
PENDING = "pending"
DONE = "done"
FAILED = "failed"


class Turn:
    """One request and its answer."""

    def __init__(self, mode=ASK, question="", answer="", state=PENDING,
                 when=None, model="", turn_id=None):
        self.id = turn_id or uuid.uuid4().hex[:12]
        self.mode = mode
        self.question = question or ""
        self.answer = answer or ""
        self.state = state
        self.when = float(when if when is not None else time.time())
        self.model = model or ""

    @property
    def pending(self):
        return self.state == PENDING

    @property
    def failed(self):
        return self.state == FAILED

    def as_row(self):
        return {
            "id": self.id,
            "ts": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(self.when)),
            "when": round(self.when, 3),
            "mode": self.mode,
            "question": self.question,
            "text": self.answer,
            "state": self.state,
            "assistant_model": self.model,
        }


def _parse(row):
    """One row of the file as a Turn, whichever of the shapes it is in.

    worker.py's rows have no `state` and use `mode: ""` for a plain dictation,
    where what was said *is* the whole of it. Rather than migrate the file — and
    lose whatever a half-finished migration would lose — both are read.
    """
    if not isinstance(row, dict):
        return None
    text = (row.get("text") or "").strip()
    question = (row.get("question") or "").strip()
    mode = row.get("mode") or DICTATE
    if mode not in (DICTATE, ASK):
        mode = ASK if question else DICTATE
    if mode == DICTATE and not text and not question:
        return None
    if mode == ASK and not (question or text):
        return None
    when = row.get("when")
    if when is None:
        when = _stamp(row.get("ts", ""))
    # A dictation has no question in it: what was said *is* what was produced,
    # so it lands in `answer` and there is nothing to show above it.
    return Turn(
        mode=mode,
        question=question if mode == ASK else "",
        answer=text,
        state=row.get("state") or (FAILED if row.get("cleanup_error")
                                   and not text else DONE),
        when=when,
        model=row.get("assistant_model") or row.get("model") or "",
        turn_id=row.get("id"),
    )


def _stamp(text):
    """The old rows keep a local timestamp and nothing else. Read it back."""
    try:
        return time.mktime(time.strptime(text, "%Y-%m-%d %H:%M:%S"))
    except (ValueError, OverflowError):
        return 0.0


class Store(QObject):
    """The turns, on disk and in order, with the one in flight on top."""

    # A turn has arrived, changed, or gone. The panel redraws from `turns()`
    # rather than being handed a diff: the list is short and a diff is a second
    # description of the same thing, free to disagree with the first.
    changed = pyqtSignal()

    def __init__(self, limit=400, parent=None):
        super().__init__(parent)
        self.limit = int(limit)
        self._pending = []

    # ---- reading ---------------------------------------------------------

    def turns(self, limit=None):
        """Oldest first, with anything still being answered at the end."""
        rows = cfg.read_history(limit or self.limit)
        out = [turn for turn in (_parse(row) for row in rows) if turn is not None]
        out.sort(key=lambda turn: turn.when)
        return out + list(self._pending)

    def __len__(self):
        return len(self.turns())

    # ---- writing ---------------------------------------------------------

    def begin(self, mode, question, model=""):
        """A request has gone out. Show it; do not write it down yet."""
        turn = Turn(mode=mode, question=question, model=model)
        self._pending.append(turn)
        self.changed.emit()
        return turn

    def finish(self, turn, answer="", error=""):
        """The answer is in. Now it is worth keeping."""
        if turn is None:
            return None
        turn.answer = (answer or "").strip() or (error or "")
        turn.state = FAILED if error and not (answer or "").strip() else DONE
        if turn in self._pending:
            self._pending.remove(turn)
        self._append(turn)
        self.changed.emit()
        return turn

    def drop(self, turn):
        """It was called off. Nothing to keep."""
        if turn in self._pending:
            self._pending.remove(turn)
            self.changed.emit()

    def record(self, mode, question, answer, model=""):
        """A whole turn at once, for the paths that have both ends already."""
        turn = Turn(mode=mode, question=question, answer=answer,
                    state=DONE, model=model)
        self._append(turn)
        self.changed.emit()
        return turn

    def _append(self, turn):
        try:
            cfg.append_history(turn.as_row())
            cfg.trim_history(self.limit)
        except OSError:
            # A history that cannot be written is not worth stopping a
            # dictation for; the answer is already on the screen.
            pass

    def clear(self):
        self._pending = []
        try:
            cfg.clear_history()
        except OSError:
            pass
        self.changed.emit()


def as_markdown(turns):
    """The whole conversation as one markdown document, for copying out."""
    out = []
    for turn in turns:
        when = time.strftime("%Y-%m-%d %H:%M", time.localtime(turn.when))
        out.append("## %s — %s" % (
            "Dikte" if turn.mode == DICTATE else "Zeno", when))
        if turn.question:
            out.append("")
            out.append("> " + turn.question.replace("\n", "\n> "))
        if turn.answer:
            out.append("")
            out.append(turn.answer)
        out.append("")
    return "\n".join(out).strip() + "\n"
