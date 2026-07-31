"""The clipboard, and the key press that empties it into the focused window.

On Linux both are somebody else's program: wl-clipboard owns the selection and
ydotool types into whatever has focus. Windows has the two built into the
system, so they are called directly through ctypes — the clipboard through
user32's own API, and the key press through SendInput, which is the same call
the keyboard driver makes and so is indistinguishable from a real one.
"""

import contextlib
import shutil
import subprocess
import time

import plat
from i18n import t

# Linux input event codes (linux/input-event-codes.h)
KEYCODES = {
    "ctrl": 29, "control": 29, "shift": 42, "alt": 56, "super": 125, "meta": 125,
    "v": 47, "insert": 110, "enter": 28, "return": 28,
}

# Windows virtual-key codes (winuser.h)
VK = {
    "ctrl": 0x11, "control": 0x11, "shift": 0x10, "alt": 0x12,
    "super": 0x5B, "meta": 0x5B,
    "v": 0x56, "insert": 0x2D, "enter": 0x0D, "return": 0x0D,
}
# Keys that live on the grey block rather than the numeric pad. Without the
# extended flag Insert is read as the keypad 0 next to it.
VK_EXTENDED = {0x2D}


class PasteError(Exception):
    pass


# --- Windows --------------------------------------------------------------

if plat.WINDOWS:
    import ctypes
    from ctypes import wintypes

    _user32 = ctypes.WinDLL("user32", use_last_error=True)
    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    CF_UNICODETEXT = 13
    GMEM_MOVEABLE = 0x0002

    _user32.OpenClipboard.argtypes = [wintypes.HWND]
    _user32.OpenClipboard.restype = wintypes.BOOL
    _user32.CloseClipboard.restype = wintypes.BOOL
    _user32.EmptyClipboard.restype = wintypes.BOOL
    _user32.GetClipboardData.argtypes = [wintypes.UINT]
    _user32.GetClipboardData.restype = wintypes.HANDLE
    _user32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
    _user32.SetClipboardData.restype = wintypes.HANDLE
    _kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
    _kernel32.GlobalAlloc.restype = wintypes.HGLOBAL
    _kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
    _kernel32.GlobalLock.restype = ctypes.c_void_p
    _kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
    _kernel32.GlobalFree.argtypes = [wintypes.HGLOBAL]
    _kernel32.GlobalFree.restype = wintypes.HGLOBAL

    ULONG_PTR = (ctypes.c_uint64 if ctypes.sizeof(ctypes.c_void_p) == 8
                 else ctypes.c_uint32)

    class _MOUSEINPUT(ctypes.Structure):
        _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG),
                    ("mouseData", wintypes.DWORD), ("dwFlags", wintypes.DWORD),
                    ("time", wintypes.DWORD), ("dwExtraInfo", ULONG_PTR)]

    class _KEYBDINPUT(ctypes.Structure):
        _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD),
                    ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD),
                    ("dwExtraInfo", ULONG_PTR)]

    class _HARDWAREINPUT(ctypes.Structure):
        _fields_ = [("uMsg", wintypes.DWORD), ("wParamL", wintypes.WORD),
                    ("wParamH", wintypes.WORD)]

    class _INPUTUNION(ctypes.Union):
        _fields_ = [("mi", _MOUSEINPUT), ("ki", _KEYBDINPUT), ("hi", _HARDWAREINPUT)]

    class _INPUT(ctypes.Structure):
        _anonymous_ = ("u",)
        _fields_ = [("type", wintypes.DWORD), ("u", _INPUTUNION)]

    _user32.SendInput.argtypes = [wintypes.UINT, ctypes.POINTER(_INPUT), ctypes.c_int]
    _user32.SendInput.restype = wintypes.UINT

    INPUT_KEYBOARD = 1
    KEYEVENTF_EXTENDEDKEY = 0x0001
    KEYEVENTF_KEYUP = 0x0002

    @contextlib.contextmanager
    def _clipboard(attempts=20, pause=0.05):
        """The clipboard is one object shared by every window on the desktop, and
        only one of them may hold it open. Another application copying at the
        same moment is a wait, not a failure, so it is given a second."""
        for _ in range(attempts):
            if _user32.OpenClipboard(None):
                break
            time.sleep(pause)
        else:
            raise PasteError(t(
                "The clipboard is held by another application. Try again."))
        try:
            yield
        finally:
            _user32.CloseClipboard()

    def _win_copy(text):
        buffer = ctypes.create_unicode_buffer(text)
        size = ctypes.sizeof(buffer)
        handle = _kernel32.GlobalAlloc(GMEM_MOVEABLE, size)
        if not handle:
            raise PasteError(t("Could not copy to clipboard: {error}",
                               error="GlobalAlloc"))
        pointer = _kernel32.GlobalLock(handle)
        if not pointer:
            _kernel32.GlobalFree(handle)
            raise PasteError(t("Could not copy to clipboard: {error}",
                               error="GlobalLock"))
        ctypes.memmove(pointer, buffer, size)
        _kernel32.GlobalUnlock(handle)
        with _clipboard():
            _user32.EmptyClipboard()
            # Once this succeeds the system owns the block; freeing it here
            # would hand the desktop a pointer into memory nobody holds.
            if not _user32.SetClipboardData(CF_UNICODETEXT, handle):
                error = ctypes.get_last_error()
                _kernel32.GlobalFree(handle)
                raise PasteError(t("Could not copy to clipboard: {error}",
                                   error=f"SetClipboardData ({error})"))

    def _win_read():
        try:
            with _clipboard(attempts=4):
                handle = _user32.GetClipboardData(CF_UNICODETEXT)
                if not handle:
                    return None
                pointer = _kernel32.GlobalLock(handle)
                if not pointer:
                    return None
                try:
                    return ctypes.wstring_at(pointer)
                finally:
                    _kernel32.GlobalUnlock(handle)
        except PasteError:
            return None

    def _win_press(codes):
        def event(code, up):
            flags = KEYEVENTF_KEYUP if up else 0
            if code in VK_EXTENDED:
                flags |= KEYEVENTF_EXTENDEDKEY
            item = _INPUT(type=INPUT_KEYBOARD)
            item.ki = _KEYBDINPUT(wVk=code, wScan=0, dwFlags=flags,
                                  time=0, dwExtraInfo=0)
            return item

        events = ([event(code, False) for code in codes]
                  + [event(code, True) for code in reversed(codes)])
        array = (_INPUT * len(events))(*events)
        sent = _user32.SendInput(len(events), array, ctypes.sizeof(_INPUT))
        if sent != len(events):
            raise PasteError(t(
                "The key press did not go through ({error}). A window running as "
                "administrator only accepts one from an application running as "
                "administrator too.", error=ctypes.get_last_error()))


# --- the interface the rest of Dikte uses ---------------------------------

def read_clipboard():
    """What is on the clipboard now, as bytes, or None.

    Bytes rather than text because it is only ever handed back to copy_bytes:
    what was there before a dictation is restored unread.
    """
    if plat.WINDOWS:
        text = _win_read()
        return text.encode("utf-8") if text is not None else None
    if not shutil.which("wl-paste"):
        return None
    try:
        res = subprocess.run(["wl-paste", "--no-newline"], capture_output=True, timeout=5)
    except (subprocess.SubprocessError, OSError):
        return None
    return res.stdout if res.returncode == 0 else None


def _run_wl_copy(payload):
    """wl-copy forks to keep owning the selection; leaving its pipes open makes
    subprocess.run wait for EOF forever, hence DEVNULL."""
    return subprocess.run(
        ["wl-copy"],
        input=payload,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=10,
    )


def copy(text):
    if plat.WINDOWS:
        _win_copy(text)
        return
    if not shutil.which("wl-copy"):
        raise PasteError(t("wl-copy not found. Install wl-clipboard."))
    try:
        res = _run_wl_copy(text.encode("utf-8"))
    except (subprocess.SubprocessError, OSError) as exc:
        raise PasteError(t("Could not copy to clipboard: {error}", error=exc)) from exc
    if res.returncode != 0:
        raise PasteError(t("wl-copy exited with code {code}.", code=res.returncode))


def copy_bytes(data):
    if data is None:
        return
    if plat.WINDOWS:
        with contextlib.suppress(PasteError, UnicodeDecodeError):
            _win_copy(data.decode("utf-8"))
        return
    if not shutil.which("wl-copy"):
        return
    try:
        _run_wl_copy(data)
    except (subprocess.SubprocessError, OSError):
        pass


def paste_ready():
    """Whether a key press can be sent into the focused window at all."""
    if plat.WINDOWS:
        return True
    return shutil.which("ydotool") is not None


def press(shortcut="ctrl+v", delay=0.12):
    """Press a key combination in the focused window, e.g. 'ctrl+v'."""
    table = VK if plat.WINDOWS else KEYCODES
    if not paste_ready():
        raise PasteError(t("ydotool not found, cannot paste automatically."))

    codes = []
    for key in (k.strip().lower() for k in shortcut.split("+") if k.strip()):
        code = table.get(key)
        if code is None:
            raise PasteError(t("Unknown key: {key}", key=key))
        codes.append(code)
    if not codes:
        raise PasteError(t("Unknown key: {key}", key=shortcut))

    time.sleep(delay)  # let the selection settle and focus come back
    if plat.WINDOWS:
        _win_press(codes)
        return

    seq = [f"{c}:1" for c in codes] + [f"{c}:0" for c in reversed(codes)]
    try:
        res = subprocess.run(["ydotool", "key", *seq], capture_output=True,
                             text=True, timeout=10)
    except (subprocess.SubprocessError, OSError) as exc:
        raise PasteError(t("Could not run ydotool: {error}", error=exc)) from exc
    if res.returncode != 0:
        raise PasteError(t(
            "ydotool failed: {error}\nIs ydotoold running? "
            "(systemctl --user status ydotool)",
            error=res.stderr.strip() or "unknown error",
        ))
