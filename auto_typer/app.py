"""CustomTkinter GUI for Auto Typer.

All Tk widget access happens on the main thread. Worker threads (typing
engine, hotkey listener) push events into a queue that a main-loop poll
drains, so Tk is never touched off-thread.
"""

from __future__ import annotations

import queue
import sys
import time
import tkinter
import tkinter.filedialog
from collections.abc import Callable
from concurrent.futures import Future
from tkinter import messagebox
from typing import Any

import customtkinter as ctk
import pyautogui
import segno

from .config import Settings, load_settings, save_settings
from .hotkeys import HotkeyManager
from .keys import CapsMode, is_word_gap, tokenize
from .remote import PROTOCOL_VERSION, RemoteError, RemoteServer, lan_ip
from .typer import TypingEngine

pyautogui.PAUSE = 0  # remove pyautogui's hidden 0.1 s per-call delay

_PAD = 24  # outer horizontal padding
_GAP = 16  # space between sections

# Colour tokens as (light, dark) pairs. Surfaces are told apart by a step in
# lightness alone (no borders, no shadows). The one hue marks live data only:
# the progress bar and the status dot. Buttons stay neutral; the primary
# action is primary by inversion.
GROUND = ("#f9fafb", "#0c0d0f")
SURFACE = ("#ffffff", "#15171a")
RAISED = ("#eef0f2", "#24272b")
HOVER = ("#e3e6e9", "#2f3338")
SELECTED = ("#ffffff", "#3d4148")
TEXT = ("#111111", "#ffffff")
MUTED = ("#5f6368", "#b4b4b4")
FAINT = ("#6b6b6b", "#949494")
PRIMARY = ("#1d1f20", "#ffffff")
PRIMARY_HOVER = ("#3a3d40", "#dedede")
ON_PRIMARY = ("#ffffff", "#000000")
ACCENT = ("#4d7c0f", "#c6f24e")
WARNING = ("#a16207", "#e5a93b")

# Segoe UI is the native Windows face; elsewhere use CustomTkinter's default.
_FONT = "Segoe UI" if sys.platform == "win32" else None
_FONT_SEMIBOLD = "Segoe UI Semibold" if sys.platform == "win32" else None

# Each case option is labelled with its own effect.
_CASE_LABELS = {
    CapsMode.AS_IS: "As is",
    CapsMode.UPPERCASE: "UPPER",
    CapsMode.LOWERCASE: "lower",
    CapsMode.SENTENCE_CASE: "Sentence",
}


def _font(size: int, semibold: bool = False) -> ctk.CTkFont:
    if semibold and _FONT_SEMIBOLD:
        return ctk.CTkFont(_FONT_SEMIBOLD, size)
    return ctk.CTkFont(_FONT, size, "bold" if semibold else "normal")


def _duration(seconds: float) -> str:
    """Short human duration: ``0.4 s``, ``12 s``, ``3 min 5 s``."""
    if seconds < 10:
        return f"{seconds:.1f} s"
    if seconds < 60:
        return f"{seconds:.0f} s"
    minutes, secs = divmod(round(seconds), 60)
    return f"{minutes} min {secs} s" if secs else f"{minutes} min"


class AutoTyperApp:
    """Main application window and controller."""

    def __init__(self) -> None:
        self.settings = load_settings()
        self._events: queue.Queue[tuple[Callable[..., None], tuple[Any, ...]]] = queue.Queue()
        self._phase = "ready"  # ready | countdown | typing | done | stopped
        self._done = 0
        self._total = 0
        self._shown_running: bool | None = None
        self._stop_requested = False
        self.current_hotkey_type: str | None = None

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
        self.hotkeys.set_hotkey(self.settings.start_hotkey)
        self.pause_hotkeys = HotkeyManager(
            on_trigger=self._emit(self.toggle_pause),
            on_stop=self._emit(self.stop_typing),
            on_captured=self._emit(self._on_hotkey_captured),
        )
        self.pause_hotkeys.set_hotkey(self.settings.pause_hotkey)
        self.stop_hotkeys = HotkeyManager(
            on_trigger=self._emit(self.stop_typing),
            on_stop=self._emit(self.stop_typing),
            on_captured=self._emit(self._on_hotkey_captured),
        )
        self.stop_hotkeys.set_hotkey(self.settings.stop_hotkey)
        self._hotkey_managers = {
            "start": self.hotkeys, "pause": self.pause_hotkeys, "stop": self.stop_hotkeys,
        }
        self._countdown_left = 0
        self._runs = 1
        self._remote_status: dict[str, Any] = {}  # replaced whole, read by the server thread
        self.remote = RemoteServer(
            lambda: self._remote_status, lambda: self.settings, self._remote_command
        )
        self._phone_dialog: ctk.CTkToplevel | None = None
        self._phone_label = ""

        self._build_ui()
        self._apply_settings_to_ui()
        self._update_status()
        self.app.protocol("WM_DELETE_WINDOW", self._on_close)
        self._poll_events()
        self._poll_timer()

    # --------------------------------------------------------------- setup

    def _build_ui(self) -> None:
        ctk.set_appearance_mode("dark" if self.settings.dark_mode else "light")

        self.app = ctk.CTk(fg_color=GROUND)
        self.app.title("Auto Typer")
        self.app.minsize(520, 600)
        self._place_window(560, 640)

        self.font_title = _font(20, semibold=True)
        self.font_section = _font(16, semibold=True)
        self.font_body = _font(14)
        self.font_strong = _font(14, semibold=True)
        self.font_small = _font(12)

        self._build_header()
        self._build_action_bar()  # packed before the body so it is never cut off

        body = ctk.CTkFrame(self.app, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=_PAD, pady=(0, _GAP))
        self._build_text_section(body)
        self._build_settings_section(body)

    def _place_window(self, width: int, height: int) -> None:
        """Size the window to fit the screen and centre it, nudged up so the
        action bar clears the taskbar. CTk scales the size but not the position."""
        scale = self.app.winfo_fpixels("1i") / 96
        height = min(height, int(self.app.winfo_screenheight() / scale) - 96)
        x = (self.app.winfo_screenwidth() - round(width * scale)) // 2
        y = max(0, (self.app.winfo_screenheight() - round((height + 80) * scale)) // 2)
        self.app.geometry(f"{width}x{height}+{x}+{y}")

    def _build_header(self) -> None:
        header = ctk.CTkFrame(self.app, fg_color="transparent")
        header.pack(fill="x", padx=_PAD, pady=(12, 10))
        ctk.CTkLabel(header, text="Auto Typer", font=self.font_title, text_color=TEXT).pack(
            side="left"
        )

        self.mode_toggle = self._small_toggle(header, ["Light", "Dark"], self._toggle_mode)
        self.mode_toggle.set("Dark" if self.settings.dark_mode else "Light")
        self.mode_toggle.pack(side="right")
        self.phone_button = ctk.CTkButton(
            header, text="Phone", command=self._open_phone_dialog, width=72, height=28,
            corner_radius=14, font=self.font_small, fg_color=RAISED, hover_color=HOVER,
            text_color=TEXT,
        )
        self.phone_button.pack(side="right", padx=(0, 8))

    def _small_toggle(
        self, parent: Any, values: list[str], command: Callable[[str], None]
    ) -> ctk.CTkSegmentedButton:
        return ctk.CTkSegmentedButton(
            parent, values=values, command=command,
            font=self.font_small, height=28, corner_radius=14, border_width=3,
            fg_color=RAISED, unselected_color=RAISED, unselected_hover_color=HOVER,
            selected_color=SELECTED, selected_hover_color=SELECTED, text_color=TEXT,
        )

    def _build_text_section(self, body: ctk.CTkFrame) -> None:
        self.text_input = ctk.CTkTextbox(
            body, height=150, font=self.font_body, wrap="word", corner_radius=16,
            fg_color=SURFACE, text_color=TEXT, border_width=1, border_color=SURFACE,
            border_spacing=10, scrollbar_button_color=RAISED, scrollbar_button_hover_color=HOVER,
        )
        self.text_input.pack(fill="both", expand=True)
        self._focus_ring(self.text_input, self.text_input, SURFACE)
        self.text_input.bind("<KeyRelease>", lambda _e: self._update_estimate())

        meta = ctk.CTkFrame(body, fg_color="transparent")
        meta.pack(fill="x", pady=(4, 0))
        self.estimate_label = ctk.CTkLabel(
            meta, text="", font=self.font_small, text_color=FAINT, anchor="w", height=28
        )
        self.estimate_label.pack(side="left", fill="x", expand=True)
        ctk.CTkButton(
            meta, text="Load file…", command=self._load_text_file, width=88, height=28,
            corner_radius=14, fg_color="transparent", hover_color=RAISED, text_color=MUTED,
            font=self.font_small,
        ).pack(side="right")

    def _build_settings_section(self, body: ctk.CTkFrame) -> None:
        self._section_title(body, "Settings", top=_GAP - 4)
        panel = ctk.CTkFrame(body, fg_color=SURFACE, corner_radius=20)
        panel.pack(fill="x")
        grid = ctk.CTkFrame(panel, fg_color="transparent")
        grid.pack(fill="x", padx=10, pady=10)
        grid.grid_columnconfigure((0, 1, 2, 3), weight=1, uniform="typing")

        self.speed_entry = self._number_field(grid, 0, "Key delay", "ms")
        self.delay_entry = self._number_field(grid, 1, "Word pause", "ms")
        self.loop_entry = self._number_field(grid, 2, "Repeat", "×")
        self.jitter_entry = self._number_field(grid, 3, "Jitter", "±%")

        case_cell = ctk.CTkFrame(grid, fg_color="transparent")
        case_cell.grid(row=1, column=0, columnspan=4, sticky="ew", padx=6, pady=6)
        ctk.CTkLabel(
            case_cell, text="Letter case", font=self.font_small, text_color=MUTED, anchor="w"
        ).pack(fill="x", pady=(0, 4))
        self.caps_mode = CapsMode.AS_IS
        self.caps_segmented = ctk.CTkSegmentedButton(
            case_cell, values=list(_CASE_LABELS.values()), command=self._on_caps_mode_changed,
            font=self.font_body, height=36, corner_radius=18, border_width=3,
            fg_color=RAISED, unselected_color=RAISED, unselected_hover_color=HOVER,
            selected_color=SELECTED, selected_hover_color=SELECTED, text_color=TEXT,
        )
        self.caps_segmented.pack(fill="x")

        hotkeys = ctk.CTkFrame(grid, fg_color="transparent")
        hotkeys.grid(row=2, column=0, columnspan=4, sticky="ew")
        hotkeys.grid_columnconfigure((0, 1, 2), weight=1, uniform="hotkeys")
        self.hotkey_buttons: dict[str, ctk.CTkButton] = {}
        kinds = (("start", "Start hotkey"), ("pause", "Pause hotkey"), ("stop", "Stop hotkey"))
        for col, (kind, label) in enumerate(kinds):
            cell = ctk.CTkFrame(hotkeys, fg_color="transparent")
            cell.grid(row=0, column=col, sticky="ew", padx=6, pady=6)
            ctk.CTkLabel(cell, text=label, font=self.font_small, text_color=MUTED, anchor="w").pack(
                fill="x", pady=(0, 4)
            )
            # A keycap: shows the combination; click it, then press new keys.
            button = ctk.CTkButton(
                cell, text="", height=36, corner_radius=10, font=self.font_strong,
                fg_color=RAISED, hover_color=HOVER, text_color=TEXT,
                border_width=1, border_color=RAISED,
                command=lambda k=kind: self._register_hotkey(k),
            )
            button.pack(fill="x")
            self.hotkey_buttons[kind] = button

    def _build_action_bar(self) -> None:
        bar = ctk.CTkFrame(self.app, fg_color=SURFACE, corner_radius=0)
        bar.pack(side="bottom", fill="x")

        self.progress_bar = ctk.CTkProgressBar(
            bar, height=4, corner_radius=0, border_width=0, fg_color=RAISED, progress_color=ACCENT
        )
        self.progress_bar.set(0)
        self.progress_bar.pack(fill="x")

        row = ctk.CTkFrame(bar, fg_color="transparent")
        row.pack(fill="x", padx=_PAD, pady=14)

        status = ctk.CTkFrame(row, fg_color="transparent")
        status.pack(side="left", fill="x", expand=True)
        line = ctk.CTkFrame(status, fg_color="transparent")
        line.pack(fill="x")
        self.status_dot = ctk.CTkLabel(line, text="●", font=self.font_small, width=14, anchor="w")
        self.status_dot.pack(side="left")
        self.status_label = ctk.CTkLabel(line, text="", font=self.font_strong, text_color=TEXT, height=20)
        self.status_label.pack(side="left", padx=(2, 0))
        self.detail_label = ctk.CTkLabel(
            status, text="", font=self.font_small, text_color=MUTED, anchor="w", height=18
        )
        self.detail_label.pack(fill="x")

        self.start_button = ctk.CTkButton(
            row, text="Start typing", command=self.start_typing, width=132, height=36,
            corner_radius=18, font=self.font_strong,
            fg_color=PRIMARY, hover_color=PRIMARY_HOVER, text_color=ON_PRIMARY,
        )
        secondary = dict(
            width=96, height=36, corner_radius=18, font=self.font_strong,
            fg_color=RAISED, hover_color=HOVER, text_color=TEXT,
        )
        self.stop_button = ctk.CTkButton(row, text="Stop", command=self.stop_typing, **secondary)
        self.pause_button = ctk.CTkButton(row, text="Pause", command=self.toggle_pause, **secondary)

    # ------------------------------------------------------------- helpers

    def _section_title(self, parent: ctk.CTkFrame, title: str, top: int = 0) -> ctk.CTkFrame:
        """A heading row; returned so a small control can sit at its right."""
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", pady=(top, 8))
        ctk.CTkLabel(row, text=title, font=self.font_section, text_color=TEXT, height=28).pack(
            side="left"
        )
        return row

    def _number_field(self, grid: ctk.CTkFrame, col: int, label: str, unit: str) -> ctk.CTkEntry:
        """Label above a pill-shaped field with its unit inside, on the right."""
        cell = ctk.CTkFrame(grid, fg_color="transparent")
        cell.grid(row=0, column=col, sticky="ew", padx=6, pady=6)
        ctk.CTkLabel(cell, text=label, font=self.font_small, text_color=MUTED, anchor="w").pack(
            fill="x", pady=(0, 4)
        )
        box = ctk.CTkFrame(
            cell, width=80, height=36, corner_radius=18, fg_color=RAISED,
            border_width=1, border_color=RAISED,
        )
        box.pack(fill="x")
        box.pack_propagate(False)
        entry = ctk.CTkEntry(
            box, width=40, height=30, border_width=0, corner_radius=0,
            fg_color=RAISED, text_color=TEXT, font=self.font_body,
        )
        entry.pack(side="left", fill="x", expand=True, padx=(14, 0))
        ctk.CTkLabel(box, text=unit, font=self.font_small, text_color=FAINT).pack(
            side="right", padx=(2, 14)
        )
        self._focus_ring(entry, box, RAISED)
        entry.bind("<KeyRelease>", lambda _e: self._update_estimate())
        return entry

    @staticmethod
    def _focus_ring(widget: Any, frame: Any, rest: tuple[str, str]) -> None:
        """Show keyboard focus as a border in the text colour."""
        widget.bind("<FocusIn>", lambda _e: frame.configure(border_color=TEXT))
        widget.bind("<FocusOut>", lambda _e: frame.configure(border_color=rest))

    def _show_hotkey(self, kind: str) -> None:
        names = getattr(self.settings, f"{kind}_hotkey")
        self.hotkey_buttons[kind].configure(
            text=HotkeyManager.format_names(names) if names else "Not set",
            text_color=TEXT if names else FAINT,
            border_color=RAISED,
        )

    def _set_fields(self, settings: Settings) -> None:
        """Show *settings* in the typing fields, replacing what they held."""
        for entry, value in (
            (self.speed_entry, settings.speed_ms),
            (self.delay_entry, settings.delay_ms),
            (self.loop_entry, settings.loop_count),
            (self.jitter_entry, settings.human_jitter_pct),
        ):
            entry.delete(0, "end")
            entry.insert(0, str(value))
        self.caps_mode = settings.caps_mode
        self.caps_segmented.set(_CASE_LABELS[self.caps_mode])

    def _apply_settings_to_ui(self) -> None:
        self._set_fields(self.settings)
        for kind in self.hotkey_buttons:
            self._show_hotkey(kind)
        self._update_estimate()

    def _update_estimate(self) -> None:
        """Show what the settings produce for the current text."""
        text = self.text_input.get("1.0", "end").strip()
        if not text:
            self.estimate_label.configure(
                text="Type or paste text. {Enter}, {Tab} and {F1}–{F12} press keys."
            )
            return
        settings = self._collect_settings()
        tokens = tokenize(text)
        gaps = sum(map(is_word_gap, tokens))
        per_run = (len(tokens) * settings.speed_ms + gaps * settings.delay_ms) / 1000
        words = len(text.split())
        if settings.loop_count == 0:
            time = f"about {_duration(per_run)} a run, repeats until stopped"
        elif settings.loop_count > 1:
            time = f"about {_duration(per_run * settings.loop_count)} for {settings.loop_count} runs"
        else:
            time = f"about {_duration(per_run)}"
        self.estimate_label.configure(
            text=f"{words} word{'s' * (words != 1)}  ·  {len(tokens)} keystrokes  ·  {time}"
        )

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
        self._update_status()
        self.app.after(200, self._poll_timer)

    def _update_status(self) -> None:
        running = self.engine.running
        phase = "paused" if running and self.engine.paused else self._phase
        progress = f"{self._done} of {self._total} keystrokes"
        elapsed = _duration(self.engine.elapsed)
        if phase == "done" and self._runs > 1:
            finished = f"{self._runs} runs in {elapsed}"
        else:
            finished = f"{self._total} keystrokes in {elapsed}"
        title, detail, colour = {
            "ready": (
                "Ready",
                f"Types into the active window after a {self.settings.start_countdown_s} s countdown",
                FAINT,
            ),
            "empty": ("Nothing to type", "Add some text above first", WARNING),
            "countdown": (
                f"Starting in {self._countdown_left}…",
                "Click into the window you want to type in",
                WARNING,
            ),
            "typing": ("Typing", f"{progress}  ·  {elapsed}  ·  Esc stops", ACCENT),
            "paused": ("Paused", f"{progress}  ·  {elapsed}  ·  Esc stops", WARNING),
            "done": ("Done", finished, ACCENT),
            "stopped": ("Stopped", f"{progress}  ·  {elapsed}", FAINT),
        }[phase]
        self.status_label.configure(text=title)
        self.status_dot.configure(text_color=colour)
        self.detail_label.configure(text=detail)
        self.pause_button.configure(text="Resume" if self.engine.paused else "Pause")

        if running != self._shown_running:  # swap Start for Pause + Stop
            self._shown_running = running
            for button in (self.start_button, self.stop_button, self.pause_button):
                button.pack_forget()
            if running:
                self.stop_button.pack(side="right")
                self.pause_button.pack(side="right", padx=(0, 8))
            else:
                self.start_button.pack(side="right")

        settings = self._collect_settings()
        self._remote_status = {
            "version": PROTOCOL_VERSION,
            "phase": phase,
            "title": title,
            "detail": detail,
            "done": self._done,
            "total": self._total,
            "elapsed_s": round(self.engine.elapsed, 1),
            "settings": {
                "speed_ms": settings.speed_ms,
                "delay_ms": settings.delay_ms,
                "loop_count": settings.loop_count,
                "human_jitter_pct": settings.human_jitter_pct,
                "caps_mode": settings.caps_mode.value,
            },
        }
        self._update_phone_button()

    # -------------------------------------------------------------- actions

    def _register_hotkey(self, hotkey_type: str) -> None:
        self.current_hotkey_type = hotkey_type
        self._hotkey_managers[hotkey_type].begin_capture()
        self.hotkey_buttons[hotkey_type].configure(
            text="Press keys…", text_color=MUTED, border_color=TEXT
        )

    def _on_hotkey_captured(self, names: list[str]) -> None:
        kind = self.current_hotkey_type
        if kind is None:
            return
        setattr(self.settings, f"{kind}_hotkey", names)
        self._hotkey_managers[kind].set_hotkey(names)
        self.current_hotkey_type = None
        self._show_hotkey(kind)

    def _on_caps_mode_changed(self, value: str) -> None:
        self.caps_mode = next(mode for mode, label in _CASE_LABELS.items() if label == value)

    def _load_text_file(self) -> None:
        path = tkinter.filedialog.askopenfilename(
            title="Load text to type",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
        )
        if not path:
            return
        try:
            with open(path, encoding="utf-8", errors="replace") as file:
                content = file.read()
        except OSError as exc:
            messagebox.showerror("Load Failed", str(exc))
            return
        self.text_input.delete("1.0", "end")
        self.text_input.insert("1.0", content)
        self._update_estimate()

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
        self.settings.caps_mode = self.caps_mode
        return self.settings.validated()

    def start_typing(self) -> None:
        text = self.text_input.get("1.0", "end").strip()
        if not text:
            self._phase = "empty"
            self.text_input.focus_set()
            self._update_status()
            return
        settings = self._collect_settings()
        if not self.engine.start(text, settings):
            return  # already running
        self._phase = "countdown" if settings.start_countdown_s else "typing"
        self._countdown_left = settings.start_countdown_s
        self._done, self._total = 0, len(tokenize(text))
        self._stop_requested = False
        self.progress_bar.set(0)
        self._update_status()

    def stop_typing(self) -> None:
        if self.engine.running:
            self._stop_requested = True
        self.engine.stop()

    def toggle_pause(self) -> None:
        if self.engine.paused:
            self.engine.resume()
        else:
            self.engine.pause()

    def _toggle_mode(self, value: str) -> None:
        self.settings.dark_mode = value == "Dark"
        ctk.set_appearance_mode(value.lower())

    # -------------------------------------------------------- engine events

    def _on_countdown(self, remaining: int) -> None:
        self._phase, self._countdown_left = "countdown", remaining
        self._update_status()

    def _on_progress(self, done: int, total: int) -> None:
        self._phase, self._done, self._total = "typing", done, total
        self.progress_bar.set(done / total if total else 0.0)

    def _on_complete(self, elapsed: float, iterations: int) -> None:
        self._phase = "stopped" if self._stop_requested else "done"
        self._runs = iterations
        if not self._stop_requested:
            self.progress_bar.set(1)
        self._update_status()

    # --------------------------------------------------------- phone remote

    def _remote_command(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        """Called on a server thread: run the command on the Tk thread and wait."""
        result: Future[dict[str, Any]] = Future()

        def run() -> None:
            try:
                result.set_result(self._run_remote_command(name, args))
            except Exception as exc:  # re-raised on the server thread
                result.set_exception(exc)

        self._events.put((run, ()))
        return result.result(timeout=5)

    def _run_remote_command(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        running = self.engine.running
        if name == "start":
            if running:
                raise RemoteError(409, "already typing")
            self._set_fields(args["settings"])
            self.text_input.delete("1.0", "end")
            self.text_input.insert("1.0", args["text"])
            self._update_estimate()
            self.start_typing()
        elif name == "pause" and running:
            self.engine.pause()
        elif name == "resume" and running:
            self.engine.resume()
        elif name == "stop":
            self.stop_typing()
        self._update_status()
        return {"ok": True}

    def _update_phone_button(self) -> None:
        if not self.remote.running:
            label = "Phone"
        elif time.monotonic() - self.remote.last_seen < 5:
            label = "Phone · connected"
        else:
            label = "Phone · on"
        if label != self._phone_label:
            self._phone_label = label
            self.phone_button.configure(text=label)

    def _open_phone_dialog(self) -> None:
        if self._phone_dialog is not None and self._phone_dialog.winfo_exists():
            self._phone_dialog.focus()
            return
        dialog = ctk.CTkToplevel(self.app, fg_color=GROUND)
        dialog.title("Connect a phone")
        dialog.resizable(False, False)
        dialog.transient(self.app)
        self._phone_dialog = dialog

        body = ctk.CTkFrame(dialog, fg_color="transparent")
        body.pack(padx=_PAD, pady=_PAD)
        row = ctk.CTkFrame(body, fg_color="transparent")
        row.pack(fill="x")
        ctk.CTkLabel(row, text="Phone remote", font=self.font_section, text_color=TEXT).pack(
            side="left"
        )
        self.remote_toggle = self._small_toggle(row, ["Off", "On"], self._toggle_remote)
        self.remote_toggle.set("On" if self.remote.running else "Off")
        self.remote_toggle.pack(side="right", padx=(24, 0))

        self.qr_canvas = tkinter.Canvas(body, bg="#ffffff", highlightthickness=0)
        self.pair_code = ctk.CTkLabel(body, text="", font=self.font_title, text_color=TEXT, anchor="w")
        self.pair_code.pack(fill="x", pady=(12, 0))
        self.pair_hint = ctk.CTkLabel(
            body, text="", font=self.font_small, text_color=MUTED, anchor="w", justify="left",
            wraplength=300,
        )
        self.pair_hint.pack(fill="x", pady=(4, 0))
        self._show_pairing()

    def _toggle_remote(self, value: str) -> None:
        if value == "On":
            try:
                self.remote.start()
            except OSError as exc:  # e.g. no network adapter
                self.remote_toggle.set("Off")
                self.pair_hint.configure(text=f"Couldn't switch the remote on: {exc}")
                return
        else:
            self.remote.stop()
        self._show_pairing()
        self._update_phone_button()

    def _show_pairing(self) -> None:
        if not self.remote.running:
            self.qr_canvas.pack_forget()
            self.pair_code.configure(text="")
            self.pair_hint.configure(
                text="Switch on to pair the Auto Typer app on your phone. "
                "Only a phone with the code can control typing."
            )
            return
        host = lan_ip()
        self._draw_qr(self.remote.pair_uri(host))
        self.qr_canvas.pack(pady=(16, 0), before=self.pair_code)
        code = self.remote.code
        self.pair_code.configure(text=f"{code[:4]} {code[4:]}")
        self.pair_hint.configure(
            text=f"Scan with the Auto Typer app, or enter {host}:{self.remote.port} and this "
            "code. Your phone must be on the same Wi-Fi. Allow Auto Typer if Windows "
            "Firewall asks. Switching off and on makes a new code."
        )

    def _draw_qr(self, text: str) -> None:
        """Draw *text* as a QR code, black on white so any scanner can read it."""
        cell = max(3, round(4 * self.app.winfo_fpixels("1i") / 96))  # canvas units are pixels
        rows = [list(row) for row in segno.make(text, error="m").matrix_iter(border=4)]
        self.qr_canvas.configure(width=len(rows) * cell, height=len(rows) * cell)
        self.qr_canvas.delete("all")
        for y, row in enumerate(rows):
            for x, dark in enumerate(row):
                if dark:
                    self.qr_canvas.create_rectangle(
                        x * cell, y * cell, (x + 1) * cell, (y + 1) * cell,
                        fill="#000000", width=0,
                    )

    # ------------------------------------------------------------ lifecycle

    def _on_close(self) -> None:
        self.remote.stop()
        self._collect_settings()
        save_settings(self.settings)
        self.engine.stop()
        for manager in self._hotkey_managers.values():
            manager.stop()
        self.app.destroy()

    def run(self) -> None:
        for manager in self._hotkey_managers.values():
            manager.start()
        self.app.mainloop()


def main() -> None:
    AutoTyperApp().run()
