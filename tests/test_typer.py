"""Tests for the TypingEngine, using a fake writer (no GUI or OS automation)."""

import threading
import time

import pytest

from auto_typer.config import Settings
from auto_typer.keys import CapsMode
from auto_typer.typer import PASTE_KEY, PASTE_SETTLE_S, TypingEngine


class FakeWriter:
    """Records writer calls; can block at a chosen call index for test control."""

    def __init__(self, block_after: int | None = None, gate: threading.Event | None = None):
        self.calls: list[tuple[str, list[str], float]] = []
        self.block_after = block_after  # block on call number block_after + 1
        self.gate = gate or threading.Event()

    def __call__(self, chunk: str, keys: list[str], interval: float) -> None:
        if self.block_after is not None and len(self.calls) >= self.block_after:
            self.gate.wait(5)
        self.calls.append((chunk, keys, interval))


class FakeDesktop:
    """Stands in for the clipboard and the foreground window."""

    def __init__(self) -> None:
        self.clipboard: list[str] = []
        self.window = "editor"
        self.focus_lost = 0


def make_engine(writer=None, desktop: FakeDesktop | None = None, **callbacks) -> TypingEngine:
    desktop = desktop or FakeDesktop()
    return TypingEngine(
        writer or FakeWriter(),
        clipboard=desktop.clipboard.append,
        foreground=lambda: desktop.window,
        **callbacks,
    )


def quick(**changes) -> Settings:
    return Settings(speed_ms=0, start_countdown_s=0, **changes)


def run_engine(text: str, settings: Settings | None = None, writer=None, desktop=None):
    """Run the engine synchronously and return (writer, progress, result)."""
    writer = writer or FakeWriter()
    engine = make_engine(writer, desktop)
    settings = settings or quick()

    done = threading.Event()
    progress: list[tuple[int, int]] = []
    result: dict = {}

    engine._on_progress = lambda d, t: progress.append((d, t))
    engine._on_complete = lambda elapsed, iters: (result.update(
        elapsed=elapsed, iterations=iters), done.set())

    assert engine.start(text, settings)
    assert done.wait(10), "engine did not finish in time"
    return writer, progress, result


def typed_text(writer: FakeWriter) -> str:
    return "".join(chunk for chunk, _, _ in writer.calls)


def pressed_keys(writer: FakeWriter) -> list[str]:
    return [key for _, keys, _ in writer.calls for key in keys]


def wait_for(predicate, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return False


class TestTyping:
    def test_types_all_text(self):
        writer, _, _ = run_engine("hello world")
        assert typed_text(writer) == "hello world"

    def test_non_ascii_text_reaches_the_writer(self):
        writer, _, _ = run_engine("café — 你好 🙂")
        assert typed_text(writer) == "café — 你好 🙂"

    def test_special_keys_pressed_not_typed(self):
        writer, _, _ = run_engine("a{Enter}b{Tab}")
        assert typed_text(writer) == "ab"
        assert pressed_keys(writer) == ["enter", "tab"]

    def test_keys_happen_in_order_within_a_word(self):
        # Regression: "abc{Left}X" used to type "abcX" and press Left after,
        # because a chunk sent all its text before any of its keys.
        writer, _, _ = run_engine("abc{Left}{Backspace}X{F5}y")
        assert writer.calls == [
            ("abc", ["left"], 0), ("", ["backspace"], 0), ("X", ["f5"], 0), ("y", [], 0),
        ]

    def test_combos_are_pressed_as_one_key(self):
        writer, _, _ = run_engine("x{Ctrl+A}{Ctrl+Shift+S}")
        assert writer.calls == [("x", ["ctrl+a"], 0), ("", ["ctrl+shift+s"], 0)]

    def test_caps_mode_applied(self):
        writer, _, _ = run_engine("hello", quick(caps_mode=CapsMode.UPPERCASE))
        assert typed_text(writer) == "HELLO"

    def test_progress_reports_completion(self):
        _, progress, result = run_engine("abcdef")
        assert progress[-1] == (6, 6)
        assert result["elapsed"] >= 0

    def test_no_interval_from_word_delay(self):
        # delay_ms applies as an engine wait at word boundaries, never as the
        # writer interval (which stays tied to per-char speed).
        writer, _, _ = run_engine("ab cd ef", quick(delay_ms=50))
        assert all(interval == 0 for _, _, interval in writer.calls)

    def test_word_pause_after_every_word(self):
        # Regression: chunks used to end just before each space, so the
        # between-words delay almost never ran.
        writer = FakeWriter()
        engine = make_engine(writer)
        waits: list[float] = []
        engine._wait = waits.append  # record the delay instead of sleeping
        done = threading.Event()
        engine._on_complete = lambda e, i: done.set()

        engine.start("hello big world{Enter}bye", quick(delay_ms=50))
        assert done.wait(5)
        assert waits == [0.05, 0.05, 0.05]  # after "hello ", "big ", "world{Enter}"
        assert typed_text(writer) == "hello big worldbye"

    def test_sleep_marker_waits_between_keystrokes(self):
        writer = FakeWriter()
        engine = make_engine(writer)
        waits: list[float] = []
        engine._wait = waits.append
        done = threading.Event()
        engine._on_complete = lambda e, i: done.set()

        engine.start("ab{Sleep 300}cd", quick())
        assert done.wait(5)
        assert waits == [0.3]
        assert typed_text(writer) == "abcd"

    def test_sleep_does_not_count_as_progress(self):
        _, progress, _ = run_engine("ab{Sleep 10}c")
        assert progress[-1] == (3, 3)

    def test_loop_count_repeats(self):
        writer, _, result = run_engine("x", quick(loop_count=3))
        assert typed_text(writer) == "xxx"
        assert result["iterations"] == 3

    def test_jitter_varies_interval(self):
        settings = Settings(speed_ms=100, start_countdown_s=0, human_jitter_pct=50)
        intervals = []

        class Recorder(FakeWriter):
            def __call__(self, chunk, keys, interval):
                super().__call__(chunk, keys, interval)
                intervals.append(interval)

        run_engine("a b c d e f g h i j k l", settings, Recorder())
        # 12 chars -> multiple chunks; jitter should produce varied intervals.
        assert len(set(intervals)) > 1
        assert all(0.05 <= i <= 0.15 for i in intervals)


class TestPasteMode:
    def test_pastes_whole_text_with_one_shortcut(self):
        desktop = FakeDesktop()
        writer, progress, _ = run_engine(
            "hello big world\nsecond line", quick(paste_mode=True), desktop=desktop
        )
        assert desktop.clipboard == ["hello big world\nsecond line"]
        assert writer.calls == [("", [PASTE_KEY], 0)]
        assert progress[-1] == (27, 27)

    def test_keys_and_pauses_still_happen_between_pastes(self):
        desktop = FakeDesktop()
        writer, _, _ = run_engine("one{Tab}two{Ctrl+Enter}", quick(paste_mode=True), desktop=desktop)
        assert desktop.clipboard == ["one", "two"]
        assert writer.calls == [("", [PASTE_KEY, "tab"], 0), ("", [PASTE_KEY, "ctrl+enter"], 0)]

    def test_no_word_delays_when_pasting(self):
        engine = make_engine()
        waits: list[float] = []
        engine._wait = waits.append
        done = threading.Event()
        engine._on_complete = lambda e, i: done.set()
        engine.start("a b c", quick(paste_mode=True, delay_ms=50))
        assert done.wait(5)
        assert waits == []

    def test_waits_for_the_target_before_replacing_the_clipboard(self):
        # Regression: the next text replaced the clipboard right after Ctrl+V,
        # so a busy target could paste the second text twice.
        engine = make_engine()
        waits: list[float] = []
        engine._wait = waits.append
        done = threading.Event()
        engine._on_complete = lambda e, i: done.set()
        engine.start("one{Tab}two", quick(paste_mode=True))
        assert done.wait(5)
        assert len(waits) == 1 and 0 < waits[0] <= PASTE_SETTLE_S


class TestFocusGuard:
    def test_pauses_when_the_active_window_changes(self):
        desktop = FakeDesktop()
        gate = threading.Event()
        writer = FakeWriter(block_after=1, gate=gate)
        engine = make_engine(writer, desktop, on_focus_lost=lambda: setattr(
            desktop, "focus_lost", desktop.focus_lost + 1))
        done = threading.Event()
        engine._on_complete = lambda e, i: done.set()

        engine.start("x" * 100, quick())
        assert wait_for(lambda: len(writer.calls) >= 1)
        desktop.window = "chat"  # the user alt-tabbed away
        gate.set()
        assert wait_for(lambda: engine.paused)
        assert desktop.focus_lost == 1
        assert len(writer.calls) == 2  # the call in flight finished; nothing more

        engine.resume()  # types into the window that's active now
        assert done.wait(5)
        assert typed_text(writer) == "x" * 100
        assert desktop.focus_lost == 1

    def test_guard_can_be_switched_off(self):
        desktop = FakeDesktop()
        gate = threading.Event()
        writer = FakeWriter(block_after=1, gate=gate)
        engine = make_engine(writer, desktop)
        done = threading.Event()
        engine._on_complete = lambda e, i: done.set()

        engine.start("x" * 100, quick(focus_guard=False))
        assert wait_for(lambda: len(writer.calls) >= 1)
        desktop.window = "chat"
        gate.set()
        assert done.wait(5)
        assert not engine.paused

    def test_unknown_foreground_disables_the_guard(self):
        engine = TypingEngine(FakeWriter(), foreground=lambda: None)
        done = threading.Event()
        engine._on_complete = lambda e, i: done.set()
        engine.start("abc", quick())
        assert done.wait(5)
        assert not engine.paused

    def test_follows_a_window_the_text_opens_after_a_sleep(self):
        # Regression: {Win+R} opened the Run dialog and the guard paused.
        desktop = FakeDesktop()

        class Launcher(FakeWriter):
            def __call__(self, chunk, keys, interval):
                super().__call__(chunk, keys, interval)
                if "win+r" in keys:
                    desktop.window = "run dialog"

        writer = Launcher()
        engine = make_engine(writer, desktop, on_focus_lost=lambda: setattr(
            desktop, "focus_lost", desktop.focus_lost + 1))
        engine._wait = lambda seconds: None
        done = threading.Event()
        engine._on_complete = lambda e, i: done.set()

        engine.start("{Win+R}{Sleep 500}notepad{Enter}", quick())
        assert done.wait(5)
        assert desktop.focus_lost == 0
        assert typed_text(writer) == "notepad"

    def test_resume_counts_down_before_picking_the_window(self):
        # Resuming from Auto Typer's own window counts down first, so the user
        # can click back into the target instead of typing into Auto Typer.
        desktop = FakeDesktop()
        gate = threading.Event()
        writer = FakeWriter(block_after=1, gate=gate)
        countdowns: list[int] = []

        def on_countdown(remaining: int) -> None:
            countdowns.append(remaining)
            desktop.window = "editor"  # the user clicks back into the editor

        engine = make_engine(writer, desktop, on_countdown=on_countdown, on_focus_lost=lambda: setattr(
            desktop, "focus_lost", desktop.focus_lost + 1))
        engine._wait = lambda seconds: None
        done = threading.Event()
        engine._on_complete = lambda e, i: done.set()

        engine.start("x" * 100, quick())
        assert wait_for(lambda: len(writer.calls) >= 1)
        desktop.window = "auto typer"  # the user clicked into Auto Typer
        gate.set()
        assert wait_for(lambda: engine.paused)

        engine.resume(countdown_s=3)
        assert done.wait(5)
        assert countdowns == [3, 2, 1]
        assert desktop.focus_lost == 1  # it went on in the editor, with no second pause
        assert typed_text(writer) == "x" * 100


class TestControl:
    def test_stop_interrupts_session(self):
        # Two calls go through, the third blocks; stop must end the session
        # once the blocked call returns, not type the remaining ~100 loops.
        gate = threading.Event()
        writer = FakeWriter(block_after=2, gate=gate)
        engine = make_engine(writer)
        done = threading.Event()
        engine._on_complete = lambda e, i: done.set()

        engine.start("x" * 500, quick(loop_count=100))
        assert wait_for(lambda: len(writer.calls) >= 2)
        engine.stop()
        gate.set()

        assert done.wait(5)
        assert len(writer.calls) <= 3
        assert not engine.running

    def test_pause_blocks_until_resumed(self):
        gate = threading.Event()
        writer = FakeWriter(block_after=1, gate=gate)
        engine = make_engine(writer)
        done = threading.Event()
        engine._on_complete = lambda e, i: done.set()

        engine.start("x" * 100, quick())
        assert wait_for(lambda: len(writer.calls) >= 1)
        engine.pause()
        engine.resume()
        gate.set()
        assert done.wait(10)

    def test_pause_wakes_on_stop(self):
        gate = threading.Event()
        writer = FakeWriter(block_after=1, gate=gate)
        engine = make_engine(writer)
        done = threading.Event()
        engine._on_complete = lambda e, i: done.set()

        engine.start("x" * 100, quick())
        assert wait_for(lambda: len(writer.calls) >= 1)
        engine.pause()
        engine.stop()
        gate.set()
        assert done.wait(5)

    def test_no_double_start(self):
        gate = threading.Event()
        writer = FakeWriter(block_after=0, gate=gate)
        engine = make_engine(writer)
        engine.start("x" * 1000, quick())
        try:
            assert wait_for(lambda: engine.running)
            assert not engine.start("y", quick())
        finally:
            gate.set()
            engine.stop()

    def test_countdown_reports_each_second(self):
        countdowns: list[int] = []
        engine = make_engine(on_countdown=lambda remaining: countdowns.append(remaining))
        done = threading.Event()
        engine._on_complete = lambda e, i: done.set()
        engine.start("x", Settings(speed_ms=0, start_countdown_s=2))
        assert done.wait(10)
        assert countdowns == [2, 1]

    def test_stop_during_countdown_skips_typing(self):
        typed: list[str] = []
        engine = make_engine(lambda chunk, keys, interval: typed.append(chunk))
        done = threading.Event()
        engine._on_complete = lambda e, i: done.set()
        engine.start("x", Settings(speed_ms=0, start_countdown_s=30))
        engine.stop()
        assert done.wait(5)
        assert typed == []


@pytest.mark.skipif(
    __import__("sys").platform != "win32", reason="checks the real Windows writer's key table"
)
def test_every_canonical_key_has_a_pynput_key():
    from pynput.keyboard import Key

    from auto_typer.keys import _SPECIAL_KEYS
    from auto_typer.typer import _pynput_keys

    table = _pynput_keys(Key)
    for name in set(_SPECIAL_KEYS.values()) | {"ctrl", "alt", "shift", "win", "\n", "\t"}:
        assert name in table
