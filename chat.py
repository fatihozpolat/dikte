"""The history, as a conversation you can read.

The third lobe opens this. It is a small application rather than a tooltip: it
has a background of its own, a title bar you can drag it by, a scrolling
conversation, and a way out. That matters because of what is in it — an answer
from an agent is not a line of status text. It is paragraphs, lists, sometimes a
block of code, and it is the thing you actually wanted. Showing it in a bubble
that fades after eleven seconds was the wrong shape for it.

Answers are rendered as markdown, by Qt itself. `QTextBrowser.setMarkdown` has
been in Qt since 5.14; using it means headings, lists, emphasis, links and fenced
code all come out right with nothing imported and nothing to keep up to date.
The request above each answer is left as plain text, deliberately — it is a
transcript of something somebody said out loud, and running speech through a
markdown parser turns an innocent asterisk into emphasis.

Each answer sizes itself to its content and does not scroll: one scrolling area,
the conversation, and never a little scrollbar inside a message. Working out the
height means laying the document out at the width it will have, which is why
`_fit` runs on every resize.
"""

import time

from PyQt6.QtCore import QEvent, QPoint, QSize, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import (QColor, QFont, QGuiApplication, QTextCharFormat,
                         QTextCursor, QTextFrameFormat)
from PyQt6.QtWidgets import (QApplication, QFrame, QGraphicsDropShadowEffect,
                             QHBoxLayout, QLabel, QPushButton, QScrollArea,
                             QSizePolicy, QTextBrowser, QVBoxLayout, QWidget)

import history
import paste
import theme
from i18n import t

WIDTH = 430
HEIGHT = 560
MIN_WIDTH = 340
MIN_HEIGHT = 320
WIDE_WIDTH = 720          # what the expand button grows it to
BUBBLE_MAX = 0.86         # of the panel width


def copy_out(text):
    """Put `text` on the clipboard, the way the rest of the application does.

    Through paste.py rather than Qt: it is the same clipboard the dictation
    writes to, and going round it here would mean two implementations of the
    one thing, free to behave differently on the platform that matters. Qt's is
    kept as a fallback for anywhere paste.py has no answer.
    """
    try:
        paste.copy(text)
        return True
    except (paste.PasteError, OSError):
        clipboard = QGuiApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(text)
        return False


def _elide(text, limit=140):
    text = " ".join((text or "").split())
    return text if len(text) <= limit else text[:limit - 1] + "…"


def _when(stamp):
    """A clock time, in the reader's own locale."""
    return time.strftime("%H:%M", time.localtime(stamp))


def _day(stamp):
    when = time.localtime(stamp)
    today = time.localtime()
    if when[:3] == today[:3]:
        return t("Today")
    yesterday = time.localtime(time.time() - 86400)
    if when[:3] == yesterday[:3]:
        return t("Yesterday")
    return time.strftime("%d %B %Y", when)


# --- the pieces of the conversation ---------------------------------------

class Separator(QWidget):
    """A date, with a rule either side of it."""

    def __init__(self, text, parent=None):
        super().__init__(parent)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, theme.GAP, 0, theme.GAP)
        row.setSpacing(theme.GAP)
        for _ in range(2):
            rule = QFrame()
            rule.setFrameShape(QFrame.Shape.HLine)
            rule.setFixedHeight(1)
            rule.setStyleSheet("background: %s; border: none;"
                               % theme.rgba("#FFFFFF", 0.1))
            row.addWidget(rule, 1)
        label = QLabel(text)
        label.setStyleSheet("color: %s; font-size: %.1fpt; font-weight: 600;"
                            % (theme.TEXT_FAINT, theme.SIZE_SMALL))
        row.insertWidget(1, label, 0)


class Request(QWidget):
    """What you said, against the right edge, in the accent.

    Plain text and right-aligned, the way the thing you typed is in every chat
    application anybody has used. The alignment is the whole of how you tell at
    a glance which side of the conversation a message is from.
    """

    def __init__(self, turn, parent=None):
        super().__init__(parent)
        self.turn = turn
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(theme.GAP)
        row.addStretch(1)

        column = QVBoxLayout()
        column.setSpacing(3)
        column.setContentsMargins(0, 0, 0, 0)

        self.label = QLabel(turn.question or t("(nothing was heard)"))
        self.label.setWordWrap(True)
        self.label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse)
        self.label.setStyleSheet("""
            background: %s;
            border: 1px solid %s;
            border-radius: %dpx;
            border-bottom-right-radius: 5px;
            padding: 9px 13px;
            color: #FFFFFF;
        """ % (theme.ACCENT, theme.rgba(theme.ACCENT_BRIGHT, 0.5),
               theme.RADIUS_CARD + 2))
        column.addWidget(self.label)

        stamp = QLabel(_when(turn.when))
        stamp.setAlignment(Qt.AlignmentFlag.AlignRight)
        stamp.setStyleSheet("color: %s; font-size: %.1fpt;"
                            % (theme.TEXT_FAINT, theme.SIZE_SMALL))
        column.addWidget(stamp)
        row.addLayout(column, 0)

    def set_max(self, width):
        self.label.setMaximumWidth(max(160, int(width * BUBBLE_MAX)))


class Answer(QWidget):
    """What came back, against the left edge, as markdown.

    The browser is sized to its document and never scrolls. A message with its
    own scrollbar inside a scrolling conversation is two things to scroll and no
    way to tell which one the wheel is about to move.
    """

    def __init__(self, turn, parent=None):
        super().__init__(parent)
        self.turn = turn
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(3)

        who = QHBoxLayout()
        who.setSpacing(6)
        who.setContentsMargins(2, 0, 0, 0)
        tint = theme.WRITE_BRIGHT if turn.mode == history.DICTATE else theme.AGENT_BRIGHT
        name = QLabel(t("Dictation") if turn.mode == history.DICTATE else "Zeno")
        name.setStyleSheet("color: %s; font-size: %.1fpt; font-weight: 600;"
                           % (tint, theme.SIZE_SMALL))
        who.addWidget(name)
        who.addStretch(1)
        self.copy_button = QPushButton(t("Copy"))
        self.copy_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.copy_button.setFixedHeight(20)
        self.copy_button.setStyleSheet("""
            QPushButton { background: transparent; border: none;
                          color: %s; font-size: %.1fpt; padding: 0 4px; }
            QPushButton:hover { color: %s; }
        """ % (theme.TEXT_FAINT, theme.SIZE_SMALL, theme.TEXT))
        self.copy_button.clicked.connect(self._copy)
        who.addWidget(self.copy_button)
        outer.addLayout(who)

        self.body = QTextBrowser()
        self.body.setOpenExternalLinks(True)
        self.body.setFrameShape(QFrame.Shape.NoFrame)
        self.body.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.body.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.body.setSizePolicy(QSizePolicy.Policy.Preferred,
                                QSizePolicy.Policy.Fixed)
        edge = theme.rgba(tint, 0.28)
        self.body.setStyleSheet("""
            QTextBrowser {
                background: %s;
                border: 1px solid %s;
                border-radius: %dpx;
                border-bottom-left-radius: 5px;
                padding: 9px 13px;
                color: %s;
            }
        """ % (theme.RAISED, edge, theme.RADIUS_CARD + 2, theme.TEXT))
        self.body.document().setDefaultStyleSheet(self._document_style(tint))
        outer.addWidget(self.body)

        self.stamp = QLabel(_when(turn.when))
        self.stamp.setStyleSheet("color: %s; font-size: %.1fpt; padding-left: 2px;"
                                 % (theme.TEXT_FAINT, theme.SIZE_SMALL))
        outer.addWidget(self.stamp)
        self.set_turn(turn)

    def _document_style(self, tint):
        """How markdown lands inside the bubble.

        Qt's rich text is a subset of CSS 2.1: no flexbox, no border-radius on
        an inline element, no `gap`. What it does honour is enough — a monospace
        family and a background on `pre`, margins on the block elements, and a
        colour on a link.
        """
        return """
            body { color: %(text)s; }
            p { margin: 0 0 8px 0; }
            h1, h2, h3, h4 { color: %(bright)s; margin: 10px 0 6px 0; }
            h1 { font-size: %(h1).1fpt; }
            h2 { font-size: %(h2).1fpt; }
            h3, h4 { font-size: %(h3).1fpt; }
            ul, ol { margin: 0 0 8px 0; -qt-list-indent: 1; }
            li { margin: 2px 0; }
            a { color: %(link)s; }
            code { font-family: %(mono)s; background: %(codebg)s; color: %(code)s; }
            pre { font-family: %(mono)s; background: %(codebg)s;
                  color: %(code)s; padding: 8px; margin: 6px 0; }
            blockquote { color: %(dim)s; margin: 6px 0 6px 10px; }
            table { border-collapse: collapse; margin: 6px 0; }
            th, td { border: 1px solid %(edge)s; padding: 4px 8px; }
            th { color: %(bright)s; }
        """ % {
            "text": theme.TEXT, "dim": theme.TEXT_DIM, "bright": tint,
            "link": theme.ACCENT_BRIGHT, "mono": theme.FONT_MONO,
            "codebg": theme.SUNKEN, "code": theme.WRITE_BRIGHT,
            "edge": theme.rgba("#FFFFFF", 0.16),
            "h1": theme.SIZE_BODY + 3, "h2": theme.SIZE_BODY + 1.5,
            "h3": theme.SIZE_BODY + 0.5,
        }

    # ---- content ---------------------------------------------------------

    def set_turn(self, turn):
        self.turn = turn
        self.stamp.setText(_when(turn.when))
        self.copy_button.setVisible(not turn.pending and bool(turn.answer))
        if turn.pending:
            self.body.setMarkdown("")
            self.body.setPlainText(t("Working on it…"))
            self._dim()
        elif turn.failed:
            self.body.setMarkdown("")
            self.body.setPlainText(turn.answer or t("It did not work."))
        elif turn.mode == history.DICTATE:
            # A dictation is a transcript of speech. Rendering it as markdown
            # would let a stray asterisk silently eat half a sentence.
            self.body.setMarkdown("")
            self.body.setPlainText(turn.answer or turn.question)
        else:
            self.body.setMarkdown(turn.answer)
            self._restyle()
        self._fit()

    def _dim(self):
        """For a line that is a placeholder rather than an answer."""
        cursor = QTextCursor(self.body.document())
        cursor.select(QTextCursor.SelectionType.Document)
        shape = QTextCharFormat()
        shape.setForeground(QColor(theme.TEXT_FAINT))
        shape.setFontItalic(True)
        cursor.mergeCharFormat(shape)

    def _restyle(self):
        """Bring what setMarkdown built back into the panel's own scale.

        Qt writes a character format onto every heading and code block as it
        parses, and a character format beats the document's stylesheet. Left
        alone, a `#` heading in a 10pt bubble comes out at twice the size of the
        window's title, and a fenced block is monospace on nothing. So the
        formats are walked and overwritten — the only reliable way to style
        markdown Qt has already laid out.
        """
        tint = QColor(theme.WRITE_BRIGHT if self.turn.mode == history.DICTATE
                      else theme.AGENT_BRIGHT)
        document = self.body.document()
        cursor = QTextCursor(document)
        runs = []                      # contiguous stretches of fenced code
        block = document.begin()
        while block.isValid():
            level = block.blockFormat().headingLevel()
            if block.blockFormat().nonBreakableLines():
                start = block.position()
                end = block.position() + block.length() - 1
                if runs and runs[-1][1] + 1 >= start:
                    runs[-1] = (runs[-1][0], end)
                else:
                    runs.append((start, end))
            elif level:
                cursor.setPosition(block.position())
                cursor.setPosition(block.position() + block.length() - 1,
                                   QTextCursor.MoveMode.KeepAnchor)
                shape = QTextCharFormat()
                shape.setFontPointSize(
                    theme.SIZE_BODY + max(0.5, 2.5 - (level - 1)))
                shape.setFontWeight(QFont.Weight.DemiBold)
                shape.setForeground(tint)
                cursor.mergeCharFormat(shape)
            block = block.next()

        # Backwards, so that moving one run into a frame does not shift the
        # positions of the runs that have not been done yet.
        for start, end in reversed(runs):
            cursor.setPosition(start)
            cursor.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
            shape = QTextCharFormat()
            shape.setFontFamilies(theme.FONT_MONO.split(", "))
            shape.setFontPointSize(theme.SIZE_BODY - 0.6)
            shape.setForeground(QColor(theme.WRITE_BRIGHT))
            cursor.mergeCharFormat(shape)
            # A frame rather than a block background: a block paints only as
            # wide as its own line, so a code listing came out with one black
            # band per line, each a different length.
            box = QTextFrameFormat()
            box.setBackground(QColor(theme.SUNKEN))
            box.setPadding(8)
            box.setLeftMargin(2)
            box.setRightMargin(2)
            box.setTopMargin(4)
            box.setBottomMargin(4)
            box.setBorder(1)
            box.setBorderBrush(QColor(theme.rgba("#FFFFFF", 0.09)))
            box.setBorderStyle(QTextFrameFormat.BorderStyle.BorderStyle_Solid)
            cursor.insertFrame(box)

    def _copy(self):
        copy_out(self.turn.answer)
        self.copy_button.setText(t("Copied"))
        QTimer.singleShot(1400, lambda: self.copy_button.setText(t("Copy")))

    # ---- sizing ----------------------------------------------------------

    def set_max(self, width):
        self.body.setMaximumWidth(max(200, int(width * BUBBLE_MAX)))
        self._fit()

    def _fit(self):
        """Grow the browser to exactly the height its document needs."""
        document = self.body.document()
        width = self.body.maximumWidth()
        if width > 16777000:                      # not constrained yet
            width = max(200, self.width())
        inner = max(80, width - 30)               # padding and border
        document.setTextWidth(inner)
        height = int(document.size().height()) + 22
        self.body.setFixedHeight(max(36, height))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._fit()


class Empty(QWidget):
    """What is here before anything has been said."""

    def __init__(self, parent=None):
        super().__init__(parent)
        column = QVBoxLayout(self)
        column.setContentsMargins(theme.PAD, 60, theme.PAD, theme.PAD)
        column.setSpacing(8)
        column.setAlignment(Qt.AlignmentFlag.AlignTop)
        title = QLabel(t("Nothing here yet"))
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("color: %s; font-size: %.1fpt; font-weight: 600;"
                            % (theme.TEXT_DIM, theme.SIZE_TITLE))
        column.addWidget(title)
        hint = QLabel(t("Press the pen to write what you say, or the spark to "
                        "ask the agent. Everything either of them does shows "
                        "up here."))
        hint.setWordWrap(True)
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint.setStyleSheet("color: %s; font-size: %.1fpt;"
                           % (theme.TEXT_FAINT, theme.SIZE_BODY))
        column.addWidget(hint)


# --- the window ------------------------------------------------------------

class Panel(QWidget):
    """The conversation, in a window of its own.

    Frameless and drawn by hand, because a native title bar on a panel this
    small is half its height and none of its content. It does take focus,
    unlike everything else this application puts on the screen: you are meant to
    scroll it, select from it and copy out of it, and a window that refuses
    focus can do none of those.
    """

    closed = pyqtSignal()
    moved = pyqtSignal(int, int)

    def __init__(self, store, parent=None):
        super().__init__(parent)
        self.store = store
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setWindowTitle("Zeno")
        self.resize(WIDTH, HEIGHT)
        self.setMinimumSize(MIN_WIDTH, MIN_HEIGHT)

        self._drag = None
        self._wide = False
        # turn id -> (Request|None, Answer). None until the first build, so
        # that an empty history still gets its empty state built once — with a
        # plain {} the "nothing has changed" test passes on the very first
        # refresh and nothing is ever put on the thread at all.
        self._rows = None
        self._at_bottom = True

        # The whole window is one card, and the shadow needs room outside it.
        shell = QVBoxLayout(self)
        shell.setContentsMargins(theme.SHADOW, theme.SHADOW,
                                 theme.SHADOW, theme.SHADOW)
        self.card = QWidget()
        self.card.setObjectName("card")
        self.card.setStyleSheet("""
            QWidget#card {
                background: %s;
                border: 1px solid %s;
                border-radius: %dpx;
            }
        """ % (theme.BASE, theme.rgba("#FFFFFF", 0.11), theme.RADIUS_PANEL))
        glow = QGraphicsDropShadowEffect(self)
        glow.setBlurRadius(theme.SHADOW * 1.6)
        glow.setColor(QColor(0, 0, 0, 190))
        glow.setOffset(0, 6)
        self.card.setGraphicsEffect(glow)
        shell.addWidget(self.card)

        inside = QVBoxLayout(self.card)
        inside.setContentsMargins(0, 0, 0, 0)
        inside.setSpacing(0)
        inside.addWidget(self._header())
        inside.addWidget(self._conversation(), 1)
        inside.addWidget(self._footer())

        self.store.changed.connect(self.refresh)
        self.refresh()

    # ---- the parts -------------------------------------------------------

    def _header(self):
        bar = QWidget()
        bar.setFixedHeight(46)
        bar.setStyleSheet(
            "background: %s; border-top-left-radius: %dpx;"
            " border-top-right-radius: %dpx; border-bottom: 1px solid %s;"
            % (theme.RAISED, theme.RADIUS_PANEL, theme.RADIUS_PANEL,
               theme.rgba("#FFFFFF", 0.08)))
        row = QHBoxLayout(bar)
        row.setContentsMargins(theme.PAD, 0, 8, 0)
        row.setSpacing(theme.GAP)

        self.dot = QLabel("●")
        self.dot.setStyleSheet("color: %s; font-size: 11pt;" % theme.ACCENT_BRIGHT)
        row.addWidget(self.dot)

        title = QLabel("Zeno")
        title.setStyleSheet("font-size: %.1fpt; font-weight: 700; color: %s;"
                            % (theme.SIZE_TITLE, theme.TEXT))
        row.addWidget(title)
        self.count = QLabel("")
        self.count.setStyleSheet("color: %s; font-size: %.1fpt;"
                                 % (theme.TEXT_FAINT, theme.SIZE_SMALL))
        row.addWidget(self.count)
        row.addStretch(1)

        self.wide_button = self._icon_button("⤢", t("Wider"), self.toggle_width)
        row.addWidget(self.wide_button)
        row.addWidget(self._icon_button("⌫", t("Clear the history"), self._clear))
        row.addWidget(self._icon_button("✕", t("Close"), self.close))
        return bar

    def _icon_button(self, glyph, tip, slot):
        button = QPushButton(glyph)
        button.setToolTip(tip)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setFixedSize(28, 28)
        button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        button.setStyleSheet("""
            QPushButton { background: transparent; border: none;
                          border-radius: 7px; color: %s; font-size: 11pt; }
            QPushButton:hover { background: %s; color: %s; }
        """ % (theme.TEXT_DIM, theme.rgba("#FFFFFF", 0.09), theme.TEXT))
        button.clicked.connect(slot)
        return button

    def _conversation(self):
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setStyleSheet("background: transparent;")
        self.scroll.verticalScrollBar().valueChanged.connect(self._note_position)

        self.thread = QWidget()
        self.thread.setStyleSheet("background: transparent;")
        self.column = QVBoxLayout(self.thread)
        self.column.setContentsMargins(theme.PAD, theme.PAD, theme.PAD, theme.PAD)
        self.column.setSpacing(theme.GAP)
        self.column.addStretch(1)
        self.scroll.setWidget(self.thread)
        return self.scroll

    def _footer(self):
        bar = QWidget()
        bar.setFixedHeight(34)
        bar.setStyleSheet(
            "background: %s; border-bottom-left-radius: %dpx;"
            " border-bottom-right-radius: %dpx; border-top: 1px solid %s;"
            % (theme.SUNKEN, theme.RADIUS_PANEL, theme.RADIUS_PANEL,
               theme.rgba("#FFFFFF", 0.06)))
        row = QHBoxLayout(bar)
        row.setContentsMargins(theme.PAD, 0, 8, 0)
        self.note = QLabel("")
        self.note.setSizePolicy(QSizePolicy.Policy.Ignored,
                                QSizePolicy.Policy.Preferred)
        self.note.setStyleSheet("color: %s; font-size: %.1fpt;"
                                % (theme.TEXT_FAINT, theme.SIZE_SMALL))
        row.addWidget(self.note, 1)
        copy_all = QPushButton(t("Copy all as markdown"))
        copy_all.setCursor(Qt.CursorShape.PointingHandCursor)
        copy_all.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        copy_all.setStyleSheet("""
            QPushButton { background: transparent; border: none; color: %s;
                          font-size: %.1fpt; padding: 0 6px; }
            QPushButton:hover { color: %s; }
        """ % (theme.TEXT_FAINT, theme.SIZE_SMALL, theme.TEXT))
        copy_all.clicked.connect(self._copy_all)
        row.addWidget(copy_all)
        return bar

    # ---- filling it in ---------------------------------------------------

    def refresh(self):
        """Rebuild the thread from the store.

        The widgets for turns that have not changed are kept, so that a
        selection you have made and the place you have scrolled to survive a new
        message arriving.
        """
        turns = self.store.turns()
        wanted = [turn.id for turn in turns]
        if self._rows is None or list(self._rows) != wanted:
            self._rebuild(turns)
        else:
            for turn in turns:
                request, answer = self._rows[turn.id]
                answer.set_turn(turn)
        self.count.setText("" if not turns else t("{n} messages").format(n=len(turns)))
        # A short status and nothing else. It used to echo the last question,
        # which is already the largest thing on the screen directly above it,
        # and long enough to run under the button beside it.
        self.note.setText(t("Working on it…") if any(turn.pending for turn in turns)
                          else t("Ready"))
        if self._at_bottom:
            QTimer.singleShot(0, self._to_bottom)

    def _rebuild(self, turns):
        while self.column.count() > 1:
            item = self.column.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self._rows = {}
        if not turns:
            self.column.insertWidget(0, Empty())
            return
        last_day = None
        for index, turn in enumerate(turns):
            day = _day(turn.when)
            if day != last_day:
                self.column.insertWidget(self.column.count() - 1, Separator(day))
                last_day = day
            request = None
            if turn.question:
                request = Request(turn)
                self.column.insertWidget(self.column.count() - 1, request)
            answer = Answer(turn)
            self.column.insertWidget(self.column.count() - 1, answer)
            self._rows[turn.id] = (request, answer)
        self._resize_bubbles()

    def _resize_bubbles(self):
        width = self.scroll.viewport().width() - theme.PAD * 2
        for request, answer in self._rows.values():
            if request is not None:
                request.set_max(width)
            answer.set_max(width)

    def _to_bottom(self):
        bar = self.scroll.verticalScrollBar()
        bar.setValue(bar.maximum())

    def _note_position(self, value):
        bar = self.scroll.verticalScrollBar()
        self._at_bottom = value >= bar.maximum() - 8

    # ---- what the buttons do ---------------------------------------------

    def toggle_width(self):
        self._wide = not self._wide
        target = WIDE_WIDTH if self._wide else WIDTH
        screen = QApplication.primaryScreen()
        if screen is not None:
            target = min(target, screen.availableGeometry().width() - 40)
        right = self.geometry().right()
        self.resize(target, self.height())
        # Grow leftwards, so the panel does not walk off the edge it is parked on.
        self.move(right - target + 1, self.y())
        self.wide_button.setToolTip(t("Narrower") if self._wide else t("Wider"))

    def _clear(self):
        self.store.clear()

    def _copy_all(self):
        text = history.as_markdown(self.store.turns())
        copy_out(text)
        self.note.setText(t("Copied."))
        QTimer.singleShot(1600, self.refresh)
        return text

    # ---- window behaviour ------------------------------------------------

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._resize_bubbles()

    def mousePressEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return
        # Only the title bar drags. Dragging from the body would fight with
        # selecting text out of it, which is most of what this window is for.
        local = event.position().toPoint()
        if local.y() - theme.SHADOW <= 46:
            self._drag = event.globalPosition().toPoint() - self.pos()

    def mouseMoveEvent(self, event):
        if self._drag is not None:
            self.move(event.globalPosition().toPoint() - self._drag)

    def mouseReleaseEvent(self, _event):
        if self._drag is not None:
            self._drag = None
            self.moved.emit(self.x(), self.y())

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.close()
            return
        super().keyPressEvent(event)

    def closeEvent(self, event):
        super().closeEvent(event)
        self.closed.emit()

    def place_beside(self, anchor, on_right=True, margin=14):
        """Sit next to the control, on whichever side has the room."""
        screen = QApplication.primaryScreen()
        if screen is None:
            return
        area = screen.availableGeometry()
        width, height = self.width(), self.height()
        if on_right:
            x = anchor.left() - width + theme.SHADOW - margin + theme.SHADOW
        else:
            x = anchor.right() + margin - theme.SHADOW
        y = anchor.center().y() - height // 2
        x = max(area.left() - theme.SHADOW,
                min(x, area.right() - width + theme.SHADOW))
        y = max(area.top() - theme.SHADOW,
                min(y, area.bottom() - height + theme.SHADOW))
        self.move(int(x), int(y))
