"""The control you press, and the band that shows what it heard.

Two pieces, and the split between them is the point.

The control is a capsule with two lobes, parked on the edge of the screen. The
left one writes: what you say is tidied and put where the cursor is. The right
one asks: what you say goes to the agent and the answer comes back spoken. They
are two buttons rather than one button with a mode, because a mode is a thing
you have to remember and a thing you can be wrong about — and being wrong here
means a note pasted into a chat window, or a question typed into a document.
Two lobes cost a few pixels and remove the question.

The band is what it heard, across the middle of the screen where you are already
looking. Behind the words a green ribbon moves with your voice, which is the
only part of this that has to be seen out of the corner of an eye: it says the
microphone is live and how loud you are, and it says it without being read. The
words are in front of it and the ribbon is dim, because the other way round —
text over a moving waveform — is a waveform with unreadable text on it.

Nothing is loaded from disk. Both are drawn, which keeps them sharp at any
scaling and keeps a picture of unclear provenance out of a GPL project.
"""

import math
import time

from PyQt6.QtCore import (QObject, QPointF, QRect, QRectF, QTimer, Qt,
                          pyqtSignal)
from PyQt6.QtGui import (QBrush, QColor, QFont, QFontMetrics, QLinearGradient,
                         QPainter, QPainterPath, QPen, QPolygonF, QRadialGradient)
from PyQt6.QtWidgets import QApplication, QWidget

# --- the two things it can be asked to do ---------------------------------

WRITE = "write"
ASK = "ask"

# --- what it is doing -----------------------------------------------------

IDLE = "idle"
LISTENING = "listening"
THINKING = "thinking"
ANSWER = "answer"
SPEAKING = "speaking"
WARNING = "warning"
ERROR = "error"

# (bright, body, deep) per lobe. Writing is the cool one and asking the warm
# one, so which half is lit is legible at the edge of vision and not only up
# close.
LOBE = {
    WRITE: ("#8CD8FF", "#2E86C8", "#0B2C45"),
    ASK: ("#C7B4FF", "#7A5AF0", "#211447"),
}

# The ribbon. Green because it is the one part that is only ever glanced at, and
# green reads as "running" without having to be thought about.
WAVE_BRIGHT = "#6BF2AE"

STATE_TINT = {
    THINKING: "#E8A33D",
    ANSWER: "#2FC08A",
    SPEAKING: "#37D69C",
    WARNING: "#E8903D",
    ERROR: "#E2453B",
}

BUSY_MS = 33
CALM_MS = 120

# How many readings the ribbon remembers. About three seconds of it at the rate
# the recorder reports, which is long enough to see the shape of a sentence.
WAVE_POINTS = 88


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
    """Two lobes in one capsule: write on the left, ask on the right."""

    pressed = pyqtSignal(str)      # WRITE or ASK
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
        self.active = None          # which lobe is working, if either
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
        self.resize(self._lobe * 2 + pad * 2, self._lobe + pad * 2)

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
            BUSY_MS if state in (LISTENING, THINKING, SPEAKING) else CALM_MS)
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
        if pad <= position.x() < pad + self._lobe:
            return WRITE
        if pad + self._lobe <= position.x() <= pad + self._lobe * 2:
            return ASK
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
        body = QRectF(pad, pad, self._lobe * 2, self._lobe)

        # The capsule they sit in, so the two read as one control.
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(14, 16, 22, 190))
        painter.drawRoundedRect(body, radius, radius)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor(255, 255, 255, 26), 1.2))
        painter.drawRoundedRect(body, radius, radius)

        for index, lobe in enumerate((WRITE, ASK)):
            centre = QPointF(pad + radius + index * self._lobe, pad + radius)
            self._paint_lobe(painter, lobe, centre, radius)

    def _paint_lobe(self, painter, lobe, centre, radius):
        bright, body, deep = LOBE[lobe]
        working = self.active == lobe and self.state != IDLE
        if working and self.state in STATE_TINT:
            bright = body = STATE_TINT[self.state]

        swell = 1.0
        if working and self.state == LISTENING:
            swell += 0.13 * self._level
        elif working:
            swell += 0.03 * math.sin(self._phase * 3.0)
        size = radius * 0.72 * swell

        if working:
            glow = QRadialGradient(centre, radius * 1.25)
            glow.setColorAt(0.0, _colour(bright, 90))
            glow.setColorAt(1.0, _colour(bright, 0))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(glow))
            painter.drawEllipse(centre, radius * 1.25, radius * 1.25)

        fill = QRadialGradient(
            QPointF(centre.x() - size * 0.3, centre.y() - size * 0.35), size * 1.7)
        alpha = 255 if working else (210 if self._hover == lobe else 150)
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
        """A nib for writing, a spark for asking. Drawn rather than lettered:
        a glyph at this size is a smudge, and a letter would be a language."""
        ink = QColor(255, 255, 255, 235)
        painter.setBrush(ink)
        painter.setPen(Qt.PenStyle.NoPen)
        unit = size * 0.52
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


# --- the band across the middle -------------------------------------------

class Stage(QWidget):
    """What it heard, over a ribbon that moves with your voice."""

    WIDTH_FRACTION = 0.62
    HEIGHT = 240

    def __init__(self, parent=None):
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
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        self.state = IDLE
        self.mode = WRITE
        self.text = ""
        self.note = ""
        self.levels = [0.0] * WAVE_POINTS
        self._phase = 0.0
        self._until = 0.0
        self._born = 0.0

        self._font = QFont()
        self._font.setPointSizeF(19.0)
        self._font.setWeight(QFont.Weight.DemiBold)
        self._small = QFont()
        self._small.setPointSizeF(10.0)

        self._anim = QTimer(self)
        self._anim.timeout.connect(self._tick)
        self._hide = QTimer(self)
        self._hide.setSingleShot(True)
        self._hide.timeout.connect(self.dismiss)

    # ---- what to show ----------------------------------------------------

    def begin(self, mode):
        self.mode = mode
        self.state = LISTENING
        self.text = ""
        self.note = ""
        self.levels = [0.0] * WAVE_POINTS
        self._hide.stop()
        self._appear()

    def push_level(self, level):
        self.levels = self.levels[1:] + [clamp(float(level), 0.0, 1.0)]

    def set_text(self, text):
        self.text = (text or "").strip()
        self._appear()

    def set_note(self, note):
        self.note = (note or "").strip()
        self._appear()

    def working(self, note=""):
        self.state = THINKING
        if note:
            self.note = note
        self._hide.stop()
        self._appear()

    def finish(self, state, text="", seconds=None):
        self.state = state
        if text:
            self.text = text.strip()
        self.note = ""
        self._appear()
        self._hide.start(int((seconds if seconds is not None
                              else bubble_seconds(self.text)) * 1000))

    def dismiss(self):
        self._hide.stop()
        self._anim.stop()
        self.state = IDLE
        self.hide()

    @property
    def showing(self):
        return self.isVisible() and self.state != IDLE

    # ---- where it sits ---------------------------------------------------

    def _appear(self):
        self.place()
        if not self.isVisible():
            self._born = time.monotonic()
            self.show()
            self.raise_()
        if not self._anim.isActive():
            self._anim.start(BUSY_MS)
        self.update()

    def place(self):
        screen = QApplication.primaryScreen()
        if screen is None:
            return
        area = screen.availableGeometry()
        width = int(area.width() * self.WIDTH_FRACTION)
        self.resize(width, self.HEIGHT)
        self.move(area.center().x() - width // 2,
                  area.center().y() - self.HEIGHT // 2)

    def _tick(self):
        self._phase += self._anim.interval() / 1000.0
        # The ribbon keeps moving while it thinks, slower and on its own, so a
        # long job does not look like a hang.
        if self.state != LISTENING:
            drift = 0.16 + 0.1 * math.sin(self._phase * 1.7)
            self.levels = self.levels[1:] + [max(0.0, drift)]
        self.update()

    # ---- drawing ---------------------------------------------------------

    def _panel(self):
        """The dark plate everything sits on.

        It has to have one. Without a backdrop the words are white paint on
        whatever happens to be behind them, and on a pale desktop the band was
        measured unreadable — the ribbon washes out and the text goes with it.
        A plate costs a rectangle and makes the thing legible on any wallpaper.
        """
        inset = self.width() * 0.03
        height = self.height() * 0.62
        return QRectF(inset, (self.height() - height) / 2.0,
                      self.width() - inset * 2, height)

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        alpha = clamp((time.monotonic() - self._born) * 5.0, 0.0, 1.0)
        panel = self._panel()
        radius = panel.height() * 0.22

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(12, 14, 18, int(214 * alpha)))
        painter.drawRoundedRect(panel, radius, radius)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(_colour(self._wave_colour().name(), int(70 * alpha)), 1.2))
        painter.drawRoundedRect(panel, radius, radius)

        shape = QPainterPath()
        shape.addRoundedRect(panel, radius, radius)
        painter.save()
        painter.setClipPath(shape)
        self._paint_wave(painter, alpha)
        painter.restore()
        self._paint_text(painter, alpha)
        painter.end()

    def _wave_colour(self):
        if self.state in STATE_TINT and self.state != THINKING:
            return QColor(STATE_TINT[self.state])
        return QColor(WAVE_BRIGHT)

    def _paint_wave(self, painter, alpha):
        """A ribbon mirrored about the middle, one point per reading.

        Kept behind the words and kept dim. It is there to be seen without
        being looked at — that the microphone is live, and how loud you are —
        and anything bright enough to read over is too bright to read through.
        """
        panel = self._panel()
        middle = panel.center().y()
        span = panel.height() * 0.46
        step = self.width() / float(len(self.levels) - 1)
        bright = self._wave_colour()

        upper, lower = [], []
        for index, level in enumerate(self.levels):
            x = index * step
            # A little always moving, so the ribbon is a ribbon and not a line.
            idle = 0.05 + 0.02 * math.sin(self._phase * 2.2 + index * 0.35)
            height = span * (idle + level * 0.95)
            upper.append(QPointF(x, middle - height))
            lower.append(QPointF(x, middle + height))

        shape = QPolygonF(upper + list(reversed(lower)))
        gradient = QLinearGradient(0, middle - span, 0, middle + span)
        gradient.setColorAt(0.0, _colour(bright.name(), 0))
        gradient.setColorAt(0.5, _colour(bright.name(), int(88 * alpha)))
        gradient.setColorAt(1.0, _colour(bright.name(), 0))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(gradient))
        painter.drawPolygon(shape)

        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(_colour(bright.name(), int(150 * alpha)), 1.6))
        painter.drawPolyline(QPolygonF(upper))
        painter.drawPolyline(QPolygonF(lower))

    def _paint_text(self, painter, alpha):
        if not self.text and not self.note:
            return
        panel = self._panel()
        box = QRect(int(panel.left() + panel.width() * 0.06),
                    int(panel.top()),
                    int(panel.width() * 0.88), int(panel.height() * 0.74))
        flags = (int(Qt.AlignmentFlag.AlignHCenter)
                 | int(Qt.AlignmentFlag.AlignVCenter) | int(Qt.TextFlag.TextWordWrap))

        if self.text:
            painter.setFont(self._font)
            # A dark pass under the light one: the band has no background of
            # its own, so the words have to survive whatever is behind them.
            painter.setPen(QColor(0, 0, 0, int(180 * alpha)))
            painter.drawText(box.adjusted(2, 2, 2, 2), flags, self.text)
            painter.setPen(_colour("#F2FBF6", int(255 * alpha)))
            painter.drawText(box, flags, self.text)

        if self.note:
            painter.setFont(self._small)
            strip = QRect(box.left(), int(panel.bottom() - 34), box.width(), 26)
            painter.setPen(QColor(0, 0, 0, int(150 * alpha)))
            painter.drawText(strip.adjusted(1, 1, 1, 1),
                             int(Qt.AlignmentFlag.AlignCenter), self.note)
            painter.setPen(_colour(self._wave_colour().name(), int(210 * alpha)))
            painter.drawText(strip, int(Qt.AlignmentFlag.AlignCenter), self.note)


# --- the two of them together ---------------------------------------------

MARGIN = 18


class Companion(QObject):
    """The control and the band, placed and driven as one thing."""

    asked = pyqtSignal(str)        # a lobe was pressed: WRITE or ASK
    moved = pyqtSignal(int, int)

    def __init__(self, conf=None, parent=None):
        super().__init__(parent)
        self.pill = Pill()
        self.stage = Stage()
        self.pill.pressed.connect(self.asked)
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
        self.place()

    def set_visible(self, visible):
        self._visible = visible
        if visible:
            self.pill.show()
            self.place()
        else:
            self.pill.hide()
            self.stage.dismiss()

    @property
    def visible(self):
        return self._visible

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
        self.stage.place()

    def _remember(self, x, y):
        self._offset = y
        self.moved.emit(x, y)

    # ---- the interface the application drives ----------------------------

    def show_recording(self, asking=False):
        mode = ASK if asking else WRITE
        self._wake()
        self.pill.set_state(LISTENING, mode)
        self.stage.begin(mode)

    def show_meeting(self):
        self._wake()
        self.pill.set_state(LISTENING, ASK)

    def show_busy(self, message):
        self._wake()
        self.pill.set_state(THINKING)
        self.stage.working(message)

    def show_done(self, message="", msec=None):
        self._wake()
        self.pill.set_state(ANSWER)
        seconds = None if msec is None else msec / 1000.0
        if message:
            self.stage.finish(ANSWER, message, self._span(message, seconds))
        elif self.stage.showing:
            self.stage.finish(ANSWER, "", self._span(self.stage.text, seconds))
        self._calm_later()

    def show_speaking(self):
        self._wake()
        self.pill.set_state(SPEAKING)
        self.stage.state = SPEAKING
        self.stage.update()

    def show_warning(self, message, msec=None):
        self._show_outcome(WARNING, message, msec)

    def show_error(self, message, msec=None):
        self._show_outcome(ERROR, message, msec)

    def _show_outcome(self, state, message, msec):
        self._wake()
        self.pill.set_state(state)
        seconds = None if msec is None else msec / 1000.0
        self.stage.finish(state, message, self._span(message, seconds))
        self._calm_later()

    def push_level(self, level):
        self.pill.push_level(level)
        self.stage.push_level(level)

    def push_levels(self, mine, theirs):
        self.push_level(max(mine, theirs))

    def set_seconds(self, _seconds):
        """The corner indicator counts; this does not need to."""

    def dismiss(self):
        self.stage.dismiss()
        self._calm_later(0)

    # ---- what it says ----------------------------------------------------

    def stage_note(self, message):
        if message and self._visible:
            self._wake()
            self.stage.set_note(message)

    def live(self, text):
        """The sentence as it is still being spoken."""
        if not self._visible:
            return
        self._wake()
        self.stage.set_text(text)

    def heard(self, text):
        """The finished sentence, which replaces whatever was live."""
        if not self._visible:
            return
        self._wake()
        self.stage.set_text(text)

    def say(self, text, kind="heard", seconds=None):
        if not (text or "").strip() or not self._visible:
            return
        self._wake()
        state = {"agent": ANSWER, "warn": WARNING, "error": ERROR}.get(kind, ANSWER)
        self.stage.finish(state, text, self._span(text, seconds))

    def _span(self, text, seconds=None):
        if seconds is not None:
            return seconds
        return bubble_seconds(text, self._floor, self._ceiling)

    # ---- the quiet in between --------------------------------------------

    def _wake(self):
        if not self._visible:
            return
        if not self.pill.isVisible():
            self.pill.show()
            self.place()

    def _calm_later(self, msec=2600):
        self._settle.start(msec)

    def _rest(self):
        self.pill.set_state(IDLE)


# Kept so the older name still resolves for anything that reaches for it.
Orb = Pill
