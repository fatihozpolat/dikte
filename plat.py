"""What the two platforms do differently, kept in one place.

Dikte was written for KDE on Wayland and reads that way throughout: a recording
comes off pw-record, the clipboard is wl-clipboard, a key press is ydotool, the
shortcut is KWin's. Windows has an answer for every one of those and shares the
name of none of them, so the modules that need one ask here rather than each
growing a sys.platform check of its own.
"""

import os
import pathlib
import signal
import subprocess
import sys

WINDOWS = sys.platform.startswith("win")

# A tray application started from pythonw.exe has no console of its own, and
# every child it starts would open one for the fraction of a second it runs:
# ffmpeg for each recording, whisper-server for the model, the agent's CLI.
# CREATE_NO_WINDOW is what keeps those black rectangles from flashing over
# whatever the user is actually looking at.
CREATE_NO_WINDOW = 0x08000000


def quiet():
    """Popen/run keyword arguments that keep a child from opening a console."""
    return {"creationflags": CREATE_NO_WINDOW} if WINDOWS else {}


def config_home():
    """Where settings live: %APPDATA% on Windows, $XDG_CONFIG_HOME otherwise."""
    if WINDOWS:
        return pathlib.Path(os.environ.get("APPDATA")
                            or pathlib.Path.home() / "AppData" / "Roaming")
    return pathlib.Path(os.environ.get("XDG_CONFIG_HOME")
                        or os.path.expanduser("~/.config"))


def data_home():
    """Where the models, the recordings and the history live."""
    if WINDOWS:
        return pathlib.Path(os.environ.get("LOCALAPPDATA")
                            or pathlib.Path.home() / "AppData" / "Local")
    return pathlib.Path(os.environ.get("XDG_DATA_HOME")
                        or os.path.expanduser("~/.local/share"))


def user_tag():
    """Something short and unique to this user, for the IPC socket's name."""
    if WINDOWS:
        name = os.environ.get("USERNAME") or "user"
        return "".join(ch for ch in name if ch.isalnum()) or "user"
    return str(os.getuid())


def interrupt(proc, timeout=2.0):
    """End a child that is streaming into a pipe, the gentle way first.

    SIGINT is what pw-record and ffmpeg both read as "stop and close down".
    Windows has no such signal to send to another process, so it is terminated
    instead, and nothing is lost by that: the audio has already been read out of
    the pipe and is held here rather than inside the child.
    """
    if proc is None or proc.poll() is not None:
        return
    try:
        if WINDOWS:
            proc.terminate()
        else:
            proc.send_signal(signal.SIGINT)
        proc.wait(timeout=timeout)
    except (subprocess.TimeoutExpired, OSError):
        try:
            proc.kill()
        except OSError:
            pass


def terminate_pid(pid):
    """Kill a process this one did not start. True when the signal went out."""
    try:
        # os.kill on Windows is TerminateProcess, which is what is wanted here:
        # the server being swept up is a leftover, and there is nothing of it
        # worth shutting down carefully.
        os.kill(pid, signal.SIGTERM)
    except OSError:
        return False
    return True


def process_identity(pid):
    """Something that tells one process apart from the next holder of its pid.

    The program it is running and the moment it started. Pids come round again;
    a pid that came round onto a process running the same program and started at
    the same hundred nanoseconds did not.

    Empty when the process is gone, or when it belongs to somebody else and this
    one may not look at it — which for the purpose this is put to reads the same
    way: not ours, leave it alone.
    """
    if not WINDOWS:
        return ""
    import ctypes
    from ctypes import wintypes

    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.QueryFullProcessImageNameW.argtypes = [
        wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)
    ]
    kernel32.GetProcessTimes.argtypes = [wintypes.HANDLE] + [
        ctypes.POINTER(wintypes.FILETIME)] * 4

    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid))
    if not handle:
        return ""
    try:
        size = wintypes.DWORD(32768)
        image = ctypes.create_unicode_buffer(size.value)
        if not kernel32.QueryFullProcessImageNameW(handle, 0, image, ctypes.byref(size)):
            return ""
        created, exited, kernel, user = (wintypes.FILETIME() for _ in range(4))
        if not kernel32.GetProcessTimes(handle, ctypes.byref(created),
                                        ctypes.byref(exited), ctypes.byref(kernel),
                                        ctypes.byref(user)):
            return ""
        started = (created.dwHighDateTime << 32) | created.dwLowDateTime
        return f"{started}\t{image.value.lower()}"
    finally:
        kernel32.CloseHandle(handle)
