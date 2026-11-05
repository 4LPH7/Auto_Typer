"""Tests for the phone remote server, over real HTTP on localhost."""

import json
import urllib.error
import urllib.request

import pytest

from auto_typer.config import Settings
from auto_typer.keys import CapsMode
from auto_typer.remote import MAX_BODY_BYTES, RemoteError, RemoteServer

STATUS = {"version": 1, "phase": "ready"}


@pytest.fixture
def remote():
    calls: list[tuple[str, dict]] = []

    def on_command(name, args):
        calls.append((name, args))
        return {"ok": True}

    server = RemoteServer(lambda: STATUS, Settings, on_command, host="127.0.0.1", port=0)
    server.start()
    yield server, calls
    server.stop()


def call(server, method, path, code=None, body=None):
    if body is not None and not isinstance(body, bytes):
        body = json.dumps(body).encode()
    request = urllib.request.Request(
        f"http://127.0.0.1:{server.port}{path}", data=body, method=method
    )
    if code is not None:
        request.add_header("Authorization", f"Bearer {code}")
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read())


def test_status_needs_the_pairing_code(remote):
    server, _ = remote
    assert call(server, "GET", "/api/status")[0] == 401
    assert call(server, "GET", "/api/status", "WRONGCOD")[0] == 401
    assert call(server, "GET", "/api/status", server.code) == (200, STATUS)


def test_locks_out_after_five_wrong_codes(remote):
    server, _ = remote
    for _ in range(5):
        call(server, "GET", "/api/status", "WRONGCOD")
    assert call(server, "GET", "/api/status", server.code)[0] == 429


def test_start_merges_and_clamps_settings(remote):
    server, calls = remote
    body = {
        "request_id": "r1",
        "text": "hello",
        "settings": {"speed_ms": 999_999, "caps_mode": "uppercase", "paste_mode": True},
    }
    assert call(server, "POST", "/api/start", server.code, body) == (200, {"ok": True})
    [(name, args)] = calls
    assert (name, args["text"]) == ("start", "hello")
    assert args["settings"].speed_ms == 10_000  # clamped
    assert args["settings"].caps_mode is CapsMode.UPPERCASE
    assert args["settings"].paste_mode is True
    assert args["settings"].delay_ms == Settings().delay_ms  # unsent fields keep the PC's value
    assert args["settings"].focus_guard == Settings().focus_guard


def test_retried_start_types_once(remote):
    server, calls = remote
    body = {"request_id": "r1", "text": "hello"}
    call(server, "POST", "/api/start", server.code, body)
    status, reply = call(server, "POST", "/api/start", server.code, body)
    assert (status, reply.get("duplicate")) == (200, True)
    assert len(calls) == 1


@pytest.mark.parametrize(
    "body",
    [
        {"text": "   "},
        {"text": "hi", "settings": {"caps_mode": "shouting"}},
        {"text": "hi", "settings": {"speed_ms": "fast"}},
        {"text": "hi", "settings": {"paste_mode": "yes"}},
        b"not json",
    ],
)
def test_invalid_start_is_rejected(remote, body):
    server, calls = remote
    assert call(server, "POST", "/api/start", server.code, body)[0] == 400
    assert calls == []


def test_oversized_text_is_rejected(remote):
    server, calls = remote
    body = json.dumps({"text": "x" * MAX_BODY_BYTES}).encode()
    assert server.handle("POST", "/api/start", "127.0.0.1", f"Bearer {server.code}", body)[0] == 413
    assert calls == []


def test_only_local_network_devices_can_connect(remote):
    server, _ = remote
    status, _ = server.handle("GET", "/api/status", "8.8.8.8", f"Bearer {server.code}", b"")
    assert status == 403


def test_command_refusals_keep_their_status():
    def busy(name, args):
        raise RemoteError(409, "already typing")

    server = RemoteServer(lambda: STATUS, Settings, busy, host="127.0.0.1", port=0)
    server.start()
    try:
        assert call(server, "POST", "/api/pause", server.code) == (409, {"error": "already typing"})
    finally:
        server.stop()


def test_switching_on_again_makes_a_new_code(remote):
    server, _ = remote
    old_code = server.code
    server.start()
    assert server.code != old_code
    assert call(server, "GET", "/api/status", old_code)[0] == 401


def test_pair_uri_carries_host_port_and_code(remote):
    server, _ = remote
    assert server.pair_uri("192.168.1.5") == (
        f"autotyper://pair?host=192.168.1.5&port={server.port}&code={server.code}&v=1"
    )
