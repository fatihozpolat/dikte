#!/usr/bin/env python3
"""Tests for the parts that differ between Linux and Windows.

Nothing here records anything or presses a key. What it covers is the reading
and the deciding: the device listing ffmpeg prints and what Dikte makes of it,
the command that comes out the other side, and the shortcut table, which has to
name the same keys on both platforms or a settings file written on one becomes
unparsable on the other.

    python3 -m unittest test_platform -v
"""

import os
import unittest
import unittest.mock

import audio
import i18n
import hotkey
import paste
import plat

# What ffmpeg 6 and older print: a heading per kind, then the devices under it.
OLD_LISTING = """\
[dshow @ 000001] DirectShow video devices (some may be both video and audio devices)
[dshow @ 000001]  "Integrated Webcam"
[dshow @ 000001]     Alternative name "@device_pnp_\\\\?\\usb#vid_0c45"
[dshow @ 000001] DirectShow audio devices
[dshow @ 000001]  "Microphone (Realtek(R) Audio)"
[dshow @ 000001]     Alternative name "@device_cm_{33D9A762}\\wave_{AAAA}"
[dshow @ 000001]  "Stereo Mix (Realtek(R) Audio)"
[dshow @ 000001]     Alternative name "@device_cm_{33D9A762}\\wave_{BBBB}"
"""

# What ffmpeg 7 and 8 print: no headings, the kind on the line itself.
NEW_LISTING = """\
[in#0 @ 000002] "Fatih adlı kişiye ait A53 (Windows Virtual Camera)" (video)
[in#0 @ 000002]   Alternative name "@device_pnp_\\\\?\\swd#vcamdevapi"
[in#0 @ 000002] "Mikrofon (USB PnP Audio Device)" (audio)
[in#0 @ 000002]   Alternative name "@device_cm_{33D9A762}\\wave_{917B}"
[in#0 @ 000002] "Stereo Karışımı (Realtek Audio)" (audio)
[in#0 @ 000002]   Alternative name "@device_cm_{33D9A762}\\wave_{CCCC}"
Error opening input file dummy.
"""


class DshowListing(unittest.TestCase):
    def test_the_new_format_yields_the_audio_devices_only(self):
        devices = audio._parse_dshow(NEW_LISTING)
        self.assertEqual([d["name"] for d in devices],
                         ["Mikrofon (USB PnP Audio Device)",
                          "Stereo Karışımı (Realtek Audio)"])

    def test_the_old_format_reads_the_same_way(self):
        devices = audio._parse_dshow(OLD_LISTING)
        self.assertEqual([d["name"] for d in devices],
                         ["Microphone (Realtek(R) Audio)",
                          "Stereo Mix (Realtek(R) Audio)"])

    def test_the_alternative_name_becomes_the_id(self):
        # It survives a rename and a move to another port; the friendly name is
        # for the person reading the list and nothing else.
        devices = audio._parse_dshow(NEW_LISTING)
        self.assertEqual(devices[0]["id"], "@device_cm_{33D9A762}\\wave_{917B}")

    def test_a_video_device_does_not_lend_its_name_to_an_audio_one(self):
        # The alternative name arrives on its own line, under whichever device
        # was named last: a camera's must not land on the microphone after it.
        devices = audio._parse_dshow(NEW_LISTING)
        self.assertNotIn("vcamdevapi", devices[0]["id"])

    def test_a_device_without_an_alternative_name_keeps_its_own(self):
        devices = audio._parse_dshow('[dshow @ 1] "Plain Mic" (audio)\n')
        self.assertEqual(devices, [{"id": "Plain Mic", "name": "Plain Mic"}])

    def test_nothing_at_all_is_not_an_error(self):
        self.assertEqual(audio._parse_dshow(""), [])
        self.assertEqual(audio._parse_dshow("ffmpeg version 8.1\n"), [])


class Loopbacks(unittest.TestCase):
    def test_the_usual_names_are_recognised(self):
        for name in ("Stereo Mix (Realtek)", "Stereo Karışımı (Realtek Audio)",
                     "CABLE Output (VB-Audio Virtual Cable)",
                     "What U Hear (SB Audigy)", "virtual-audio-capturer"):
            self.assertTrue(audio._is_loopback(name), name)

    def test_a_microphone_is_not_one(self):
        for name in ("Mikrofon (USB PnP Audio Device)", "Microphone Array",
                     "Headset (Jabra)"):
            self.assertFalse(audio._is_loopback(name), name)


class Commands(unittest.TestCase):
    """What ends up on the command line, with the device list stood in for."""

    def setUp(self):
        self.devices = [
            {"id": "mic-id", "name": "Mikrofon (USB PnP Audio Device)"},
            {"id": "mix-id", "name": "Stereo Mix (Realtek)"},
        ]
        patch = unittest.mock.patch.object(
            audio, "_audio_devices", lambda force=False: list(self.devices))
        patch.start()
        self.addCleanup(patch.stop)
        which = unittest.mock.patch.object(
            audio.shutil, "which", lambda name: f"/usr/bin/{name}")
        which.start()
        self.addCleanup(which.stop)

    @unittest.skipUnless(plat.WINDOWS, "DirectShow is Windows only")
    def test_an_unset_microphone_becomes_the_first_real_input(self):
        cmd = audio.capture_command("")
        self.assertIn("audio=mic-id", cmd)
        self.assertIn("dshow", cmd)

    @unittest.skipUnless(plat.WINDOWS, "DirectShow is Windows only")
    def test_the_loopback_is_never_picked_as_the_microphone(self):
        self.devices.reverse()          # the mix now comes first
        self.assertIn("audio=mic-id", audio.capture_command(""))

    @unittest.skipUnless(plat.WINDOWS, "DirectShow is Windows only")
    def test_a_chosen_device_is_passed_through_as_it_is(self):
        self.assertIn("audio=whatever", audio.capture_command("whatever"))

    @unittest.skipUnless(plat.WINDOWS, "DirectShow is Windows only")
    def test_the_capture_is_one_channel_of_16k_pcm(self):
        cmd = audio.capture_command("")
        self.assertEqual(cmd[cmd.index("-ar") + 1], str(audio.RATE))
        self.assertEqual(cmd[cmd.index("-ac") + 1], "1")
        self.assertEqual(cmd[cmd.index("-f", cmd.index("-ac")) + 1], "s16le")
        # Without it DirectShow hands over half-second blocks and the waveform
        # trails the voice by that much.
        self.assertIn("-audio_buffer_size", cmd)

    @unittest.skipUnless(plat.WINDOWS, "DirectShow is Windows only")
    def test_a_meeting_takes_both_sides_and_merges_them(self):
        cmd = audio.meeting_command("", "")
        self.assertEqual(cmd.count("dshow"), 2)
        self.assertIn("audio=mic-id", cmd)
        self.assertIn("audio=mix-id", cmd)     # found on its own
        self.assertIn("amerge=inputs=2[out]", cmd[cmd.index("-filter_complex") + 1])

    @unittest.skipUnless(plat.WINDOWS, "DirectShow is Windows only")
    def test_a_meeting_without_a_loopback_says_so_rather_than_recording_half(self):
        """The language is pinned because the message is translated, and which
        one is loaded depends on which other test module ran first."""
        was = i18n.language()
        i18n.set_language("en")
        self.addCleanup(i18n.set_language, was)
        self.devices = [self.devices[0]]
        with self.assertRaises(audio.AudioError) as caught:
            audio.meeting_command("", "")
        self.assertIn("Stereo Mix", str(caught.exception))

    @unittest.skipUnless(plat.WINDOWS, "DirectShow is Windows only")
    def test_no_device_at_all_is_reported_before_ffmpeg_is_started(self):
        self.devices = []
        with self.assertRaises(audio.AudioError):
            audio.capture_command("")

    @unittest.skipIf(plat.WINDOWS, "pw-record is Linux only")
    def test_linux_still_records_through_pw_record(self):
        cmd = audio.capture_command("some.source")
        self.assertEqual(cmd[0], "pw-record")
        self.assertIn("--target=some.source", cmd)


class Shortcuts(unittest.TestCase):
    def test_a_combination_comes_back_as_modifiers_and_a_key_name(self):
        self.assertEqual(hotkey.parse_shortcut("Ctrl+Space"), ({"ctrl"}, "space"))
        self.assertEqual(hotkey.parse_shortcut("ctrl+alt+F9"),
                         ({"ctrl", "alt"}, "f9"))

    def test_the_two_spellings_of_the_windows_key_agree(self):
        self.assertEqual(hotkey.parse_shortcut("Meta+K"),
                         hotkey.parse_shortcut("Super+k"))

    def test_control_is_the_same_modifier_as_ctrl(self):
        self.assertEqual(hotkey.parse_shortcut("Control+V")[0], {"ctrl"})

    def test_nonsense_is_refused_rather_than_half_read(self):
        for text in ("", "Ctrl", "Ctrl+", "Ctrl+Nope", "a+b", None):
            self.assertEqual(hotkey.parse_shortcut(text), (None, None), repr(text))

    def test_both_platforms_know_the_same_key_names(self):
        # A settings file is portable; a combination typed on one machine has to
        # parse on the other, so neither table may know a name the other does not.
        self.assertEqual(set(hotkey.KEYS), set(hotkey.WIN_KEYS))

    def test_every_modifier_has_a_windows_flag(self):
        self.assertEqual(set(hotkey.MODIFIERS), set(hotkey.WIN_MODS))

    def test_the_listener_is_what_binds_the_key_on_windows(self):
        self.assertEqual(hotkey.native_shortcuts(), not plat.WINDOWS)
        self.assertEqual(hotkey.listener_swallows_key(), plat.WINDOWS)


class PasteKeys(unittest.TestCase):
    def test_both_platforms_know_the_same_keys(self):
        self.assertEqual(set(paste.KEYCODES), set(paste.VK))

    def test_the_default_paste_shortcut_can_be_pressed(self):
        for key in "ctrl+v".split("+"):
            self.assertIn(key, paste.VK)
            self.assertIn(key, paste.KEYCODES)


class Locations(unittest.TestCase):
    def test_the_directories_are_under_the_users_own_profile(self):
        home = os.path.expanduser("~").lower()
        for path in (plat.config_home(), plat.data_home()):
            self.assertTrue(str(path).lower().startswith(home), path)

    @unittest.skipIf(plat.WINDOWS, "XDG is Linux only")
    def test_xdg_is_honoured_where_it_exists(self):
        with unittest.mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": "/tmp/conf"}):
            self.assertEqual(str(plat.config_home()), "/tmp/conf")

    def test_the_ipc_name_is_the_users_own(self):
        tag = plat.user_tag()
        self.assertTrue(tag)
        self.assertTrue(tag.isalnum())

    def test_a_console_is_only_suppressed_where_there_is_one_to_suppress(self):
        self.assertEqual(bool(plat.quiet()), plat.WINDOWS)


if __name__ == "__main__":
    unittest.main(verbosity=2)
