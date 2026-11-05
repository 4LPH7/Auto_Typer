# Phone remote protocol (v1)

The contract between the PC app (`auto_typer/remote.py`) and the Android app
(`android/.../PcClient.kt`). The PC types; the phone only sends text, settings and commands.

## Pairing

On the PC, **Phone → On** starts a small HTTP server on the local network (port 8765, or a free
port if that one is taken) and shows a QR code holding:

```
autotyper://pair?host=192.168.1.5&port=8765&code=K7Q2M9XD&v=1
```

The code is 8 characters from `ABCDEFGHJKLMNPQRSTUVWXYZ23456789` and changes every time the remote
is switched on. Every request carries it:

```
Authorization: Bearer K7Q2M9XD
```

## Calls

All bodies and replies are JSON.

| Call | Body | Reply |
| --- | --- | --- |
| `GET /api/status` | none | the status object below |
| `POST /api/start` | `{"request_id": "…", "text": "…", "settings": {…}}` | `{"ok": true}` |
| `POST /api/pause` | none | `{"ok": true}` |
| `POST /api/resume` | none | `{"ok": true}` |
| `POST /api/stop` | none | `{"ok": true}` |

Status object:

```json
{
  "version": 1,
  "phase": "typing",
  "title": "Typing",
  "detail": "58 of 149 keystrokes  ·  2.4 s  ·  Esc stops",
  "done": 58,
  "total": 149,
  "elapsed_s": 2.4,
  "settings": {
    "speed_ms": 25, "delay_ms": 0, "loop_count": 1, "human_jitter_pct": 0, "caps_mode": "as_is",
    "paste_mode": false, "focus_guard": true
  }
}
```

`phase` is one of `ready`, `empty`, `countdown`, `typing`, `paused`, `done`, `stopped`.
`caps_mode` is one of `as_is`, `uppercase`, `lowercase`, `sentence_case`.
`paste_mode` puts the text on the PC's clipboard and presses Ctrl+V instead of typing it.
`focus_guard` pauses typing if the PC's active window changes; `resume` continues into whichever
window is active then. Both are booleans and were added after v1 shipped; older phones never send
them and older PCs ignore them.

### Start

- `settings` is optional, and so is each field in it; missing fields keep the PC's current values.
  Values are clamped to the PC's limits (for example `speed_ms` to 0–10000).
- `request_id` makes retries safe: a start with the same id as the last accepted one is not typed
  again and replies `{"ok": true, "duplicate": true}`. Send a new id for each new start.
- The PC shows the phone's text and settings in its own window before typing, after its usual
  countdown, into whichever window is active.

## Errors

Errors reply `{"error": "…"}` with:

| Status | When |
| --- | --- |
| 400 | invalid JSON, empty text, a wrong type (booleans must be `true`/`false`), or an unknown `caps_mode` |
| 401 | missing or wrong code |
| 403 | the phone isn't on a private (local) network address |
| 404 | unknown path |
| 409 | `start` while typing is already running |
| 413 | body over 256 KB |
| 429 | 5 wrong codes from one address within 60 s; wait a minute |
| 503 | the PC app didn't answer in time |

## Security notes

The server is off by default and listens only while switched on. Requests travel as plain HTTP on
the local network, so use it on a network you trust; anyone who can watch that Wi-Fi could read the
code. Pressing Esc on the PC always stops typing.
