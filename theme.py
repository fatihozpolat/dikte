"""One palette, one set of shapes, one type scale — for the whole application.

Everything on the screen used to pick its own colours: the control had one dark,
the bubbles another, the settings window whatever Windows gave it. Three windows
that belong to one program looked like three programs. This module is the single
place a colour is decided, and the rest of the code asks it rather than writing a
hex value down.

The palette is a dark one built around a single accent, and it is dark on
purpose: the control and the chat panel float over whatever you are working in,
and a pale panel over a dark editor is a lamp in the corner of your eye. The
accent is the indigo the asking lobe already used; the writing lobe keeps its
blue and the agent its green, because those two say *which of the three things
is happening* and a single accent cannot.

Nothing here imports a widget, so it can be read by tests and by the drawing code
alike without dragging a window system in behind it.
"""

# --- the palette -----------------------------------------------------------

# Surfaces, darkest first. `SUNKEN` is the well a scrolling list sits in, `BASE`
# the window itself, `RAISED` a card on top of it, `HOVER` the same card under
# the pointer. Four steps is enough to build any of these panels and few enough
# that they stay distinguishable.
SUNKEN = "#0B0D12"
BASE = "#12151C"
RAISED = "#1A1E27"
HOVER = "#222733"

# The line between a surface and what is behind it. Light and very transparent,
# because a dark border on a dark panel is a smudge and a bright one is a box.
EDGE = "#FFFFFF1F"
EDGE_STRONG = "#FFFFFF33"

# Ink, brightest first.
TEXT = "#E9ECF3"
TEXT_DIM = "#A2AAB9"
TEXT_FAINT = "#6C7486"

# The one accent, and the two colours that mean *which job*.
ACCENT = "#7A5AF0"
ACCENT_BRIGHT = "#9C86FF"
ACCENT_DEEP = "#211447"
WRITE_COLOUR = "#2E86C8"
WRITE_BRIGHT = "#8CD8FF"
WRITE_DEEP = "#0B2C45"
AGENT_COLOUR = "#2FC08A"
AGENT_BRIGHT = "#6BF2AE"
AGENT_DEEP = "#0C2C22"

# What is going on. Kept apart from the accent so that "working" never reads as
# "this is the important button".
BUSY = "#E8A33D"
GOOD = "#2FC08A"
WARN = "#E8903D"
BAD = "#E2453B"

# --- shapes ----------------------------------------------------------------

# Radii. A panel, a card inside it, and a control. Three sizes, in proportion,
# so nothing looks borrowed from another program.
RADIUS_PANEL = 16
RADIUS_CARD = 12
RADIUS_CONTROL = 8

# The room a drop shadow needs around a translucent window. Reserved rather than
# guessed: a window clips its own painting, and a shadow drawn past the edge is
# simply not drawn.
SHADOW = 24

PAD = 14          # inside a panel
GAP = 10          # between two things that belong together
GAP_WIDE = 18     # between two things that do not

# --- type ------------------------------------------------------------------

# Point sizes rather than pixels, so they follow the screen's scaling. The stack
# is named rather than left to the default because the default on Windows is a
# UI font with no monospace sibling, and a code block in a proportional font is
# the fastest way to make an answer look cheap.
FONT_UI = "Segoe UI Variable Text, Segoe UI, Inter, system-ui, sans-serif"
FONT_MONO = "Cascadia Code, Consolas, JetBrains Mono, Menlo, monospace"

SIZE_TITLE = 12.0
SIZE_BODY = 10.0
SIZE_SMALL = 8.6

# --- putting one on another ------------------------------------------------


def alpha(colour, amount):
    """`colour` at `amount` (0..1) opacity, as #RRGGBBAA.

    Written out rather than done with QColor so that a stylesheet, a painter and
    a test can all be given the same string.
    """
    value = colour.lstrip("#")[:6]
    return "#%s%02X" % (value, max(0, min(255, int(round(amount * 255)))))


def rgba(colour, amount):
    """The same thing in the form a Qt stylesheet understands."""
    value = colour.lstrip("#")[:6]
    return "rgba(%d, %d, %d, %.3f)" % (
        int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16), amount)


# --- the stylesheet --------------------------------------------------------

def tick(folder):
    """Draw the checkbox tick and return its path, or "" if it cannot be.

    A Qt stylesheet can only put a picture in a checkbox from a file — there is
    no way to draw a tick in CSS and no data: URI support. Rather than ship a
    binary asset, one is drawn here and written out once. If that fails the
    stylesheet simply leaves the rule out: a filled indicator still says
    "checked", it just says it less plainly.
    """
    from PyQt6.QtCore import QPointF, Qt
    from PyQt6.QtGui import QPainter, QPen, QPixmap

    try:
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / "tick.png"
        size = 32                       # drawn large and scaled down by Qt
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(Qt.GlobalColor.white, size * 0.16,
                            Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap,
                            Qt.PenJoinStyle.RoundJoin))
        painter.drawPolyline(QPointF(size * 0.23, size * 0.52),
                             QPointF(size * 0.42, size * 0.71),
                             QPointF(size * 0.78, size * 0.29))
        painter.end()
        if not pixmap.save(str(path), "PNG"):
            return ""
        return str(path).replace("\\", "/")
    except (OSError, ValueError):
        return ""


def stylesheet(tick_path=""):
    """The look, for every widget the application shows in an ordinary window.

    One string rather than a stylesheet per window: a rule written twice is a
    rule that will disagree with itself the first time one copy is edited.
    """
    ticked = ("        image: url(%s);\n" % tick_path) if tick_path else ""
    return ("""
    * {
        font-family: %(ui)s;
        font-size: %(body).1fpt;
        color: %(text)s;
    }
    QWidget#panel, QDialog, QMainWindow {
        background: %(base)s;
    }
    QLabel { background: transparent; }
    QLabel[role="title"] {
        font-size: %(title).1fpt;
        font-weight: 600;
    }
    QLabel[role="hint"] {
        color: %(dim)s;
        font-size: %(small).1fpt;
    }
    QLabel[role="faint"] { color: %(faint)s; font-size: %(small).1fpt; }

    QGroupBox {
        background: %(raised)s;
        border: 1px solid %(edge)s;
        border-radius: %(rcard)dpx;
        margin-top: 16px;
        padding: 14px 14px 12px 14px;
        font-weight: 600;
    }
    QGroupBox::title {
        subcontrol-origin: margin;
        subcontrol-position: top left;
        left: 12px;
        padding: 0 6px;
        color: %(dim)s;
    }

    QLineEdit, QPlainTextEdit, QTextEdit, QSpinBox, QDoubleSpinBox, QComboBox {
        background: %(sunken)s;
        border: 1px solid %(edge)s;
        border-radius: %(rctl)dpx;
        padding: 6px 9px;
        selection-background-color: %(accent)s;
    }
    QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus,
    QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {
        border: 1px solid %(accent)s;
    }
    QLineEdit:disabled, QSpinBox:disabled, QComboBox:disabled,
    QPlainTextEdit:disabled { color: %(faint)s; }
    QComboBox::drop-down { border: none; width: 20px; }
    QComboBox QAbstractItemView {
        background: %(raised)s;
        border: 1px solid %(edge)s;
        selection-background-color: %(accent)s;
        outline: none;
    }

    QPushButton {
        background: %(raised)s;
        border: 1px solid %(edge)s;
        border-radius: %(rctl)dpx;
        padding: 7px 14px;
        font-weight: 500;
    }
    QPushButton:hover { background: %(hover)s; border-color: %(edgeup)s; }
    QPushButton:pressed { background: %(sunken)s; }
    QPushButton:disabled { color: %(faint)s; background: %(base)s; }
    QPushButton[role="primary"] {
        background: %(accent)s;
        border: 1px solid %(accentup)s;
        color: #FFFFFF;
    }
    QPushButton[role="primary"]:hover { background: %(accentup)s; }
    QPushButton[role="quiet"] {
        background: transparent;
        border: 1px solid transparent;
        color: %(dim)s;
    }
    QPushButton[role="quiet"]:hover { background: %(hover)s; color: %(text)s; }

    QCheckBox, QRadioButton { spacing: 8px; background: transparent; }
    QCheckBox::indicator, QRadioButton::indicator { width: 16px; height: 16px; }
    QCheckBox::indicator {
        border: 1px solid %(edgeup)s;
        border-radius: 4px;
        background: %(sunken)s;
    }
    QCheckBox::indicator:checked {
        background: %(accent)s;
        border-color: %(accent)s;
%(ticked)s    }
    QCheckBox::indicator:hover { border-color: %(accentup)s; }

    QTabWidget::pane {
        border: 1px solid %(edge)s;
        border-radius: %(rcard)dpx;
        top: -1px;
    }
    QTabBar::tab {
        background: transparent;
        color: %(dim)s;
        padding: 8px 16px;
        margin-right: 2px;
        border-top-left-radius: %(rctl)dpx;
        border-top-right-radius: %(rctl)dpx;
    }
    QTabBar::tab:selected { background: %(raised)s; color: %(text)s; }
    QTabBar::tab:hover:!selected { color: %(text)s; }

    QScrollBar:vertical {
        background: transparent; width: 10px; margin: 2px;
    }
    QScrollBar::handle:vertical {
        background: %(scroll)s; border-radius: 4px; min-height: 28px;
    }
    QScrollBar::handle:vertical:hover { background: %(scrollup)s; }
    QScrollBar::add-line, QScrollBar::sub-line { height: 0; width: 0; }
    QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }
    QScrollBar:horizontal { background: transparent; height: 10px; margin: 2px; }
    QScrollBar::handle:horizontal {
        background: %(scroll)s; border-radius: 4px; min-width: 28px;
    }

    QToolTip {
        background: %(raised)s;
        color: %(text)s;
        border: 1px solid %(edge)s;
        border-radius: 6px;
        padding: 5px 8px;
    }
    QMenu {
        background: %(raised)s;
        border: 1px solid %(edge)s;
        border-radius: %(rctl)dpx;
        padding: 5px;
    }
    QMenu::item { padding: 6px 22px 6px 12px; border-radius: 5px; }
    QMenu::item:selected { background: %(accent)s; }
    QMenu::separator { height: 1px; background: %(edge)s; margin: 5px 8px; }
    """ % {
        "ui": FONT_UI, "body": SIZE_BODY, "title": SIZE_TITLE,
        "small": SIZE_SMALL, "text": TEXT, "dim": TEXT_DIM, "faint": TEXT_FAINT,
        "base": BASE, "raised": RAISED, "hover": HOVER, "sunken": SUNKEN,
        "edge": rgba("#FFFFFF", 0.12), "edgeup": rgba("#FFFFFF", 0.2),
        "accent": ACCENT, "accentup": ACCENT_BRIGHT,
        "scroll": rgba("#FFFFFF", 0.16), "scrollup": rgba("#FFFFFF", 0.28),
        "rcard": RADIUS_CARD, "rctl": RADIUS_CONTROL, "ticked": ticked,
    })


def apply_to(app, asset_dir=None):
    """Dress the application. Safe to call more than once."""
    app.setStyleSheet(stylesheet(tick(asset_dir) if asset_dir else ""))
