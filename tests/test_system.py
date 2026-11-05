"""Tests for the Windows integrations; they run only where the real thing exists."""

import sys

import pytest

from auto_typer import system

windows_only = pytest.mark.skipif(sys.platform != "win32", reason="Windows integration")


@windows_only
def test_clipboard_round_trip_keeps_unicode():
    before = system.read_text()
    try:
        system.copy_text("café — 你好 🙂\nline two")
        assert system.read_text() == "café — 你好 🙂\nline two"
    finally:
        system.copy_text(before)


@windows_only
def test_foreground_window_is_a_handle():
    assert isinstance(system.foreground_window(), int | None)


@windows_only
def test_autostart_toggles_a_run_entry():
    import winreg

    key = r"Software\AutoTyperTests\Run"
    try:
        assert not system.autostart_enabled(key)
        system.set_autostart(True, key)
        assert system.autostart_enabled(key)
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key) as run:
            command, _ = winreg.QueryValueEx(run, system.RUN_VALUE)
        assert command == system.autostart_command()
        assert command.endswith("--hidden")
        system.set_autostart(False, key)
        assert not system.autostart_enabled(key)
        system.set_autostart(False, key)  # removing twice is fine
    finally:
        try:
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER, key)
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER, r"Software\AutoTyperTests")
        except OSError:
            pass


def test_autostart_command_quotes_the_program():
    command = system.autostart_command()
    assert command.startswith('"') and command.endswith(" --hidden")
