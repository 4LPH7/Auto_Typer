"""Small Windows integrations: the clipboard, the foreground window, autostart.

Each function degrades gracefully elsewhere so the engine and tests run on any
platform; only Windows gets the real behaviour.
"""

from __future__ import annotations

import ctypes
import os
import sys
import time
from pathlib import Path

_IS_WINDOWS = sys.platform == "win32"

# ------------------------------------------------------------------ clipboard

_CF_UNICODETEXT = 13
_GMEM_MOVEABLE = 0x0002

if _IS_WINDOWS:
    _user32 = ctypes.windll.user32
    _kernel32 = ctypes.windll.kernel32
    _user32.OpenClipboard.argtypes = [ctypes.c_void_p]
    _user32.GetClipboardData.restype = ctypes.c_void_p
    _user32.SetClipboardData.argtypes = [ctypes.c_uint, ctypes.c_void_p]
    _user32.SetClipboardData.restype = ctypes.c_void_p
    _user32.GetForegroundWindow.restype = ctypes.c_void_p
    _user32.GetWindowThreadProcessId.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_ulong)]
    _kernel32.GlobalAlloc.argtypes = [ctypes.c_uint, ctypes.c_size_t]
    _kernel32.GlobalAlloc.restype = ctypes.c_void_p
    _kernel32.GlobalLock.argtypes = [ctypes.c_void_p]
    _kernel32.GlobalLock.restype = ctypes.c_void_p
    _kernel32.GlobalUnlock.argtypes = [ctypes.c_void_p]
    _kernel32.GlobalFree.argtypes = [ctypes.c_void_p]


def _open_clipboard() -> None:
    for _ in range(20):  # another program may hold the clipboard for a moment
        if _user32.OpenClipboard(None):
            return
        time.sleep(0.01)
    raise OSError("the clipboard is in use by another program")


def copy_text(text: str) -> None:
    """Put *text* on the clipboard."""
    if not _IS_WINDOWS:
        import pyperclip  # optional on other platforms

        pyperclip.copy(text)
        return
    data = text.encode("utf-16-le") + b"\x00\x00"
    _open_clipboard()
    try:
        _user32.EmptyClipboard()
        handle = _kernel32.GlobalAlloc(_GMEM_MOVEABLE, len(data))
        if not handle:
            raise OSError("out of memory for the clipboard")
        ctypes.memmove(_kernel32.GlobalLock(handle), data, len(data))
        _kernel32.GlobalUnlock(handle)
        if not _user32.SetClipboardData(_CF_UNICODETEXT, handle):
            _kernel32.GlobalFree(handle)
            raise OSError("couldn't write to the clipboard")
    finally:
        _user32.CloseClipboard()


def read_text() -> str:
    """The clipboard's text, or "" if it holds none."""
    if not _IS_WINDOWS:
        import pyperclip

        return str(pyperclip.paste())
    _open_clipboard()
    try:
        handle = _user32.GetClipboardData(_CF_UNICODETEXT)
        if not handle:
            return ""
        pointer = _kernel32.GlobalLock(handle)
        try:
            return ctypes.wstring_at(pointer)
        finally:
            _kernel32.GlobalUnlock(handle)
    finally:
        _user32.CloseClipboard()


# ----------------------------------------------------------- foreground window


def foreground_window() -> int | None:
    """A handle identifying the window that has focus, or None if unknown."""
    if not _IS_WINDOWS:
        return None
    return _user32.GetForegroundWindow() or None


def foreground_is_ours() -> bool:
    """True if the window that has focus belongs to Auto Typer itself."""
    if not _IS_WINDOWS:
        return False
    hwnd = _user32.GetForegroundWindow()
    if not hwnd:
        return False
    pid = ctypes.c_ulong()
    _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return pid.value == os.getpid()


# ------------------------------------------------------------------ autostart

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_VALUE = "AutoTyper"


def autostart_command() -> str:
    """The command Windows should run at sign-in to start this copy hidden."""
    if getattr(sys, "frozen", False):  # the PyInstaller exe
        return f'"{sys.executable}" --hidden'
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    python = pythonw if pythonw.exists() else Path(sys.executable)
    return f'"{python}" -m auto_typer --hidden'


def autostart_enabled(key: str = RUN_KEY) -> bool:
    """True if Windows is set to start Auto Typer at sign-in."""
    if not _IS_WINDOWS:
        return False
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key) as run:
            value, _ = winreg.QueryValueEx(run, RUN_VALUE)
            return bool(value)
    except OSError:
        return False


def set_autostart(enabled: bool, key: str = RUN_KEY) -> None:
    """Make Windows start (or stop starting) Auto Typer at sign-in.

    Re-registering while enabled refreshes the command, so a moved exe keeps
    working. Does nothing on other platforms.
    """
    if not _IS_WINDOWS:
        return
    import winreg

    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, key) as run:
        if enabled:
            winreg.SetValueEx(run, RUN_VALUE, 0, winreg.REG_SZ, autostart_command())
        else:
            try:
                winreg.DeleteValue(run, RUN_VALUE)
            except FileNotFoundError:
                pass
