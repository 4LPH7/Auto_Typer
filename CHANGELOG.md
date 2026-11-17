# Changelog

## 2.3.0 — 2026-11-17

### Added
- **Phone remote: paste mode and focus guard.** The Android app has switches for both, matching
  the desktop settings.
- **Phone remote: "Send to Auto Typer".** Share text from any app to the phone remote.
- **Phone remote: Back and Change PC.** The phone can open the connect screen again without
  forgetting the saved PC, and Back returns to the remote.

### Changed
- **Faster phone remote.** The PC server keeps HTTP connections open between the phone's polls
  (HTTP/1.1 keep-alive, `TCP_NODELAY`) and closes idle ones after 30 s.
- **Phone reconnects when Wi-Fi returns.** It polls at once instead of waiting for the next retry.
- **Phone rejects QR codes from other protocol versions.**

## 2.2.0 — 2026-11-05

### Added
- **Runs in the background.** Closing the window keeps Auto Typer in the system tray, so hotkeys
  and the phone remote keep working. A second launch shows the running copy instead of starting
  another one. The tray menu can turn this off, and can make Auto Typer **start with Windows**
  (hidden in the tray).
- **Pause if the window changes.** If another window takes focus while typing, Auto Typer pauses
  instead of typing into it. After a `{Sleep}` it follows whichever window is active, so text can
  open a window and type into it: `{Win+R}{Sleep 500}notepad{Enter}`. Resuming from Auto Typer's
  own window counts down 3 s first, so typing doesn't land in Auto Typer itself. On by default;
  switch it off in Settings for targets that open their own windows.
- **Paste instead of typing.** Puts the text on the clipboard and presses Ctrl+V. Instant, for
  long texts into targets that allow pasting; keys such as `{Tab}` still press in between, with
  0.2 s between pastes so each one lands before the clipboard changes.
- **Key combinations** in the text: `{Ctrl+A}`, `{Ctrl+Shift+S}`, `{Alt+F4}`, `{Win+R}`.
- **Pauses** in the text: `{Sleep 500}` (also `Delay`, `Wait`) waits that many milliseconds.
- The phone remote accepts and reports `paste_mode` and `focus_guard` (optional; older phones
  keep working).

### Fixed
- **Accents, symbols, emoji and non-Latin scripts now type.** The old engine dropped any character
  outside the US keyboard layout; the new one sends Unicode input, so `café`, `—`, `你好` and `🙂`
  arrive as written.
- Keys inside a word now happen in order: `abc{Left}X` used to type `abcX` and press Left after.
- Hotkeys with letters work: Windows reports Ctrl+T as a control character, which never matched.
  Hotkey labels read `Ctrl+T`, not `Ctrl_l+T`.
- Settings toggled from the tray are saved at once, not only on quit.

### Changed
- The window, taskbar, tray and exe share one icon.
- The exe is no longer UPX-packed, which was a common antivirus false positive.
- PyAutoGUI is no longer a dependency; typing goes through pynput.
- Development: `ruff` and `mypy` run in CI alongside the tests, which also run on pushes to `main`.
  Dependencies live in `pyproject.toml` only (`pip install -e .[dev]`).

## 2.1.0

- Phone remote: control typing from an Android phone over Wi-Fi, paired with a QR code.
- Hotkeys ignore the app's own keystrokes, so a typed `.` no longer fires a `.` hotkey.

## 2.0.0

- CustomTkinter interface with light and dark modes, a pinned action bar and live estimates.
- Chunked typing engine with pause / resume, loops, countdown, jitter and special keys.
- Settings persist in `%APPDATA%/AutoTyper/settings.json`.
