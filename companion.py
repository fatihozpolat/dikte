"""The character at the edge of the screen, and the bubbles it speaks in.

Dikte's corner indicator appears for the length of a dictation and goes away
again. This is the opposite: something that stays, so there is a place on the
screen that is the assistant, whether or not it is doing anything. It is a
sphere because a sphere has no front and no orientation to get wrong, and
because the whole of it can carry state — its colour, its size, what moves
inside it — where an icon could only change shape.

Nothing is loaded from disk. The sphere is drawn: a glow, a body lit from the
upper left, three soft blobs drifting inside it at different speeds, a specular
highlight, and rings that only come out while it is thinking. Drawing it rather
than shipping an image is what makes it sharp at any size and any scaling, and
what keeps a picture of unclear provenance out of a GPL project.

The bubbles are a second window, to the left of the sphere and transparent to
the mouse, so the text can be as wide as it needs to be without the character
becoming a thing that swallows clicks.
"""

import math
import time

from PyQt6.QtCore import QObject, QPoint, QPointF, QRect, QRectF, QTimer, Qt, pyqtSignal
from PyQt6.QtGui import (QBrush, QColor, QFont, QFontMetrics, QPainter, QPainterPath,
                         QPen, QRadialGradient)
from PyQt6.QtWidgets import QApplication, QWidget

# --- states ---------------------------------------------------------------

IDLE = "idle"
LISTENING = "listening"
THINKING = "thinking"
ANSWER = "answer"
SPEAKING = "speaking"
WARNING = "warning"
ERROR = "error"

# (highlight, body, depth, accent) — the accent is what drifts inside.
PALETTE = {
    IDLE:      ("#8FB4FF", "#3F5FD9", "#131C4A", "#7B6BFF"),
    LISTENING: ("#8CEEFF", "#1FA8E0", "#06364F", "#4BE3C0"),
    THINKING:  ("#FFDF9E", "#E8A33D", "#4A2D08", "#FF8A5C"),
    ANSWER:    ("#A6F3D2", "#2FC08A", "#08402F", "#6FE0FF"),
    # Talking, rather than having finished: the same family as an answer,
    # turned toward the light, so the two read as one thing in two moments.
    SPEAKING:  ("#CFFBE8", "#37D69C", "#0A4A38", "#8FE9FF"),
    WARNING:   ("#FFD79E", "#E8903D", "#4A2A08", "#FF7A5C"),
    ERROR:     ("#FFB0AA", "#E2453B", "#4A100D", "#FF7BA8"),
}

# How fast the inside turns over, per state. Thinking is the busy one; idle
# barely moves, which is the point of idle.
CHURN = {IDLE: 0.35, LISTENING: 1.5, THINKING: 2.2,
         ANSWER: 0.9, SPEAKING: 2.0, WARNING: 0.9, ERROR: 0.9}

# Repaint interval. A character that sits on the screen all day should not spend
# the day repainting, so it slows right down when there is nothing happening.
BUSY_MS = 33
CALM_MS = 100


def bubble_seconds(text, floor=3.0, ceiling=30.0):
    """How long a bubble stays up, from how much there is to read.

    Roughly eleven characters a second, which is a comfortable reading pace with
    a moment at each end to find the text and to finish it. The floor is there
    because a two-word answer still has to be seen, and the ceiling because a
    long one should not own the corner of the screen for the rest of the day.
    """
    seconds = 1.5 + len(str(text)) / 11.0
    return max(floor, min(ceiling, seconds))


def _colour(name, alpha=255):
    colour = QColor(name)
    colour.setAlpha(alpha)
    return colour


# --- the sphere -----------------------------------------------------------

class Orb(QWidget):
    """The character itself: one window, the size of the sphere and its glow."""

    clicked = pyqtSignal()
    moved = pyqtSignal(int, int)

    def __init__(self, size=128, parent=None):
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
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        self.state = IDLE
        self._phase = 0.0
        self._level = 0.0          # smoothed microphone level
        self._ripples = []         # (born, strength)
        self._press = None         # where a drag started
        self._dragged = False
        self.resize(size, size)

        self._anim = QTimer(self)
        self._anim.timeout.connect(self._tick)
        self._anim.start(CALM_MS)

    # ---- state ----------------------------------------------------------

    def set_state(self, state):
        if state == self.state:
            return
        self.state = state
        if state != LISTENING:
            self._level = 0.0
            self._ripples.clear()
        self._anim.setInterval(
            BUSY_MS if state in (LISTENING, THINKING, SPEAKING) else CALM_MS)
        self.update()

    def push_level(self, level):
        """A microphone reading, 0..1. The sphere breathes on it."""
        level = max(0.0, min(1.0, float(level)))
        # Rises with the voice and falls slowly after it, so the sphere follows
        # speech rather than flickering on every syllable.
        self._level = max(level, self._level * 0.82)
        if level > 0.28 and len(self._ripples) < 4:
            last = self._ripples[-1][0] if self._ripples else 0.0
            if time.monotonic() - last > 0.28:
                self._ripples.append((time.monotonic(), level))

    def _tick(self):
        self._phase += self._anim.interval() / 1000.0
        now = time.monotonic()
        self._ripples = [r for r in self._ripples if now - r[0] < 1.4]
        self.update()

    # ---- moving it about --------------------------------------------------

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._press = event.globalPosition().toPoint() - self.pos()
            self._dragged = False

    def mouseMoveEvent(self, event):
        if self._press is None:
            return
        target = event.globalPosition().toPoint() - self._press
        if not self._dragged:
            moved = (target - self.pos()).manhattanLength()
            if moved < 6:      # a click with an unsteady hand is still a click
                return
            self._dragged = True
        self.move(target)

    def mouseReleaseEvent(self, event):
        if self._press is None:
            return
        self._press = None
        if self._dragged:
            self.moved.emit(self.x(), self.y())
        else:
            self.clicked.emit()

    # ---- drawing ----------------------------------------------------------

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        self._paint(painter, self.width())
        painter.end()

    def _paint(self, painter, size):
        highlight, body, depth, accent = PALETTE.get(self.state, PALETTE[IDLE])
        centre = QPointF(size / 2.0, size / 2.0)
        radius = size * 0.33 * self._swell()

        self._paint_ripples(painter, centre, radius, highlight)
        self._paint_glow(painter, centre, size, body, highlight)
        self._paint_body(painter, centre, radius, highlight, body, depth)
        self._paint_inside(painter, centre, radius, highlight, accent)
        self._paint_sheen(painter, centre, radius)
        if self.state in (THINKING, SPEAKING):
            self._paint_rings(painter, centre, radius, highlight)

    def _swell(self):
        """How big the sphere is right now, as a multiple of its resting size."""
        breath = 1.0 + 0.035 * math.sin(self._phase * 0.9)
        if self.state == LISTENING:
            return breath + 0.16 * self._level
        if self.state == THINKING:
            return breath + 0.02 * math.sin(self._phase * 4.0)
        if self.state == SPEAKING:
            # A steadier pulse than listening, because it is following its
            # own cadence rather than somebody else's voice.
            return breath + 0.055 * abs(math.sin(self._phase * 5.5))
        return breath

    def _paint_ripples(self, painter, centre, radius, highlight):
        now = time.monotonic()
        painter.setBrush(Qt.BrushStyle.NoBrush)
        for born, strength in self._ripples:
            age = (now - born) / 1.4
            if not 0.0 <= age < 1.0:
                continue
            spread = radius * (1.0 + age * 0.45)
            alpha = int(190 * strength * (1.0 - age) ** 1.4)
            painter.setPen(QPen(_colour(highlight, alpha), 2.6 * (1.0 - age * 0.6)))
            painter.drawEllipse(centre, spread, spread)

    def _paint_glow(self, painter, centre, size, body, highlight):
        glow = QRadialGradient(centre, size * 0.5)
        strength = 0.55 + 0.45 * self._level if self.state == LISTENING else 0.55
        glow.setColorAt(0.00, _colour(highlight, int(60 * strength)))
        glow.setColorAt(0.55, _colour(body, int(85 * strength)))
        glow.setColorAt(0.78, _colour(body, int(30 * strength)))
        glow.setColorAt(1.00, _colour(body, 0))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(glow))
        painter.drawEllipse(centre, size * 0.5, size * 0.5)

    def _paint_body(self, painter, centre, radius, highlight, body, depth):
        # Lit from the upper left, so the sphere reads as a sphere and not as a
        # disc: the gradient's focus is off centre, not its middle.
        gradient = QRadialGradient(
            QPointF(centre.x() - radius * 0.30, centre.y() - radius * 0.36),
            radius * 1.75)
        gradient.setColorAt(0.00, _colour(highlight, 255))
        gradient.setColorAt(0.34, _colour(body, 255))
        gradient.setColorAt(0.72, _colour(depth, 255))
        gradient.setColorAt(1.00, _colour(depth, 255))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(gradient))
        painter.drawEllipse(centre, radius, radius)

    def _paint_inside(self, painter, centre, radius, highlight, accent):
        """Three soft lights drifting inside the sphere at different speeds.

        Added rather than painted over one another, which is what turns two
        colours into the third one where they overlap and gives the inside its
        depth instead of a flat wash.
        """
        clip = QPainterPath()
        clip.addEllipse(centre, radius, radius)
        painter.save()
        painter.setClipPath(clip)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)
        painter.setPen(Qt.PenStyle.NoPen)

        churn = CHURN.get(self.state, 0.5)
        # Reach beyond 1.0 so a light can pass behind the rim and come back,
        # which is what stops the three of them from looking like a fixed
        # pattern going round.
        blobs = ((accent, 0.62, 0.62, 0.0, 0.78), (highlight, 0.41, 0.74, 2.3, 0.62),
                 (accent, 0.83, 0.50, 4.1, 0.55))
        for colour, speed, reach, offset, span in blobs:
            angle = self._phase * churn * speed + offset
            position = QPointF(
                centre.x() + math.cos(angle) * radius * reach,
                centre.y() + math.sin(angle * 0.77 + offset) * radius * reach * 0.8)
            blob = QRadialGradient(position, radius * span)
            blob.setColorAt(0.0, _colour(colour, 190))
            blob.setColorAt(0.45, _colour(colour, 72))
            blob.setColorAt(1.0, _colour(colour, 0))
            painter.setBrush(QBrush(blob))
            painter.drawEllipse(position, radius * span, radius * span)
        painter.restore()

    def _paint_sheen(self, painter, centre, radius):
        """The wet highlight near the top, and the rim light opposite it."""
        spot = QPointF(centre.x() - radius * 0.34, centre.y() - radius * 0.42)
        sheen = QRadialGradient(spot, radius * 0.52)
        sheen.setColorAt(0.0, QColor(255, 255, 255, 165))
        sheen.setColorAt(0.6, QColor(255, 255, 255, 30))
        sheen.setColorAt(1.0, QColor(255, 255, 255, 0))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(sheen))
        painter.drawEllipse(spot, radius * 0.52, radius * 0.52)

        rim = QPainterPath()
        rim.addEllipse(centre, radius, radius)
        painter.save()
        painter.setClipPath(rim)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor(255, 255, 255, 46), max(1.0, radius * 0.07)))
        painter.drawEllipse(centre, radius * 0.97, radius * 0.97)
        painter.restore()

    def _paint_rings(self, painter, centre, radius, highlight):
        """Two rings at different speeds: the sign that work is going on.

        Each is a faint full circle with a bright stretch running round it. The
        circle is what makes the bright part read as travelling rather than as a
        scratch on the screen, which is all a lone arc looks like at this size.
        """
        painter.setBrush(Qt.BrushStyle.NoBrush)
        for index, (reach, speed, span, width) in enumerate(
                ((1.19, 150.0, 105, 2.6), (1.38, -92.0, 65, 1.8))):
            box = QRectF(centre.x() - radius * reach, centre.y() - radius * reach,
                         radius * reach * 2, radius * reach * 2)
            painter.setPen(QPen(_colour(highlight, 46), width * 0.7))
            painter.drawEllipse(box)
            start = int((self._phase * speed + index * 140) % 360)
            painter.setPen(QPen(_colour(highlight, 225 - index * 55), width,
                                Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            painter.drawArc(box, start * 16, span * 16)


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


# --- the two of them together ---------------------------------------------

MARGIN = 18          # from the edge of the screen
BUBBLE_MARGIN = 12   # between the bubbles and the sphere


class Companion(QObject):
    """The character and its bubbles, placed and driven as one thing.

    It answers to the same calls the corner indicator does — show_recording,
    show_busy, show_done and the rest — so the application can hand progress to
    either of them without knowing which it is talking to.
    """

    clicked = pyqtSignal()
    moved = pyqtSignal(int, int)

    def __init__(self, conf=None, parent=None):
        super().__init__(parent)
        self.orb = Orb()
        self.bubbles = Bubbles()
        self.orb.moved.connect(self._remember)
        self.orb.clicked.connect(self.clicked)
        self._floor = 3.0
        self._ceiling = 30.0
        self._on_right = True
        self._offset = None       # remembered y, or None for the middle
        self._settle = QTimer(self)
        self._settle.setSingleShot(True)
        self._settle.timeout.connect(self._rest)
        self._visible = False
        if conf is not None:
            self.apply(conf)

    # ---- settings ---------------------------------------------------------

    def apply(self, conf):
        size = int(conf["companion_size"])
        self._floor = float(conf["companion_bubble_min"])
        self._ceiling = max(self._floor, float(conf["companion_bubble_max"]))
        self._on_right = conf["companion_side"] != "left"
        self._offset = conf["companion_offset"] or None
        if self.orb.width() != size:
            self.orb.resize(size, size)
        self.bubbles.set_side(self._on_right)
        self.place()

    def set_visible(self, visible):
        self._visible = visible
        if visible:
            self.orb.show()
            self.place()
        else:
            self.orb.hide()
            self.bubbles.hide()
            self.bubbles.clear()

    @property
    def visible(self):
        return self._visible

    # ---- where it sits ----------------------------------------------------

    def place(self):
        """Put the sphere against its edge, and the bubbles beside it."""
        screen = QApplication.primaryScreen()
        if screen is None:
            return
        area = screen.availableGeometry()
        size = self.orb.width()
        x = (area.right() - size - MARGIN + 1) if self._on_right else (area.left() + MARGIN)
        if self._offset is None:
            y = area.center().y() - size // 2
        else:
            y = clamp(int(self._offset), area.top(), area.bottom() - size + 1)
        self.orb.move(int(x), int(y))
        self._place_bubbles()

    def _place_bubbles(self):
        area = QApplication.primaryScreen().availableGeometry()
        orb = self.orb.geometry()
        width = self.bubbles.width()
        if self._on_right:
            x = orb.left() - width - BUBBLE_MARGIN
        else:
            x = orb.right() + BUBBLE_MARGIN
        # A stack taller than the room above the sphere grows downwards instead
        # of off the top of the screen.
        bottom = orb.center().y() + self.bubbles.height() // 2
        bottom = clamp(bottom, area.top() + self.bubbles.height(), area.bottom())
        self.bubbles.move(int(clamp(x, area.left(), area.right() - width)),
                          int(bottom - self.bubbles.height()))

    def _remember(self, _x, y):
        self._offset = y
        self.moved.emit(_x, y)
        self._place_bubbles()

    # ---- the indicator interface -----------------------------------------

    def show_recording(self, asking=False):
        self._wake()
        self.orb.set_state(LISTENING)

    def show_meeting(self):
        self._wake()
        self.orb.set_state(LISTENING)

    def show_busy(self, message):
        self._wake()
        self.orb.set_state(THINKING)
        self.stage(message)

    def show_done(self, message="", msec=None):
        self._wake()
        self.orb.set_state(ANSWER)
        if message:
            self.say(message, "agent", None if msec is None else msec / 1000.0)
        self._calm_later()

    def show_warning(self, message, msec=None):
        self._wake()
        self.orb.set_state(WARNING)
        self.say(message, "warn", None if msec is None else msec / 1000.0)
        self._calm_later()

    def show_error(self, message, msec=None):
        self._wake()
        self.orb.set_state(ERROR)
        self.say(message, "error", None if msec is None else msec / 1000.0)
        self._calm_later()

    def show_speaking(self):
        """It is saying the answer out loud rather than only showing it."""
        self._wake()
        self.orb.set_state(SPEAKING)

    def push_level(self, level):
        self.orb.push_level(level)

    def push_levels(self, mine, theirs):
        self.orb.push_level(max(mine, theirs))

    def set_seconds(self, _seconds):
        """The corner indicator counts; the character does not need to."""

    def dismiss(self):
        self.bubbles.drop_live()
        self._calm_later(0)

    # ---- what it says -----------------------------------------------------

    def stage(self, message):
        """A line about what is going on, in the quiet style.

        The same line twice running is dropped: the application announces a
        stage and the pipeline announces the same one a moment later, and two
        identical bubbles read as something having gone round twice.
        """
        if message and message != self.bubbles.last_stage():
            self._wake()
            self.say(message, "stage", 6.0)

    def live(self, text):
        """The sentence as it is still being spoken."""
        self._wake()
        self.bubbles.live(text)
        self._place_bubbles()

    def heard(self, text):
        """The finished sentence, which replaces whatever was live."""
        self._wake()
        self.bubbles.drop_live()
        self.say(text, "heard")

    def say(self, text, kind="heard", seconds=None):
        if not (text or "").strip():
            return
        self._wake()
        self.bubbles.say(text, kind, seconds, self._floor, self._ceiling)
        self._place_bubbles()

    # ---- the quiet in between ---------------------------------------------

    def _wake(self):
        if not self._visible:
            return
        if not self.orb.isVisible():
            self.orb.show()
            self.place()
        if not self.bubbles.isVisible():
            self.bubbles.show()
        self._place_bubbles()

    def _calm_later(self, msec=2600):
        """Back to idle once the outcome has been seen."""
        self._settle.start(msec)

    def _rest(self):
        self.orb.set_state(IDLE)


def clamp(value, low, high):
    return max(low, min(high, value))
