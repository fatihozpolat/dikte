#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for the control, the band, and reading a sentence back live.

There is a QApplication here because the widgets are real ones, but nothing is
shown on a screen and nothing is recorded: the band is asked what it holds
rather than photographed, the control is pressed by hand, and the live preview
is driven by a recorder and a transcriber that are stood in for. What is being
checked is the part that would be wrong without anybody noticing — which lobe a
press lands on, how long something stays up, where the two windows land on a
screen of a given size, and the rules the preview obeys about when it may run.

    python3 -m unittest test_companion -v
"""

import time
import unittest
import unittest.mock

from PyQt6.QtCore import QPointF, QRect
from PyQt6.QtGui import QPainter, QPixmap
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication

import audio
import companion
import live

_app = QApplication.instance() or QApplication([])


class HowLongItStays(unittest.TestCase):
    def test_a_short_line_still_gets_the_floor(self):
        self.assertEqual(companion.bubble_seconds("Tamam"), 3.0)
        self.assertEqual(companion.bubble_seconds(""), 3.0)

    def test_a_long_one_is_capped(self):
        self.assertEqual(companion.bubble_seconds("x" * 5000), 30.0)

    def test_in_between_it_follows_the_length(self):
        short = companion.bubble_seconds("x" * 60)
        long = companion.bubble_seconds("x" * 200)
        self.assertLess(short, long)
        self.assertTrue(3.0 < short < 30.0)

    def test_it_never_leaves_the_floor_and_ceiling(self):
        for length in (0, 1, 5, 40, 120, 400, 1200):
            seconds = companion.bubble_seconds("x" * length)
            self.assertGreaterEqual(seconds, 3.0, length)
            self.assertLessEqual(seconds, 30.0, length)

    def test_the_two_ends_can_be_moved(self):
        self.assertEqual(companion.bubble_seconds("hi", floor=5.0, ceiling=8.0), 5.0)
        self.assertEqual(
            companion.bubble_seconds("x" * 400, floor=5.0, ceiling=8.0), 8.0)

    def test_a_reading_pace_a_person_could_keep_up_with(self):
        seconds = companion.bubble_seconds("x" * 100)
        self.assertTrue(6.0 < seconds < 14.0, seconds)


class TwoLobes(unittest.TestCase):
    """Which half of the control a press lands on.

    The one thing here that must never be wrong. Writing and asking do opposite
    things with the same sentence, and getting the half wrong means a note sent
    to an agent or a question typed into a document.
    """

    def setUp(self):
        self.pill = companion.Pill(52)
        self.addCleanup(self.pill.deleteLater)

    def middle(self, fraction):
        pad = int(self.pill._lobe * 0.22)
        return QPointF(pad + self.pill._lobe * 2 * fraction, pad + self.pill._lobe / 2)

    def test_the_left_half_writes_and_the_right_half_asks(self):
        self.assertEqual(self.pill._lobe_at(self.middle(0.25)), companion.WRITE)
        self.assertEqual(self.pill._lobe_at(self.middle(0.75)), companion.ASK)

    def test_the_line_between_them_is_the_middle(self):
        pad = int(self.pill._lobe * 0.22)
        just_left = QPointF(pad + self.pill._lobe - 1, pad + self.pill._lobe / 2)
        just_right = QPointF(pad + self.pill._lobe + 1, pad + self.pill._lobe / 2)
        self.assertEqual(self.pill._lobe_at(just_left), companion.WRITE)
        self.assertEqual(self.pill._lobe_at(just_right), companion.ASK)

    def test_the_padding_around_it_is_not_either_of_them(self):
        self.assertIsNone(self.pill._lobe_at(QPointF(1, 1)))
        self.assertIsNone(
            self.pill._lobe_at(QPointF(self.pill.width() - 1, self.pill.height() - 1)))

    def test_it_grows_and_shrinks_with_the_setting(self):
        for lobe in (30, 52, 96):
            self.pill.set_lobe(lobe)
            self.assertGreater(self.pill.width(), self.pill.height())
            self.assertEqual(self.pill._lobe_at(self.middle(0.25)), companion.WRITE)
            self.assertEqual(self.pill._lobe_at(self.middle(0.75)), companion.ASK)

    def test_it_is_never_shrunk_to_nothing(self):
        self.pill.set_lobe(2)
        self.assertGreaterEqual(self.pill._lobe, 28)


class PillStates(unittest.TestCase):
    def setUp(self):
        self.pill = companion.Pill(52)
        self.addCleanup(self.pill.deleteLater)

    def test_it_starts_waiting_with_neither_half_lit(self):
        self.assertEqual(self.pill.state, companion.IDLE)
        self.assertIsNone(self.pill.active)

    def test_the_working_half_is_remembered(self):
        self.pill.set_state(companion.LISTENING, companion.ASK)
        self.assertEqual(self.pill.active, companion.ASK)

    def test_going_back_to_waiting_puts_both_halves_out(self):
        self.pill.set_state(companion.LISTENING, companion.WRITE)
        self.pill.set_state(companion.IDLE)
        self.assertIsNone(self.pill.active)

    def test_the_busy_states_are_the_ones_that_animate_fast(self):
        for state, interval in ((companion.LISTENING, companion.BUSY_MS),
                                (companion.THINKING, companion.BUSY_MS),
                                (companion.SPEAKING, companion.BUSY_MS),
                                (companion.IDLE, companion.CALM_MS),
                                (companion.ANSWER, companion.CALM_MS)):
            self.pill.set_state(state, companion.WRITE)
            self.assertEqual(self.pill._anim.interval(), interval, state)

    def test_the_level_rises_at_once_and_falls_slowly(self):
        self.pill.set_state(companion.LISTENING, companion.WRITE)
        self.pill.push_level(0.9)
        self.assertAlmostEqual(self.pill._level, 0.9)
        self.pill.push_level(0.0)
        self.assertGreater(self.pill._level, 0.5)
        for _ in range(40):
            self.pill.push_level(0.0)
        self.assertLess(self.pill._level, 0.01)

    def test_a_level_out_of_range_is_brought_back_into_it(self):
        fresh = companion.Pill(40)
        fresh.push_level(9.0)
        self.assertEqual(fresh._level, 1.0)
        fresh.deleteLater()
        other = companion.Pill(40)
        other.push_level(-3.0)
        self.assertEqual(other._level, 0.0)
        other.deleteLater()

    def test_both_lobes_have_a_palette(self):
        self.assertEqual(set(companion.LOBE), {companion.WRITE, companion.ASK})
        for colours in companion.LOBE.values():
            self.assertEqual(len(colours), 3)

    def test_it_paints_at_any_size_and_in_any_state(self):
        for lobe_size in (30, 52, 90):
            for state in (companion.IDLE, companion.LISTENING, companion.THINKING,
                          companion.ANSWER, companion.SPEAKING, companion.ERROR):
                pill = companion.Pill(lobe_size)
                pill.state = state
                pill.active = companion.ASK
                pill.push_level(0.7)
                pixmap = QPixmap(pill.width(), pill.height())
                pixmap.fill(Qt.GlobalColor.transparent)
                painter = QPainter(pixmap)
                pill._paint(painter)
                painter.end()
                pill.deleteLater()
                self.assertFalse(pixmap.isNull())


class TheBand(unittest.TestCase):
    def setUp(self):
        self.stage = companion.Stage()
        self.stage.resize(700, companion.Stage.HEIGHT)
        self.addCleanup(self.stage.deleteLater)

    def test_it_starts_with_nothing_on_it(self):
        self.assertEqual(self.stage.state, companion.IDLE)
        self.assertEqual(self.stage.text, "")

    def test_beginning_clears_what_the_last_one_left(self):
        self.stage.begin(companion.WRITE)
        self.stage.set_text("bir şey")
        self.stage.begin(companion.ASK)
        self.assertEqual(self.stage.text, "")
        self.assertEqual(self.stage.mode, companion.ASK)
        self.assertEqual(self.stage.state, companion.LISTENING)

    def test_the_live_sentence_replaces_itself_rather_than_piling_up(self):
        self.stage.begin(companion.WRITE)
        self.stage.set_text("bugün")
        self.stage.set_text("bugün kubernetes")
        self.assertEqual(self.stage.text, "bugün kubernetes")

    def test_an_outcome_stays_for_as_long_as_it_takes_to_read(self):
        self.stage.begin(companion.ASK)
        self.stage.finish(companion.ANSWER, "Perşembe üçe eklendi.")
        self.assertEqual(self.stage.state, companion.ANSWER)
        self.assertTrue(self.stage._hide.isActive())
        self.assertGreater(self.stage._hide.interval(), 3000)

    def test_being_dismissed_takes_it_off_the_screen(self):
        self.stage.begin(companion.WRITE)
        self.stage.dismiss()
        self.assertEqual(self.stage.state, companion.IDLE)
        self.assertFalse(self.stage.showing)

    def test_the_ribbon_remembers_a_fixed_stretch_of_readings(self):
        self.stage.begin(companion.WRITE)
        for _ in range(300):
            self.stage.push_level(0.5)
        self.assertEqual(len(self.stage.levels), companion.WAVE_POINTS)

    def test_a_reading_out_of_range_is_brought_back_into_it(self):
        self.stage.push_level(4.0)
        self.stage.push_level(-1.0)
        self.assertTrue(all(0.0 <= value <= 1.0 for value in self.stage.levels))

    def test_the_words_sit_on_a_plate_of_their_own(self):
        """Without one they are white paint on whatever is behind them, and on
        a pale desktop the band was measured unreadable."""
        panel = self.stage._panel()
        self.assertGreater(panel.width(), 0)
        self.assertGreater(panel.height(), 0)
        self.assertLess(panel.height(), self.stage.height())

    def test_it_paints_in_every_state_without_falling_over(self):
        for state in (companion.LISTENING, companion.THINKING, companion.ANSWER,
                      companion.SPEAKING, companion.WARNING, companion.ERROR):
            self.stage.state = state
            self.stage.text = "bir cümle " * 6
            self.stage.note = "Yazıya çevriliyor…"
            self.stage._born = time.monotonic() - 1
            pixmap = self.stage.grab()
            self.assertFalse(pixmap.isNull(), state)


class Placement(unittest.TestCase):
    class _Screen:
        def __init__(self, rect):
            self._rect = rect

        def availableGeometry(self):
            return self._rect

    def setUp(self):
        self.area = QRect(0, 0, 1920, 1080)
        patch = unittest.mock.patch.object(
            companion.QApplication, "primaryScreen",
            staticmethod(lambda: Placement._Screen(self.area)))
        patch.start()
        self.addCleanup(patch.stop)
        self.conf = {
            "companion_size": 104, "companion_side": "right",
            "companion_offset": 0, "companion_bubble_min": 3,
            "companion_bubble_max": 30,
        }
        self.mate = companion.Companion(self.conf)
        self.addCleanup(self.mate.pill.deleteLater)
        self.addCleanup(self.mate.stage.deleteLater)

    def test_the_control_sits_against_the_right_edge(self):
        self.mate.place()
        self.assertEqual(self.mate.pill.geometry().right(),
                         self.area.right() - companion.MARGIN)

    def test_the_left_edge_is_the_mirror_of_it(self):
        self.conf["companion_side"] = "left"
        self.mate.apply(self.conf)
        self.assertEqual(self.mate.pill.geometry().left(),
                         self.area.left() + companion.MARGIN)

    def test_a_remembered_position_is_used(self):
        self.conf["companion_offset"] = 400
        self.mate.apply(self.conf)
        self.assertEqual(self.mate.pill.y(), 400)

    def test_a_position_off_the_screen_is_pulled_back_on(self):
        self.conf["companion_offset"] = 99999
        self.mate.apply(self.conf)
        self.assertLessEqual(self.mate.pill.geometry().bottom(), self.area.bottom())

    def test_the_band_is_across_the_middle(self):
        self.mate.place()
        band = self.mate.stage.geometry()
        self.assertLessEqual(abs(band.center().x() - self.area.center().x()), 2)
        self.assertLessEqual(abs(band.center().y() - self.area.center().y()), 2)

    def test_the_size_setting_reaches_the_control(self):
        self.conf["companion_size"] = 72
        self.mate.apply(self.conf)
        self.assertEqual(self.mate.pill._lobe, 36)


class Reporting(unittest.TestCase):
    def setUp(self):
        self.conf = {
            "companion_size": 104, "companion_side": "right",
            "companion_offset": 0, "companion_bubble_min": 3,
            "companion_bubble_max": 30,
        }
        self.mate = companion.Companion(self.conf)
        self.mate._visible = True          # as if it had been shown
        self.addCleanup(self.mate.pill.deleteLater)
        self.addCleanup(self.mate.stage.deleteLater)

    def test_writing_lights_the_writing_half(self):
        self.mate.show_recording(asking=False)
        self.assertEqual(self.mate.pill.active, companion.WRITE)
        self.assertEqual(self.mate.stage.mode, companion.WRITE)

    def test_asking_lights_the_asking_half(self):
        self.mate.show_recording(asking=True)
        self.assertEqual(self.mate.pill.active, companion.ASK)
        self.assertEqual(self.mate.stage.mode, companion.ASK)

    def test_working_turns_it_to_thinking_and_says_what_it_is_doing(self):
        self.mate.show_busy("Yazıya çevriliyor…")
        self.assertEqual(self.mate.pill.state, companion.THINKING)
        self.assertEqual(self.mate.stage.note, "Yazıya çevriliyor…")

    def test_what_it_heard_replaces_what_it_was_hearing(self):
        self.mate.live("bugün kuber")
        self.assertEqual(self.mate.stage.text, "bugün kuber")
        self.mate.heard("Bugün Kubernetes.")
        self.assertEqual(self.mate.stage.text, "Bugün Kubernetes.")

    def test_an_answer_gets_its_own_colour(self):
        self.mate.say("Takvime eklendi.", "agent")
        self.assertEqual(self.mate.stage.state, companion.ANSWER)
        self.assertEqual(self.mate.stage.text, "Takvime eklendi.")

    def test_an_error_is_shown_and_turns_it_red(self):
        self.mate.show_error("Bir şey oldu")
        self.assertEqual(self.mate.pill.state, companion.ERROR)
        self.assertEqual(self.mate.stage.state, companion.ERROR)

    def test_it_goes_back_to_waiting_after_an_outcome(self):
        self.mate.show_done("bitti")
        self.assertEqual(self.mate.pill.state, companion.ANSWER)
        self.mate._rest()
        self.assertEqual(self.mate.pill.state, companion.IDLE)

    def test_it_says_nothing_when_there_is_nothing_to_say(self):
        self.mate.say("")
        self.mate.stage_note("")
        self.mate.live("")
        self.assertEqual(self.mate.stage.text, "")
        self.assertEqual(self.mate.stage.note, "")

    def test_nothing_is_shown_at_all_while_it_is_switched_off(self):
        self.mate._visible = False
        self.mate.live("bir şey")
        self.mate.heard("bir şey")
        self.assertEqual(self.mate.stage.text, "")

    def test_pressing_a_lobe_is_passed_straight_on(self):
        asked = []
        self.mate.asked.connect(asked.append)
        self.mate.pill.pressed.emit(companion.ASK)
        self.assertEqual(asked, [companion.ASK])


# --- reading the sentence back while it is spoken -------------------------

class FakeRecorder:
    def __init__(self, seconds=0.0, loud=True):
        self.set(seconds, loud)

    def set(self, seconds, loud=True):
        frames = int(seconds * audio.RATE)
        self.pcm = b"\x00\x00" * frames
        blocks = max(1, frames // audio.CHUNK_FRAMES)
        self.rms = ([0.0006] * blocks if not loud
                    else [0.0006 if i % 3 else 0.09 for i in range(blocks)])

    def snapshot(self):
        return self.pcm, list(self.rms)


class FakeConf(dict):
    def transcribe_target(self):
        return "target"


def a_conf(**changes):
    conf = FakeConf({
        "companion_enabled": True, "companion_live": True,
        "transcribe_provider": "local", "language": "tr",
        "transcribe_prompt": "", "silence_db": -55.0,
        "speech_margin_db": 10.0, "min_voiced_seconds": 0.3,
    })
    conf.update(changes)
    return conf


class LiveRules(unittest.TestCase):
    def test_it_wants_to_run_on_a_local_setup(self):
        self.assertTrue(live.wanted(a_conf()))

    def test_it_stays_out_of_the_way_of_a_paid_provider(self):
        self.assertFalse(live.wanted(a_conf(transcribe_provider="openai")))
        self.assertFalse(live.wanted(a_conf(transcribe_provider="openrouter")))

    def test_turning_it_off_turns_it_off(self):
        self.assertFalse(live.wanted(a_conf(companion_live=False)))

    def test_no_character_means_nothing_to_show_it_in(self):
        self.assertFalse(live.wanted(a_conf(companion_enabled=False)))


class LivePreview(unittest.TestCase):
    def setUp(self):
        self.conf = a_conf()
        self.recorder = FakeRecorder(4.0)
        self.transcriber = live.LiveTranscriber(self.conf, self.recorder)
        self.addCleanup(self.transcriber.stop)
        self.seen = []
        self.transcriber.partial.connect(self.seen.append)
        self.calls = []

        def transcribe(_target, path, language=None, prompt=None):
            self.calls.append(path)
            return "  duyduğu şey  "

        self.patches = [
            unittest.mock.patch.object(live.api, "transcribe", transcribe),
            unittest.mock.patch.object(live.whispercpp, "running", lambda: True),
        ]
        for patch in self.patches:
            patch.start()
            self.addCleanup(patch.stop)

    def drain(self):
        for _ in range(200):
            _app.processEvents()
            if not self.transcriber._busy and (self.seen or self.calls):
                break
            time.sleep(0.01)
        _app.processEvents()

    def test_it_reads_back_what_was_said_so_far(self):
        self.transcriber.start()
        self.transcriber._look()
        self.drain()
        self.assertEqual(self.seen, ["duyduğu şey"])

    def test_it_will_not_start_without_a_server_already_up(self):
        with unittest.mock.patch.object(live.whispercpp, "running", lambda: False):
            self.assertFalse(self.transcriber.start())

    def test_it_will_not_start_where_it_has_no_business_running(self):
        self.conf["transcribe_provider"] = "openai"
        self.assertFalse(self.transcriber.start())

    def test_too_little_audio_is_left_alone(self):
        self.recorder.set(0.4)
        self.transcriber.start()
        self.transcriber._look()
        self.drain()
        self.assertEqual(self.calls, [])

    def test_a_silent_room_is_never_sent(self):
        self.recorder.set(6.0, loud=False)
        self.transcriber.start()
        self.transcriber._look()
        self.drain()
        self.assertEqual(self.calls, [])

    def test_a_very_long_recording_stops_being_previewed(self):
        self.recorder.set(live.MAX_SECONDS + 10)
        self.transcriber.start()
        self.transcriber._look()
        self.assertEqual(self.calls, [])
        self.assertFalse(self.transcriber.running)

    def test_two_readings_never_run_at_once(self):
        self.transcriber.start()
        self.transcriber._busy = True
        self.transcriber._look()
        self.assertEqual(self.calls, [])

    def test_an_answer_that_arrives_after_the_stop_is_dropped(self):
        self.transcriber.start()
        run = self.transcriber._run
        self.transcriber.stop()
        self.transcriber._read(self.recorder.pcm, 4.0, run)
        self.assertEqual(self.seen, [])

    def test_the_same_sentence_twice_is_only_reported_once(self):
        self.transcriber.start()
        self.transcriber._look()
        self.drain()
        self.transcriber._look()
        self.drain()
        self.assertEqual(self.seen, ["duyduğu şey"])
        self.assertEqual(len(self.calls), 2)

    def test_an_invented_sentence_is_not_shown(self):
        with unittest.mock.patch.object(live.api, "transcribe",
                                        lambda *a, **k: "Altyazı M.K."):
            self.recorder.set(3.0)
            self.transcriber.start()
            self.transcriber._look()
            self.drain()
        self.assertEqual(self.seen, [])

    def test_a_failure_is_swallowed_rather_than_shown(self):
        def boom(*_a, **_k):
            raise live.api.ApiError("no")

        with unittest.mock.patch.object(live.api, "transcribe", boom):
            self.transcriber.start()
            self.transcriber._look()
            self.drain()
        self.assertEqual(self.seen, [])
        self.assertFalse(self.transcriber._busy)

    def test_it_writes_over_one_file_rather_than_one_per_second(self):
        self.transcriber.start()
        self.transcriber._look()
        self.drain()
        self.transcriber._look()
        self.drain()
        self.assertEqual(len(set(self.calls)), 1)


class Snapshot(unittest.TestCase):
    def test_it_comes_back_whole_and_changes_nothing(self):
        recorder = audio.Recorder()
        recorder._buffer = bytearray(b"\x01\x02" * 100)
        recorder._rms = [0.1, 0.2]
        pcm, rms = recorder.snapshot()
        self.assertEqual(len(pcm), 200)
        self.assertEqual(rms, [0.1, 0.2])
        rms.append(9.9)
        self.assertEqual(recorder._rms, [0.1, 0.2])

    def test_an_empty_recorder_is_not_an_error(self):
        pcm, rms = audio.Recorder().snapshot()
        self.assertEqual(pcm, b"")
        self.assertEqual(rms, [])


class Wiring(unittest.TestCase):
    """The real application object, driven by hand."""

    @classmethod
    def setUpClass(cls):
        import pathlib
        import shutil
        import tempfile

        import config as cfg
        import dikte as app_module

        cls.tmp = tempfile.mkdtemp(prefix="dikte-wiring-")
        cls.patches = [
            unittest.mock.patch.object(cfg, "CONFIG_DIR", pathlib.Path(cls.tmp)),
            unittest.mock.patch.object(
                cfg, "CONFIG_FILE", pathlib.Path(cls.tmp) / "config.json"),
            unittest.mock.patch.object(app_module.whispercpp, "sweep", lambda: False),
            unittest.mock.patch.object(app_module.audio, "warm_devices", lambda: None),
        ]
        for patch in cls.patches:
            patch.start()
        cls.app_module = app_module
        cls.tmpdir = cls.tmp
        cls._rmtree = shutil.rmtree

    @classmethod
    def tearDownClass(cls):
        for patch in cls.patches:
            patch.stop()
        cls._rmtree(cls.tmpdir, ignore_errors=True)

    def setUp(self):
        self.dikte = self.app_module.Dikte(_app)
        self.dikte.conf["evdev_hotkey"] = False
        self.dikte.conf["local_preload"] = False
        self.dikte.conf["companion_enabled"] = True
        self.dikte.conf["companion_replaces_overlay"] = True
        self.dikte._apply_companion()
        self.addCleanup(self.dikte.shutdown)

    def test_the_control_is_up_and_the_corner_has_stood_down(self):
        self.assertTrue(self.dikte.companion.visible)
        self.assertFalse(self.dikte.overlay.enabled)

    def test_turning_it_off_gives_the_corner_its_voice_back(self):
        self.dikte.conf["companion_enabled"] = False
        self.dikte._apply_companion()
        self.assertFalse(self.dikte.companion.visible)
        self.assertTrue(self.dikte.overlay.enabled)

    def test_a_disabled_corner_paints_nothing_but_still_takes_the_calls(self):
        self.dikte.overlay.show_busy("bir şey")
        self.assertFalse(self.dikte.overlay.showing)

    def test_pressing_the_writing_lobe_starts_a_writing_job(self):
        started = []
        self.dikte.talk_to_zeno = lambda mode=None: started.append(mode)
        self.dikte._companion_asked(companion.WRITE)
        self.assertEqual(started, [companion.WRITE])

    def test_pressing_the_asking_lobe_starts_an_asking_job(self):
        started = []
        self.dikte.talk_to_zeno = lambda mode=None: started.append(mode)
        self.dikte._companion_asked(companion.ASK)
        self.assertEqual(started, [companion.ASK])

    def test_pressing_either_lobe_mid_job_calls_it_off(self):
        """Hunting for the right half of a button to stop it with would be
        nearly as bad as having no way to stop it."""
        cancelled = []
        self.dikte.zeno.cancel = lambda: cancelled.append(True)
        type(self.dikte.zeno).busy = property(lambda _self: True)
        self.addCleanup(lambda: setattr(
            type(self.dikte.zeno), "busy",
            property(lambda s: s.state != __import__("conversation").WAITING)))
        self.dikte._companion_asked(companion.WRITE)
        self.dikte._companion_asked(companion.ASK)
        self.assertEqual(cancelled, [True, True])

    def test_a_finished_dictation_reaches_the_band(self):
        self.dikte.pipeline.finished.emit("ham", "Temiz cümle.", "")
        self.assertEqual(self.dikte.companion.stage.text, "Temiz cümle.")

    def test_a_stage_from_the_pipeline_reaches_the_band(self):
        self.dikte.pipeline.stage.emit("Yazıya çevriliyor…")
        self.assertEqual(self.dikte.companion.stage.note, "Yazıya çevriliyor…")
        self.assertEqual(self.dikte.companion.pill.state, companion.THINKING)

    def test_a_failure_turns_it_red_and_says_why(self):
        self.dikte.pipeline.failed.emit("Mikrofon bulunamadı")
        self.assertEqual(self.dikte.companion.pill.state, companion.ERROR)

    def test_the_microphone_level_reaches_both_of_them(self):
        self.dikte.companion.pill.set_state(companion.LISTENING, companion.WRITE)
        self.dikte.recorder.level.emit(0.8)
        self.assertGreater(self.dikte.companion.pill._level, 0.5)
        self.assertGreater(max(self.dikte.companion.stage.levels), 0.5)

    def test_a_live_reading_reaches_the_band(self):
        self.dikte.live.partial.emit("yarım cümle")
        self.assertEqual(self.dikte.companion.stage.text, "yarım cümle")

    def test_dragging_it_is_remembered(self):
        self.dikte.companion.moved.emit(10, 640)
        self.assertEqual(self.dikte.conf["companion_offset"], 640)

    def test_a_shortcut_somebody_else_holds_does_not_take_startup_down(self):
        self.dikte.evdev.failed.emit("Ctrl+Space is already taken")
        self.assertEqual(self.dikte.companion.pill.state, companion.ERROR)

    def test_shutting_down_takes_it_off_the_screen(self):
        self.dikte.shutdown()
        self.assertFalse(self.dikte.companion.visible)
        self.assertFalse(self.dikte.companion.pill.isVisible())
        self.assertFalse(self.dikte.live.running)


if __name__ == "__main__":
    unittest.main(verbosity=2)
