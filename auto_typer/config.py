"""Application settings with JSON persistence.

Settings are stored in ``%APPDATA%/AutoTyper/settings.json`` on Windows
(falling back to the user's home directory elsewhere) and survive restarts.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field, fields, replace
from pathlib import Path

from .keys import CapsMode

_SETTINGS_DIR_NAME = "AutoTyper"
_SETTINGS_FILE_NAME = "settings.json"


def settings_path() -> Path:
    """Return the platform-appropriate settings file path."""
    appdata = os.environ.get("APPDATA")
    base = Path(appdata) if appdata else Path.home()
    return base / _SETTINGS_DIR_NAME / _SETTINGS_FILE_NAME


@dataclass(slots=True)
class Settings:
    """User-adjustable application settings."""

    speed_ms: int = 25  # delay between characters
    delay_ms: int = 0  # extra pause at word boundaries
    caps_mode: CapsMode = CapsMode.AS_IS
    hotkey: list[str] = field(default_factory=list)  # pynput key names, empty = disabled
    dark_mode: bool = True
    loop_count: int = 1  # 0 = infinite
    human_jitter_pct: int = 0  # ±% random speed variation, 0 = off
    start_countdown_s: int = 3  # countdown before typing begins

    def validated(self) -> Settings:
        """Return a copy with out-of-range values clamped to safe defaults."""
        return replace(
            self,
            speed_ms=max(0, min(self.speed_ms, 10_000)),
            delay_ms=max(0, min(self.delay_ms, 10_000)),
            loop_count=max(0, min(self.loop_count, 10_000)),
            human_jitter_pct=max(0, min(self.human_jitter_pct, 100)),
            start_countdown_s=max(0, min(self.start_countdown_s, 30)),
        )


def load_settings(path: Path | None = None) -> Settings:
    """Load settings from *path*, tolerating missing or corrupt files."""
    path = path or settings_path()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return Settings()

    known = {f.name for f in fields(Settings)}
    data = {k: v for k, v in raw.items() if k in known}
    try:
        data["caps_mode"] = CapsMode(data.get("caps_mode", CapsMode.AS_IS))
        data["hotkey"] = [str(k) for k in data.get("hotkey", [])]
        return Settings(**data).validated()
    except (TypeError, ValueError):
        return Settings()


def save_settings(settings: Settings, path: Path | None = None) -> bool:
    """Persist *settings* as JSON. Returns True on success."""
    path = path or settings_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = asdict(settings)
        payload["caps_mode"] = settings.caps_mode.value
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return True
    except OSError:
        return False
