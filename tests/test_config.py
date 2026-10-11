"""Tests for settings persistence."""

import json

from auto_typer.config import Settings, load_settings, save_settings
from auto_typer.keys import CapsMode


def test_default_settings():
    s = Settings()
    assert s.speed_ms == 25
    assert s.caps_mode == CapsMode.AS_IS
    assert s.hotkey == []
    assert s.loop_count == 1


def test_round_trip(tmp_path):
    path = tmp_path / "settings.json"
    original = Settings(
        speed_ms=10, delay_ms=50, caps_mode=CapsMode.UPPERCASE,
        hotkey=["ctrl", "alt", "t"], dark_mode=False,
        loop_count=5, human_jitter_pct=20, start_countdown_s=1,
    )
    assert save_settings(original, path)
    assert load_settings(path) == original


def test_load_missing_file_returns_defaults(tmp_path):
    assert load_settings(tmp_path / "missing.json") == Settings()


def test_load_corrupt_file_returns_defaults(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text("{not json", encoding="utf-8")
    assert load_settings(path) == Settings()


def test_load_ignores_unknown_fields(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"speed_ms": 5, "future_field": 1}), encoding="utf-8")
    assert load_settings(path).speed_ms == 5


def test_load_rejects_bad_types(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"speed_ms": "fast", "loop_count": None}), encoding="utf-8")
    assert load_settings(path) == Settings()


def test_validated_clamps_ranges():
    s = Settings(speed_ms=-5, delay_ms=99999, loop_count=-1,
                 human_jitter_pct=500, start_countdown_s=100).validated()
    assert s.speed_ms == 0
    assert s.delay_ms == 10_000
    assert s.loop_count == 0
    assert s.human_jitter_pct == 100
    assert s.start_countdown_s == 30
