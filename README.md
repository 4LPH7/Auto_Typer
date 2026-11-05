# Auto Typer

A modern and customizable auto-typing application built with Python 3.15 and CustomTkinter. This tool automates typing tasks with configurable speed, word delay, caps modes, hotkeys, loops, and a human-like typing mode.

## Features
- **Customizable Typing Speed and Delay**: Set the typing speed (ms per character) and the extra pause at word boundaries.
- **Hotkey Support**: Assign any key combination as a global hotkey to trigger auto-typing.
- **Caps Mode**: `As Is`, `All Caps`, `Sentence Case`, and `Lower Case`.
- **Loop / Repeat**: Repeat the text N times or infinitely (0).
- **Start Countdown**: A configurable 3-2-1 countdown so you can focus the target window before typing starts.
- **Pause / Resume**: Pause an in-flight session and resume it later; `ESC` always stops.
- **Progress Bar**: Live character progress (`x / N · %`) while typing.
- **Load Text from File**: Pick a `.txt` file instead of pasting.
- **Types Anything**: accents, symbols, emoji and non-Latin scripts (`café`, `—`, `你好`, `🙂`) arrive as written, not just US-keyboard characters.
- **Special Keys**: `{Enter}`, `{Tab}`, `{Space}`, `{Backspace}`, `{Delete}`, `{Esc}`, `{Up}`/`{Down}`/`{Left}`/`{Right}`, `{Home}`, `{End}`, `{PageUp}`, `{PageDown}`, `{Win}`, `{F1}`–`{F12}`. Unknown `{...}` sequences are typed literally.
- **Key Combinations**: `{Ctrl+A}`, `{Ctrl+Shift+S}`, `{Alt+F4}`, `{Win+R}` press the combination.
- **Pauses in the Text**: `{Sleep 500}` (also `Delay` / `Wait`) waits that many milliseconds before going on.
- **Pause if the Window Changes**: if another window takes focus mid-typing, Auto Typer pauses instead of typing into it. After a `{Sleep}` it follows whichever window is active, so text can open a window and type into it: `{Win+R}{Sleep 500}notepad{Enter}`.
- **Paste Mode**: put the text on the clipboard and press Ctrl+V instead of typing it — instant, for long texts into targets that allow pasting.
- **Human Mode**: Randomized per-chunk speed jitter (±%) for realistic typing.
- **Saved Settings**: Speed, delay, hotkey, theme, and options persist across sessions (`%APPDATA%/AutoTyper/settings.json`).
- **Dark and Light Mode**: Light / Dark toggle in the header; preference is remembered.
- **Runs in the Background**: closing the window keeps Auto Typer in the system tray, so hotkeys and the phone remote keep working. Right-click the tray icon to show it, turn this off, start it with Windows, or quit. Launching it again brings back the running copy.
- **Polished UI**: Compact window with a pinned action bar (status, progress, Start / Pause / Stop), a live word, keystroke and time estimate for your text, keycap-style hotkey buttons, and a letter-case control labelled by its effect.
- **Fast Typing Engine**: Types in small chunks with no hidden per-call pauses — the requested speed is the speed you get, and Stop always answers within a few keystrokes.

## Requirements
- **Python 3.15 or higher**
- Windows (uses pynput global hooks and PyAutoGUI)

## Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/4LPH7/Auto_Typer.git
   cd Auto_Typer
   ```

2. Create a virtual environment and install:
   ```bash
   py -3.15 -m venv .venv
   .venv\Scripts\pip install -e .
   ```

3. Run the application:
   ```bash
   .venv\Scripts\auto-typer
   # or
   .venv\Scripts\python -m auto_typer
   ```

## Usage

1. **Enter text**: type or paste it, or use *Load file…*. `{Enter}`, `{Ctrl+S}` and `{Sleep 500}` press keys and wait; see the feature list for all markers.
2. **Settings**: key delay, word pause, repeat, jitter and letter case. *Paste instead of typing* sends the whole text with one Ctrl+V. *Pause if the window changes* is on by default; switch it off for targets that open their own windows while you type.
3. **Hotkeys** (optional): click the Start, Pause or Stop key and press the keys you want. F8, F9 or Ctrl+Alt+letter work well; avoid bare letters and punctuation, which fire whenever you type them.
4. **Start typing**: click it or press your Start hotkey. After a 3 s countdown it types into the active window.
5. **Pause / Stop**: use the buttons or your hotkeys. `Esc` always stops. If the active window changed, Auto Typer is paused: press your Pause hotkey in the window you want, or click Resume and then click into that window within 3 seconds.
6. **Close the window** to keep Auto Typer in the tray. Right-click the tray icon for *Start with Windows*, which starts it hidden at sign-in.

## Phone remote (Android)

Send text from your phone and let the PC type it.

1. Install `AutoTyper.apk` from the [latest release](https://github.com/4LPH7/Auto_Typer/releases/latest) on your phone (allow installs from your browser or file manager when Android asks).
2. On the PC, click **Phone** and switch it **On**. Allow Auto Typer if Windows Firewall asks.
3. In the app, tap **Scan QR code**, or type the address and code shown on the PC.
4. Write or paste text, set the options and tap **Start typing**. The PC types into its active window; pause, resume or stop from the phone, or press `Esc` on the PC.

The phone and PC must be on the same Wi-Fi. The remote is off every time Auto Typer starts, and switching it off and on makes a new code. The protocol is in [docs/remote-protocol.md](docs/remote-protocol.md).

## Standalone Executable

Build a one-file Windows executable (no Python required to run it):

```bash
.venv\Scripts\pip install pyinstaller
build_exe.bat
# -> dist\AutoTyper.exe
```

## Development

Install the development tools, then run the checks CI runs:

```bash
.venv\Scripts\pip install -e .[dev]
.venv\Scripts\ruff check .
.venv\Scripts\mypy
.venv\Scripts\pytest
```

Pull requests and pushes to `main` build the exe and the APK; a `v*` tag publishes them as a release. See [CHANGELOG.md](CHANGELOG.md) for what changed in each version.

## Project Layout
```
auto_typer/
├── app.py         # GUI + controller (all Tk access on the main thread)
├── typer.py       # TypingEngine: chunked typing, pause/stop, loops, jitter, paste mode, focus guard
├── keys.py        # tokenizer: characters, {Keys}, {Ctrl+Combos}, {Sleep n}; caps modes
├── config.py      # Settings dataclass + JSON persistence
├── hotkeys.py     # pynput global hotkey listener
├── remote.py      # phone remote: LAN HTTP server (docs/remote-protocol.md)
├── background.py  # tray icon, single instance, app icon
└── system.py      # Windows bits: clipboard, foreground window, start-with-Windows
android/          # Android remote app (Kotlin + Jetpack Compose)
```

## Contribution
- Contributions are welcome! Feel free to fork the repository and submit a pull request.

## License
- This project is licensed under the [MIT License](LICENSE).

## Disclaimer
 - Use this tool responsibly and avoid using it for malicious purposes.

### Show your support

Give a ⭐ if you like this project!

<a href="https://buymeacoffee.com/arulartadg" target="_blank"><img src="https://cdn.buymeacoffee.com/buttons/v2/default-violet.png" alt="Buy Me A Coffee" height= "60px" width= "217px" ></a>
