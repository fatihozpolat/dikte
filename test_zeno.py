#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for being spoken to: what a command meant, and the loop that runs it.

Nothing here records, transcribes, speaks or pastes. The recorder, the chain and
the voice are stood in for, and what is checked is the part that decides: which
of two opposite things a sentence asked for, when an instruction has finished
being given, and that the assistant is never listening while it is talking.

    python3 -m unittest test_zeno -v
"""

import io
import os
import pathlib
import shutil
import tempfile
import time
import unittest
import unittest.mock

from PyQt6.QtWidgets import QApplication

import audio
import history
import conversation

_app = QApplication.instance() or QApplication([])


# --- the loop -------------------------------------------------------------

class FakeRecorder:
    def __init__(self):
        self.active = False
        self.started = 0
        self.cancelled = 0
        self.stopped = 0
        self.pcm = b""
        self.rms = []

    def start(self, _target="", _limit=0):
        self.active = True
        self.started += 1

    def snapshot(self):
        return self.pcm, list(self.rms)

    def cancel(self):
        self.active = False
        self.cancelled += 1

    def stop(self):
        self.active = False
        self.stopped += 1


class FakeSignal:
    def __init__(self):
        self._slots = []

    def connect(self, slot):
        self._slots.append(slot)

    def emit(self, *args):
        for slot in list(self._slots):
            # A Qt signal connected to another signal is forwarded, not
            # called; the real thing does this and the stand-in has to too.
            (slot.emit if hasattr(slot, "emit") else slot)(*args)


class FakePipeline:
    def __init__(self):
        self.finished = FakeSignal()
        self.failed = FakeSignal()
        self.stage = FakeSignal()
        self.runs = []

    def run(self, wav, duration, rms, ask=False, paste_it=None):
        self.runs.append({"wav": wav, "ask": ask, "paste": paste_it})


class Conf(dict):
    pass


def a_conf(**changes):
    conf = Conf({"mic_target": "", "speech_margin_db": 10.0,
                 "silence_db": -55.0, "min_voiced_seconds": 0.3,
})
    conf.update(changes)
    return conf


def quiet_rms(seconds):
    blocks = max(1, int(seconds / (audio.CHUNK_FRAMES / audio.RATE)))
    return [0.0004] * blocks


def loud_rms(seconds):
    blocks = max(1, int(seconds / (audio.CHUNK_FRAMES / audio.RATE)))
    # Mostly loud, so it holds more than the minimum of actual speech.
    return [0.0004 if i % 4 == 3 else 0.2 for i in range(blocks)]


class TheLoop(unittest.TestCase):
    """Press, talk, press. Both edges are given, so both are tested."""

    def setUp(self):
        self.conf = a_conf()
        self.recorder = FakeRecorder()
        self.pipeline = FakePipeline()
        self.zeno = conversation.Conversation(
            self.conf, self.recorder, self.pipeline)
        self.states = []
        self.zeno.state_changed.connect(self.states.append)
        self.pasted = []
        self.asked = []
        self.answers = []
        self.zeno.finish_dictation.connect(self.pasted.append)
        self.zeno.ask_agent.connect(self.asked.append)
        self.zeno.answered.connect(self.answers.append)

    def test_it_starts_out_waiting(self):
        self.assertEqual(self.zeno.state, conversation.WAITING)
        self.assertFalse(self.zeno.busy)
        self.assertFalse(self.zeno.listening)

    def test_the_first_press_opens_the_microphone(self):
        self.assertTrue(self.zeno.wake(conversation.ASK))
        self.assertEqual(self.zeno.state, conversation.LISTENING)
        self.assertTrue(self.zeno.listening)
        self.assertEqual(self.recorder.started, 1)

    def test_pressing_a_second_lobe_while_listening_changes_nothing(self):
        self.zeno.wake(conversation.ASK)
        self.assertFalse(self.zeno.wake(conversation.DICTATE))
        self.assertEqual(self.recorder.started, 1)
        self.assertEqual(self.zeno.mode, conversation.ASK)

    def test_the_second_press_stops_it_and_keeps_what_was_said(self):
        """Stopped, not thrown away. The second press is how a recording ends,
        so it must never do what giving up on one does."""
        self.zeno.wake()
        self.assertTrue(self.zeno.finish())
        self.assertEqual(self.zeno.state, conversation.WORKING)
        self.assertEqual(self.recorder.stopped, 1)
        self.assertEqual(self.recorder.cancelled, 0)

    def test_a_second_press_when_it_is_not_listening_does_nothing(self):
        self.assertFalse(self.zeno.finish())
        self.zeno.wake()
        self.zeno.finish()
        self.assertFalse(self.zeno.finish())
        self.assertEqual(self.recorder.stopped, 1)

    def test_quiet_does_not_end_it(self):
        """Why silence detection was taken out: somebody hunting for a word
        pauses, and the sentence they were building is cut in half."""
        self.zeno.wake()
        self.recorder.rms = quiet_rms(30.0)
        for _ in range(20):
            _app.processEvents()
        self.assertEqual(self.zeno.state, conversation.LISTENING)
        self.assertEqual(self.recorder.stopped, 0)

    def test_a_press_that_never_comes_back_is_not_recorded_for_ever(self):
        self.zeno.wake()
        self.zeno._out_of_time()
        self.assertEqual(self.zeno.state, conversation.WORKING)
        self.assertEqual(self.recorder.stopped, 1)

    def test_the_recording_is_transcribed_without_being_pasted(self):
        """What was said has to be read before anything can be done with it,
        and under the asking lobe it must not be pasted at all."""
        self.zeno.wake()
        self.zeno.take("clip.wav", 2.0, [])
        self.assertEqual(len(self.pipeline.runs), 1)
        self.assertFalse(self.pipeline.runs[0]["ask"])
        self.assertFalse(self.pipeline.runs[0]["paste"])

    def test_the_writing_lobe_pastes_and_never_reaches_the_agent(self):
        self.zeno.wake(conversation.DICTATE)
        self.zeno.take("clip.wav", 2.0, [])
        self.pipeline.finished.emit("ham", "Bugun uc karar aldik.", "")
        self.assertEqual(self.pasted, ["Bugun uc karar aldik."])
        self.assertEqual(self.asked, [])

    def test_the_writing_lobe_pastes_even_when_it_sounds_like_an_order(self):
        """Nothing is read out of the words. The button already said."""
        self.zeno.wake(conversation.DICTATE)
        self.zeno.take("clip.wav", 2.0, [])
        self.pipeline.finished.emit("ham", "Takvime toplanti ekle", "")
        self.assertEqual(self.pasted, ["Takvime toplanti ekle"])
        self.assertEqual(self.asked, [])

    def test_the_asking_lobe_asks_and_never_pastes(self):
        self.zeno.wake(conversation.ASK)
        self.zeno.take("clip.wav", 2.0, [])
        self.pipeline.finished.emit("ham", "Takvime toplanti ekle", "")
        self.assertEqual(self.asked, ["Takvime toplanti ekle"])
        self.assertEqual(self.pasted, [])

    def test_the_asking_lobe_asks_even_when_it_starts_with_write(self):
        """"Yaz bana bir e-posta" is a thing you say *to* an assistant. Reading
        the opening word would have pasted it instead of answering it."""
        self.zeno.wake(conversation.ASK)
        self.zeno.take("clip.wav", 2.0, [])
        self.pipeline.finished.emit("ham", "yaz bana bir e-posta taslagi", "")
        self.assertEqual(self.asked, ["yaz bana bir e-posta taslagi"])
        self.assertEqual(self.pasted, [])

    def test_what_was_heard_is_shown_either_way(self):
        seen = []
        self.zeno.heard.connect(seen.append)
        self.zeno.wake(conversation.DICTATE)
        self.zeno.take("clip.wav", 2.0, [])
        self.pipeline.finished.emit("ham", "iki kelime", "")
        self.assertEqual(seen, ["iki kelime"])

    def test_the_answer_is_shown_and_then_it_is_free_again(self):
        self.zeno.wake()
        self.zeno.finish()
        self.zeno.answer("Persembe uce eklendi.")
        self.assertIn("Persembe uce eklendi.", self.answers)
        self.assertEqual(self.zeno.state, conversation.WAITING)
        self.assertFalse(self.zeno.busy)

    def test_a_warning_alongside_an_answer_is_reported_as_well(self):
        seen = []
        self.zeno.failed.connect(seen.append)
        self.zeno.wake()
        self.zeno.finish()
        self.zeno.answer("Oldu.", "temizleme calismadi")
        self.assertEqual(self.answers, ["Oldu."])
        self.assertEqual(seen, ["temizleme calismadi"])

    def test_what_the_agent_says_crosses_from_its_own_thread(self):
        """A timer started on a worker thread never fires, and every answer was
        being lost that way without a word about it. A signal does cross."""
        import threading
        self.zeno.agent_answered.connect(self.zeno.answer)
        self.zeno.wake()
        self.zeno.finish()
        threading.Thread(
            target=lambda: self.zeno.agent_answered.emit("Oldu.", ""),
            daemon=True).start()
        for _ in range(400):
            _app.processEvents()
            if self.answers:
                break
            time.sleep(0.005)
        self.assertEqual(self.answers, ["Oldu."])

    def test_a_transcription_that_came_back_empty_ends_it(self):
        self.zeno.wake()
        self.zeno.take("clip.wav", 2.0, [])
        self.pipeline.finished.emit("", "", "")
        self.assertEqual(self.zeno.state, conversation.WAITING)
        self.assertEqual(self.pasted, [])
        self.assertEqual(self.asked, [])

    def test_a_failure_is_reported_and_does_not_leave_it_stuck(self):
        seen = []
        self.zeno.failed.connect(seen.append)
        self.zeno.wake()
        self.zeno.take("clip.wav", 2.0, [])
        self.pipeline.failed.emit("mikrofon yok")
        self.assertEqual(seen, ["mikrofon yok"])
        self.assertEqual(self.zeno.state, conversation.WAITING)

    def test_giving_up_stops_everything_it_started(self):
        self.zeno.wake()
        self.zeno.cancel()
        self.assertEqual(self.zeno.state, conversation.WAITING)
        self.assertEqual(self.recorder.cancelled, 1)

    def test_it_can_be_used_again_straight_after(self):
        self.zeno.wake(conversation.DICTATE)
        self.zeno.take("clip.wav", 2.0, [])
        self.pipeline.finished.emit("ham", "ilki", "")
        self.assertTrue(self.zeno.wake(conversation.ASK))
        self.zeno.take("clip.wav", 2.0, [])
        self.pipeline.finished.emit("ham", "ikincisi", "")
        self.assertEqual(self.pasted, ["ilki"])
        self.assertEqual(self.asked, ["ikincisi"])

    def test_a_stage_from_the_chain_is_passed_on(self):
        seen = []
        self.zeno.stage.connect(seen.append)
        self.pipeline.stage.emit("Yaziya cevriliyor...")
        self.assertEqual(seen, ["Yaziya cevriliyor..."])


class TheStore(unittest.TestCase):
    """What is kept of a turn, and what is not."""

    def setUp(self):
        import config as cfg
        self.tmp = tempfile.mkdtemp(prefix="dikte-history-")
        patch = unittest.mock.patch.object(
            cfg, "HISTORY_FILE", pathlib.Path(self.tmp) / "history.jsonl")
        patch.start()
        self.addCleanup(patch.stop)
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.store = history.Store()

    def test_it_starts_empty(self):
        self.assertEqual(self.store.turns(), [])

    def test_a_question_shows_before_it_is_answered(self):
        """You should see what went out while it is still out. The panel is
        driven from the store, so the store is where the in-flight turn lives."""
        turn = self.store.begin(history.ASK, "takvime toplanti ekle")
        self.assertEqual([t.question for t in self.store.turns()],
                         ["takvime toplanti ekle"])
        self.assertTrue(turn.pending)

    def test_an_unanswered_question_is_never_written_down(self):
        """If the application stops between the asking and the answering there
        is nothing there to resume, so there is nothing worth keeping."""
        self.store.begin(history.ASK, "yarim kalan")
        self.assertEqual(history.Store().turns(), [])

    def test_the_answer_is_what_makes_it_worth_keeping(self):
        turn = self.store.begin(history.ASK, "soru")
        self.store.finish(turn, answer="cevap")
        kept = history.Store().turns()
        self.assertEqual([(t.question, t.answer) for t in kept],
                         [("soru", "cevap")])
        self.assertFalse(kept[0].pending)

    def test_a_failure_is_kept_too_and_says_so(self):
        turn = self.store.begin(history.ASK, "soru")
        self.store.finish(turn, error="claude bulunamadi")
        kept = history.Store().turns()
        self.assertTrue(kept[0].failed)
        self.assertEqual(kept[0].answer, "claude bulunamadi")

    def test_calling_it_off_leaves_nothing_behind(self):
        turn = self.store.begin(history.ASK, "bosver")
        self.store.drop(turn)
        self.assertEqual(self.store.turns(), [])
        self.assertEqual(history.Store().turns(), [])

    def test_a_dictation_is_kept_whole_in_one_go(self):
        self.store.record(history.DICTATE, "", "Bugun uc karar aldik.")
        kept = history.Store().turns()
        self.assertEqual(kept[0].mode, history.DICTATE)
        self.assertEqual(kept[0].answer, "Bugun uc karar aldik.")

    def test_the_rows_the_worker_already_writes_are_read_back(self):
        """history.jsonl predates this module by a long way. Rewriting the file
        into a new shape would have lost whatever a half-done migration lost."""
        import config as cfg
        cfg.append_history({"ts": "2026-01-02 09:30:00", "mode": "",
                            "question": "", "text": "eski bir dikte"})
        cfg.append_history({"ts": "2026-01-02 09:31:00", "mode": "ask",
                            "question": "eski bir soru", "text": "eski cevap"})
        kept = history.Store().turns()
        self.assertEqual([t.mode for t in kept],
                         [history.DICTATE, history.ASK])
        self.assertEqual(kept[0].answer, "eski bir dikte")
        self.assertEqual(kept[1].question, "eski bir soru")

    def test_an_unreadable_line_does_not_take_the_rest_with_it(self):
        import config as cfg
        cfg.append_history({"mode": "ask", "question": "s", "text": "c"})
        with io.open(cfg.HISTORY_FILE, "a", encoding="utf-8") as handle:
            handle.write("{ bu json degil\n")
        self.assertEqual(len(history.Store().turns()), 1)

    def test_they_come_back_oldest_first(self):
        self.store.record(history.ASK, "bir", "1")
        self.store.record(history.ASK, "iki", "2")
        self.assertEqual([t.question for t in self.store.turns()],
                         ["bir", "iki"])

    def test_the_one_in_flight_is_last(self):
        self.store.record(history.ASK, "bitmis", "cevap")
        self.store.begin(history.ASK, "suruyor")
        self.assertEqual([t.question for t in self.store.turns()],
                         ["bitmis", "suruyor"])

    def test_clearing_it_clears_the_one_in_flight_too(self):
        self.store.record(history.ASK, "bir", "1")
        self.store.begin(history.ASK, "iki")
        self.store.clear()
        self.assertEqual(self.store.turns(), [])

    def test_it_says_when_something_changed(self):
        seen = []
        self.store.changed.connect(lambda: seen.append(True))
        turn = self.store.begin(history.ASK, "soru")
        self.store.finish(turn, answer="cevap")
        self.assertEqual(len(seen), 2)

    def test_the_whole_thing_comes_out_as_markdown(self):
        self.store.record(history.ASK, "takvime ekle", "## Eklendi\n\nOldu.")
        text = history.as_markdown(self.store.turns())
        self.assertIn("> takvime ekle", text)
        self.assertIn("## Eklendi", text)

    def test_a_history_that_cannot_be_written_is_not_an_error(self):
        """The answer is already on the screen. A disk that will not take it is
        not a reason to lose the answer as well."""
        import config as cfg
        with unittest.mock.patch.object(
                cfg, "append_history", side_effect=OSError("disk dolu")):
            self.store.record(history.ASK, "soru", "cevap")


if __name__ == "__main__":
    unittest.main(verbosity=2)
