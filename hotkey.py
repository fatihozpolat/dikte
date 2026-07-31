"""The global shortcut: the one thing every desktop does its own way.

KDE keeps its shortcuts in a file KWin reads at startup, so a shortcut installed
now does not fire until the next login; the listener that reads /dev/input
directly is what covers the gap, at the cost of not swallowing the key.

Windows has nothing of that shape. RegisterHotKey is the whole mechanism: it is
asked for a combination, it either gets it or somebody else already has it, and
from then on the key press is delivered here and nowhere else. There is no file
to install, nothing to log out for, and no second path — which is why the
listener is on by default there and the KDE half of this file goes quiet.
"""

import glob
import os
import pathlib
import re
import select
import struct
import subprocess
import threading

from PyQt6.QtCore import QObject, pyqtSignal

import plat
from i18n import t

DESKTOP_ID = "dikte-toggle.desktop"
MEETING_DESKTOP_ID = "dikte-meeting.desktop"
ASK_DESKTOP_ID = "dikte-ask.desktop"
APPLICATIONS_DIR = pathlib.Path.home() / ".local/share/applications"
DESKTOP_FILE = APPLICATIONS_DIR / DESKTOP_ID
SHORTCUTS_FILE = pathlib.Path.home() / ".config/kglobalshortcutsrc"

MODIFIERS = ("ctrl", "shift", "alt", "super")

# --- evdev key codes (linux/input-event-codes.h) --------------------------

EV_KEY = 0x01
KEYS = {
    "space": 57, "tab": 15, "enter": 28, "return": 28, "esc": 1, "escape": 1,
    "backspace": 14, "insert": 110, "delete": 111, "home": 102, "end": 107,
    "pgup": 104, "pgdown": 109, "up": 103, "down": 108, "left": 105, "right": 106,
    "1": 2, "2": 3, "3": 4, "4": 5, "5": 6, "6": 7, "7": 8, "8": 9, "9": 10, "0": 11,
    "q": 16, "w": 17, "e": 18, "r": 19, "t": 20, "y": 21, "u": 22, "i": 23, "o": 24,
    "p": 25, "a": 30, "s": 31, "d": 32, "f": 33, "g": 34, "h": 35, "j": 36, "k": 37,
    "l": 38, "z": 44, "x": 45, "c": 46, "v": 47, "b": 48, "n": 49, "m": 50,
    "f1": 59, "f2": 60, "f3": 61, "f4": 62, "f5": 63, "f6": 64, "f7": 65, "f8": 66,
    "f9": 67, "f10": 68, "f11": 87, "f12": 88,
}
MODS = {
    "ctrl": (29, 97), "control": (29, 97),
    "shift": (42, 54),
    "alt": (56, 100),
    "meta": (125, 126), "super": (125, 126),
}
ALL_MOD_CODES = {code for pair in MODS.values() for code in pair}

# --- Windows virtual-key codes (winuser.h) --------------------------------

WIN_KEYS = {
    "space": 0x20, "tab": 0x09, "enter": 0x0D, "return": 0x0D,
    "esc": 0x1B, "escape": 0x1B, "backspace": 0x08,
    "insert": 0x2D, "delete": 0x2E, "home": 0x24, "end": 0x23,
    "pgup": 0x21, "pgdown": 0x22,
    "up": 0x26, "down": 0x28, "left": 0x25, "right": 0x27,
}
WIN_KEYS.update({chr(code): code for code in range(0x30, 0x3A)})          # 0-9
WIN_KEYS.update({chr(code + 32): code for code in range(0x41, 0x5B)})     # a-z
WIN_KEYS.update({f"f{n}": 0x6F + n for n in range(1, 13)})                # F1-F12

WIN_MODS = {"alt": 0x0001, "ctrl": 0x0002, "shift": 0x0004, "super": 0x0008}
MOD_NOREPEAT = 0x4000
WM_HOTKEY = 0x0312
WM_QUIT = 0x0012


def key_table():
    """The keys this platform can bind, by name."""
    return WIN_KEYS if plat.WINDOWS else KEYS


def parse_shortcut(text):
    """'Ctrl+Space' -> ({'ctrl'}, 'space'), or (None, None) when unparsable.

    The key comes back by name rather than by code: the two platforms number
    the same keys differently, and only the listener needs the number.
    """
    parts = [p.strip().lower() for p in str(text).split("+") if p.strip()]
    if not parts:
        return None, None
    mods, key = set(), None
    table = key_table()
    for part in parts:
        if part in ("ctrl", "control"):
            mods.add("ctrl")
        elif part in ("meta", "super"):
            mods.add("super")
        elif part in ("shift", "alt"):
            mods.add(part)
        elif key is None and part in table:
            key = part
        else:
            return None, None
    if key is None:
        return None, None
    return mods, key


# --- the built-in listener, Linux ------------------------------------------

class EvdevHotkey(QObject):
    """Catches global shortcuts by reading /dev/input directly.

    It does not swallow the key; the focused application sees the combination
    too. This is the fallback that works before the KDE shortcut goes live.
    """

    triggered = pyqtSignal(str)   # the name the binding was registered under
    failed = pyqtSignal(str)

    EVENT_FMT = "llHHi"
    EVENT_SIZE = struct.calcsize(EVENT_FMT)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._thread = None
        self._stop = threading.Event()
        self._bindings = {}   # key code -> [(mods, name)]

    @property
    def running(self):
        return self._thread is not None and self._thread.is_alive()

    def start(self, bindings):
        """`bindings` is {name: 'Ctrl+Space'}; an empty combination is skipped."""
        self.stop()
        parsed = {}
        for name, shortcut in bindings.items():
            if not shortcut:
                continue
            mods, key = parse_shortcut(shortcut)
            if key is None:
                self.failed.emit(
                    t("Could not parse the shortcut: {shortcut}", shortcut=shortcut)
                )
                continue
            parsed.setdefault(KEYS[key], []).append((mods, name))
        if not parsed:
            return False
        devices = self._open_devices()
        if not devices:
            self.failed.emit(t(
                "Cannot read /dev/input. Your user needs to be in the 'input' group:\n"
                "  sudo usermod -aG input $USER   (then log out and back in)"
            ))
            return False
        self._bindings = parsed
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, args=(devices,), daemon=True)
        self._thread.start()
        return True

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=1.5)
        self._thread = None

    def _open_devices(self):
        fds = []
        for path in sorted(glob.glob("/dev/input/event*")):
            try:
                fds.append(os.open(path, os.O_RDONLY | os.O_NONBLOCK))
            except OSError:
                continue
        return fds

    def _loop(self, fds):
        held = set()
        try:
            while not self._stop.is_set():
                # Short enough that stop() does not stall its caller waiting for
                # the read to come back around.
                ready, _, _ = select.select(fds, [], [], 0.15)
                for fd in ready:
                    try:
                        data = os.read(fd, self.EVENT_SIZE * 64)
                    except (BlockingIOError, OSError):
                        continue
                    for offset in range(0, len(data) - self.EVENT_SIZE + 1, self.EVENT_SIZE):
                        _s, _us, etype, code, value = struct.unpack(
                            self.EVENT_FMT, data[offset:offset + self.EVENT_SIZE]
                        )
                        if etype != EV_KEY:
                            continue
                        if code in ALL_MOD_CODES:
                            held.add(code) if value else held.discard(code)
                        elif value == 1:
                            for mods, name in self._bindings.get(code, ()):
                                if self._mods_match(held, mods):
                                    self.triggered.emit(name)
        finally:
            for fd in fds:
                try:
                    os.close(fd)
                except OSError:
                    pass

    @staticmethod
    def _mods_match(held, wanted):
        for name, codes in MODS.items():
            if name in ("control", "super"):
                continue
            pressed = any(code in held for code in codes)
            if pressed != (name in wanted):
                return False
        return True


# --- the built-in listener, Windows ----------------------------------------

class WinHotkey(QObject):
    """Global shortcuts through RegisterHotKey.

    Unlike the evdev listener this one does swallow the key: while Dikte holds
    Ctrl+Space, nothing else on the desktop sees it. The other side of that is
    that a combination somebody else already holds cannot be had at all, which
    is a thing to be told about rather than to fail quietly over.

    The registration and the loop that receives the presses have to live on the
    same thread, and that thread has to sit in GetMessage rather than in Qt's
    event loop, so it gets a thread of its own and hands each press over as a
    signal.
    """

    triggered = pyqtSignal(str)
    failed = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._thread = None
        self._thread_id = 0
        self._ready = threading.Event()
        self._problems = []

    @property
    def running(self):
        return self._thread is not None and self._thread.is_alive()

    def start(self, bindings):
        self.stop()
        parsed = []
        for name, shortcut in bindings.items():
            if not shortcut:
                continue
            mods, key = parse_shortcut(shortcut)
            if key is None:
                self.failed.emit(
                    t("Could not parse the shortcut: {shortcut}", shortcut=shortcut)
                )
                continue
            flags = MOD_NOREPEAT
            for mod in mods:
                flags |= WIN_MODS.get(mod, 0)
            parsed.append((name, shortcut, flags, WIN_KEYS[key]))
        if not parsed:
            return False

        self._problems = []
        self._ready.clear()
        self._thread = threading.Thread(target=self._loop, args=(parsed,), daemon=True)
        self._thread.start()
        # The registrations happen on that thread, and whether they worked is
        # the answer this call owes its caller, so it waits for them.
        self._ready.wait(3.0)
        if self._problems:
            self.failed.emit("\n".join(self._problems))
        return self.running

    def stop(self):
        thread, self._thread = self._thread, None
        if thread is None:
            return
        if self._thread_id:
            import ctypes
            ctypes.WinDLL("user32", use_last_error=True).PostThreadMessageW(
                self._thread_id, WM_QUIT, 0, 0)
        thread.join(timeout=2)
        self._thread_id = 0

    def _loop(self, parsed):
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.WinDLL("user32", use_last_error=True)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        user32.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int,
                                          wintypes.UINT, wintypes.UINT]
        user32.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
        user32.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND,
                                       wintypes.UINT, wintypes.UINT]
        user32.PostThreadMessageW.argtypes = [wintypes.DWORD, wintypes.UINT,
                                              wintypes.WPARAM, wintypes.LPARAM]

        self._thread_id = kernel32.GetCurrentThreadId()
        names = {}
        for index, (name, shortcut, flags, vk) in enumerate(parsed, start=1):
            if user32.RegisterHotKey(None, index, flags, vk):
                names[index] = name
            else:
                self._problems.append(t(
                    "{shortcut} is already taken by another application, so Dikte "
                    "cannot use it. Pick another combination under "
                    "Settings → Shortcut.", shortcut=shortcut))
        self._ready.set()
        try:
            if not names:
                return
            message = wintypes.MSG()
            while True:
                got = user32.GetMessageW(ctypes.byref(message), None, 0, 0)
                if got in (0, -1):     # WM_QUIT, or the queue fell over
                    break
                if message.message == WM_HOTKEY:
                    name = names.get(message.wParam)
                    if name:
                        self.triggered.emit(name)
        finally:
            for index in names:
                user32.UnregisterHotKey(None, index)
            # Thread ids come round again like pids do, and a WM_QUIT posted to
            # a number this thread no longer owns would land on somebody else's.
            self._thread_id = 0


Hotkey = WinHotkey if plat.WINDOWS else EvdevHotkey


def listener_swallows_key():
    """Whether the listener takes the key press away from the focused window."""
    return plat.WINDOWS


def listener_label():
    """What the checkbox that turns the listener on says."""
    if plat.WINDOWS:
        return t("Register the shortcut with Windows")
    return t("Use the built-in listener (/dev/input), for when the KDE shortcut is "
             "not active yet")


def listener_hint():
    """The tooltip on that checkbox."""
    if plat.WINDOWS:
        return t("This is what makes the shortcut work at all on Windows. "
                 "Leave it on.")
    return t("Works immediately, no session restart. The only difference: the key "
             "combination also reaches the focused application.")


def shortcut_note():
    """The paragraph under the shortcut settings."""
    if plat.WINDOWS:
        return t(
            "Windows keeps no list of shortcuts to install into, so Dikte asks "
            "for the combination itself while it runs, and has it from the "
            "moment it starts — no logout, and nothing else on the desktop sees "
            "the key while Dikte holds it. A combination another application "
            "already holds cannot be had at all; if that happens it is said "
            "here, and another one is the answer."
        )
    return t(
        "KWin only reads shortcut settings at startup. After 'Install' the "
        "shortcut shows up under System Settings → Shortcuts, but it will not "
        "fire until you log out and back in. Until then, use the built-in listener."
    )


# --- KDE custom shortcut --------------------------------------------------

def native_shortcuts():
    """Whether this desktop has a shortcut registry Dikte can write to."""
    return not plat.WINDOWS


def install_kde_shortcut(shortcut, exec_command, name="Dikte: start/stop recording",
                         desktop_id=DESKTOP_ID):
    """Write the desktop file and the kglobalshortcutsrc entry.

    KWin only reads that file at startup, so the entry goes live after the next
    login. Returns (True, message) or (False, error).
    """
    if plat.WINDOWS:
        return False, t("Windows has no shortcut registry to install into; the "
                        "listener above is what binds the key.")
    desktop_file = APPLICATIONS_DIR / desktop_id
    try:
        desktop_file.parent.mkdir(parents=True, exist_ok=True)
        desktop_file.write_text(
            "[Desktop Entry]\n"
            f"Exec={exec_command}\n"
            f"Name={name}\n"
            "NoDisplay=true\n"
            "StartupNotify=false\n"
            "Type=Application\n"
            "X-KDE-GlobalAccel-CommandShortcut=true\n",
            encoding="utf-8",
        )
    except OSError as exc:
        return False, t("Could not write the desktop file: {error}", error=exc)

    try:
        subprocess.run(
            ["kwriteconfig6", "--notify", "--file", "kglobalshortcutsrc",
             "--group", "services", "--group", desktop_id,
             "--key", "_launch", shortcut],
            capture_output=True, text=True, timeout=10, check=True,
        )
    except (subprocess.SubprocessError, OSError) as exc:
        return False, t("Could not write kglobalshortcutsrc: {error}", error=exc)

    return True, t(
        "Shortcut saved: {shortcut}\nKWin only reads this file at startup, so it "
        "will not fire until you log out and back in. To use it right away, turn "
        "on the built-in listener.",
        shortcut=shortcut,
    )


def remove_kde_shortcut(desktop_id=DESKTOP_ID):
    if plat.WINDOWS:
        return
    try:
        (APPLICATIONS_DIR / desktop_id).unlink(missing_ok=True)
    except OSError:
        pass
    try:
        subprocess.run(
            ["kwriteconfig6", "--notify", "--file", "kglobalshortcutsrc",
             "--group", "services", "--group", desktop_id, "--key", "_launch", "--delete"],
            capture_output=True, timeout=10,
        )
    except (subprocess.SubprocessError, OSError):
        pass


def kde_shortcut_status(desktop_id=DESKTOP_ID):
    """The registered shortcut, or None."""
    if plat.WINDOWS or not (APPLICATIONS_DIR / desktop_id).exists():
        return None
    try:
        text = SHORTCUTS_FILE.read_text(encoding="utf-8")
    except OSError:
        return None
    match = re.search(
        r"\[services\]\[" + re.escape(desktop_id) + r"\]\n_launch=([^\n]*)", text
    )
    if not match:
        return None
    value = match.group(1).split("\t")[0].strip()
    return value or None


def conflicting_shortcuts(shortcut, desktop_id=DESKTOP_ID):
    """Names of other KDE entries bound to the same combination."""
    if plat.WINDOWS:
        # Windows keeps no list to read: a combination somebody else holds is
        # only discovered by asking for it, and start() reports what came back.
        return []
    try:
        text = SHORTCUTS_FILE.read_text(encoding="utf-8")
    except OSError:
        return []
    hits, section = [], ""
    for line in text.splitlines():
        if line.startswith("["):
            section = line.strip("[]").replace("][", " / ")
            continue
        if "=" not in line or desktop_id in section:
            continue
        key, _, value = line.partition("=")
        if shortcut.lower() in value.lower().split(","):
            hits.append(f"{section} → {key}")
        elif any(shortcut.lower() == part.strip().lower()
                 for part in re.split(r"[,\t]", value)):
            hits.append(f"{section} → {key}")
    return hits
