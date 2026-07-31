#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for the character, its bubbles, and reading a sentence back live.

There is a QApplication here because the widgets are real ones, but nothing is
shown on a screen and nothing is recorded: the bubbles are asked what they hold
rather than photographed, and the live preview is driven by a recorder and a
transcriber that are stood in for. What is actually being checked is the part
that would be wrong without noticing — how long a bubble stays, which bubble
replaces which, where the two windows land on a screen of a given size, and the
rules the preview obeys about when it may run at all.

    python3 -m unittest test_companion -v
"""

import time
import unittest
import unittest.mock

from PyQt6.QtWidgets import QApplication

import audio
import companion
import live

_app = QApplication.instance() or QApplication([])


class BubbleLength(unittest.TestCase):
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
        self.assertTrue(3.0 < long < 30.0)

    def test_it_never_leaves_the_floor_and_ceiling(self):
        for length in (0, 1, 5, 40, 120, 400, 1200):
            seconds = companion.bubble_seconds("x" * length)
            self.assertGreaterEqual(seconds, 3.0, length)
            self.assertLessEqual(seconds, 30.0, length)

    def test_the_two_ends_can_be_moved(self):
        self.assertEqual(companion.bubble_seconds("hi", floor=5.0, ceiling=8.0), 5.0)
        self.assertEqual(companion.bubble_seconds("x" * 400, floor=5.0, ceiling=8.0), 8.0)

    def test_a_reading_pace_a_person_could_keep_up_with(self):
        # A sentence of about a hundred characters is a couple of seconds to
        # read; anything under four would be a bubble that flashes past.
        seconds = companion.bubble_seconds("x" * 100)
        self.assertTrue(6.0 < seconds < 14.0, seconds)


class BubbleStack(unittest.TestCase):
    def setUp(self):
        self.bubbles = companion.Bubbles()
        self.addCleanup(self.bubbles.deleteLater)

    def texts(self, kind=None):
        return [s.text for s in self.bubbles._said
                if s.closing is None and (kind is None or s.kind == kind)]

    def test_saying_nothing_adds_nothing(self):
        self.bubbles.say("")
        self.bubbles.say("   ")
        self.bubbles.say(None)
        self.assertEqual(self.texts(), [])

    def test_the_newest_is_last_because_last_is_nearest_the_sphere(self):
        self.bubbles.say("bir")
        self.bubbles.say("iki")
        self.assertEqual(self.texts(), ["bir", "iki"])

    def test_a_live_line_is_replaced_rather_than_stacked(self):
        self.bubbles.live("bugün")
        self.bubbles.live("bugün kubernetes")
        self.bubbles.live("bugün kubernetes üzerinde")
        self.assertEqual(self.texts(), ["bugün kubernetes üzerinde"])

    def test_a_live_line_has_no_lifetime_of_its_own(self):
        self.bubbles.live("yarım cümle")
        said = self.bubbles._said[-1]
        self.assertIsNone(said.seconds)
        said.born = time.monotonic() - 600
        self.assertFalse(said.expired())

    def test_the_finished_sentence_takes_the_live_one_away(self):
        self.bubbles.live("bugün kuber")
        self.bubbles.drop_live()
        self.bubbles.say("Bugün Kubernetes üzerinde çalıştım.", "heard")
        self.assertEqual(self.texts("live"), [])
        self.assertEqual(self.texts("heard"), ["Bugün Kubernetes üzerinde çalıştım."])

    def test_a_stack_that_grows_drops_its_oldest(self):
        for index in range(9):
            self.bubbles.say(f"satır {index}")
        self.assertEqual(self.texts(), [f"satır {i}" for i in range(4, 9)])

    def test_an_expired_bubble_is_swept_away(self):
        self.bubbles.say("kısa", seconds=0.01)
        self.bubbles._said[0].born = time.monotonic() - 5
        self.bubbles._sweep()
        self.assertEqual(self.texts(), [])

    def test_a_bubble_arrives_and_leaves_rather_than_blinking(self):
        said = companion._Said("merhaba", "heard", 10.0)
        said.born = time.monotonic()
        self.assertLess(said.alpha(), 1.0)          # still arriving
        said.born = time.monotonic() - 1.0
        self.assertEqual(said.alpha(), 1.0)         # fully there
        said.close()
        self.assertLessEqual(said.alpha(), 1.0)
        said.closing = time.monotonic() - 10
        self.assertEqual(said.alpha(), 0.0)         # gone
        self.assertTrue(said.expired())

    def test_the_last_progress_line_is_the_one_still_showing(self):
        self.bubbles.say("Yazıya çevriliyor…", "stage")
        self.assertEqual(self.bubbles.last_stage(), "Yazıya çevriliyor…")
        self.bubbles.say("Temizleniyor…", "stage")
        self.assertEqual(self.bubbles.last_stage(), "Temizleniyor…")
        self.bubbles.clear()
        self.assertEqual(self.bubbles.last_stage(), "")

    def test_a_taller_bubble_is_given_more_room(self):
        self.bubbles.say("kısa")
        short = self.bubbles._said[-1].height
        self.bubbles.say("çok daha uzun bir cümle " * 12)
        self.assertGreater(self.bubbles._said[-1].height, short)

    def test_the_text_is_never_wider_than_the_window(self):
        self.bubbles.say("uzun " * 60)
        rect = self.bubbles._text_rect(self.bubbles._said[-1])
        self.assertLessEqual(rect.width(), self.bubbles.width())


def _level_after(reading):
    """What a sphere that has heard nothing yet makes of one reading."""
    orb = companion.Orb(64)
    orb.push_level(reading)
    level = orb._level
    orb.deleteLater()
    return level


class OrbStates(unittest.TestCase):
    def setUp(self):
        self.orb = companion.Orb(128)
        self.addCleanup(self.orb.deleteLater)

    def test_it_starts_waiting(self):
        self.assertEqual(self.orb.state, companion.IDLE)

    def test_the_busy_states_are_the_ones_that_animate_fast(self):
        for state, interval in ((companion.LISTENING, companion.BUSY_MS),
                                (companion.THINKING, companion.BUSY_MS),
                                (companion.IDLE, companion.CALM_MS),
                                (companion.ANSWER, companion.CALM_MS),
                                (companion.ERROR, companion.CALM_MS)):
            self.orb.set_state(state)
            self.assertEqual(self.orb._anim.interval(), interval, state)

    def test_the_level_rises_at_once_and_falls_slowly(self):
        self.orb.set_state(companion.LISTENING)
        self.orb.push_level(0.9)
        self.assertAlmostEqual(self.orb._level, 0.9)
        self.orb.push_level(0.0)
        self.assertGreater(self.orb._level, 0.5)     # still coming down
        for _ in range(40):
            self.orb.push_level(0.0)
        self.assertLess(self.orb._level, 0.01)

    def test_a_level_out_of_range_is_brought_back_into_it(self):
        self.orb.push_level(9.0)
        self.assertEqual(self.orb._level, 1.0)
        # A fresh one, because the fall is deliberately slow and would otherwise
        # be what the second reading was measuring.
        self.assertEqual(_level_after(-3.0), 0.0)
        self.assertEqual(_level_after(0.5), 0.5)

    def test_leaving_listening_clears_what_belonged_to_it(self):
        self.orb.set_state(companion.LISTENING)
        self.orb.push_level(0.9)
        self.orb.set_state(companion.THINKING)
        self.assertEqual(self.orb._level, 0.0)
        self.assertEqual(self.orb._ripples, [])

    def test_it_swells_with_the_voice(self):
        self.orb.set_state(companion.LISTENING)
        self.orb.push_level(0.0)
        quiet = self.orb._swell()
        self.orb.push_level(1.0)
        self.assertGreater(self.orb._swell(), quiet)

    def test_every_state_has_a_palette_and_a_churn(self):
        for state in (companion.IDLE, companion.LISTENING, companion.THINKING,
                      companion.ANSWER, companion.WARNING, companion.ERROR):
            self.assertIn(state, companion.PALETTE, state)
            self.assertEqual(len(companion.PALETTE[state]), 4, state)
            self.assertIn(state, companion.CHURN, state)

    def test_it_paints_at_any_size_without_falling_over(self):
        from PyQt6.QtCore import Qt
        from PyQt6.QtGui import QPainter, QPixmap
        for size in (48, 128, 320):
            for state in companion.PALETTE:
                orb = companion.Orb(size)
                orb.state = state
                orb.push_level(0.7)
                pixmap = QPixmap(size, size)
                pixmap.fill(Qt.GlobalColor.transparent)
                painter = QPainter(pixmap)
                orb._paint(painter, size)
                painter.end()
                self.assertFalse(pixmap.isNull())


class Placement(unittest.TestCase):
    """Where the two windows land, on a screen of a known size."""

    class _Screen:
        def __init__(self, rect):
            self._rect = rect

        def availableGeometry(self):
            return self._rect

    def setUp(self):
        from PyQt6.QtCore import QRect
        self.area = QRect(0, 0, 1920, 1080)
        patch = unittest.mock.patch.object(
            companion.QApplication, "primaryScreen",
            staticmethod(lambda: Placement._Screen(self.area)))
        patch.start()
        self.addCleanup(patch.stop)
        self.conf = {
            "companion_size": 128, "companion_side": "right",
            "companion_offset": 0, "companion_bubble_min": 3,
            "companion_bubble_max": 30,
        }
        self.mate = companion.Companion(self.conf)
        self.addCleanup(self.mate.orb.deleteLater)
        self.addCleanup(self.mate.bubbles.deleteLater)

    def test_it_sits_against_the_right_edge_and_centred(self):
        self.mate.place()
        orb = self.mate.orb.geometry()
        self.assertEqual(orb.right(), self.area.right() - companion.MARGIN)
        # Within a pixel: QRect.center() rounds an even height down.
        self.assertLessEqual(abs(orb.center().y() - self.area.center().y()), 1)

    def test_the_left_edge_is_the_mirror_of_it(self):
        self.conf["companion_side"] = "left"
        self.mate.apply(self.conf)
        self.assertEqual(self.mate.orb.geometry().left(),
                         self.area.left() + companion.MARGIN)

    def test_a_remembered_position_is_used(self):
        self.conf["companion_offset"] = 400
        self.mate.apply(self.conf)
        self.assertEqual(self.mate.orb.y(), 400)

    def test_a_position_off_the_screen_is_pulled_back_on(self):
        self.conf["companion_offset"] = 99999
        self.mate.apply(self.conf)
        self.assertLessEqual(self.mate.orb.geometry().bottom(), self.area.bottom())
        self.conf["companion_offset"] = -5000
        self.mate.apply(self.conf)
        self.assertGreaterEqual(self.mate.orb.y(), self.area.top())

    def test_the_bubbles_sit_beside_the_sphere_on_the_correct_side(self):
        self.mate.place()
        self.mate.say("bir cümle")
        self.assertLess(self.mate.bubbles.geometry().right(),
                        self.mate.orb.geometry().left())
        self.conf["companion_side"] = "left"
        self.mate.apply(self.conf)
        self.mate.say("bir cümle")
        self.assertGreater(self.mate.bubbles.geometry().left(),
                           self.mate.orb.geometry().right())

    def test_a_tall_stack_does_not_run_off_the_top(self):
        self.mate.place()
        for index in range(5):
            self.mate.say("uzun bir cümle " * 20 + str(index))
        self.assertGreaterEqual(self.mate.bubbles.y(), self.area.top())
        self.assertLessEqual(self.mate.bubbles.geometry().bottom(),
                             self.area.bottom())

    def test_the_size_setting_reaches_the_sphere(self):
        self.conf["companion_size"] = 96
        self.mate.apply(self.conf)
        self.assertEqual(self.mate.orb.width(), 96)
        self.assertEqual(self.mate.orb.height(), 96)

    def test_the_bubble_ends_are_put_the_right_way_round(self):
        self.conf["companion_bubble_min"] = 20
        self.conf["companion_bubble_max"] = 5
        self.mate.apply(self.conf)
        self.assertGreaterEqual(self.mate._ceiling, self.mate._floor)


class Reporting(unittest.TestCase):
    """The calls the application makes, and what the character does with them."""

    def setUp(self):
        self.conf = {
            "companion_size": 128, "companion_side": "right",
            "companion_offset": 0, "companion_bubble_min": 3,
            "companion_bubble_max": 30,
        }
        self.mate = companion.Companion(self.conf)
        self.addCleanup(self.mate.orb.deleteLater)
        self.addCleanup(self.mate.bubbles.deleteLater)

    def kinds(self):
        return [s.kind for s in self.mate.bubbles._said if s.closing is None]

    def test_recording_turns_it_to_listening(self):
        self.mate.show_recording()
        self.assertEqual(self.mate.orb.state, companion.LISTENING)

    def test_working_turns_it_to_thinking_and_says_so(self):
        self.mate.show_busy("Yazıya çevriliyor…")
        self.assertEqual(self.mate.orb.state, companion.THINKING)
        self.assertEqual(self.kinds(), ["stage"])

    def test_the_same_progress_line_twice_is_only_said_once(self):
        self.mate.show_busy("Yazıya çevriliyor…")
        self.mate.show_busy("Yazıya çevriliyor…")
        self.assertEqual(self.kinds(), ["stage"])
        self.mate.show_busy("Temizleniyor…")
        self.assertEqual(self.kinds(), ["stage", "stage"])

    def test_what_it_heard_replaces_what_it_was_hearing(self):
        self.mate.live("bugün kuber netis")
        self.assertEqual(self.kinds(), ["live"])
        self.mate.heard("Bugün Kubernetes.")
        self.assertEqual(self.kinds(), ["heard"])

    def test_an_error_is_shown_in_full_and_turns_it_red(self):
        self.mate.show_error("Bir şey oldu\nikinci satır")
        self.assertEqual(self.mate.orb.state, companion.ERROR)
        self.assertEqual(self.kinds(), ["error"])

    def test_an_answer_gets_its_own_colour(self):
        self.mate.say("Takvime eklendi.", "agent")
        self.assertEqual(self.kinds(), ["agent"])

    def test_it_goes_back_to_waiting_after_an_outcome(self):
        self.mate.show_done("bitti")
        self.assertEqual(self.mate.orb.state, companion.ANSWER)
        self.mate._rest()
        self.assertEqual(self.mate.orb.state, companion.IDLE)

    def test_every_kind_it_can_say_has_a_style(self):
        for kind in ("heard", "live", "stage", "agent", "warn", "error"):
            self.assertIn(kind, companion.BUBBLE_STYLE, kind)

    def test_it_says_nothing_when_there_is_nothing_to_say(self):
        self.mate.say("")
        self.mate.stage("")
        self.mate.live("")
        self.assertEqual(self.kinds(), [])


# --- reading the sentence back while it is spoken -------------------------

class FakeRecorder:
    def __init__(self, seconds=0.0, loud=True):
        self.set(seconds, loud)

    def set(self, seconds, loud=True):
        frames = int(seconds * audio.RATE)
        self.pcm = b"\x00\x00" * frames
        blocks = max(1, frames // audio.CHUNK_FRAMES)
        # A quiet recording is flat near the floor, which is what the silence
        # test throws away; a loud one alternates well above it.
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
    """When a preview may run at all."""

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
        """Let the reading thread finish and its signal be delivered."""
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
        self.assertFalse(self.transcriber.running)

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
        self.assertEqual(len(self.calls), 2)      # asked twice, said once

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

    def test_stopping_takes_the_file_away(self):
        import os
        self.transcriber.start()
        self.transcriber._look()
        self.drain()
        path = self.calls[0]
        self.transcriber.stop()
        self.assertFalse(os.path.exists(path))


class Snapshot(unittest.TestCase):
    """What the recorder hands the preview while it is still recording."""

    def test_it_comes_back_whole_and_changes_nothing(self):
        recorder = audio.Recorder()
        recorder._buffer = bytearray(b"\x01\x02" * 100)
        recorder._rms = [0.1, 0.2]
        pcm, rms = recorder.snapshot()
        self.assertEqual(len(pcm), 200)
        self.assertEqual(rms, [0.1, 0.2])
        # A copy: the recording carries on appending to its own.
        rms.append(9.9)
        self.assertEqual(recorder._rms, [0.1, 0.2])
        self.assertEqual(len(recorder._buffer), 200)

    def test_an_empty_recorder_is_not_an_error(self):
        pcm, rms = audio.Recorder().snapshot()
        self.assertEqual(pcm, b"")
        self.assertEqual(rms, [])


class Wiring(unittest.TestCase):
    """The real application object, driven by hand.

    Everything above tests the character on its own. This one builds the thing
    that owns it and calls the handlers the pipelines call, because a bubble
    that works perfectly and is never connected to anything is the failure the
    rest of this file cannot see.

    It runs against a settings file in a temporary directory, so a test can
    neither read the keys in the real one nor write over it, and with the
    shortcut listener and the model preload off, so building it does not take
    Ctrl+Space away from the desktop or load a gigabyte onto the card.
    """

    @classmethod
    def setUpClass(cls):
        import shutil
        import tempfile

        import config as cfg
        import dikte as app_module

        cls.tmp = tempfile.mkdtemp(prefix="dikte-wiring-")
        cls.patches = [
            unittest.mock.patch.object(cfg, "CONFIG_DIR", __import__("pathlib").Path(cls.tmp)),
            unittest.mock.patch.object(
                cfg, "CONFIG_FILE", __import__("pathlib").Path(cls.tmp) / "config.json"),
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

    def kinds(self):
        return [s.kind for s in self.dikte.companion.bubbles._said if s.closing is None]

    def texts(self):
        return [s.text for s in self.dikte.companion.bubbles._said if s.closing is None]

    def test_the_character_is_up_and_the_corner_has_stood_down(self):
        self.assertTrue(self.dikte.companion.visible)
        self.assertFalse(self.dikte.overlay.enabled)
        self.assertFalse(self.dikte.ask_overlay.enabled)

    def test_turning_it_off_gives_the_corner_its_voice_back(self):
        self.dikte.conf["companion_enabled"] = False
        self.dikte._apply_companion()
        self.assertFalse(self.dikte.companion.visible)
        self.assertTrue(self.dikte.overlay.enabled)

    def test_keeping_both_leaves_the_corner_working(self):
        self.dikte.conf["companion_replaces_overlay"] = False
        self.dikte._apply_companion()
        self.assertTrue(self.dikte.companion.visible)
        self.assertTrue(self.dikte.overlay.enabled)

    def test_a_disabled_corner_paints_nothing_but_still_takes_the_calls(self):
        self.dikte.overlay.show_busy("bir şey")
        self.assertFalse(self.dikte.overlay.showing)

    def test_a_finished_dictation_reaches_the_bubbles(self):
        self.dikte.pipeline.finished.emit("ham", "Temiz cümle.", "")
        self.assertIn("Temiz cümle.", self.texts())
        self.assertEqual(self.dikte.companion.orb.state, companion.ANSWER)

    def test_a_stage_from_the_pipeline_reaches_the_bubbles(self):
        self.dikte.pipeline.stage.emit("Yazıya çevriliyor…")
        self.assertIn("stage", self.kinds())
        self.assertEqual(self.dikte.companion.orb.state, companion.THINKING)

    def test_an_agent_run_shows_the_question_then_the_answer(self):
        self.dikte.ask_pipeline.finished.emit("perşembe üçe koy", "Takvime eklendi.", "")
        self.assertEqual(self.kinds()[-2:], ["heard", "agent"])
        self.assertEqual(self.texts()[-2:], ["perşembe üçe koy", "Takvime eklendi."])

    def test_a_failure_turns_the_sphere_red_and_says_why(self):
        self.dikte.pipeline.failed.emit("Mikrofon bulunamadı")
        self.assertIn("error", self.kinds())
        self.assertEqual(self.dikte.companion.orb.state, companion.ERROR)

    def test_a_cleanup_that_failed_is_still_a_warning_worth_seeing(self):
        self.dikte.pipeline.finished.emit("ham", "Ham metin.", "Anahtar reddedildi")
        self.assertIn("warn", self.kinds())
        self.assertEqual(self.dikte.companion.orb.state, companion.WARNING)

    def test_the_microphone_level_reaches_the_sphere(self):
        self.dikte.companion.orb.set_state(companion.LISTENING)
        self.dikte.recorder.level.emit(0.8)
        self.assertGreater(self.dikte.companion.orb._level, 0.5)

    def test_a_live_reading_reaches_the_bubbles(self):
        self.dikte.live.partial.emit("yarım cümle")
        self.assertIn("live", self.kinds())

    def test_clicking_the_sphere_is_the_same_as_the_shortcut(self):
        pressed = []
        self.dikte._toggle = lambda: pressed.append("dictation")
        self.dikte.companion.clicked.emit()
        self.assertEqual(pressed, ["dictation"])

    def test_dragging_it_is_remembered(self):
        self.dikte.companion.moved.emit(10, 640)
        self.assertEqual(self.dikte.conf["companion_offset"], 640)

    def test_a_shortcut_somebody_else_holds_does_not_take_startup_down(self):
        """Starting up reports failures through the tray, so the tray has to
        exist before anything that can fail is started. It did not, and a
        combination another application already held ended the whole run in an
        AttributeError on a menu that had not been built yet."""
        self.dikte.evdev.failed.emit("Ctrl+Space is already taken")
        self.assertIn("error", self.kinds())

    def test_shutting_down_takes_the_character_off_the_screen(self):
        self.dikte.shutdown()
        self.assertFalse(self.dikte.companion.visible)
        self.assertFalse(self.dikte.companion.orb.isVisible())
        self.assertFalse(self.dikte.live.running)


if __name__ == "__main__":
    unittest.main(verbosity=2)
