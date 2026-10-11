"""Tests for the TypingEngine, using a fake writer (no GUI or OS automation)."""

import threading
import time

from auto_typer.config import Settings
from auto_typer.keys import CapsMode
from auto_typer.typer import TypingEngine


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


def run_engine(text: str, settings: Settings | None = None, writer=None):
    """Run the engine synchronously and return (writer, progress, elapsed, iterations)."""
    writer = writer or FakeWriter()
    engine = TypingEngine(writer)
    settings = settings or Settings(speed_ms=0, start_countdown_s=0)

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

    def test_special_keys_pressed_not_typed(self):
        writer, _, _ = run_engine("a{Enter}b{Tab}")
        assert typed_text(writer) == "ab"
        assert pressed_keys(writer) == ["enter", "tab"]

    def test_caps_mode_applied(self):
        writer, _, _ = run_engine(
            "hello", Settings(speed_ms=0, start_countdown_s=0, caps_mode=CapsMode.UPPERCASE)
        )
        assert typed_text(writer) == "HELLO"

    def test_progress_reports_completion(self):
        _, progress, result = run_engine("abcdef")
        assert progress[-1] == (6, 6)
        assert result["elapsed"] >= 0

    def test_no_interval_from_word_delay(self):
        # delay_ms applies as an engine wait at word boundaries, never as the
        # writer interval (which stays tied to per-char speed).
        writer, _, _ = run_engine("ab cd ef", Settings(speed_ms=0, delay_ms=50,
                                                        start_countdown_s=0))
        assert all(interval == 0 for _, _, interval in writer.calls)

    def test_loop_count_repeats(self):
        writer, _, result = run_engine(
            "x", Settings(speed_ms=0, start_countdown_s=0, loop_count=3)
        )
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


class TestControl:
    def test_stop_interrupts_session(self):
        # Two calls go through, the third blocks; stop must end the session
        # once the blocked call returns, not type the remaining ~100 loops.
        gate = threading.Event()
        writer = FakeWriter(block_after=2, gate=gate)
        engine = TypingEngine(writer)
        done = threading.Event()
        engine._on_complete = lambda e, i: done.set()

        engine.start("x" * 500, Settings(speed_ms=0, start_countdown_s=0, loop_count=100))
        assert wait_for(lambda: len(writer.calls) >= 2)
        engine.stop()
        gate.set()

        assert done.wait(5)
        assert len(writer.calls) <= 3
        assert not engine.running

    def test_pause_blocks_until_resumed(self):
        gate = threading.Event()
        writer = FakeWriter(block_after=1, gate=gate)
        engine = TypingEngine(writer)
        done = threading.Event()
        engine._on_complete = lambda e, i: done.set()

        engine.start("x" * 100, Settings(speed_ms=0, start_countdown_s=0))
        assert wait_for(lambda: len(writer.calls) >= 1)
        engine.pause()
        engine.resume()
        gate.set()
        assert done.wait(10)

    def test_pause_wakes_on_stop(self):
        gate = threading.Event()
        writer = FakeWriter(block_after=1, gate=gate)
        engine = TypingEngine(writer)
        done = threading.Event()
        engine._on_complete = lambda e, i: done.set()

        engine.start("x" * 100, Settings(speed_ms=0, start_countdown_s=0))
        assert wait_for(lambda: len(writer.calls) >= 1)
        engine.pause()
        engine.stop()
        gate.set()
        assert done.wait(5)

    def test_no_double_start(self):
        gate = threading.Event()
        writer = FakeWriter(block_after=0, gate=gate)
        engine = TypingEngine(writer)
        engine.start("x" * 1000, Settings(speed_ms=0, start_countdown_s=0))
        try:
            assert wait_for(lambda: engine.running)
            assert not engine.start("y", Settings(speed_ms=0, start_countdown_s=0))
        finally:
            gate.set()
            engine.stop()

    def test_countdown_reports_each_second(self):
        countdowns: list[int] = []
        engine = TypingEngine(
            FakeWriter(),
            on_countdown=lambda remaining: countdowns.append(remaining),
        )
        done = threading.Event()
        engine._on_complete = lambda e, i: done.set()
        engine.start("x", Settings(speed_ms=0, start_countdown_s=2))
        assert done.wait(10)
        assert countdowns == [2, 1]

    def test_stop_during_countdown_skips_typing(self):
        typed: list[str] = []
        engine = TypingEngine(lambda chunk, keys, interval: typed.append(chunk))
        done = threading.Event()
        engine._on_complete = lambda e, i: done.set()
        engine.start("x", Settings(speed_ms=0, start_countdown_s=30))
        engine.stop()
        assert done.wait(5)
        assert typed == []
