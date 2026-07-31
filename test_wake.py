#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for hearing the name.

The signal processing is checked against arithmetic that cannot be argued with —
the fast transform against the slow one, a known tone against the bin it must
land in — and the matcher against sequences built to be the same, the same but
slower, or nothing alike. What is deliberately not asserted here is a wake rate:
that depends on a voice and a room, is measured against recordings rather than
claimed, and is written down in the README.

    python3 -m unittest test_wake -v
"""

import cmath
import json
import math
import os
import random
import shutil
import tempfile
import time
import unittest

import audio
import wake


def tone(hz, samples=wake.FRAME, rate=wake.FEATURE_RATE, amplitude=10000):
    return [amplitude * math.sin(2 * math.pi * hz * t / rate) for t in range(samples)]


def speechy(seconds=1.0, pitch=180.0, seed=1, rate=audio.RATE):
    """Something with harmonics and an envelope, which silence is not."""
    random.seed(seed)
    out = []
    for t in range(int(seconds * rate)):
        envelope = 0.45 + 0.55 * math.sin(2 * math.pi * 3.1 * t / rate)
        value = sum(math.sin(2 * math.pi * pitch * (h + 1) * t / rate) / (h + 1)
                    for h in range(5))
        out.append(int(7000 * envelope * value / 2 + random.gauss(0, 25)))
    return out


class Transform(unittest.TestCase):
    def test_the_fast_transform_agrees_with_the_slow_one(self):
        random.seed(4)
        values = [random.uniform(-1, 1) for _ in range(wake.FRAME)]
        slow = [sum(values[t] * cmath.exp(-2j * math.pi * k * t / len(values))
                    for t in range(len(values))) for k in range(len(values))]
        fast = wake._fft(values)
        self.assertLess(max(abs(a - b) for a, b in zip(fast, slow)), 1e-9)

    def test_a_known_tone_lands_in_the_bin_it_should(self):
        for hz in (300, 1000, 2500):
            windowed = [tone(hz)[i] * wake._WINDOW[i] for i in range(wake.FRAME)]
            spectrum = wake._fft(windowed)
            peak = max(range(wake.FRAME // 2),
                       key=lambda k: abs(spectrum[k]))
            found = peak * wake.FEATURE_RATE / wake.FRAME
            self.assertLess(abs(found - hz), wake.FEATURE_RATE / wake.FRAME, hz)

    def test_the_filterbank_covers_the_band_and_no_more(self):
        self.assertEqual(len(wake._FILTERS), wake.MEL_BANDS)
        bins = wake.FRAME // 2 + 1
        for first, weights in wake._FILTERS:
            self.assertGreaterEqual(first, 0)
            self.assertLessEqual(first + len(weights), bins + 1)
            self.assertTrue(any(w > 0 for w in weights))

    def test_halving_the_rate_halves_the_samples(self):
        self.assertEqual(len(wake.decimate(list(range(1000)))), 500)


class Features(unittest.TestCase):
    def test_a_second_of_sound_gives_about_the_expected_frames(self):
        rows = wake.features(speechy(1.0))
        expected = wake.FEATURE_RATE / wake.HOP
        self.assertLess(abs(len(rows) - expected), 3)
        self.assertTrue(all(len(row) == wake.CEPSTRA for row in rows))

    def test_silence_produces_something_rather_than_falling_over(self):
        self.assertEqual(wake.features([0] * 16000).__class__, list)
        self.assertEqual(wake.features([]), [])
        self.assertEqual(wake.features([1, 2, 3]), [])

    def test_the_same_sound_quieter_is_still_the_same_sound(self):
        """Loudness must not be part of what is compared: the same words at
        arm's length and across the room have to match."""
        loud = speechy(1.0)
        quiet = [int(round(s * 0.25)) for s in loud]
        self.assertLess(wake.distance(wake.features(loud), wake.features(quiet)), 0.5)

    def test_different_sounds_are_further_apart_than_the_same_one(self):
        same = wake.distance(wake.features(speechy(1.0, 180)),
                             wake.features(speechy(1.0, 180, seed=2)))
        other = wake.distance(wake.features(speechy(1.0, 180)),
                              wake.features(speechy(1.0, 440, seed=3)))
        self.assertLess(same, other)

    def test_only_the_front_is_looked_at(self):
        long_one = speechy(4.0)
        self.assertLess(len(wake.head_features(long_one)),
                        len(wake.features(long_one)))


def ramp(length, offset=0.0, step=0.11):
    return [[math.sin(step * i + k + offset) for k in range(wake.CEPSTRA)]
            for i in range(length)]


class Warping(unittest.TestCase):
    def test_a_sequence_matches_itself_exactly(self):
        rows = ramp(40)
        self.assertAlmostEqual(wake.distance(rows, list(rows)), 0.0)

    def test_the_same_thing_said_slower_still_matches(self):
        rows = ramp(40)
        slower = [row for row in rows for _ in range(2)]
        self.assertLess(wake.distance(rows, slower), 0.25)

    def test_something_else_does_not(self):
        self.assertGreater(wake.distance(ramp(40), ramp(40, offset=2.0, step=0.4)), 0.8)

    def test_nothing_is_infinitely_far_from_anything(self):
        self.assertEqual(wake.distance([], ramp(10)), float("inf"))
        self.assertEqual(wake.distance(ramp(10), []), float("inf"))

    def test_the_prefix_match_finds_where_the_name_stopped(self):
        name = ramp(30)
        said = name + ramp(60, offset=3.0, step=0.5)
        score, end = wake.prefix_distance(name, said)
        self.assertLess(score, 0.3)
        self.assertLess(abs(end - 30), 8)

    def test_a_longer_path_is_not_made_to_look_cheaper(self):
        """The score is per step of the path actually taken.

        Dividing by anything worked out from the endpoint instead rewards
        running on, and the match then slides to the end of the sentence: the
        bug this exists to keep fixed.
        """
        name = ramp(30)
        said = name + ramp(120, offset=3.0, step=0.5)
        _score, end = wake.prefix_distance(name, said)
        self.assertLess(end, 60)


class Calibration(unittest.TestCase):
    def test_each_recording_is_judged_against_its_own_twin(self):
        """Recorded several ways, the name must not be given one loose threshold
        measured across the difference between the ways."""
        tight = [ramp(30), ramp(30, offset=0.02)]          # said twice, alike
        loose = [ramp(52, offset=4.0), ramp(52, offset=4.1)]
        templates = wake.calibrate(tight + loose)
        self.assertEqual(len(templates.thresholds), 4)
        self.assertLess(max(templates.thresholds[:2]),
                        max(templates.thresholds) * 3)

    def test_two_recordings_are_the_fewest_that_will_do(self):
        self.assertFalse(wake.calibrate([ramp(30)]).ready)
        self.assertTrue(wake.calibrate([ramp(30), ramp(30, 0.05)]).ready)

    def test_very_alike_recordings_still_leave_room_to_be_matched(self):
        templates = wake.calibrate([ramp(30), ramp(30)])
        self.assertGreaterEqual(min(templates.thresholds), wake.ACCEPT_FLOOR)

    def test_the_name_is_recognised_and_something_else_is_not(self):
        templates = wake.calibrate([ramp(30), ramp(30, offset=0.05)])
        heard, score, _end = templates.matches(ramp(30, offset=0.02))
        self.assertTrue(heard)
        self.assertLess(score, 1.0)
        missed, score, _end = templates.matches(ramp(30, offset=2.5, step=0.6))
        self.assertFalse(missed)
        self.assertGreater(score, 1.0)

    def test_sensitivity_moves_the_line(self):
        """Whatever a reading scores, the dial has to be able to fall either
        side of it — measured against the reading rather than against a number
        assumed here, which would only be testing the fixture."""
        templates = wake.calibrate([ramp(30), ramp(30, offset=0.05)])
        awkward = ramp(30, offset=0.9)
        _heard, score, _end = templates.matches(awkward)
        self.assertTrue(0.0 < score < float("inf"))
        strict, _, _ = templates.matches(awkward, sensitivity=score * 0.9)
        loose, _, _ = templates.matches(awkward, sensitivity=score * 1.1)
        self.assertFalse(strict)
        self.assertTrue(loose)

    def test_too_short_to_hold_the_name_is_refused_before_it_is_compared(self):
        templates = wake.calibrate([ramp(40), ramp(40, offset=0.05)])
        heard, _score, _end = templates.matches(ramp(4))
        self.assertFalse(heard)

    def test_nothing_recorded_means_nothing_is_heard(self):
        heard, _score, _end = wake.Templates().matches(ramp(30))
        self.assertFalse(heard)


class Keeping(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="dikte-wake-")
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.path = os.path.join(self.tmp, "wake.json")

    def test_what_is_written_comes_back(self):
        templates = wake.calibrate([ramp(30), ramp(30, offset=0.05)], "Zeno")
        templates.save(self.path)
        again = wake.Templates.load(self.path)
        self.assertEqual(again.phrase, "Zeno")
        self.assertEqual(again.thresholds, templates.thresholds)
        self.assertTrue(again.ready)

    def test_nothing_playable_is_kept(self):
        """Only the cepstra. What is on disk cannot be turned back into a
        recording of somebody's voice."""
        wake.calibrate([ramp(30), ramp(30, 0.05)], "Zeno").save(self.path)
        with open(self.path, encoding="utf-8") as handle:
            stored = json.load(handle)
        self.assertEqual(set(stored) - {"version", "phrase", "threshold",
                                        "lengths", "thresholds", "templates"},
                         set())

    def test_a_missing_or_broken_file_is_simply_nothing(self):
        self.assertFalse(wake.Templates.load(self.path).ready)
        with open(self.path, "w", encoding="utf-8") as handle:
            handle.write("{not json")
        self.assertFalse(wake.Templates.load(self.path).ready)

    def test_a_note_from_another_version_is_not_trusted(self):
        with open(self.path, "w", encoding="utf-8") as handle:
            json.dump({"version": 99, "templates": [ramp(30)]}, handle)
        self.assertFalse(wake.Templates.load(self.path).ready)


class Segmenting(unittest.TestCase):
    def blocks(self, samples):
        return [samples[i:i + wake.BLOCK]
                for i in range(0, len(samples) - wake.BLOCK, wake.BLOCK)]

    def run_through(self, samples):
        segmenter = wake.Segmenter()
        found = []
        for block in self.blocks(samples):
            utterance = segmenter.feed(block, wake.levels(block))
            if utterance:
                found.append(utterance)
        return found

    def test_a_quiet_room_produces_nothing(self):
        random.seed(9)
        hiss = [int(random.gauss(0, 12)) for _ in range(audio.RATE * 3)]
        self.assertEqual(self.run_through(hiss), [])

    def test_speech_between_silences_comes_out_as_one_utterance(self):
        quiet = [0] * int(audio.RATE * 0.8)
        found = self.run_through(quiet + speechy(1.0) + quiet)
        self.assertEqual(len(found), 1)
        seconds = len(found[0]) / audio.RATE
        self.assertTrue(0.8 < seconds < 2.0, seconds)

    def test_two_sayings_with_a_gap_are_two_utterances(self):
        quiet = [0] * int(audio.RATE * 0.8)
        found = self.run_through(quiet + speechy(0.9) + quiet + speechy(0.9, seed=5) + quiet)
        self.assertEqual(len(found), 2)

    def test_what_came_just_before_it_started_is_kept(self):
        """Speech does not begin at the loudness it is measured by, so the
        blocks before the level crossed have to be there or the first sound of
        the name is missing."""
        quiet = [0] * int(audio.RATE * 0.8)
        found = self.run_through(quiet + speechy(1.0) + quiet)
        self.assertGreater(len(found[0]) / audio.RATE, 1.0)

    def test_something_far_too_long_is_not_offered_as_the_name(self):
        found = self.run_through(speechy(6.0) + [0] * int(audio.RATE * 0.8))
        for utterance in found:
            self.assertLessEqual(len(utterance) / audio.RATE,
                                 wake.MAX_SECONDS + wake.TAIL_SECONDS + 0.2)

    def test_the_floor_follows_a_room_that_is_not_silent(self):
        random.seed(11)
        noisy = [int(random.gauss(0, 400)) for _ in range(audio.RATE * 2)]
        self.assertEqual(self.run_through(noisy), [])

    def test_levels_are_a_fraction_of_full_scale(self):
        self.assertEqual(wake.levels([]), 0.0)
        self.assertAlmostEqual(wake.levels([32767] * 100), 1.0, places=3)
        self.assertAlmostEqual(wake.levels([0] * 100), 0.0)




# --- the whole path, with the microphone stood in for ----------------------

class FakeStdout:
    """Hands out a recording in blocks, then silence for ever, like a device.

    Paced, not poured. A real microphone delivers a block every sixty-four
    milliseconds, and the marks that cut a take out of the stream are only
    meaningful against that. Handed over all at once, the stream was past
    its own end before the first mark was set and every take came out of
    the silence after it.
    """

    PACE = wake.BLOCK_SECONDS / 4.0   # quick for a test, slow enough to aim at

    def __init__(self, chunks):
        self._data = b"".join(chunks)
        self._at = 0

    def read(self, count):
        time.sleep(self.PACE)
        if self._at >= len(self._data):
            return b"\x00" * count          # a quiet room, not end of stream
        piece = self._data[self._at:self._at + count]
        self._at += count
        return piece.ljust(count, b"\x00")


class FakeProcess:
    def __init__(self, chunks):
        self.stdout = FakeStdout(chunks)
        self._alive = True

    def poll(self):
        return None if self._alive else 0

    def terminate(self):
        self._alive = False

    def kill(self):
        self._alive = False

    def wait(self, timeout=None):
        self._alive = False
        return 0


def as_bytes(samples):
    import array
    return array.array("h", [max(-32768, min(32767, int(s))) for s in samples]).tobytes()


def a_saying(seed, pitch=190.0):
    """One take: a breath of quiet, something voice-like, a breath of quiet.

    Short padding on purpose. A held button is released about when the word
    ends, so a take is mostly word; padding it out with digital silence would
    fill the compared span with frames whose cepstra are pure noise, and the
    fixture would be measuring its own random number generator.
    """
    quiet = [0] * int(audio.RATE * 0.12)
    return quiet + speechy(0.85, pitch, seed=seed) + quiet


class TheWholePath(unittest.TestCase):
    """Recording the name by hand, and then hearing it.

    Split deliberately. Driving a threaded capture from a test means racing it,
    and a race decides where a take is cut to within a block either way — which
    is exactly the sloppiness the trimming exists to absorb. So the plumbing is
    tested for plumbing (four holds, four takes, nothing refused), the trimming
    is tested on audio handed to it directly, and the matching is tested on
    takes that were cut the way the trimmer cuts them. Asserting a calibrated
    threshold at the end of a race would be asserting the race.
    """

    def setUp(self):
        import unittest.mock
        self.tmp = tempfile.mkdtemp(prefix="dikte-path-")
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.path = os.path.join(self.tmp, "wake.json")
        self.conf = {"mic_target": "", "wake_sensitivity": 1.0}
        self.chunks = []
        patch = unittest.mock.patch.object(
            wake.subprocess, "Popen", lambda *a, **k: FakeProcess(self.chunks))
        patch.start()
        self.addCleanup(patch.stop)
        command = unittest.mock.patch.object(
            wake.audio, "capture_command", lambda target="": ["fake"])
        command.start()
        self.addCleanup(command.stop)

    # ---- the plumbing ------------------------------------------------------

    def test_holding_the_button_four_times_gives_four_takes(self):
        from PyQt6.QtWidgets import QApplication
        app = QApplication.instance() or QApplication([])
        gap = [0] * int(audio.RATE * 0.3)
        stream, marks = [], []
        for seed in (1, 2, 3, 4):
            saying = a_saying(seed)
            marks.append((len(stream), len(stream) + len(saying)))
            stream.extend(saying)
            stream.extend(gap)
        self.chunks = [as_bytes(stream)]

        recorder = wake.HoldRecorder(self.conf)
        takes, refused = [], []
        recorder.captured.connect(takes.append)
        recorder.rejected.connect(refused.append)
        self.assertTrue(recorder.start())
        try:
            for index, (begin, finish) in enumerate(marks):
                self._wait(app, lambda b=begin: recorder._total > b)
                recorder.press()
                self.assertTrue(recorder.holding)
                self._wait(app, lambda f=finish: recorder._total >= f)
                recorder.release()
                self._wait(app, lambda i=index: len(takes) + len(refused) > i)
        finally:
            recorder.stop()
        self.assertEqual(refused, [])
        self.assertEqual(len(takes), 4)
        for take in takes:
            self.assertGreater(len(take) / audio.RATE, 0.5)

    def test_a_click_rather_than_a_hold_is_refused(self):
        from PyQt6.QtWidgets import QApplication
        app = QApplication.instance() or QApplication([])
        self.chunks = [as_bytes(a_saying(1) * 3)]
        recorder = wake.HoldRecorder(self.conf)
        refused = []
        recorder.rejected.connect(refused.append)
        self.assertTrue(recorder.start())
        try:
            self._wait(app, lambda: recorder._total > audio.RATE // 4)
            recorder.press()
            recorder.release()          # let go at once
            self._wait(app, lambda: bool(refused))
        finally:
            recorder.stop()
        self.assertEqual(refused, ["short"])

    def test_saying_nothing_at_all_is_refused(self):
        from PyQt6.QtWidgets import QApplication
        app = QApplication.instance() or QApplication([])
        self.chunks = [as_bytes([0] * int(audio.RATE * 4))]
        recorder = wake.HoldRecorder(self.conf)
        refused = []
        recorder.rejected.connect(refused.append)
        self.assertTrue(recorder.start())
        try:
            self._wait(app, lambda: recorder._total > audio.RATE // 2)
            recorder.press()
            self._wait(app, lambda: recorder._total > int(audio.RATE * 1.5))
            recorder.release()
            self._wait(app, lambda: bool(refused))
        finally:
            recorder.stop()
        self.assertEqual(refused, ["silent"])

    def _wait(self, app, done, limit=1500):
        for _ in range(limit):
            app.processEvents()
            if done():
                return True
            time.sleep(0.005)
        return False

    # ---- the trimming ------------------------------------------------------

    def test_a_take_is_cut_down_to_the_speech_inside_it(self):
        """A finger is far less precise than a syllable. However much quiet the
        button left on either end, what comes out has to be the same length, or
        two takes of one word are two different words to the matcher."""
        lengths = set()
        for padding in (0.05, 0.2, 0.35, 0.6):
            quiet = [0] * int(audio.RATE * padding)
            lengths.add(round(len(wake.trim(quiet + a_saying(1) + quiet))
                              / audio.RATE, 2))
        self.assertEqual(len(lengths), 1, lengths)

    def test_trimming_leaves_a_little_room_around_the_word(self):
        trimmed = wake.trim(a_saying(1))
        self.assertGreater(len(trimmed) / audio.RATE, 0.85)

    def test_a_take_with_nothing_in_it_is_left_alone_rather_than_emptied(self):
        quiet = [0] * int(audio.RATE * 1.0)
        self.assertEqual(len(wake.trim(quiet)), len(quiet))
        self.assertEqual(wake.trim([]), [])

    # ---- the matching ------------------------------------------------------

    def taken(self, seed, padding=0.2):
        """A take as the recorder would hand it over: cut sloppily, trimmed."""
        quiet = [0] * int(audio.RATE * padding)
        return wake.trim(quiet + a_saying(seed) + quiet)

    def test_recording_it_and_then_hearing_it(self):
        takes = [self.taken(seed, padding) for seed, padding
                 in ((1, 0.1), (2, 0.3), (3, 0.2), (4, 0.45))]
        templates = wake.calibrate([wake.head_features(t) for t in takes], "Zeno")
        self.assertTrue(templates.ready, templates.thresholds)
        templates.save(self.path)

        again = wake.Templates.load(self.path)
        self.assertTrue(again.ready)
        _heard, near, _end = again.matches(wake.head_features(self.taken(5)))
        other = wake.trim([0] * int(audio.RATE * 0.2) + speechy(1.4, 95.0, seed=9))
        _missed, far, _end = again.matches(wake.head_features(other))
        self.assertLess(near * 2, far)

    def test_the_odd_take_out_is_dropped_rather_than_failing_the_lot(self):
        """One bad take out of four costs that take, not the recording.
        Somebody clears their throat or starts again; the other three are
        perfectly good and the calibration is better without the fourth."""
        good = [wake.head_features(self.taken(seed, pad)) for seed, pad
                in ((1, 0.1), (2, 0.3), (3, 0.2))]
        cough = wake.head_features(
            wake.trim([0] * int(audio.RATE * 0.2) + speechy(1.5, 95.0, seed=9)))
        kept = wake.calibrate(good + [cough])
        self.assertEqual(len(kept.rows), 3)
        self.assertTrue(kept.ready)
        # And with nothing to drop, nothing is dropped.
        self.assertEqual(len(wake.calibrate(good).rows), 3)

    def test_two_recordings_are_never_winnowed_down_to_one(self):
        pair = [wake.head_features(self.taken(1)), wake.head_features(self.taken(9))]
        self.assertEqual(len(wake.winnow(pair)), 2)

    def test_wide_recordings_are_kept_but_flagged(self):
        """There is no distance that means "not the same word": how alike four
        sayings are depends on the voice and the room, and a line drawn here
        was measured turning away real recordings while a quiet room passed.
        So it is said rather than enforced."""
        # A quiet room, not digital silence: perfect zeros are identical to
        # each other and calibrate to the floor, which is the one kind of
        # nothing this cannot be caught out by. Real hiss is random, and four
        # takes of it agree with each other about as much as four strangers do.
        random.seed(5)
        hiss = [wake.head_features(
            [int(random.gauss(0, 60)) for _ in range(int(audio.RATE * 1.2))])
            for _ in range(4)]
        loose = wake.calibrate(hiss)
        self.assertTrue(loose.ready)          # usable, if it is what you meant
        self.assertTrue(loose.loose)          # and said to be wide

        tight = wake.calibrate(
            [wake.head_features(self.taken(seed, pad)) for seed, pad
             in ((1, 0.1), (2, 0.3), (3, 0.2), (4, 0.45))])
        self.assertFalse(tight.loose)

    def test_the_listener_will_not_start_before_the_name_is_recorded(self):
        listener = wake.WakeListener(self.conf, self.path)
        self.assertFalse(listener.start())
        self.assertFalse(listener.running)


if __name__ == "__main__":
    unittest.main(verbosity=2)
