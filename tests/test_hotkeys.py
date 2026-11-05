"""Tests for HotkeyManager matching, fed with fake key events (no OS hook)."""

from pynput.keyboard import Key, KeyCode

from auto_typer.hotkeys import HotkeyManager


def make_manager(names: list[str]) -> tuple[HotkeyManager, list[str]]:
    fired: list[str] = []
    manager = HotkeyManager(
        on_trigger=lambda: fired.append("trigger"),
        on_stop=lambda: fired.append("stop"),
        on_captured=lambda captured: fired.append(f"captured {captured}"),
    )
    manager.set_hotkey(names)
    return manager, fired


def tap(manager: HotkeyManager, key, injected: bool) -> None:
    manager._on_press(key, injected)
    manager._on_release(key, injected)


def test_own_typing_never_triggers_hotkeys():
    # Regression: typing a passage containing the hotkey's character (".")
    # fired the hotkey, and a typed {Esc} stopped the session.
    manager, fired = make_manager(["."])
    tap(manager, KeyCode.from_char("."), injected=True)
    tap(manager, Key.esc, injected=True)
    assert fired == []


def test_real_key_presses_still_work():
    manager, fired = make_manager(["."])
    tap(manager, KeyCode.from_char("."), injected=False)
    tap(manager, Key.esc, injected=False)
    assert fired == ["trigger", "stop"]


def test_held_hotkey_fires_once():
    # Windows repeats key-down events while a key is held; a held Pause
    # hotkey used to toggle pause on and off with every repeat.
    manager, fired = make_manager(["f9"])
    for _ in range(5):
        manager._on_press(Key.f9, False)
    manager._on_release(Key.f9, False)
    assert fired == ["trigger"]


def test_capture_ignores_own_typing():
    manager, fired = make_manager([])
    manager.begin_capture()
    tap(manager, KeyCode.from_char("a"), injected=True)
    tap(manager, Key.f8, injected=False)
    assert fired == ["captured ['f8']"]


def test_ctrl_letter_matches_by_virtual_key():
    # Windows reports T as "" while Ctrl is held; Ctrl+T must still match.
    manager, fired = make_manager(["ctrl_l", "t"])
    manager._on_press(Key.ctrl_l, False)
    manager._on_press(KeyCode(vk=0x54, char=""), False)
    manager._on_release(KeyCode(vk=0x54, char=""), False)
    manager._on_release(Key.ctrl_l, False)
    assert fired == ["trigger"]


def test_capture_names_ctrl_letter_by_its_letter():
    manager, fired = make_manager([])
    manager.begin_capture()
    manager._on_press(Key.ctrl_l, False)
    manager._on_press(KeyCode(vk=0x54, char=""), False)
    assert fired == ["captured ['ctrl_l', 't']"]
    assert HotkeyManager.format_names(["t", "ctrl_l"]) == "Ctrl+T"
    assert HotkeyManager.format_names(["f8"]) == "F8"
    assert HotkeyManager.format_names([]) == "Not Set"
