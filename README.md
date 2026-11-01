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
- **Extended Special Keys**: `{Enter}`, `{Tab}`, `{Space}`, `{Backspace}`, `{Delete}`, `{Esc}`, `{Up}`/`{Down}`/`{Left}`/`{Right}`, `{Home}`, `{End}`, `{PageUp}`, `{PageDown}`, `{Win}`, `{F1}`–`{F12}`. Unknown `{...}` sequences are typed literally.
- **Human Mode**: Randomized per-chunk speed jitter (±%) for realistic typing.
- **Saved Settings**: Speed, delay, hotkey, theme, and options persist across sessions (`%APPDATA%/AutoTyper/settings.json`).
- **Dark and Light Mode**: Light / Dark toggle in the header; preference is remembered.
- **Polished UI**: Compact window with a pinned action bar (status, progress, Start / Pause / Stop), a live word, keystroke and time estimate for your text, keycap-style hotkey buttons, and a letter-case control labelled by its effect.
- **Fast Typing Engine**: Types in chunks with pyautogui's hidden per-call pause disabled — the requested speed is the speed you get.

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

1. **Enter text**: type or paste it, or use *Load file…*. `{Enter}`, `{Tab}` and `{F1}`–`{F12}` press keys.
2. **Settings**: key delay, word pause, repeat, jitter and letter case.
3. **Hotkeys** (optional): click the Start, Pause or Stop key and press the keys you want. F8 and F9 work well; avoid letters and punctuation, which fire whenever you type them.
4. **Start typing**: click it or press your Start hotkey. After a 3 s countdown it types into the active window.
5. **Pause / Stop**: use the buttons or your hotkeys. `Esc` always stops.

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

Run the test suite:

```bash
.venv\Scripts\pip install -e .[dev]
.venv\Scripts\pytest
```

## Project Layout
```
auto_typer/
├── app.py        # GUI + controller (all Tk access on the main thread)
├── typer.py      # TypingEngine: chunked typing, pause/stop, loops, jitter
├── keys.py       # tokenizer + caps modes
├── config.py     # Settings dataclass + JSON persistence
├── hotkeys.py    # pynput global hotkey listener
└── remote.py     # phone remote: LAN HTTP server (docs/remote-protocol.md)
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
