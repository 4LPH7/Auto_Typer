"""Typing engine: a worker thread that types tokenized text via an injected writer.

The engine owns its lifecycle (start / pause / resume / stop), types in small
chunks so stop and pause stay responsive, and reports progress and completion
through thread-safe callbacks. GUI code wraps the callbacks with
``widget.after(...)`` to marshal them onto the Tk main loop.

Two things make the engine safer in use than a plain loop:

* the **focus guard** pauses the session if the active window changes while
  typing, so an alt-tab doesn't send the text somewhere else; and
* **paste mode** puts the text on the clipboard and presses Ctrl+V, for long
  texts into targets that allow pasting.
"""

from __future__ import annotations

import random
import threading
import time
from collections.abc import Callable, Iterator
from typing import Any, Protocol

from .config import Settings
from .keys import KeyCombo, Pause, SpecialKey, Token, apply_caps_mode, is_word_gap, tokenize
from .system import copy_text, foreground_window

_TOKENS_PER_CHUNK = 8
PASTE_KEY = "ctrl+v"
# The target reads the clipboard when it gets to the Ctrl+V, not when it's
# sent; wait this long before replacing the clipboard for the next paste.
PASTE_SETTLE_S = 0.2


class Writer(Protocol):
    """Something that can type a chunk of text, then press *keys*.

    Each key is a canonical special key name (``enter``, ``f5``) or a combo
    such as ``ctrl+shift+s``. *interval* is the pause after each keystroke.
    """

    def __call__(self, chunk: str, keys: list[str], interval: float) -> None: ...


class PynputWriter:
    """The default writer: pynput's controller, which sends Unicode input on
    Windows so accents, symbols and non-Latin scripts type correctly."""

    def __init__(self) -> None:
        self._controller: Any = None

    def __call__(self, chunk: str, keys: list[str], interval: float) -> None:
        from pynput.keyboard import Controller, Key, KeyCode

        if self._controller is None:
            self._controller = Controller()
        keyboard = self._controller
        named = _pynput_keys(Key)

        for char in chunk:
            if char == "\r":
                continue  # Windows line endings: the "\n" presses Enter
            keyboard.tap(named.get(char) or KeyCode.from_char(char))
            time.sleep(interval)
        for name in keys:
            *modifiers, last = name.split("+")
            key = named.get(last) or KeyCode.from_char(last)
            with keyboard.pressed(*(named[m] for m in modifiers)):
                keyboard.tap(key)
            time.sleep(interval)


_PYNPUT_NAMES = {
    "enter": "enter", "\n": "enter", "tab": "tab", "\t": "tab", "space": "space",
    "backspace": "backspace", "delete": "delete", "esc": "esc",
    "up": "up", "down": "down", "left": "left", "right": "right",
    "home": "home", "end": "end", "pageup": "page_up", "pagedown": "page_down",
    "win": "cmd", "ctrl": "ctrl", "alt": "alt", "shift": "shift",
    **{f"f{i}": f"f{i}" for i in range(1, 13)},
}


def _pynput_keys(key_enum: object) -> dict[str, object]:
    """Canonical key names (and newline / tab) mapped to pynput ``Key`` members."""
    return {name: getattr(key_enum, attr) for name, attr in _PYNPUT_NAMES.items()}


class TypingEngine:
    """Runs typing sessions on a daemon thread with pause/stop support."""

    def __init__(
        self,
        writer: Writer | None = None,
        *,
        clipboard: Callable[[str], None] = copy_text,
        foreground: Callable[[], object] = foreground_window,
        on_countdown: Callable[[int], None] | None = None,
        on_progress: Callable[[int, int], None] | None = None,
        on_complete: Callable[[float, int], None] | None = None,
        on_focus_lost: Callable[[], None] | None = None,
    ) -> None:
        """Callbacks receive: countdown seconds remaining, (chars done, total),
        (elapsed seconds, completed iterations), and nothing when the focus
        guard pauses the session."""
        self._writer: Writer = writer or PynputWriter()
        self._clipboard = clipboard
        self._foreground = foreground
        self._on_countdown = on_countdown
        self._on_progress = on_progress
        self._on_complete = on_complete
        self._on_focus_lost = on_focus_lost

        self._stop = threading.Event()
        self._pause = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._iteration = 0
        self._started_at: float | None = None
        self._last_elapsed = 0.0
        self._target: object = None  # the window typing goes into
        self._adopt = False  # send the next input to whichever window is active then
        self._resume_countdown = 0  # seconds to count down before adopting
        self._pasted_at: float | None = None  # when the last Ctrl+V was sent

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    @property
    def elapsed(self) -> float:
        """Seconds since the current session started, or the last session's total."""
        if self.running and self._started_at is not None:
            return time.perf_counter() - self._started_at
        return self._last_elapsed

    @property
    def paused(self) -> bool:
        return self._pause.is_set()

    def start(self, text: str, settings: Settings) -> bool:
        """Begin a typing session. Returns False if one is already running."""
        with self._lock:
            if self.running:
                return False
            self._stop.clear()
            self._pause.clear()
            self._iteration = 0
            self._adopt = False
            self._resume_countdown = 0
            self._pasted_at = None
            self._started_at = time.perf_counter()
            self._thread = threading.Thread(
                target=self._run, args=(text, settings), daemon=True, name="typing-engine"
            )
            self._thread.start()
            return True

    def stop(self) -> None:
        """Request the session to stop (interrupts countdown and pause)."""
        self._stop.set()
        self._pause.set()  # wake a paused worker so it can observe the stop

    def pause(self) -> None:
        self._pause.set()

    def resume(self, countdown_s: int = 0) -> None:
        """Continue typing into whichever window is active then, after counting
        down *countdown_s* seconds (time to click back into the target)."""
        if not self._stop.is_set():
            self._resume_countdown = countdown_s
            self._adopt = True
            self._pause.clear()

    def _wait(self, seconds: float) -> None:
        """Sleep that wakes early on stop."""
        self._stop.wait(seconds)

    def _run(self, text: str, settings: Settings) -> None:
        started = time.perf_counter()
        tokens = tokenize(apply_caps_mode(text, settings.caps_mode))
        total = sum(len(t) if isinstance(t, str) else 0 if isinstance(t, Pause) else 1 for t in tokens)
        loops = settings.loop_count or 10**9  # 0 = infinite

        for iteration in range(1, loops + 1):
            with self._lock:
                self._iteration = iteration
            if not self._run_one(tokens, total, settings):
                break

        with self._lock:
            self._last_elapsed = time.perf_counter() - started
            self._started_at = None
            completed = self._iteration if self._stop.is_set() else loops
        if self._on_complete:
            self._on_complete(self._last_elapsed, completed)

    def _run_one(self, tokens: list[Token], total: int, settings: Settings) -> bool:
        """Type the token list once. Returns False if stopped."""
        self._countdown(settings.start_countdown_s)
        if self._stop.is_set():
            return False
        self._target = self._foreground()

        done = 0
        for chunk_tokens in self._chunks(tokens, paste=settings.paste_mode):
            chunk, keys, pause, width = self._materialize(chunk_tokens)
            if not self._wait_for_focus(settings, sends=bool(chunk or keys)):
                return False
            interval = self._interval(settings.speed_ms, settings)
            if settings.paste_mode and chunk:
                self._settle_paste()
                self._clipboard(chunk)
                self._writer("", [PASTE_KEY, *keys], interval)
                self._pasted_at = time.monotonic()
            elif chunk or keys:
                self._writer(chunk, keys, interval)
            done += width
            if self._on_progress:
                self._on_progress(done, total)
            if pause:
                self._wait(pause)
                self._adopt = True  # a {Sleep} hands over to the window that's active after it
            if not settings.paste_mode and is_word_gap(chunk_tokens[-1]):
                # Word boundary: apply the configured between-words delay.
                if not self._wait_if_paused():
                    return False
                self._wait(settings.delay_ms / 1000.0)
        return True

    @staticmethod
    def _chunks(tokens: list[Token], *, paste: bool = False) -> Iterator[list[Token]]:
        """Yield token batches: a run of characters, optionally ending with one
        key, combo or pause so those happen in order. Typing batches hold at
        most a few tokens and end after every word gap, so stop stays
        responsive and the between-words delay lands after each full word.
        Paste batches hold the whole run of text."""
        limit = 10**9 if paste else _TOKENS_PER_CHUNK
        batch: list[Token] = []
        for token in tokens:
            batch.append(token)
            if not isinstance(token, str) or len(batch) >= limit or (not paste and is_word_gap(token)):
                yield batch
                batch = []
        if batch:
            yield batch

    @staticmethod
    def _materialize(tokens: list[Token]) -> tuple[str, list[str], float, int]:
        """Split tokens into (text chunk, keys to press, seconds to pause, progress width)."""
        chars: list[str] = []
        keys: list[str] = []
        pause = 0.0
        width = 0
        for token in tokens:
            if isinstance(token, str):
                chars.append(token)
                width += len(token)
            elif isinstance(token, SpecialKey | KeyCombo):
                keys.append(token.name)
                width += 1
            else:
                pause += token.seconds
        return "".join(chars), keys, pause, width

    def _countdown(self, seconds: int) -> None:
        for remaining in range(seconds, 0, -1):
            if self._stop.is_set():
                return
            if self._on_countdown:
                self._on_countdown(remaining)
            self._wait(1)

    @staticmethod
    def _interval(speed_ms: int, settings: Settings) -> float:
        base = speed_ms / 1000.0
        if settings.human_jitter_pct:
            jitter = settings.human_jitter_pct / 100.0
            base *= 1 + random.uniform(-jitter, jitter)
        return max(0.0, base)

    def _wait_for_focus(self, settings: Settings, *, sends: bool) -> bool:
        """Block while paused and, before sending input, make sure it goes to
        the target window: the one typing started in, or after a resume or a
        ``{Sleep}`` whichever window is active then. That lets a script open a
        window and type into it: ``{Win+R}{Sleep 500}notepad{Enter}``.
        Returns False if stopped."""
        while True:
            if not self._wait_if_paused():
                return False
            if not sends:
                return True
            if self._adopt:
                self._adopt = False
                countdown, self._resume_countdown = self._resume_countdown, 0
                self._countdown(countdown)
                if self._stop.is_set():
                    return False
                self._target = self._foreground()
                return True
            if (
                settings.focus_guard
                and self._target is not None
                and self._foreground() != self._target
            ):
                self._pause.set()
                if self._on_focus_lost:
                    self._on_focus_lost()
                continue  # wait for a resume, which adopts the new window
            return True

    def _settle_paste(self) -> None:
        """Before replacing the clipboard, give the target time to paste the
        previous text; otherwise it may paste the new text twice."""
        if self._pasted_at is not None:
            remaining = PASTE_SETTLE_S - (time.monotonic() - self._pasted_at)
            if remaining > 0:
                self._wait(remaining)

    def _wait_if_paused(self) -> bool:
        """Block while paused. Returns False if stopped."""
        while self._pause.is_set():
            if self._stop.is_set():
                return False
            time.sleep(0.05)
        return True
