"""The tray icon, looked up where there is a theme and drawn where there is not.

Linux ships an icon theme, and the three names Dikte asks for — a microphone, a
record dot, a refresh arrow — are in every one of them, in the colours the rest
of the desktop uses.

Windows ships no theme. Qt does answer for these names there, out of a small set
it carries itself, but it answers with white line drawings meant for a menu:
side by side in a tray they are three similar glyphs, and on a light taskbar
they are three invisible ones. So on Windows the same three are drawn here
instead, in colour — which is also what makes the state readable at tray size,
where a shape is four pixels of detail and a colour is the whole icon.
"""

import plat

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap

SIZE = 64

IDLE = QColor("#4C8DF6")      # a microphone, waiting
BUSY = QColor("#E8A33D")      # working on it
RECORD = QColor("#E2453B")    # recording


def tray_icon(name):
    """The themed icon by name, or a drawn stand-in where the theme is no use."""
    if not plat.WINDOWS:
        icon = QIcon.fromTheme(name)
        if not icon.isNull():
            return icon
    drawn = {
        "media-record": _record,
        "view-refresh": _busy,
    }.get(name, _microphone)
    return QIcon(drawn())


def app_icon():
    """What the settings window and the taskbar show."""
    return tray_icon("audio-input-microphone")


def _canvas():
    pixmap = QPixmap(SIZE, SIZE)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    return pixmap, painter


def _microphone():
    pixmap, painter = _canvas()
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(IDLE)
    # The capsule, and the stand under it: a neck and a foot.
    painter.drawRoundedRect(QRectF(23, 8, 18, 30), 9, 9)
    painter.drawRect(QRectF(30, 46, 4, 10))
    painter.drawRoundedRect(QRectF(21, 54, 22, 4), 2, 2)
    # The cradle the capsule sits in, drawn as the lower half of a ring.
    pen = QPen(IDLE, 4.5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawArc(QRectF(16, 20, 32, 30), 180 * 16, 180 * 16)
    painter.end()
    return pixmap


def _record():
    pixmap, painter = _canvas()
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(RECORD)
    painter.drawEllipse(QPointF(32, 32), 21, 21)
    painter.end()
    return pixmap


def _busy():
    pixmap, painter = _canvas()
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.setPen(QPen(BUSY, 8, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
    # Three quarters of a ring: the gap is what makes it read as turning
    # rather than as a full stop.
    painter.drawArc(QRectF(11, 11, 42, 42), 90 * 16, -270 * 16)
    painter.end()
    return pixmap
