"""The control you press, and the running commentary beside it.

Two pieces, and the split between them is the point.

The control is a capsule with three lobes, parked on the edge of the screen. The
first writes: what you say is tidied and put where the cursor is. The second
asks: what you say goes to the agent and the answer comes back written. The
third opens the history — everything either of the first two has ever done, as a
conversation you can read and copy out of.

The first two are separate buttons rather than one button with a mode, because a
mode is a thing you have to remember and a thing you can be wrong about — and
being wrong here means a note pasted into a chat window, or a question typed
into a document. A lobe costs a few pixels and removes the question.

Beside it, bubbles: what it heard as you are still saying it, and what came of
it. They sit against the same edge the control does, deliberately. Across the
middle of the screen was tried, over a ribbon that moved with the voice, and it
is the wrong place: something that appears for every sentence you dictate has no
business in the middle of what you are working on. An edge is where a running
commentary belongs.

Nothing is loaded from disk. Both are drawn, which keeps them sharp at any
scaling and keeps a picture of unclear provenance out of a GPL project.
"""

import math
import time

from PyQt6.QtCore import (QObject, QPointF, QRect, QRectF, QTimer, Qt,
                          pyqtSignal)
from PyQt6.QtGui import (QBrush, QColor, QFont, QFontMetrics, QPainter,
                         QPainterPath, QPen, QRadialGradient)
from PyQt6.QtWidgets import QApplication, QWidget

import theme

# --- the three things it can be asked to do -------------------------------

WRITE = "write"
ASK = "ask"
HISTORY = "history"

ORDER = (WRITE, ASK, HISTORY)

# --- what it is doing -----------------------------------------------------

IDLE = "idle"
LISTENING = "listening"
THINKING = "thinking"
ANSWER = "answer"
WARNING = "warning"
ERROR = "error"

# (bright, body, deep) per lobe, from the one palette. Writing is the cool one,
# asking the accent and the history the green the agent already answers in, so
# which lobe is lit is legible at the edge of vision and not only up close.
LOBE = {
    WRITE: (theme.WRITE_BRIGHT, theme.WRITE_COLOUR, theme.WRITE_DEEP),
    ASK: (theme.ACCENT_BRIGHT, theme.ACCENT, theme.ACCENT_DEEP),
    HISTORY: (theme.AGENT_BRIGHT, theme.AGENT_COLOUR, theme.AGENT_DEEP),
}


STATE_TINT = {
    THINKING: theme.BUSY,
    ANSWER: theme.GOOD,
    WARNING: theme.WARN,
    ERROR: theme.BAD,
}

BUSY_MS = 33
CALM_MS = 120



def bubble_seconds(text, floor=3.0, ceiling=30.0):
    """How long something stays on screen, from how much there is to read.

    Roughly eleven characters a second, which is a comfortable reading pace with
    a moment at each end to find the text and to finish it. The floor is there
    because a two-word answer still has to be seen, and the ceiling because a
    long one should not own the middle of the screen for the rest of the day.
    """
    seconds = 1.5 + len(str(text)) / 11.0
    return max(floor, min(ceiling, seconds))


def clamp(value, low, high):
    return max(low, min(high, value))


def _colour(name, alpha=255):
    colour = QColor(name)
    colour.setAlpha(alpha)
    return colour


# --- the control ----------------------------------------------------------

class Pill(QWidget):
    """Three lobes in one capsule: write, ask, and what has been asked before."""

    pressed = pyqtSignal(str)      # WRITE, ASK or HISTORY
    moved = pyqtSignal(int, int)

    def __init__(self, lobe=52, parent=None):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowDoesNotAcceptFocus
            | Qt.WindowType.X11BypassWindowManagerHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        self.state = IDLE
        self.active = None          # which lobe is working, if any
        self.held = None            # a lobe lit because something it opened is
                                    # still open, rather than because it is busy
        self._phase = 0.0
        self._level = 0.0
        self._hover = None
        self._press = None
        self._press_lobe = None
        self._dragged = False
        self.set_lobe(lobe)

        self._anim = QTimer(self)
        self._anim.timeout.connect(self._tick)
        self._anim.start(CALM_MS)

    def set_lobe(self, lobe):
        self._lobe = max(28, int(lobe))
        pad = int(self._lobe * 0.22)
        self.resize(self._lobe * len(ORDER) + pad * 2, self._lobe + pad * 2)

    # ---- state -----------------------------------------------------------

    def set_state(self, state, lobe=None):
        if lobe is not None:
            self.active = lobe
        if state == IDLE:
            self.active = None
        if state == self.state:
            self.update()
            return
        self.state = state
        if state != LISTENING:
            self._level = 0.0
        self._anim.setInterval(
            BUSY_MS if state in (LISTENING, THINKING) else CALM_MS)
        self.update()

    def hold(self, lobe):
        """Keep a lobe lit for as long as what it opened stays open."""
        if lobe != self.held:
            self.held = lobe
            self.update()

    def push_level(self, level):
        level = clamp(float(level), 0.0, 1.0)
        self._level = max(level, self._level * 0.82)

    def _tick(self):
        self._phase += self._anim.interval() / 1000.0
        self.update()

    # ---- pressing and dragging -------------------------------------------

    def _lobe_at(self, position):
        pad = int(self._lobe * 0.22)
        if not (pad <= position.y() <= pad + self._lobe):
            return None
        for index, lobe in enumerate(ORDER):
            left = pad + self._lobe * index
            if left <= position.x() < left + self._lobe:
                return lobe
        return None

    def mouseMoveEvent(self, event):
        if self._press is not None:
            target = event.globalPosition().toPoint() - self._press
            if not self._dragged:
                if (target - self.pos()).manhattanLength() < 6:
                    return
                self._dragged = True
            self.move(target)
            return
        found = self._lobe_at(event.position())
        if found != self._hover:
            self._hover = found
            self.update()

    def leaveEvent(self, _event):
        self._hover = None
        self.update()

    def mousePressEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return
        self._press = event.globalPosition().toPoint() - self.pos()
        self._press_lobe = self._lobe_at(event.position())
        self._dragged = False

    def mouseReleaseEvent(self, event):
        if self._press is None:
            return
        self._press = None
        if self._dragged:
            self.moved.emit(self.x(), self.y())
        elif self._press_lobe:
            self.pressed.emit(self._press_lobe)
        self._press_lobe = None

    # ---- drawing ---------------------------------------------------------

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        self._paint(painter)
        painter.end()

    def _paint(self, painter):
        pad = self._lobe * 0.22
        radius = self._lobe / 2.0
        body = QRectF(pad, pad, self._lobe * len(ORDER), self._lobe)

        # The capsule they sit in, so the two read as one control.
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(14, 16, 22, 190))
        painter.drawRoundedRect(body, radius, radius)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor(255, 255, 255, 26), 1.2))
        painter.drawRoundedRect(body, radius, radius)

        for index, lobe in enumerate(ORDER):
            centre = QPointF(pad + radius + index * self._lobe, pad + radius)
            self._paint_lobe(painter, lobe, centre, radius)

    def _paint_lobe(self, painter, lobe, centre, radius):
        bright, body, deep = LOBE[lobe]
        working = self.active == lobe and self.state != IDLE
        lit = working or self.held == lobe
        if working and self.state in STATE_TINT:
            bright = body = STATE_TINT[self.state]

        swell = 1.0
        if working and self.state == LISTENING:
            swell += 0.13 * self._level
        elif working:
            swell += 0.03 * math.sin(self._phase * 3.0)
        size = radius * 0.72 * swell

        if lit:
            glow = QRadialGradient(centre, radius * 1.25)
            glow.setColorAt(0.0, _colour(bright, 90))
            glow.setColorAt(1.0, _colour(bright, 0))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(glow))
            painter.drawEllipse(centre, radius * 1.25, radius * 1.25)

        fill = QRadialGradient(
            QPointF(centre.x() - size * 0.3, centre.y() - size * 0.35), size * 1.7)
        alpha = 255 if lit else (210 if self._hover == lobe else 150)
        fill.setColorAt(0.0, _colour(bright, alpha))
        fill.setColorAt(0.55, _colour(body, alpha))
        fill.setColorAt(1.0, _colour(deep, alpha))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(fill))
        painter.drawEllipse(centre, size, size)

        self._paint_mark(painter, lobe, centre, size)

        if working and self.state == THINKING:
            painter.setBrush(Qt.BrushStyle.NoBrush)
            box = QRectF(centre.x() - radius * 0.92, centre.y() - radius * 0.92,
                         radius * 1.84, radius * 1.84)
            painter.setPen(QPen(_colour(bright, 40), 2.0))
            painter.drawEllipse(box)
            painter.setPen(QPen(_colour(bright, 210), 2.4,
                                Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            painter.drawArc(box, int(self._phase * 190) % 360 * 16, 100 * 16)

    def _paint_mark(self, painter, lobe, centre, size):
        """A nib for writing, a spark for asking, two bubbles for the history.

        Drawn rather than lettered: a glyph at this size is a smudge, and a
        letter would be a language.
        """
        ink = QColor(255, 255, 255, 235)
        painter.setBrush(ink)
        painter.setPen(Qt.PenStyle.NoPen)
        unit = size * 0.52
        if lobe == HISTORY:
            # Two overlapping speech bubbles: the one thing at this size that
            # reads as "a conversation" without any text in it.
            back = QRectF(centre.x() - unit * 1.02, centre.y() - unit * 0.96,
                          unit * 1.6, unit * 1.18)
            front = QRectF(centre.x() - unit * 0.52, centre.y() - unit * 0.30,
                           unit * 1.6, unit * 1.18)
            painter.setBrush(QColor(255, 255, 255, 130))
            painter.drawRoundedRect(back, unit * 0.34, unit * 0.34)
            painter.setBrush(QColor(14, 16, 22, 235))
            painter.drawRoundedRect(front.adjusted(-unit * 0.11, -unit * 0.11,
                                                   unit * 0.11, unit * 0.11),
                                    unit * 0.42, unit * 0.42)
            painter.setBrush(ink)
            painter.drawRoundedRect(front, unit * 0.34, unit * 0.34)
            tail = QPainterPath()
            tail.moveTo(front.left() + unit * 0.30, front.bottom() - unit * 0.04)
            tail.lineTo(front.left() + unit * 0.06, front.bottom() + unit * 0.46)
            tail.lineTo(front.left() + unit * 0.74, front.bottom() - unit * 0.04)
            tail.closeSubpath()
            painter.drawPath(tail)
            return
        if lobe == WRITE:
            nib = QPainterPath()
            nib.moveTo(centre.x() - unit * 0.75, centre.y() + unit * 0.75)
            nib.lineTo(centre.x() - unit * 0.42, centre.y() + unit * 0.30)
            nib.lineTo(centre.x() + unit * 0.72, centre.y() - unit * 0.84)
            nib.lineTo(centre.x() + unit * 0.98, centre.y() - unit * 0.52)
            nib.lineTo(centre.x() - unit * 0.20, centre.y() + unit * 0.62)
            nib.closeSubpath()
            painter.drawPath(nib)
            painter.setPen(QPen(ink, max(1.4, unit * 0.16),
                                Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            painter.drawLine(QPointF(centre.x() - unit * 0.85, centre.y() + unit * 1.02),
                             QPointF(centre.x() + unit * 0.55, centre.y() + unit * 1.02))
            return
        star = QPainterPath()
        for index in range(8):
            angle = math.pi * index / 4.0
            reach = unit * (1.05 if index % 2 == 0 else 0.34)
            point = QPointF(centre.x() + math.cos(angle) * reach,
                            centre.y() + math.sin(angle) * reach)
            star.lineTo(point) if index else star.moveTo(point)
        star.closeSubpath()
        painter.drawPath(star)


# --- what it says ---------------------------------------------------------

# (background, border, text) for each kind of bubble.
BUBBLE_STYLE = {
    "heard": ("#1E2A4Aee", "#3F5FD9", "#E8EEFF"),
    "live":  ("#1B2440cc", "#2E3F86", "#AFC0E8"),
    "stage": ("#22242Add", "#3A3D46", "#B8BDC8"),
    "agent": ("#132E28ee", "#2FC08A", "#DCFFF1"),
    "warn":  ("#33260Fee", "#E8903D", "#FFE7C6"),
    "error": ("#33120Fee", "#E2453B", "#FFD6D2"),
}

BUBBLE_WIDTH = 348
BUBBLE_PADDING = 11
BUBBLE_GAP = 7
BUBBLE_RADIUS = 13
# The strip the tail sticks out into. Reserved rather than drawn over the edge,
# because a window clips its own painting and a tail drawn past the edge is
# simply not there.
BUBBLE_TAIL = 7
FADE_MS = 220.0


class _Said:
    """One bubble: what it says, how it is styled, and when it goes away."""

    def __init__(self, text, kind, seconds):
        self.text = text
        self.kind = kind
        self.seconds = seconds
        self.born = time.monotonic()
        self.closing = None       # set when it has been asked to leave early
        self.height = 0

    def age(self):
        return time.monotonic() - self.born

    def alpha(self):
        """0..1, so a bubble arrives and leaves rather than blinking."""
        appearing = min(1.0, self.age() * 1000.0 / FADE_MS)
        if self.closing is None:
            return appearing
        leaving = 1.0 - (time.monotonic() - self.closing) * 1000.0 / FADE_MS
        return max(0.0, min(appearing, leaving))

    def expired(self):
        if self.closing is not None:
            return (time.monotonic() - self.closing) * 1000.0 > FADE_MS
        return self.seconds is not None and self.age() > self.seconds

    def close(self):
        if self.closing is None:
            self.closing = time.monotonic()


class Bubbles(QWidget):
    """The stack beside the character. Newest at the bottom, nearest to it."""

    emptied = pyqtSignal()

    def __init__(self, width=BUBBLE_WIDTH, parent=None):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowDoesNotAcceptFocus
            | Qt.WindowType.X11BypassWindowManagerHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        # Nothing here is meant to be clicked, and a wide invisible window that
        # ate clicks would be the worst thing on the screen.
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        self._width = width
        self._said = []
        self._on_right = True
        self._font = QFont()
        self._font.setPointSizeF(9.5)
        self._small = QFont()
        self._small.setPointSizeF(8.5)
        self.resize(width, 10)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._sweep)

    # ---- saying things ----------------------------------------------------

    def say(self, text, kind="heard", seconds=None, floor=3.0, ceiling=30.0):
        """Add a bubble. `seconds=None` works the length out from the text."""
        text = (text or "").strip()
        if not text:
            return
        if seconds is None:
            seconds = bubble_seconds(text, floor, ceiling)
        self._said.append(_Said(text, kind, seconds))
        self._trim()
        self._relayout()

    def live(self, text):
        """Update the bubble that is still being spoken, or start one.

        It has no lifetime of its own: it stands until the recording ends and
        the finished sentence replaces it.
        """
        text = (text or "").strip()
        if not text:
            return
        for said in reversed(self._said):
            if said.kind == "live" and said.closing is None:
                said.text = text
                self._relayout()
                return
        self._said.append(_Said(text, "live", None))
        self._trim()
        self._relayout()

    def last_stage(self):
        """The most recent progress line still on the screen, or ""."""
        for said in reversed(self._said):
            if said.kind == "stage" and said.closing is None:
                return said.text
        return ""

    def drop_live(self):
        for said in self._said:
            if said.kind == "live":
                said.close()
        self._relayout()

    def clear(self):
        for said in self._said:
            said.close()
        self._relayout()

    def _trim(self, keep=5):
        alive = [s for s in self._said if s.closing is None]
        for said in alive[:-keep]:
            said.close()

    # ---- geometry ---------------------------------------------------------

    def set_side(self, on_right):
        """Which way the tail points: at the character, wherever it is."""
        self._on_right = on_right
        self.update()

    def _body_rect(self, top, height):
        """Where the rounded box goes, leaving the tail its strip."""
        width = self._width - BUBBLE_TAIL - 2
        left = 1 if self._on_right else 1 + BUBBLE_TAIL
        return QRectF(left, top, width, height)

    def _text_rect(self, said):
        metrics = QFontMetrics(self._small if said.kind == "stage" else self._font)
        inner = self._width - BUBBLE_TAIL - 2 - 2 * BUBBLE_PADDING
        return metrics.boundingRect(
            QRect(0, 0, inner, 10000),
            int(Qt.TextFlag.TextWordWrap) | int(Qt.AlignmentFlag.AlignLeft),
            said.text)

    def _relayout(self):
        total = 0
        for said in self._said:
            said.height = self._text_rect(said).height() + 2 * BUBBLE_PADDING
            total += said.height + BUBBLE_GAP
        height = max(1, total)
        if height != self.height():
            self.resize(self._width, height)
        if self._said and not self._timer.isActive():
            self._timer.start(33)
        self.update()

    def _sweep(self):
        gone = [s for s in self._said if s.expired()]
        if gone:
            self._said = [s for s in self._said if not s.expired()]
            self._relayout()
            if not self._said:
                self._timer.stop()
                self.emptied.emit()
                return
        self.update()

    @property
    def busy(self):
        return bool(self._said)

    # ---- drawing ----------------------------------------------------------

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        y = self.height()
        for said in reversed(self._said):
            y -= said.height + BUBBLE_GAP
            self._paint_bubble(painter, said, y)
        painter.end()

    def _paint_bubble(self, painter, said, top):
        alpha = said.alpha()
        if alpha <= 0.01:
            return
        background, border, ink = BUBBLE_STYLE.get(said.kind, BUBBLE_STYLE["heard"])
        box = self._body_rect(top, said.height)

        path = QPainterPath()
        path.addRoundedRect(box, BUBBLE_RADIUS, BUBBLE_RADIUS)
        # The tail is a small triangle rather than a curve: at this size a
        # curved one reads as a smudge.
        tail = QPainterPath()
        point_y = min(box.bottom() - BUBBLE_RADIUS, box.top() + said.height * 0.62)
        if self._on_right:
            tail.moveTo(box.right() - 2, point_y - 7)
            tail.lineTo(box.right() + BUBBLE_TAIL - 1, point_y)
            tail.lineTo(box.right() - 2, point_y + 7)
        else:
            tail.moveTo(box.left() + 2, point_y - 7)
            tail.lineTo(box.left() - BUBBLE_TAIL + 1, point_y)
            tail.lineTo(box.left() + 2, point_y + 7)
        tail.closeSubpath()
        path = path.united(tail)

        fill = QColor(background[:7])
        fill.setAlpha(int(int(background[7:], 16) * alpha))
        edge = QColor(border)
        edge.setAlpha(int(150 * alpha))
        painter.setBrush(QBrush(fill))
        painter.setPen(QPen(edge, 1.2))
        painter.drawPath(path)

        colour = QColor(ink)
        colour.setAlpha(int(255 * alpha))
        painter.setPen(colour)
        painter.setFont(self._small if said.kind == "stage" else self._font)
        painter.drawText(
            QRectF(box.left() + BUBBLE_PADDING, box.top() + BUBBLE_PADDING,
                   box.width() - 2 * BUBBLE_PADDING, said.height - 2 * BUBBLE_PADDING),
            int(Qt.TextFlag.TextWordWrap) | int(Qt.AlignmentFlag.AlignLeft),
            said.text)


# --- the three of them together -------------------------------------------

MARGIN = 18          # from the edge of the screen
BUBBLE_MARGIN = 12   # between the bubbles and the control


class Companion(QObject):
    """The control, what it says, and the history behind it — as one thing.

    The bubbles and the panel are two views of the same events and they are
    kept that way on purpose. The bubbles are the glance: what is happening,
    right now, in the corner of your eye, gone in a few seconds. The panel is
    the read: all of it, in full, whenever you want it. Trying to make one of
    them do both jobs is how the band across the middle of the screen came
    about, and it did neither well.
    """

    asked = pyqtSignal(str)        # a lobe that starts a job: WRITE or ASK
    moved = pyqtSignal(int, int)

    def __init__(self, conf=None, store=None, parent=None):
        super().__init__(parent)
        self.pill = Pill()
        self.bubbles = Bubbles()
        self.store = store
        self.panel = None
        self.pill.pressed.connect(self._pressed)
        self.pill.moved.connect(self._remember)
        self._floor = 3.0
        self._ceiling = 30.0
        self._on_right = True
        self._offset = None
        self._visible = False
        self._settle = QTimer(self)
        self._settle.setSingleShot(True)
        self._settle.timeout.connect(self._rest)
        if conf is not None:
            self.apply(conf)

    # ---- settings --------------------------------------------------------

    def apply(self, conf):
        self._floor = float(conf["companion_bubble_min"])
        self._ceiling = max(self._floor, float(conf["companion_bubble_max"]))
        self._on_right = conf["companion_side"] != "left"
        self._offset = conf["companion_offset"] or None
        self.pill.set_lobe(int(conf["companion_size"]) // 2)
        self.bubbles.set_side(self._on_right)
        self.place()

    def set_visible(self, visible):
        self._visible = visible
        if visible:
            self.pill.show()
            self.place()
        else:
            self.pill.hide()
            self.bubbles.hide()
            self.bubbles.clear()
            self.close_history()

    @property
    def visible(self):
        return self._visible

    # ---- where it sits ---------------------------------------------------

    def place(self):
        screen = QApplication.primaryScreen()
        if screen is None:
            return
        area = screen.availableGeometry()
        width, height = self.pill.width(), self.pill.height()
        x = (area.right() - width - MARGIN + 1) if self._on_right else (area.left() + MARGIN)
        y = (area.center().y() - height // 2 if self._offset is None
             else clamp(int(self._offset), area.top(), area.bottom() - height + 1))
        self.pill.move(int(x), int(y))
        self._place_bubbles()

    def _place_bubbles(self):
        screen = QApplication.primaryScreen()
        if screen is None:
            return
        area = screen.availableGeometry()
        pill = self.pill.geometry()
        width = self.bubbles.width()
        x = (pill.left() - width - BUBBLE_MARGIN if self._on_right
             else pill.right() + BUBBLE_MARGIN)
        bottom = pill.center().y() + self.bubbles.height() // 2
        bottom = clamp(bottom, area.top() + self.bubbles.height(), area.bottom())
        self.bubbles.move(int(clamp(x, area.left(), area.right() - width)),
                          int(bottom - self.bubbles.height()))

    def _remember(self, x, y):
        self._offset = y
        self.moved.emit(x, y)
        self._place_bubbles()
        if self.panel is not None and self.panel.isVisible():
            self.panel.place_beside(self.pill.geometry(), self._on_right)

    # ---- the history -----------------------------------------------------

    def _pressed(self, lobe):
        """A lobe was pressed. The third one is ours; the other two are not."""
        if lobe == HISTORY:
            self.toggle_history()
            return
        self.asked.emit(lobe)

    def toggle_history(self):
        if self.panel is not None and self.panel.isVisible():
            self.close_history()
        else:
            self.open_history()

    def open_history(self):
        if self.store is None:
            return None
        if self.panel is None:
            import chat                      # only when it is first wanted
            self.panel = chat.Panel(self.store)
            self.panel.closed.connect(self._history_closed)
        self.panel.refresh()
        self.panel.place_beside(self.pill.geometry(), self._on_right)
        self.panel.show()
        self.panel.raise_()
        self.panel.activateWindow()
        self.pill.hold(HISTORY)
        return self.panel

    def close_history(self):
        if self.panel is not None:
            self.panel.hide()
        self.pill.hold(None)

    def _history_closed(self):
        self.pill.hold(None)

    @property
    def history_open(self):
        return self.panel is not None and self.panel.isVisible()

    # ---- the interface the application drives ----------------------------

    def show_recording(self, asking=False):
        self._wake()
        self.pill.set_state(LISTENING, ASK if asking else WRITE)

    def show_meeting(self):
        self._wake()
        self.pill.set_state(LISTENING, ASK)

    def show_busy(self, message):
        self._wake()
        self.pill.set_state(THINKING)
        self.stage_note(message)

    def show_done(self, message="", msec=None):
        self._wake()
        self.pill.set_state(ANSWER)
        if message:
            self.say(message, "agent", None if msec is None else msec / 1000.0)
        self._calm_later()

    def show_warning(self, message, msec=None):
        self._wake()
        self.pill.set_state(WARNING)
        self.say(message, "warn", None if msec is None else msec / 1000.0)
        self._calm_later()

    def show_error(self, message, msec=None):
        self._wake()
        self.pill.set_state(ERROR)
        self.say(message, "error", None if msec is None else msec / 1000.0)
        self._calm_later()

    def push_level(self, level):
        self.pill.push_level(level)

    def push_levels(self, mine, theirs):
        self.pill.push_level(max(mine, theirs))

    def set_seconds(self, _seconds):
        """The corner indicator counts; the control does not need to."""

    def dismiss(self):
        self.bubbles.drop_live()
        self._calm_later(0)

    # ---- what it says ----------------------------------------------------

    def stage_note(self, message):
        """A line about what is going on, in the quiet style."""
        if message and message != self.bubbles.last_stage():
            self._wake()
            self.say(message, "stage", 6.0)

    def live(self, text):
        """The sentence as it is still being spoken."""
        if not self._visible:
            return
        self._wake()
        self.bubbles.live(text)
        self._place_bubbles()

    def heard(self, text):
        """The finished sentence, which replaces whatever was live."""
        if not self._visible:
            return
        self._wake()
        self.bubbles.drop_live()
        self.say(text, "heard")

    def say(self, text, kind="heard", seconds=None):
        if not (text or "").strip() or not self._visible:
            return
        self._wake()
        self.bubbles.say(text, kind, seconds, self._floor, self._ceiling)
        self._place_bubbles()

    # ---- the quiet in between --------------------------------------------

    def _wake(self):
        if not self._visible:
            return
        if not self.pill.isVisible():
            self.pill.show()
            self.place()
        if not self.bubbles.isVisible():
            self.bubbles.show()
        self._place_bubbles()

    def _calm_later(self, msec=2600):
        self._settle.start(msec)

    def _rest(self):
        self.pill.set_state(IDLE)
        # Going idle clears `active`, but not a lobe held open by its window.
        if self.history_open:
            self.pill.hold(HISTORY)


# Kept so the older name still resolves for anything that reaches for it.
Orb = Pill
