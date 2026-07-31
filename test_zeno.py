#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for being spoken to: what a command meant, and the loop that runs it.

Nothing here records, transcribes, speaks or pastes. The recorder, the chain and
the voice are stood in for, and what is checked is the part that decides: which
of two opposite things a sentence asked for, when an instruction has finished
being given, and that the assistant is never listening while it is talking.

    python3 -m unittest test_zeno -v
"""

import time
import unittest

from PyQt6.QtWidgets import QApplication

import audio
import conversation
import router
import tts

_app = QApplication.instance() or QApplication([])


class WhatWasMeant(unittest.TestCase):
    def assertDictated(self, said, expected):
        mode, payload = router.route(said)
        self.assertEqual(mode, router.DICTATE, said)
        self.assertEqual(payload, expected, said)

    def assertAsked(self, said):
        mode, payload = router.route(said)
        self.assertEqual(mode, router.ASK, said)
        self.assertEqual(payload, said.strip())

    def test_being_told_to_write_something_hands_back_the_something(self):
        self.assertDictated("Yaz: bugün üç karar aldık.", "bugün üç karar aldık.")
        self.assertDictated("yaz şunu bugün hava güzeldi", "bugün hava güzeldi")
        self.assertDictated("Not al, yarın Ahmet'i ara.", "yarın Ahmet'i ara.")
        self.assertDictated("Metne dök: merhaba dünya", "merhaba dünya")

    def test_english_openings_work_too(self):
        self.assertDictated("Write this down: we agreed three things",
                            "we agreed three things")
        self.assertDictated("take a note buy milk", "buy milk")

    def test_an_instruction_on_its_own_leaves_the_words_still_to_come(self):
        for said in ("Dikte et", "yazar mısın bunu", "write this down"):
            mode, payload = router.route(said)
            self.assertEqual(mode, router.DICTATE, said)
            self.assertEqual(payload, "", said)

    def test_anything_else_goes_to_the_agent_whole(self):
        self.assertAsked("Takvime perşembe saat üçe toplantı ekle")
        self.assertAsked("Bugün hava nasıl?")
        self.assertAsked("Notlarımı aç")

    def test_the_opening_is_only_an_opening(self):
        """The trap this exists for: a word that means "write" in the middle of
        a sentence is not an instruction to write the sentence down."""
        self.assertAsked("Sonra sana yazarım, şimdi toplantıdayım")
        self.assertAsked("Yazılım ekibine haber ver")
        self.assertAsked("Bu notu Ahmet'e ilet")

    def test_the_dotted_and_dotless_i_are_the_same_word_here(self):
        """Turkish has two i's and a transcriber picks between them by ear. If
        that decided whether a command was heard, half of them would not be."""
        self.assertEqual(router.fold("YAZI"), router.fold("yazı"))
        self.assertEqual(router.fold("Dikte Et"), "dikte et")
        self.assertEqual(router.fold("METNE DÖK"), "metne dok")

    def test_something_added_by_hand_is_honoured(self):
        mode, payload = router.route("kaydet bunu bir fikir", "kaydet")
        self.assertEqual(mode, router.DICTATE)
        self.assertEqual(payload, "bir fikir")

    def test_nothing_said_is_not_a_dictation(self):
        self.assertEqual(router.route(""), (router.ASK, ""))
        self.assertEqual(router.route("   "), (router.ASK, ""))

    def test_the_longest_matching_opening_wins(self):
        """"not al" has to be tried before anything shorter would swallow it."""
        mode, payload = router.route("not al süt almayı unutma")
        self.assertEqual(mode, router.DICTATE)
        self.assertEqual(payload, "süt almayı unutma")


class WhatIsWorthSaying(unittest.TestCase):
    def test_a_code_block_is_not_read_out(self):
        spoken = tts.speakable("Tamam.\n```python\nprint('x')\n```\nBitti.")
        self.assertNotIn("print", spoken)
        self.assertIn("Tamam", spoken)
        self.assertIn("Bitti", spoken)

    def test_a_link_is_not_read_out(self):
        self.assertNotIn("http", tts.speakable("Bak: https://example.com/a/b şuraya."))

    def test_the_punctuation_that_makes_a_heading_is_dropped(self):
        self.assertNotIn("#", tts.speakable("## Başlık\n**kalın** _eğik_"))

    def test_it_is_split_into_sentences_so_it_can_start_sooner(self):
        parts = tts.sentences("Bir. İki! Üç? Dört.")
        self.assertEqual(len(parts), 4)

    def test_a_recital_is_cut_short(self):
        parts = tts.sentences("Cümle. " * 400)
        self.assertLessEqual(sum(len(p) for p in parts), tts.MAX_SPOKEN + 20)

    def test_nothing_to_say_is_no_sentences(self):
        self.assertEqual(tts.sentences(""), [])
        self.assertEqual(tts.sentences("```only code```"), [])

    def test_speed_runs_the_opposite_way_to_duration(self):
        class Conf(dict):
            pass
        voice = tts.Voice(Conf({"tts_speed": 2.0, "tts_enabled": True}), ".")
        fast = voice._length_scale()
        voice.conf["tts_speed"] = 0.5
        self.assertGreater(voice._length_scale(), fast)


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


class FakeVoice:
    def __init__(self, works=True):
        self.finished = FakeSignal()
        self.failed = FakeSignal()
        self.said = []
        self.stopped = 0
        self.works = works

    def say(self, text):
        self.said.append(text)
        return self.works

    def stop(self):
        self.stopped += 1


class Conf(dict):
    pass


def a_conf(**changes):
    conf = Conf({"mic_target": "", "speech_margin_db": 10.0,
                 "silence_db": -55.0, "min_voiced_seconds": 0.3,
                 "dictation_openings": ""})
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
    def setUp(self):
        self.conf = a_conf()
        self.recorder = FakeRecorder()
        self.pipeline = FakePipeline()
        self.voice = FakeVoice()
        self.zeno = conversation.Conversation(
            self.conf, self.recorder, self.pipeline, self.voice)
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

    def test_being_called_opens_the_microphone_and_listens(self):
        self.assertTrue(self.zeno.wake())
        self.assertEqual(self.zeno.state, conversation.LISTENING)
        self.assertEqual(self.recorder.started, 1)

    def test_being_called_twice_over_is_ignored(self):
        self.zeno.wake()
        self.assertFalse(self.zeno.wake())
        self.assertEqual(self.recorder.started, 1)

    def test_called_and_then_nothing_gives_up_quietly(self):
        """A name misheard off the television costs a moment of listening and
        nothing else — no answer, no bubble, no recording kept."""
        self.zeno.wake()
        self.recorder.rms = quiet_rms(1.0)
        self.zeno._began = time.monotonic() - conversation.PATIENCE_SECONDS - 0.1
        self.zeno._look()
        self.assertEqual(self.zeno.state, conversation.WAITING)
        self.assertEqual(self.recorder.cancelled, 1)
        self.assertEqual(self.answers, [])

    def test_the_microphones_own_hiss_is_not_somebody_talking(self):
        """The bug this guards: relative loudness alone is met by the spread of
        a quiet room's own noise, and it sat there recording nothing for ever."""
        import random
        random.seed(3)
        blocks = int(6.0 / (audio.CHUNK_FRAMES / audio.RATE))
        self.zeno.wake()
        # Hiss: quiet, but with the ragged spread real microphone noise has.
        self.recorder.rms = [abs(random.gauss(0, 0.00035)) + 1e-5
                             for _ in range(blocks)]
        self.zeno._began = time.monotonic() - conversation.PATIENCE_SECONDS - 0.1
        self.zeno._look()
        self.assertEqual(self.zeno.state, conversation.WAITING)
        self.assertEqual(self.recorder.cancelled, 1)

    def test_a_pause_to_find_a_word_does_not_end_the_instruction(self):
        self.zeno.wake()
        self.recorder.rms = loud_rms(1.0)
        self.zeno._look()
        self.assertEqual(self.zeno.state, conversation.LISTENING)
        # Quiet, but not for as long as it takes to mean "finished".
        self.recorder.rms = loud_rms(1.0) + quiet_rms(0.4)
        self.zeno._spoke_at = time.monotonic() - (conversation.SETTLE_SECONDS - 0.3)
        self.zeno._look()
        self.assertEqual(self.zeno.state, conversation.LISTENING)

    def test_settling_into_silence_ends_it(self):
        self.zeno.wake()
        self.recorder.rms = loud_rms(1.0)
        self.zeno._look()
        # Quiet at the end, and quiet for long enough to mean finished.
        self.recorder.rms = loud_rms(1.0) + quiet_rms(0.5)
        self.zeno._spoke_at = time.monotonic() - conversation.SETTLE_SECONDS - 0.1
        self.zeno._look()
        self.assertEqual(self.zeno.state, conversation.WORKING)
        self.assertEqual(self.recorder.stopped, 1)

    def test_talking_for_far_too_long_ends_it_too(self):
        self.zeno.wake()
        self.recorder.rms = loud_rms(1.0)
        self.zeno._began = time.monotonic() - conversation.LIMIT_SECONDS - 1
        self.zeno._look()
        self.assertEqual(self.zeno.state, conversation.WORKING)

    def test_the_recording_is_transcribed_without_being_pasted(self):
        """What was said has to be read before anybody can tell whether it was
        meant to be pasted at all."""
        self.zeno.wake()
        self.zeno.take("clip.wav", 2.0, [])
        self.assertEqual(len(self.pipeline.runs), 1)
        self.assertFalse(self.pipeline.runs[0]["ask"])
        self.assertFalse(self.pipeline.runs[0]["paste"])

    def test_an_instruction_to_write_ends_in_a_paste(self):
        self.zeno.wake()
        self.zeno.take("clip.wav", 2.0, [])
        self.pipeline.finished.emit("ham", "Yaz: bugün üç karar aldık.", "")
        self.assertEqual(self.pasted, ["bugün üç karar aldık."])
        self.assertEqual(self.asked, [])
        self.assertEqual(self.zeno.state, conversation.WAITING)

    def test_anything_else_goes_to_the_agent(self):
        self.zeno.wake()
        self.zeno.take("clip.wav", 2.0, [])
        self.pipeline.finished.emit("ham", "Takvime toplantı ekle", "")
        self.assertEqual(self.asked, ["Takvime toplantı ekle"])
        self.assertEqual(self.pasted, [])

    def test_told_to_write_with_nothing_to_write_it_waits_for_the_words(self):
        self.zeno.wake()
        self.zeno.take("clip.wav", 2.0, [])
        self.pipeline.finished.emit("ham", "Dikte et", "")
        self.assertTrue(self.zeno.pending_dictation)
        self.assertEqual(self.pasted, [])
        self.assertTrue(self.voice.said)
        # The next thing said is the note, whatever it happens to start with.
        self.pipeline.finished.emit("ham", "Takvime toplantı ekle", "")
        self.assertEqual(self.pasted, ["Takvime toplantı ekle"])
        self.assertFalse(self.zeno.pending_dictation)

    def test_the_answer_is_spoken_and_shown(self):
        self.zeno.wake()
        self.zeno._set_state(conversation.WORKING)
        self.zeno.answer("Perşembe üçe eklendi.")
        self.assertEqual(self.voice.said, ["Perşembe üçe eklendi."])
        self.assertIn("Perşembe üçe eklendi.", self.answers)
        self.assertEqual(self.zeno.state, conversation.ANSWERING)
        self.voice.finished.emit()
        self.assertEqual(self.zeno.state, conversation.WAITING)

    def test_with_no_voice_the_answer_is_still_shown(self):
        self.voice.works = False
        self.zeno.wake()
        self.zeno._set_state(conversation.WORKING)
        self.zeno.answer("Perşembe üçe eklendi.")
        self.assertIn("Perşembe üçe eklendi.", self.answers)
        self.assertEqual(self.zeno.state, conversation.WAITING)

    def test_a_transcription_that_came_back_empty_ends_it(self):
        self.zeno.wake()
        self.zeno.take("clip.wav", 2.0, [])
        self.pipeline.finished.emit("", "", "")
        self.assertEqual(self.zeno.state, conversation.WAITING)
        self.assertEqual(self.pasted, [])
        self.assertEqual(self.asked, [])

    def test_a_failure_is_reported_and_does_not_leave_it_stuck(self):
        self.zeno.wake()
        self.zeno.take("clip.wav", 2.0, [])
        seen = []
        self.zeno.failed.connect(seen.append)
        self.pipeline.failed.emit("mikrofon yok")
        self.assertEqual(seen, ["mikrofon yok"])
        self.assertEqual(self.zeno.state, conversation.WAITING)
        self.assertFalse(self.zeno.pending_dictation)

    def test_giving_up_stops_everything_it_started(self):
        self.zeno.wake()
        self.zeno.pending_dictation = True
        self.zeno.cancel()
        self.assertEqual(self.zeno.state, conversation.WAITING)
        self.assertEqual(self.recorder.cancelled, 1)
        self.assertEqual(self.voice.stopped, 1)
        self.assertFalse(self.zeno.pending_dictation)

    def test_a_stage_from_the_chain_is_passed_on(self):
        seen = []
        self.zeno.stage.connect(seen.append)
        self.pipeline.stage.emit("Yazıya çevriliyor…")
        self.assertEqual(seen, ["Yazıya çevriliyor…"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
