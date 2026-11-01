"""Phone remote: a small LAN HTTP server that lets the Android app drive typing.

Every request must carry the pairing code shown in the desktop app. Commands
are handed to the app's callbacks, which run them on the Tk thread, so the
desktop stays in charge. The protocol is documented in docs/remote-protocol.md.
"""

from __future__ import annotations

import hmac
import ipaddress
import json
import secrets
import socket
import threading
import time
from collections.abc import Callable
from dataclasses import replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from .config import Settings
from .keys import CapsMode

PROTOCOL_VERSION = 1
DEFAULT_PORT = 8765
MAX_BODY_BYTES = 256 * 1024

_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no 0/O or 1/I to mix up
_CODE_LENGTH = 8  # 40 bits; brute force is capped by the lockout below
_MAX_FAILURES = 5
_FAILURE_WINDOW_S = 60.0
_COMMANDS = ("start", "pause", "resume", "stop")
_INT_SETTINGS = ("speed_ms", "delay_ms", "loop_count", "human_jitter_pct")


class RemoteError(Exception):
    """A request the server refuses, with the HTTP status to reply with."""

    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status


def make_code() -> str:
    return "".join(secrets.choice(_CODE_ALPHABET) for _ in range(_CODE_LENGTH))


def lan_ip() -> str:
    """The address other devices on the LAN reach this PC at (sends no packets)."""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
        try:
            probe.connect(("10.255.255.255", 1))
            return probe.getsockname()[0]
        except OSError:
            return "127.0.0.1"


def parse_start(payload: Any, current: Settings) -> tuple[str, Settings]:
    """Validate a start request; returns the text and the merged, clamped settings."""
    if not isinstance(payload, dict):
        raise RemoteError(400, "body must be a JSON object")
    text = payload.get("text")
    if not isinstance(text, str) or not text.strip():
        raise RemoteError(400, "text must be a non-empty string")
    raw = payload.get("settings") or {}
    if not isinstance(raw, dict):
        raise RemoteError(400, "settings must be an object")

    changes: dict[str, Any] = {}
    for name in _INT_SETTINGS:
        if name in raw:
            value = raw[name]
            if isinstance(value, bool) or not isinstance(value, int):
                raise RemoteError(400, f"{name} must be a whole number")
            changes[name] = value
    if "caps_mode" in raw:
        try:
            changes["caps_mode"] = CapsMode(raw["caps_mode"])
        except ValueError:
            raise RemoteError(400, "unknown caps_mode") from None
    return text, replace(current, **changes).validated()


class RemoteServer:
    """Serves the phone API on a daemon thread while switched on."""

    def __init__(
        self,
        get_status: Callable[[], dict[str, Any]],
        get_settings: Callable[[], Settings],
        on_command: Callable[[str, dict[str, Any]], dict[str, Any]],
        *,
        host: str = "0.0.0.0",
        port: int = DEFAULT_PORT,
    ) -> None:
        """``on_command(name, args)`` runs a command and returns the JSON reply;
        it may raise RemoteError (e.g. 409 while typing is already running)."""
        self._get_status = get_status
        self._get_settings = get_settings
        self._on_command = on_command
        self._host = host
        self._port = port
        self._server: ThreadingHTTPServer | None = None
        self._lock = threading.Lock()
        self._failures: dict[str, list[float]] = {}
        self._last_start_id: str | None = None
        self.code = ""
        self.last_seen = 0.0  # time.monotonic() of the last authorized request

    @property
    def running(self) -> bool:
        return self._server is not None

    @property
    def port(self) -> int:
        return self._server.server_address[1] if self._server else 0

    def start(self) -> None:
        """Start serving with a fresh pairing code."""
        self.stop()
        self.code = make_code()
        self._failures.clear()
        self._last_start_id = None
        handler = _make_handler(self)
        try:
            server = ThreadingHTTPServer((self._host, self._port), handler)
        except OSError:  # port taken: let the OS pick a free one
            server = ThreadingHTTPServer((self._host, 0), handler)
        server.daemon_threads = True
        self._server = server
        threading.Thread(target=server.serve_forever, daemon=True, name="remote-server").start()

    def stop(self) -> None:
        if self._server:
            self._server.shutdown()
            self._server.server_close()
            self._server = None

    def pair_uri(self, host: str) -> str:
        """What the QR code carries; the Android app parses it."""
        return f"autotyper://pair?host={host}&port={self.port}&code={self.code}&v={PROTOCOL_VERSION}"

    def handle(
        self, method: str, path: str, client_ip: str, authorization: str | None, body: bytes
    ) -> tuple[int, dict[str, Any]]:
        """Answer one request with (HTTP status, JSON reply)."""
        try:
            return 200, self._route(method, path, client_ip, authorization, body)
        except RemoteError as exc:
            return exc.status, {"error": str(exc)}
        except TimeoutError:
            return 503, {"error": "the PC app is busy, try again"}
        except Exception as exc:  # report it to the phone rather than drop the connection
            return 500, {"error": f"the PC app hit an error: {exc}"}

    def _route(
        self, method: str, path: str, client_ip: str, authorization: str | None, body: bytes
    ) -> dict[str, Any]:
        if not ipaddress.ip_address(client_ip).is_private:
            raise RemoteError(403, "only devices on your local network can connect")
        self._authorize(client_ip, authorization)

        if method == "GET" and path == "/api/status":
            return self._get_status()
        command = path.removeprefix("/api/")
        if method != "POST" or command not in _COMMANDS:
            raise RemoteError(404, "not found")
        if len(body) > MAX_BODY_BYTES:
            raise RemoteError(413, "text is too long")
        try:
            payload = json.loads(body or b"{}")
        except ValueError:
            raise RemoteError(400, "body is not valid JSON") from None

        if command != "start":
            return self._on_command(command, {})
        request_id = payload.get("request_id") if isinstance(payload, dict) else None
        if request_id is not None and request_id == self._last_start_id:
            return {"ok": True, "duplicate": True}  # a retry of a start we already ran
        text, settings = parse_start(payload, self._get_settings())
        reply = self._on_command("start", {"text": text, "settings": settings})
        self._last_start_id = request_id
        return reply

    def _authorize(self, client_ip: str, authorization: str | None) -> None:
        now = time.monotonic()
        with self._lock:
            recent = [t for t in self._failures.get(client_ip, []) if now - t < _FAILURE_WINDOW_S]
            self._failures[client_ip] = recent
            if len(recent) >= _MAX_FAILURES:
                raise RemoteError(429, "too many wrong codes, try again in a minute")
            supplied = (authorization or "").removeprefix("Bearer ").strip().upper()
            if not hmac.compare_digest(supplied.encode(), self.code.encode()):
                recent.append(now)
                raise RemoteError(401, "wrong pairing code")
            self.last_seen = now


def _make_handler(remote: RemoteServer) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            self._answer(b"")

        def do_POST(self) -> None:
            length = int(self.headers.get("Content-Length") or 0)
            if length > MAX_BODY_BYTES:
                self._send(413, {"error": "text is too long"})
                return
            self._answer(self.rfile.read(length))

        def _answer(self, body: bytes) -> None:
            status, reply = remote.handle(
                self.command, self.path, self.client_address[0],
                self.headers.get("Authorization"), body,
            )
            self._send(status, reply)

        def _send(self, status: int, reply: dict[str, Any]) -> None:
            data = json.dumps(reply).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, format: str, *args: Any) -> None:
            pass  # the windowed exe has no stderr to log to

    return Handler
