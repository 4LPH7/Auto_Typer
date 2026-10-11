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
- **Dark and Light Mode**.
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

1. **Enter Text**: Input the text to be auto-typed (or load a `.txt` file).
2. **Configure Settings**: Adjust typing speed, word delay, loop count, jitter, and caps mode.
3. **Register Hotkey**: Click *Register Hotkey* and press the desired combination.
4. **Start Typing**: Press the hotkey or click *Start Typing* — a countdown gives you time to focus the target window.
5. **Pause / Stop**: Click *Pause Typing* to hold mid-session; press `ESC` or *Stop Typing* to halt.

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
└── hotkeys.py    # pynput global hotkey listener
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
