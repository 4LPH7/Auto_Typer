"""CustomTkinter GUI for Auto Typer.

All Tk widget access happens on the main thread. Worker threads (typing
engine, hotkey listener) push events into a queue that a main-loop poll
drains, so Tk is never touched off-thread.
"""

from __future__ import annotations

import queue
import tkinter.filedialog
from collections.abc import Callable
from tkinter import messagebox
from typing import Any

import customtkinter as ctk
import pyautogui

from .config import Settings, load_settings, save_settings
from .hotkeys import HotkeyManager
from .keys import CapsMode
from .typer import TypingEngine

pyautogui.PAUSE = 0  # remove pyautogui's hidden 0.1 s per-call delay


class AutoTyperApp:
    """Main application window and controller."""

    def __init__(self) -> None:
        self.settings = load_settings()
        self._events: queue.Queue[tuple[Callable[..., None], tuple[Any, ...]]] = queue.Queue()

        self.engine = TypingEngine(
            on_countdown=self._emit(self._on_countdown),
            on_progress=self._emit(self._on_progress),
            on_complete=self._emit(self._on_complete),
        )
        self.hotkeys = HotkeyManager(
            on_trigger=self._emit(self.start_typing),
            on_stop=self._emit(self.stop_typing),
            on_captured=self._emit(self._on_hotkey_captured),
        )
        self.hotkeys.set_hotkey(self.settings.hotkey)

        self._build_ui()
        self._apply_settings_to_ui()
        self.app.protocol("WM_DELETE_WINDOW", self._on_close)
        self._poll_events()
        self._poll_timer()

    # --------------------------------------------------------------- setup

    def _build_ui(self) -> None:
        ctk.set_appearance_mode("dark" if self.settings.dark_mode else "light")
        ctk.set_default_color_theme("blue")

        self.app = ctk.CTk()
        self.app.title("Modern Auto Typer")
        self.app.geometry("640x780")

        ctk.CTkLabel(self.app, text="Auto Typer", font=("Arial", 24, "bold")).pack(pady=10)

        self.text_input = ctk.CTkTextbox(self.app, width=540, height=140, font=("Arial", 14))
        self.text_input.pack(pady=10)

        # Timer / status / progress
        self.timer_label = ctk.CTkLabel(
            self.app, text="Total Typing Time: 0.00 seconds", font=("Arial", 14)
        )
        self.timer_label.pack(pady=5)
        self.progress_bar = ctk.CTkProgressBar(self.app, width=540)
        self.progress_bar.set(0)
        self.progress_bar.pack(pady=5)
        self.progress_label = ctk.CTkLabel(self.app, text="", font=("Arial", 12))
        self.progress_label.pack(pady=2)

        # Speed / delay / loop / jitter entries
        entry_frame = ctk.CTkFrame(self.app)
        entry_frame.pack(pady=5, fill="x", padx=20)
        entry_frame.grid_columnconfigure((0, 1), weight=1)

        self.speed_entry = ctk.CTkEntry(
            entry_frame, placeholder_text="Typing Speed (ms/char)", width=220
        )
        self.speed_entry.grid(row=0, column=0, padx=5, pady=5)
        self.delay_entry = ctk.CTkEntry(
            entry_frame, placeholder_text="Delay Between Words (ms)", width=220
        )
        self.delay_entry.grid(row=0, column=1, padx=5, pady=5)

        self.loop_entry = ctk.CTkEntry(
            entry_frame, placeholder_text="Loop Count (0 = infinite)", width=220
        )
        self.loop_entry.grid(row=1, column=0, padx=5, pady=5)
        self.jitter_entry = ctk.CTkEntry(
            entry_frame, placeholder_text="Human Jitter ±% (0 = off)", width=220
        )
        self.jitter_entry.grid(row=1, column=1, padx=5, pady=5)

        # Hotkey
        self.hotkey_display = ctk.CTkLabel(
            self.app,
            text=f"Hotkey: {HotkeyManager.format_names(self.settings.hotkey)}",
            font=("Arial", 14),
        )
        self.hotkey_display.pack(pady=5)
        ctk.CTkButton(self.app, text="Register Hotkey", command=self._register_hotkey).pack(pady=5)

        # Caps mode radios
        self.caps_mode_var = ctk.StringVar(value=CapsMode.AS_IS.value)
        caps_frame = ctk.CTkFrame(self.app)
        caps_frame.pack(pady=10, fill="x", padx=20)
        ctk.CTkLabel(caps_frame, text="Caps Lock Mode:", font=("Arial", 14)).grid(
            row=0, column=0, padx=5
        )
        for col, (label, mode) in enumerate(
            [
                ("Type As It Is", CapsMode.AS_IS),
                ("Type All Capital", CapsMode.UPPERCASE),
                ("Sentence Case", CapsMode.SENTENCE_CASE),
                ("Lower Case", CapsMode.LOWERCASE),
            ],
            start=1,
        ):
            ctk.CTkRadioButton(
                caps_frame, text=label, value=mode.value, variable=self.caps_mode_var
            ).grid(row=0, column=col, padx=5)

        # Control buttons
        ctk.CTkButton(
            self.app, text="Load Text from File…", command=self._load_text_file, width=220
        ).pack(pady=5)
        ctk.CTkButton(
            self.app, text="Start Typing", command=self.start_typing, fg_color="green"
        ).pack(pady=5)
        self.pause_button = ctk.CTkButton(
            self.app, text="Pause Typing", command=self.toggle_pause, fg_color="orange"
        )
        self.pause_button.pack(pady=5)
        ctk.CTkButton(
            self.app, text="Stop Typing", command=self.stop_typing, fg_color="red"
        ).pack(pady=5)
        self.mode_button = ctk.CTkButton(
            self.app,
            text=f"Switch to {'Light' if self.settings.dark_mode else 'Dark'} Mode",
            command=self._toggle_mode,
        )
        self.mode_button.pack(pady=5)

    def _apply_settings_to_ui(self) -> None:
        self.speed_entry.insert(0, str(self.settings.speed_ms))
        self.delay_entry.insert(0, str(self.settings.delay_ms))
        if self.settings.loop_count != 1:
            self.loop_entry.insert(0, str(self.settings.loop_count))
        if self.settings.human_jitter_pct:
            self.jitter_entry.insert(0, str(self.settings.human_jitter_pct))
        self.caps_mode_var.set(self.settings.caps_mode.value)

    # ------------------------------------------------- cross-thread plumbing

    def _emit(self, fn: Callable[..., None]) -> Callable[..., None]:
        """Wrap a worker-thread callback so it is executed on the main loop."""

        def wrapper(*args: Any) -> None:
            self._events.put((fn, args))

        return wrapper

    def _poll_events(self) -> None:
        while True:
            try:
                fn, args = self._events.get_nowait()
            except queue.Empty:
                break
            fn(*args)
        self.app.after(50, self._poll_events)

    def _poll_timer(self) -> None:
        if self.engine.running:
            self.timer_label.configure(
                text=f"Total Typing Time: {self.engine.elapsed:.2f} seconds"
            )
        self.pause_button.configure(
            text="Resume Typing" if self.engine.paused else "Pause Typing",
            state="normal" if self.engine.running else "disabled",
        )
        self.app.after(200, self._poll_timer)

    # -------------------------------------------------------------- actions

    def _register_hotkey(self) -> None:
        self.hotkeys.begin_capture()
        self.hotkey_display.configure(text="Press keys for hotkey...")

    def _on_hotkey_captured(self, names: list[str]) -> None:
        self.settings.hotkey = names
        self.hotkey_display.configure(
            text=f"Hotkey Registered: {HotkeyManager.format_names(names)}"
        )

    def _load_text_file(self) -> None:
        path = tkinter.filedialog.askopenfilename(
            title="Load text to type",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
        )
        if not path:
            return
        try:
            content = open(path, encoding="utf-8", errors="replace").read()
        except OSError as exc:
            messagebox.showerror("Load Failed", str(exc))
            return
        self.text_input.delete("1.0", "end")
        self.text_input.insert("1.0", content)

    def _collect_settings(self) -> Settings:
        def int_or(entry: ctk.CTkEntry, default: int) -> int:
            try:
                return int(entry.get())
            except ValueError:
                return default

        self.settings.speed_ms = int_or(self.speed_entry, self.settings.speed_ms)
        self.settings.delay_ms = int_or(self.delay_entry, self.settings.delay_ms)
        self.settings.loop_count = int_or(self.loop_entry, self.settings.loop_count)
        self.settings.human_jitter_pct = int_or(self.jitter_entry, self.settings.human_jitter_pct)
        self.settings.caps_mode = CapsMode(self.caps_mode_var.get())
        return self.settings.validated()

    def start_typing(self) -> None:
        text = self.text_input.get("1.0", "end").strip()
        if not text:
            return
        settings = self._collect_settings()
        self.progress_bar.set(0)
        self.progress_label.configure(text="")
        self.engine.start(text, settings)

    def stop_typing(self) -> None:
        self.engine.stop()

    def toggle_pause(self) -> None:
        if self.engine.paused:
            self.engine.resume()
        else:
            self.engine.pause()

    def _toggle_mode(self) -> None:
        self.settings.dark_mode = not self.settings.dark_mode
        ctk.set_appearance_mode("dark" if self.settings.dark_mode else "light")
        self.mode_button.configure(
            text=f"Switch to {'Light' if self.settings.dark_mode else 'Dark'} Mode"
        )

    # -------------------------------------------------------- engine events

    def _on_countdown(self, remaining: int) -> None:
        self.progress_label.configure(text=f"Starting in {remaining}…")

    def _on_progress(self, done: int, total: int) -> None:
        fraction = done / total if total else 0.0
        self.progress_bar.set(fraction)
        self.progress_label.configure(
            text=f"{done} / {total} characters ({fraction:.0%})"
        )

    def _on_complete(self, elapsed: float, iterations: int) -> None:
        self.progress_bar.set(1)
        self.progress_label.configure(text="")
        self.timer_label.configure(text=f"Total Typing Time: {elapsed:.2f} seconds")
        messagebox.showinfo(
            "Typing Complete",
            "Typing session completed successfully.\n"
            f"Iterations: {iterations}\nElapsed Time: {elapsed:.2f} seconds",
        )

    # ------------------------------------------------------------ lifecycle

    def _on_close(self) -> None:
        self._collect_settings()
        save_settings(self.settings)
        self.engine.stop()
        self.hotkeys.stop()
        self.app.destroy()

    def run(self) -> None:
        self.hotkeys.start()
        self.app.mainloop()


def main() -> None:
    AutoTyperApp().run()
