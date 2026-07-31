#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for the panel the third lobe opens.

The widgets are real, but nothing is shown on a screen. What is checked is the
part that would be wrong without anybody noticing: that an answer is rendered as
markdown and a dictation is not, that a message sizes itself to its content
instead of growing a scrollbar of its own, that a turn still being answered says
so, and that the thread is rebuilt without throwing away what you had selected.

    python3 -m unittest test_chat -v
"""

import pathlib
import shutil
import tempfile
import time
import unittest
import unittest.mock

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication

import chat
import config as cfg
import history
import theme

_app = QApplication.instance() or QApplication([])


def a_turn(mode=history.ASK, question="soru", answer="cevap",
           state=history.DONE, when=None):
    return history.Turn(mode=mode, question=question, answer=answer,
                        state=state, when=when if when is not None else time.time())


class Rendering(unittest.TestCase):
    """What a message does with the text it is given."""

    def answer_for(self, turn):
        widget = chat.Answer(turn)
        self.addCleanup(widget.deleteLater)
        return widget

    def test_an_agent_answer_is_read_as_markdown(self):
        widget = self.answer_for(a_turn(answer="## Başlık\n\n- bir\n- iki"))
        text = widget.body.toPlainText()
        self.assertNotIn("##", text)
        self.assertIn("Başlık", text)
        self.assertIn("bir", text)

    def test_a_dictation_is_left_exactly_as_it_was_said(self):
        """It is a transcript of speech, not a document. Run through a markdown
        parser, a stray asterisk silently eats half the sentence."""
        said = "yıldız * işareti ve _alt tire_ aynen kalmalı"
        widget = self.answer_for(a_turn(mode=history.DICTATE, question="",
                                        answer=said))
        self.assertEqual(widget.body.toPlainText(), said)

    def test_a_heading_is_brought_down_to_the_panel_scale(self):
        """Qt writes its own point size onto every heading as it parses, and it
        beats the stylesheet: left alone a `#` came out twice the window title."""
        widget = self.answer_for(a_turn(answer="# Kocaman"))
        block = widget.body.document().begin()
        size = block.begin().fragment().charFormat().fontPointSize()
        self.assertGreater(size, theme.SIZE_BODY)
        self.assertLess(size, theme.SIZE_BODY + 4)

    def test_a_fenced_block_is_put_in_a_frame_of_its_own(self):
        """A block paints only as wide as its own line, so a listing came out as
        one ragged black band per line. A frame is one box round the lot."""
        widget = self.answer_for(
            a_turn(answer="Şuna bak:\n\n```python\nbir = 1\niki = 2\n```\n"))
        root = widget.body.document().rootFrame()
        self.assertTrue(any(child.childFrames() is not None
                            for child in root.childFrames()))
        self.assertGreaterEqual(len(root.childFrames()), 1)

    def test_a_turn_still_being_answered_says_so(self):
        widget = self.answer_for(a_turn(answer="", state=history.PENDING))
        self.assertTrue(widget.body.toPlainText().strip())
        self.assertFalse(widget.copy_button.isVisible())

    def test_a_failure_shows_what_went_wrong(self):
        widget = self.answer_for(
            a_turn(answer="claude bulunamadı", state=history.FAILED))
        self.assertIn("bulunamadı", widget.body.toPlainText())

    def test_a_message_never_grows_a_scrollbar_of_its_own(self):
        """Two things to scroll and no way to tell which one the wheel is
        about to move."""
        widget = self.answer_for(a_turn(answer="uzun bir cümle " * 90))
        widget.set_max(400)
        self.assertEqual(widget.body.verticalScrollBarPolicy(),
                         Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.assertGreaterEqual(
            widget.body.height(),
            int(widget.body.document().size().height()))

    def test_a_long_answer_is_taller_than_a_short_one(self):
        short = self.answer_for(a_turn(answer="kısa"))
        short.set_max(400)
        long = self.answer_for(a_turn(answer="uzun bir cümle " * 40))
        long.set_max(400)
        self.assertGreater(long.body.height(), short.body.height())

    def test_a_request_is_never_wider_than_the_panel(self):
        widget = chat.Request(a_turn(question="uzun bir soru " * 40))
        self.addCleanup(widget.deleteLater)
        widget.set_max(400)
        self.assertLessEqual(widget.label.maximumWidth(), 400)

    def test_a_question_nobody_could_make_out_still_says_something(self):
        widget = chat.Request(a_turn(question=""))
        self.addCleanup(widget.deleteLater)
        self.assertTrue(widget.label.text().strip())


class Panel(unittest.TestCase):
    """The window itself, driven by the store."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="dikte-chat-")
        patch = unittest.mock.patch.object(
            cfg, "HISTORY_FILE", pathlib.Path(self.tmp) / "history.jsonl")
        patch.start()
        self.addCleanup(patch.stop)
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.store = history.Store()
        self.panel = chat.Panel(self.store)
        self.addCleanup(self.panel.deleteLater)

    def test_an_empty_history_says_what_to_do_rather_than_nothing(self):
        self.assertEqual(self.panel._rows, {})
        kinds = [type(self.panel.column.itemAt(i).widget()).__name__
                 for i in range(self.panel.column.count())]
        self.assertIn("Empty", kinds)

    def test_a_turn_arriving_puts_a_message_on_the_thread(self):
        self.store.record(history.ASK, "soru", "cevap")
        self.assertEqual(len(self.panel._rows), 1)

    def test_the_panel_follows_the_store_without_being_told_twice(self):
        """The store's signal is the only wiring. If the panel had to be
        refreshed by hand as well, one of the two would be forgotten."""
        self.store.record(history.ASK, "bir", "1")
        self.store.record(history.ASK, "iki", "2")
        self.assertEqual(len(self.panel._rows), 2)

    def test_a_dictation_has_no_request_above_it(self):
        self.store.record(history.DICTATE, "", "yazılan cümle")
        request, answer = list(self.panel._rows.values())[0]
        self.assertIsNone(request)
        self.assertIn("yazılan", answer.body.toPlainText())

    def test_an_answer_arriving_does_not_rebuild_what_was_already_there(self):
        """Rebuilding throws away a selection and the place you had scrolled
        to, which is most of what this window is for."""
        turn = self.store.begin(history.ASK, "soru")
        before = self.panel._rows[turn.id][1]
        self.store.finish(turn, answer="cevap")
        after = self.panel._rows[turn.id][1]
        self.assertIs(before, after)
        self.assertIn("cevap", after.body.toPlainText())

    def test_a_day_gets_one_separator_and_not_one_per_message(self):
        now = time.time()
        for index in range(3):
            self.store.record(history.ASK, "soru %d" % index, "cevap")
        kinds = [type(self.panel.column.itemAt(i).widget()).__name__
                 for i in range(self.panel.column.count())]
        self.assertEqual(kinds.count("Separator"), 1)

    def test_yesterday_is_told_apart_from_today(self):
        self.assertEqual(chat._day(time.time()), chat._day(time.time() - 60))
        self.assertNotEqual(chat._day(time.time()),
                            chat._day(time.time() - 86400))

    def test_clearing_it_empties_the_thread(self):
        self.store.record(history.ASK, "soru", "cevap")
        self.panel._clear()
        self.assertEqual(self.panel._rows, {})

    def test_the_whole_conversation_can_be_taken_away_as_markdown(self):
        self.store.record(history.ASK, "takvime ekle", "## Eklendi")
        text = self.panel._copy_all()
        self.assertIn("takvime ekle", text)
        self.assertIn("## Eklendi", text)

    def test_widening_it_keeps_the_edge_it_is_parked_against(self):
        """It sits against the right-hand edge of the screen. Growing to the
        right would walk it off."""
        self.panel.move(900, 200)
        right = self.panel.geometry().right()
        self.panel.toggle_width()
        self.assertGreater(self.panel.width(), chat.WIDTH)
        self.assertEqual(self.panel.geometry().right(), right)
        self.panel.toggle_width()
        self.assertEqual(self.panel.width(), chat.WIDTH)

    def test_closing_it_says_so_so_the_lobe_can_go_out(self):
        seen = []
        self.panel.closed.connect(lambda: seen.append(True))
        self.panel.close()
        self.assertEqual(seen, [True])

    def test_it_paints_a_whole_conversation_without_falling_over(self):
        self.store.record(history.DICTATE, "", "bir dikte")
        self.store.record(history.ASK, "bir soru",
                          "# Başlık\n\nBir **paragraf**.\n\n"
                          "- madde\n- madde\n\n```sh\nls -la\n```\n\n"
                          "| a | b |\n| - | - |\n| 1 | 2 |\n")
        self.store.begin(history.ASK, "süren bir soru")
        pixmap = self.panel.grab()
        self.assertFalse(pixmap.isNull())


if __name__ == "__main__":
    unittest.main(verbosity=2)
