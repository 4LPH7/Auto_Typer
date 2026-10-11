"""Global hotkey handling via pynput.

The listener runs on its own daemon thread; it never touches Tk directly.
Instead it invokes callbacks which the GUI marshals onto the main loop.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Any

from pynput import keyboard

# Modifier keys that may be part of a registered combination.
_MODIFIER_NAMES = {"ctrl", "ctrl_l", "ctrl_r", "alt", "alt_l", "alt_r",
                   "shift", "shift_l", "shift_r", "cmd", "cmd_l", "cmd_r", "win"}


def _key_name(key: Any) -> str | None:
    """Canonical name for *key*, or None if unnameable."""
    if isinstance(key, keyboard.KeyCode):
        return key.char.lower() if key.char else None
    return getattr(key, "name", None)


def _is_modifier(name: str | None) -> bool:
    return name in _MODIFIER_NAMES


class HotkeyManager:
    """Listens for a registered combination and supports live re-capture."""

    def __init__(
        self,
        *,
        on_trigger: Callable[[], None],
        on_stop: Callable[[], None],
        on_captured: Callable[[list[str]], None],
    ) -> None:
        """``on_captured`` receives the canonical key names of the pressed
        combination when a capture completes."""
        self._on_trigger = on_trigger
        self._on_stop = on_stop
        self._on_captured = on_captured

        self._lock = threading.Lock()
        self._hotkey: frozenset[str] = frozenset()
        self._pressed: set[str] = set()
        self._capturing = False
        self._listener: keyboard.Listener | None = None

    def set_hotkey(self, names: list[str]) -> None:
        with self._lock:
            self._hotkey = frozenset(names)

    def hotkey_names(self) -> list[str]:
        return sorted(self._hotkey)

    @staticmethod
    def format_names(names: list[str] | set[str]) -> str:
        """Human-readable label, e.g. ``Ctrl+Alt+T``."""
        parts = [n.capitalize() for n in sorted(names)]
        return "+".join(parts) if parts else "Not Set"

    def begin_capture(self) -> None:
        with self._lock:
            self._capturing = True
            self._pressed.clear()

    def start(self) -> None:
        self._listener = keyboard.Listener(on_press=self._on_press, on_release=self._on_release)
        self._listener.daemon = True
        self._listener.start()

    def stop(self) -> None:
        if self._listener:
            self._listener.stop()

    def _on_press(self, key: Any) -> None:
        name = _key_name(key)
        if name is None:
            return

        fire_captured: list[str] | None = None
        fire_trigger = False
        with self._lock:
            self._pressed.add(name)
            if self._capturing:
                # Capture completes as soon as a non-modifier joins the
                # combination; a bare modifier completes on its release.
                if not _is_modifier(name):
                    fire_captured = sorted(self._pressed)
                    self._hotkey = frozenset(fire_captured)
                    self._capturing = False
            elif self._hotkey and self._pressed == set(self._hotkey):
                fire_trigger = True

        if fire_captured is not None:
            self._on_captured(fire_captured)
        elif fire_trigger:
            self._on_trigger()

    def _on_release(self, key: Any) -> None:
        name = _key_name(key)

        fire_captured: list[str] | None = None
        with self._lock:
            if name:
                self._pressed.discard(name)
                if self._capturing and not self._pressed:
                    # Everything released: capture a bare-modifier hotkey
                    # (single-key captures complete on press instead).
                    fire_captured = [name]
                    self._hotkey = frozenset(fire_captured)
                    self._capturing = False

        if fire_captured is not None:
            self._on_captured(fire_captured)
        if name == "esc":
            self._on_stop()
