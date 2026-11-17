# Android app improvements: research notes

- Date: 2026-11-17
- Question: "how can i improve the android app i want new features and fast connectivity and more useful features"
- Scope: `android/` (Kotlin + Compose), `auto_typer/remote.py`, `docs/remote-protocol.md`. No source changed.

Citation format: `path:line` for repo facts; URL plus section/anchor for external facts. Items marked **unverified** could not be confirmed from a primary source during this run.

## 1. Current state (facts from the repo)

### Build and toolchain

| Item | Value | Source |
| --- | --- | --- |
| compileSdk | 36 | `android/app/build.gradle.kts:14` |
| minSdk | 26 | `android/app/build.gradle.kts:18` |
| targetSdk | 36 (comment: 37 needs ACCESS_LOCAL_NETWORK) | `android/app/build.gradle.kts:19` |
| versionName / versionCode | 2.2.0 / 2 | `android/app/build.gradle.kts:20-21` |
| AGP | 8.13.2 ("AGP 8 line on purpose") | `android/gradle/libs.versions.toml:1-3` |
| Kotlin | 2.2.21 (with Compose compiler plugin) | `libs.versions.toml:4`, plugin block |
| Compose BOM | 2025.12.01 | `libs.versions.toml:5` |
| activity-compose / lifecycle / core-ktx | 1.11.0 / 2.9.4 / 1.17.0 | `libs.versions.toml:6-8` |
| zxing-android-embedded (QR scan) | 4.3.0 | `libs.versions.toml:9` |
| Gradle wrapper | 8.14.6 | `android/gradle/wrapper/gradle-wrapper.properties` |
| JVM target | 17 (compile options); CI JDK 21 | `build.gradle.kts` compileOptions; `.github/workflows/build.yml` apk job |
| Minify | release `isMinifyEnabled = false` | `build.gradle.kts:37` |
| Tests | 5 JUnit tests, all for parsing (QR, typed address, status JSON, settings JSON) | `android/app/src/test/.../PcClientTest.kt` |
| CI | `./gradlew test assembleDebug` on PR/main; signed release on tag | `.github/workflows/build.yml` apk job |

### Networking and transport

- **No networking library.** The app uses `java.net.HttpURLConnection` directly (`PcClient.kt:100`, `:128-130`). Timeouts: connect 3000 ms, read 8000 ms (`PcClient.kt:128-129`). Auth is `Authorization: Bearer <code>` (`PcClient.kt:130`).
- **Transport:** plain HTTP/1.x over the LAN to `http://<host>:<port>/api` (`PcClient.kt:100`). Cleartext is allowed app-wide with `android:usesCleartextTraffic="true"` (`app/src/main/AndroidManifest.xml:13`).
- **Keep-alive:** none on purpose or by design. Each call opens a connection and disconnects in `finally` (`PcClient.kt`, `request()`). The PC side is `BaseHTTPRequestHandler` with the default `protocol_version` (see section 2), so every request is a new TCP connection.
- **Discovery:** manual IP or QR code only. `Pairing.fromQr` accepts `autotyper://pair?host=&port=&code=` (`PcClient.kt:13-20`), `Pairing.fromTyped` takes `ip[:port]` plus the 8-character code (`PcClient.kt:22-28`). There is no NSD, mDNS, multicast, `WifiManager`, or `ConnectivityManager` use (repo-wide grep returned none).
- **Pairing persistence:** `SharedPreferences("pairing", MODE_PRIVATE)` holds host, port, and code (`RemoteViewModel.kt:19`, `:31-38`).
- **QR parser:** checks scheme and host only, not `v=1` (`PcClient.kt:15`). A future protocol v2 would not be rejected.

### Reconnect and keep-alive behavior

- `RemoteViewModel.poll()` loops while the screen is started (`RemoteScreen.kt`, `repeatOnLifecycle(STARTED)`): 250 ms while running, 1000 ms idle, 2000 ms after a `PcException` or `IOException` (`RemoteViewModel.kt:71-90`).
- Error text when unreachable: "Can't reach your PC. Check that its phone remote is on and you're on the same Wi-Fi." (`RemoteViewModel.kt:132-134`).
- A failed start is retried with the same `request_id`, so the PC types once (`RemoteViewModel.kt:95-96`; PC side `remote.py:184-186`).
- No `ConnectivityManager` callback: a Wi-Fi change is noticed only by the next failed poll (up to 2 s later).

### Protocol surface (`docs/remote-protocol.md`, `auto_typer/remote.py`)

- Calls: `GET /api/status`, `POST /api/start|pause|resume|stop` (protocol doc "Calls" table).
- Status object includes `phase`, `title`, `detail`, `done`, `total`, `elapsed_s`, `settings` (protocol doc, status example).
- `settings` fields: `speed_ms, delay_ms, loop_count, human_jitter_pct, caps_mode, paste_mode, focus_guard` (protocol doc; `remote.py:34-35`).
- Limits: body 256 KB (`remote.py:27`); 5 wrong codes per minute per IP then 429 (`remote.py:31-32`, `:197`); private-address check, 403 otherwise (`remote.py:166`).
- Server binds `0.0.0.0` by default (`remote.py:100`), with a fallback to an OS-picked port (`remote.py:133-135`). `daemon_threads = True` (`remote.py:136`).

### UI screens

- **ConnectScreen:** "Scan QR code" (zxing `ScanContract`), manual address and code fields, Connect button (`ConnectScreen.kt`).
- **RemoteScreen:** text field (max 60 000 chars, `RemoteViewModel.kt:132`), NumberFields for key delay, word pause, repeat, jitter, segmented control for letter case, status card with progress bar, Start / Pause-Resume / Stop (`RemoteScreen.kt:104-178`). "Pair again" clears the saved pairing (`RemoteViewModel.kt` `forget()`).
- Manifest: `INTERNET` only (`AndroidManifest.xml:5`). The QR scanner is zxing's `CaptureActivity` with `fullSensor` orientation.

### Gaps between the docs and the app

- `CHANGELOG.md` (2.2.0) says the phone "accepts and reports `paste_mode` and `focus_guard`". The Android `TypingSettings` has five fields only, `speedMs, delayMs, loopCount, jitterPct, capsMode` (`PcClient.kt:43-49`), and `toJson()` sends only those five. The Android app has no toggle for either option (`RemoteScreen.kt`). The PC keeps its own values for both.
- `auto_typer/remote.py` returns 403 for non-private IPs (`remote.py:166`); the phone has no UI that explains this error.

## 2. Findings

Effort: S = under a day, M = a few days, L = more than a week. Each item has a "skip until" condition.

(Sections A, B, C and the rejected list follow in the next writes.)

### A. Fast connectivity

**A1. Keep-alive on the PC server (stdlib only). Effort S.**
- Set `protocol_version = "HTTP/1.1"` on the handler, keep `Content-Length` on every reply, and always read or close the request body. Python says HTTP/1.1 persistent connections need "an accurate `Content-Length` header ... in all of its responses" and the default is HTTP/1.0 (https://docs.python.org/3/library/http.server.html, `protocol_version` entry).
- Set `disable_nagle_algorithm = True` on the handler to get `TCP_NODELAY`. CPython defines it on `StreamRequestHandler` with default `False` and calls `setsockopt(..., TCP_NODELAY, True)` when set (https://raw.githubusercontent.com/python/cpython/3.15/Lib/socketserver.py, around lines 800-812).
- Set a handler `timeout` (default `None`, which blocks forever on an idle keep-alive socket; same source, line ~800). Doc: https://docs.python.org/3/library/socketserver.html, `timeout` class variable.
- Caveat in current code: `do_POST` sends 413 without reading the body (`remote.py:213-215`). Under HTTP/1.1 that leaves unread bytes on the socket. Read or close first.
- Why: today every poll (4 per second while typing) pays a TCP handshake. Expected gain is about one LAN round trip per call. Measure before claiming a number.
- Skip until: measured status-poll latency is a visible problem on the target Wi-Fi.

**A2. Connection-level reuse on the phone. Effort S (after A1).**
- `HttpURLConnection` pools connections when the server allows it. I could not confirm the pooling behavior from the Android reference page (no keep-alive text found in https://developer.android.com/reference/java/net/HttpURLConnection). **Unverified** for Android internals; test it with A1 in place.
- Skip until: A1 is done and measured.

**A3. Re-poll on network change with `ConnectivityManager.NetworkCallback`. Effort S.**
- Register a `NetworkCallback` on the Wi-Fi network; on `onAvailable`, poll immediately instead of waiting out the 2 s backoff; on `onLost`, show "Wi-Fi lost" at once. The reference says `onAvailable` is followed by capability and link-property callbacks and that you must not call the synchronous `getNetworkCapabilities` / `getLinkProperties` from inside the callback (https://developer.android.com/reference/android/net/ConnectivityManager.NetworkCallback, `onAvailable`).
- This directly reduces the "reconnect" delay the user asks about: today it is up to 2000 ms after the network returns (`RemoteViewModel.kt:85`, `:88`).
- Requires `ACCESS_NETWORK_STATE` (**unverified** from the callback page; check the permission list on the ConnectivityManager reference before adding it).
- Skip until: users report slow recovery after Wi-Fi roam or sleep.

**A4. Stop the 2 s error backoff from being the only retry. Effort S.**
- Retry once after 300 ms on `IOException` before showing the error, and keep the 2 s backoff only for repeated failures (`RemoteViewModel.kt:86-88`). This is a code-level change with no external source; it is a judgment call, so measure it.
- Skip until: A3 is in and the error still shows for transient drops.

**A5. Power-save / low-latency Wi-Fi lock while a session runs. Effort S, but battery cost.**
- `WifiManager.WifiLock` keeps the radio awake while held; the doc advises holding it only when needed and says it needs `WAKE_LOCK` (https://developer.android.com/reference/android/net/wifi/WifiManager.WifiLock, class description).
- `WIFI_MODE_FULL_LOW_LATENCY` is a `createWifiLock` mode; the WifiManager reference says it carries "all the restrictions documented on that lock" (https://developer.android.com/reference/android/net/wifi/WifiManager, `createWifiLock(int, String)`). The page does not give a latency number.
- Skip until: measured command latency on Wi-Fi power save is noticeable. Acquire only while `status.running` and release on stop.

**A6. Discovery without typing an IP (NSD on the phone, plus a PC advertiser). Effort M.**
- Android NSD: register/discover a `_service._tcp` type, resolve the instance, use `ServerSocket(0)` for ports, and let Android resolve name conflicts (https://developer.android.com/develop/connectivity/wifi/use-nsd, sections "Register your service" and "Discover services").
- Phone side is platform-only, no dependency. The PC side is the problem: stdlib cannot advertise mDNS on Windows. A pure-Python mDNS library (e.g. `zeroconf`) would be a new dependency. **Unverified** for that library's current maintenance status; not checked in this run.
- Lower-dependency option: a UDP beacon from the PC (stdlib `socket`) carrying only host, port and a name, never the code. Phone listens with `WifiManager.MulticastLock` if the beacon uses multicast; the lock "Allows an application to receive Wifi Multicast packets" (https://developer.android.com/reference/android/net/wifi/WifiManager.MulticastLock). Whether a limited-broadcast address needs the lock is **unverified**; test it.
- Skip until: users run more than one PC, or DHCP changes the IP often enough that the QR code must be rescanned. QR pairing already removes typing.

**A7. Push instead of poll: Server-Sent Events or WebSocket. Effort M to L. Not recommended now.**
- SSE is plain HTTP: `text/event-stream` over one long-lived response (https://html.spec.whatwg.org/multipage/server-sent-events.html). Stdlib on the PC could stream it; the phone would read the stream with `HttpURLConnection`. Needs A1 first.
- WebSocket is RFC 6455 (https://www.rfc-editor.org/rfc/rfc6455). Python stdlib has no WebSocket server, and I did not verify a platform WebSocket client on Android. OkHttp WebSocket docs were unreachable in this run (**unverified**). Adding a server library and OkHttp is a dependency cost the repo has avoided.
- Status updates are small and 250 ms polling is adequate for progress text. Push mainly saves battery.
- Skip until: polling wakeups are measured as a battery problem, or the status must update faster than about 250 ms.

**A8. Shorter connect timeout for status polls. Effort S.**
- `connectTimeout = 3_000` (`PcClient.kt:128`) means a sleeping PC shows an error only after 3 s, and polls at 2 s intervals stack up. A 1000 ms connect timeout for `status()` only is a judgment call with no external source. Measure on the target network first.
- Skip until: users report the "can't reach" message appearing too late.

### B. New useful features

**B1. Expose `paste_mode` and `focus_guard` on the phone. Effort S. Highest value per effort.**
- The protocol already carries both (`docs/remote-protocol.md` status and Start settings; `remote.py:35`, `_BOOL_SETTINGS`), and `parse_start` validates them (`remote.py:78-82`). The Android app drops them: `TypingSettings` has five fields (`PcClient.kt:43-49`) and `RemoteScreen.kt` has no switch for either.
- Add two `Switch` rows to `RemoteScreen`, two fields to `TypingSettings` and to `toJson`/`fromJson`. The protocol doc says older PCs ignore unknown fields.
- Skip until: never. This closes a documented gap.

**B2. Share target: "Send to Auto Typer" from any app. Effort S.**
- Declare an `ACTION_SEND` intent filter for `text/plain` and prefill the text field from `EXTRA_TEXT` (https://developer.android.com/training/sharing/receive, the simple-data section, which names `ACTION_SEND` and the `text/plain` MIME type).
- No new dependency. `MainActivity.kt:13-22` would read the incoming intent and call `model.updateText`.
- Skip until: never. Cheap and common for a text-typing app.

**B3. Saved snippets / recent texts. Effort S to M.**
- Preferences DataStore is the first-party store for this. The DataStore page recommends migrating from SharedPreferences (https://developer.android.com/topic/libraries/architecture/datastore). Keep the existing pairing in SharedPreferences; migration is optional.
- DataStore is a new dependency (`androidx.datastore`). The zero-dependency option is a JSON string in SharedPreferences, which fits a short list. Prefer that unless the data grows.
- Skip until: users keep re-typing the same texts and that is the complaint.

**B4. "Paste from clipboard" button. Effort S.**
- Android 10 limits clipboard reads from the background (https://developer.android.com/about/versions/10/privacy/changes, "Limited access to clipboard data"). Read only on a button press while the screen is in the foreground.
- Skip until: users ask for it. Typing or pasting into the text field already covers most cases.

**B5. Quick Settings tile (one-tap pause / stop). Effort M.**
- `TileService` provides a Quick Settings tile (https://developer.android.com/reference/android/service/quicksettings/TileService). It would call the PC's pause or stop from outside the app, so it reuses the saved pairing.
- Skip until: users want to stop typing without opening the app. Esc on the PC already stops it.

**B6. Home-screen widget with pause / stop. Effort M to L.**
- Options: AppWidget (https://developer.android.com/develop/ui/views/appwidgets/overview), or Glance, "a framework built on top of the Jetpack Compose runtime" (https://developer.android.com/develop/ui/compose/glance). Glance is a new dependency; AppWidgets need none but more code.
- Skip until: B5 is in and users still want a glanceable status.

**B7. Foreground service that keeps the remote alive. Effort M. Not recommended.**
- A foreground service needs a notification and a declared type (https://developer.android.com/develop/background-work/services/fgs). The PC keeps typing with the phone off, so the phone needs no live connection during a run. This adds battery and policy surface for little gain.
- Skip until: a pause or stop control in the notification shade is requested.

**B8. Type from any keyboard via an input method. Effort L.**
- `InputMethodService` lets an app act as a keyboard (https://developer.android.com/reference/android/inputmethodservice/InputMethodService). Each keypress would go to the PC. Large scope: a new component, IME settings UX, and per-key HTTP calls, which makes A1 matter more.
- Skip until: users want to type into other apps' fields through the phone.

**B9. Accessibility service to drive the phone. Rejected.**
- Google Play limits `AccessibilityService` to apps that help people with disabilities; the `isAccessibilityTool` flag is for that purpose (https://support.google.com/googleplay/android-developer/answer/10964491). This app does not qualify for that use on Play.

### C. Code and build hygiene

**C1. Verify the QR protocol version. Effort S.**
- `Pairing.fromQr` ignores `v` (`PcClient.kt:15`). Reject any `v` other than `1` with a clear message; the PC emits `v={PROTOCOL_VERSION}` (`remote.py:148`).
- Skip until: never. It is a short guard that matters the first time the protocol changes.

**C2. Tests beyond parsing. Effort M.**
- The only tests cover parsing (`PcClientTest.kt`). Nothing covers `RemoteViewModel` (status, `request_id` retry, error text) or the HTTP path. The user's testing rule asks for 80% coverage. For the HTTP path, a stdlib `HttpServer` in the test source set avoids a new dependency; OkHttp `MockWebServer` would add one. **Unverified** that a stdlib server runs on the JVM unit-test classpath without Android stubs; test it.
- Skip until: C1 and B1 are in and changes start breaking silently.

**C3. AGP is behind. Effort M.**
- The pin is AGP 8.13.2 with the comment "AGP 8 line on purpose" (`libs.versions.toml:1`). The AGP release notes list the 9.5 line, including an alpha (https://developer.android.com/build/releases/gradle-plugin). Whether 9.x is stable and required by the next AndroidX releases is **unverified** in this run.
- Skip until: a needed AndroidX release requires AGP 9, or a compileSdk bump forces it.

**C4. Local network protection when targetSdk reaches 37. Effort S when it happens; a blocker later.**
- Local network protections are enforced for apps targeting Android 17 (API 37) or higher, using `ACCESS_LOCAL_NETWORK` (https://developer.android.com/privacy-and-security/local-network-permission, "Android 17 Enforcement"). The app talks to private addresses, so raising `targetSdk` (`build.gradle.kts:19`) needs the permission and a runtime prompt. The existing build comment is correct.
- Skip until: targetSdk is raised to 37.

**C5. Cleartext is allowed app-wide. Effort M, partial fix only.**
- `usesCleartextTraffic="true"` (`AndroidManifest.xml:13`) applies to every host. The Network Security Config can set `cleartextTrafficPermitted` per `domain-config` (https://developer.android.com/privacy-and-security/security-config). **Unverified:** whether it accepts IP literals or CIDR ranges. I found no CIDR option on that page, so the app-wide flag may stay.
- Skip until: a security review asks for it, or the protocol moves to HTTPS.

**C6. Release minification is off. Effort S.**
- `isMinifyEnabled = false` (`build.gradle.kts:37`). **Unverified** whether R8 is worth enabling; the gain is unknown.
- Skip until: APK size is a concern.

**C7. Check whether a newer Compose BOM exists. Effort S.**
- BOM `2025.12.01` is pinned (`libs.versions.toml:5`). The BOM mapping page lists it (https://developer.android.com/develop/ui/compose/bom/bom-mapping). Whether a newer BOM is current is **unverified** in this run.
- Skip until: the app needs a Compose API this BOM lacks.

**C8. A status refresh inside `send()` can turn success into an error. Effort S.**
- In `RemoteViewModel.send()`, the post-action `status()` call sits inside the same `try`. If it throws `PcException`, a successful command is reported as failed (`RemoteViewModel.kt`, `send` function). Catch the refresh separately. Code-level judgment; no external source.
- Skip until: users report a false error after a successful command.

## 3. Priority order (recommendation)

1. **B1** expose `paste_mode` and `focus_guard` (S). Closes a documented gap.
2. **A1** HTTP/1.1 keep-alive and `TCP_NODELAY` on the PC server (S). Measure before and after.
3. **A3** re-poll on Wi-Fi change via `NetworkCallback` (S). Directly addresses reconnect speed.
4. **B2** share target (S). Cheap, platform-only.
5. **C1** QR protocol version check (S).
6. Defer: A6 discovery, A7 push, B5/B6 tile and widget, B8 IME, C3 AGP 9 until a trigger in each "skip until" appears.

## 4. Checked and rejected

| Option | Decision | Reason | Source |
| --- | --- | --- | --- |
| WebSocket (RFC 6455) | Rejected for now | No stdlib server on the PC; a platform client on Android was not verified; adds OkHttp and a server library. SSE covers push with stdlib if needed. | https://www.rfc-editor.org/rfc/rfc6455; https://html.spec.whatwg.org/multipage/server-sent-events.html |
| Accessibility service to drive the phone | Rejected | Play policy limits it to disability-help apps (`isAccessibilityTool`). | https://support.google.com/googleplay/android-developer/answer/10964491 |
| Foreground service to keep the remote alive | Rejected | The PC keeps typing with the phone off; the phone needs no live connection. | https://developer.android.com/develop/background-work/services/fgs |
| Migrate `RemoteViewModel` state to `StateFlow` | Rejected | Current `mutableStateOf` state works and is in the Compose path; no user-visible gain. The Kotlin Flow page was checked for this decision (https://developer.android.com/kotlin/flow/stateflow-and-sharedflow). | same |
| Move pairing from SharedPreferences to DataStore | Rejected | Works; the migration page says "consider", not "must". | https://developer.android.com/topic/libraries/architecture/datastore |
| Glance widget now | Deferred | New dependency; B5 first. | https://developer.android.com/develop/ui/compose/glance |
| Full TLS on the LAN | Deferred | Needs certificate pinning UX on the phone; the protocol doc already states the LAN threat model. | `docs/remote-protocol.md`, Security notes |

## 5. Open questions for the user

1. Is the goal lower latency per command, faster reconnect, or fewer manual steps? The answer decides between A1/A3 and A6.
2. How many PCs will one phone pair with? If one, QR pairing stays and A6 is deferred.
3. Should the phone expose `paste_mode` and `focus_guard` now (B1)? The protocol and CHANGELOG already promise it.
4. Is the app meant for Play Store distribution or only GitHub APK releases? Affects C4 timing and accessibility-policy wording.
5. Is a home-screen widget or Quick Settings tile wanted (B5, B6), or is the in-app remote enough?
6. Which target network do latency numbers need to come from? Measurements from the user's home Wi-Fi decide A1 and A5.

## 6. Unverified items (not confirmed from a primary source in this run)

- HttpURLConnection connection pooling on Android (A2).
- Whether `ACCESS_NETWORK_STATE` is needed for the callback in A3.
- Whether a limited-broadcast UDP beacon needs `MulticastLock` (A6).
- Current maintenance status of a pure-Python mDNS library (A6).
- OkHttp WebSocket platform support (A7); OkHttp docs were unreachable.
- Whether zxing's merged manifest adds CAMERA permission (QR scan). The upstream manifest fetch failed; check the merged manifest in a build.
- Whether the stdlib test server runs on the JVM classpath (C2).
- Whether the Network Security Config accepts IP literals or CIDR (C5).
- Whether AGP 9.x is stable and required for upcoming AndroidX releases (C3).
- Whether a newer Compose BOM is current (C7).
- Whether R8 is worth enabling for this APK size (C6).
