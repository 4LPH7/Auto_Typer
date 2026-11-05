"""Tests for SingleInstance: one Auto Typer at a time, over loopback."""

import socket
import threading

from auto_typer.background import SingleInstance


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def test_second_launch_shows_the_running_copy_instead_of_starting():
    port = free_port()
    first = SingleInstance.claim(port)
    assert first is not None
    shown = threading.Event()
    first.listen(shown.set)
    try:
        assert SingleInstance.claim(port) is None
        assert shown.wait(2)
    finally:
        first.close()


def test_port_is_free_again_after_the_running_copy_quits():
    port = free_port()
    first = SingleInstance.claim(port)
    first.listen(lambda: None)
    assert SingleInstance.claim(port) is None  # a second launch talks to it
    first.close()

    again = SingleInstance.claim(port)
    try:
        assert again is not None and again._server is not None
    finally:
        again.close()


def test_runs_anyway_when_another_program_holds_the_port():
    with socket.socket() as other:  # listens but never answers like Auto Typer
        other.bind(("127.0.0.1", 0))
        other.listen()
        instance = SingleInstance.claim(other.getsockname()[1])
    assert instance is not None


def test_icon_file_has_every_size(tmp_path):
    from PIL import Image

    from auto_typer.background import write_icon

    path = write_icon(tmp_path / "icons" / "AutoTyper.ico")
    with Image.open(path) as icon:
        assert icon.format == "ICO"
        assert {(16, 16), (32, 32), (48, 48), (256, 256)} <= set(icon.info["sizes"])
