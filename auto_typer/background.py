"""Running in the background: a tray icon, autostart, and one Auto Typer at a time.

Closing the window hides it to the tray, where hotkeys and the phone remote keep
working. A hidden copy is easy to forget, and two copies would each type on the
same hotkey, so a second launch doesn't start another one: it asks the running
copy to show its window instead.
"""

from __future__ import annotations

import socket
import sys
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

from . import system

INSTANCE_PORT = 48765  # bound on 127.0.0.1 only, so nothing outside this PC can reach it
_SHOW = b"show"
_SHOWN = b"shown"


class SingleInstance:
    """Holds a loopback port while this copy of Auto Typer runs."""

    def __init__(self, server: socket.socket | None) -> None:
        self._server = server

    @classmethod
    def claim(cls, port: int = INSTANCE_PORT) -> SingleInstance | None:
        """Become the running copy, or return None after asking the copy that
        already runs to show its window."""
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            server.bind(("127.0.0.1", port))
        except OSError:
            server.close()
            if _ask_to_show(port):
                return None
            return cls(None)  # another program holds the port: run without the check
        server.listen()
        return cls(server)

    def listen(self, on_show: Callable[[], None]) -> None:
        """Call *on_show*, on a background thread, whenever a later launch asks."""
        server = self._server
        if server is None:
            return

        def serve() -> None:
            while True:
                try:
                    conn, _ = server.accept()
                except OSError:  # the socket was closed: Auto Typer is quitting
                    return
                with conn:
                    conn.settimeout(1)
                    try:
                        if conn.recv(16) == _SHOW:
                            on_show()
                            conn.sendall(_SHOWN)
                            conn.recv(1)  # let the caller hang up first; frees the port sooner
                    except OSError:
                        pass  # the caller hung up early; there's no one to answer

        threading.Thread(target=serve, daemon=True, name="single-instance").start()

    def close(self) -> None:
        if self._server is not None:
            self._server.close()
            self._server = None


def _ask_to_show(port: int) -> bool:
    """True if an Auto Typer answered on *port* and is showing its window."""
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=1) as conn:
            conn.sendall(_SHOW)
            return conn.recv(16) == _SHOWN
    except OSError:
        return False


def app_image(size: int = 64) -> Any:
    """The app icon: a key with a text caret, over the lime progress line."""
    from PIL import Image, ImageDraw

    image = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((0, 0, 63, 63), radius=14, fill=(12, 13, 15, 255))
    draw.rounded_rectangle((14, 12, 49, 43), radius=5, fill=(255, 255, 255, 255))
    draw.rectangle((30, 18, 33, 37), fill=(12, 13, 15, 255))
    draw.rectangle((14, 49, 49, 52), fill=(198, 242, 78, 255))
    return image if size == 64 else image.resize((size, size), Image.Resampling.LANCZOS)


tray_image = app_image  # the tray shows the same icon


def write_icon(path: Path) -> Path:
    """Save the app icon as a multi-size ``.ico`` (for the window and the exe)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    app_image(256).save(path, format="ICO", sizes=[(16, 16), (32, 32), (48, 48), (256, 256)])
    return path


def start_tray(
    on_show: Callable[[], None],
    on_quit: Callable[[], None],
    keep_running: Callable[[], bool],
    on_toggle_keep_running: Callable[[], None],
    on_toggle_autostart: Callable[[], None],
) -> Any:
    """Show the tray icon on its own thread and return it (a ``pystray.Icon``).

    The callbacks run on the tray's thread; the app marshals them to Tk.
    """
    import pystray  # here, so tests and headless runs don't need a tray

    menu = pystray.Menu(
        pystray.MenuItem("Show Auto Typer", on_show, default=True),
        pystray.MenuItem(
            "Keep running when closed",
            on_toggle_keep_running,
            checked=lambda item: keep_running(),
        ),
        pystray.MenuItem(
            "Start with Windows",
            on_toggle_autostart,
            checked=lambda item: system.autostart_enabled(),
            visible=sys.platform == "win32",
        ),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Quit Auto Typer", on_quit),
    )
    icon = pystray.Icon("AutoTyper", tray_image(), "Auto Typer", menu)
    threading.Thread(target=icon.run, daemon=True, name="tray").start()
    return icon
