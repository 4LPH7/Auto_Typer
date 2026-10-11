"""Typing engine: a worker thread that types tokenized text via an injected writer.

The engine owns its lifecycle (start / pause / resume / stop), types in small
chunks so stop and pause stay responsive, and reports progress and completion
through thread-safe callbacks. GUI code wraps the callbacks with
``widget.after(...)`` to marshal them onto the Tk main loop.
"""

from __future__ import annotations

import random
import threading
import time
from collections.abc import Callable
from typing import Protocol

from .config import Settings
from .keys import SpecialKey, apply_caps_mode, tokenize

_TOKENS_PER_CHUNK = 8

# pyautogui applies a hidden 0.1 s pause after every call by default, which
# would make typed output ~10x slower than the requested speed. Callers using
# pyautogui should set ``pyautogui.PAUSE = 0`` once at startup.


class Writer(Protocol):
    """Something that can type a chunk of text, pressing *keys* for SpecialKeys."""

    def __call__(self, chunk: str, keys: list[str], interval: float) -> None: ...


def pyautogui_writer(chunk: str, keys: list[str], interval: float) -> None:
    """Default writer backed by pyautogui (imported lazily for testability)."""
    import pyautogui

    if chunk:
        pyautogui.write(chunk, interval=interval)
    for key in keys:
        pyautogui.press(key)
        time.sleep(interval)


class TypingEngine:
    """Runs typing sessions on a daemon thread with pause/stop support."""

    def __init__(
        self,
        writer: Writer = pyautogui_writer,
        *,
        on_countdown: Callable[[int], None] | None = None,
        on_progress: Callable[[int, int], None] | None = None,
        on_complete: Callable[[float, int], None] | None = None,
    ) -> None:
        """Callbacks receive: countdown seconds remaining, (chars done, total),
        and (elapsed seconds, completed iterations) respectively."""
        self._writer = writer
        self._on_countdown = on_countdown
        self._on_progress = on_progress
        self._on_complete = on_complete

        self._stop = threading.Event()
        self._pause = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._iteration = 0
        self._started_at: float | None = None
        self._last_elapsed = 0.0

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

    def resume(self) -> None:
        if not self._stop.is_set():
            self._pause.clear()

    def _wait(self, seconds: float) -> None:
        """Sleep that wakes early on stop."""
        self._stop.wait(seconds)

    def _run(self, text: str, settings: Settings) -> None:
        started = time.perf_counter()
        tokens = tokenize(apply_caps_mode(text, settings.caps_mode))
        total = sum(len(t) if isinstance(t, str) else 1 for t in tokens)
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

    def _run_one(self, tokens: list[str | SpecialKey], total: int, settings: Settings) -> bool:
        """Type the token list once. Returns False if stopped."""
        self._countdown(settings.start_countdown_s)
        if self._stop.is_set():
            return False

        done = 0
        for chunk_tokens in self._chunks(tokens):
            if not self._wait_if_paused():
                return False
            chunk, keys, width = self._materialize(chunk_tokens)
            self._writer(chunk, keys, self._interval(settings.speed_ms, settings))
            done += width
            if self._on_progress:
                self._on_progress(done, total)
            if isinstance(chunk_tokens[-1], str) and chunk_tokens[-1].isspace():
                # Word boundary: apply the configured between-words delay.
                if not self._wait_if_paused():
                    return False
                self._wait(settings.delay_ms / 1000.0)
        return True

    @staticmethod
    def _chunks(tokens: list[str | SpecialKey], limit: int = _TOKENS_PER_CHUNK):
        """Yield token batches of at most *limit*, breaking early at word
        boundaries so the between-words delay lands after a full word."""
        batch: list[str | SpecialKey] = []
        for i, token in enumerate(tokens):
            batch.append(token)
            next_is_space = (
                i + 1 < len(tokens) and isinstance(tokens[i + 1], str) and tokens[i + 1].isspace()
            )
            if len(batch) >= limit or (len(batch) >= limit // 2 and next_is_space):
                yield batch
                batch = []
        if batch:
            yield batch

    @staticmethod
    def _materialize(tokens: list[str | SpecialKey]) -> tuple[str, list[str], int]:
        """Split tokens into (text chunk, special keys to press, progress width)."""
        chars: list[str] = []
        keys: list[str] = []
        width = 0
        for token in tokens:
            width += len(token) if isinstance(token, str) else 1
            if isinstance(token, SpecialKey):
                keys.append(token.name)
            else:
                chars.append(token)
        return "".join(chars), keys, width

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

    def _wait_if_paused(self) -> bool:
        """Block while paused. Returns False if stopped."""
        while self._pause.is_set():
            if self._stop.is_set():
                return False
            time.sleep(0.05)
        return True
