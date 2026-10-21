# NFL-TRACK-API-001 — noforeignland Boat Tracking API

| Field | Value |
|---|---|
| Spec ID | NFL-TRACK-API-001 |
| Status | Draft |
| Version | 0.2.0 |
| Date | 2026-10-21 |
| Owner | Olivier |
| Nature | Reverse-engineered contract of a third-party, undocumented API |
| Primary source | `noforeignland/nfl-signalk` v1.4.0 (GitHub, maintained by noforeignland, MIT) |
| Secondary sources | noforeignland.com/help/tracking, Saillogger and Boat Logbook integration notes |
| Used by | HA-SAIL-SPEC-001 X-12, OD-27; issue #51 |

---

## 1. Purpose and scope

This document specifies the HTTP contract used to push boat position and track data to noforeignland.com, so that an independent producer (Go service, Home Assistant automation, NMEA bridge) can update a boat's position and track on the noforeignland map without going through SignalK or a commercial tracker.

In scope:

- The track upload endpoint, its authentication, request and response formats.
- Server-side semantics inferred from the reference client (deduplication, keepalive, error classes).
- Reference client behaviour (sampling, filtering, scheduling) that a conforming producer should reproduce.
- Guidance for a Go producer.

Out of scope:

- Other noforeignland APIs (places, boats, groups, chat) — not documented, not reverse-engineered here.
- The email / SMS position-report channels (Iridium, Zoleo). Mentioned in §9 only as alternatives.
- The noforeignland mobile app's own upload protocol.

**Vigie context.** Vigie itself makes no network connection (HA-SAIL-SPEC-001 §2.2, §12, OD-27). In Vigie's design the producer is Home Assistant, reading `device_tracker.<boat>`; see §12.

## 2. Source of truth and confidence

noforeignland publishes no API documentation. The contract below is derived from the official SignalK plugin source (`src/types/api.ts`, `src/lib/TrackSender.ts`, `src/lib/TrackLogger.ts`, `src/lib/configSchema.ts`). Each statement carries a confidence tag:

- **[OBS]** — observed directly in client code or in noforeignland's own documentation.
- **[INF]** — inferred from client behaviour or comments; plausible, unconfirmed by the server.
- **[UNK]** — unknown; listed as an open decision in §10.

The plugin's comments explicitly invite third parties to request their own integration key from `support@noforeignland.com` [OBS], which indicates the endpoint is intended for external producers, not merely a private app API.

The endpoint, the `X-NFL-API-Key` header, the boat-key location and the "request your own key" comment were also checked independently in the published npm package `@noforeignland/signalk-to-noforeignland` 1.4.0 (2026-10-21). The other source-level statements rest on the review of the GitHub source.

## 3. Endpoint

| Item | Value | Conf. |
|---|---|---|
| Method | `POST` | OBS |
| URL | `https://www.noforeignland.com/home/api/v1/boat/tracking/track` | OBS |
| Content-Type | `application/x-www-form-urlencoded` | OBS |
| Response | `application/json` | OBS |
| TLS | HTTPS only, standard CA chain | OBS |
| Compression | Reference client sends `Accept-Encoding: identity` (no gzip) because gzipped replies have caused truncated-body failures in node-fetch | OBS |

Note: `www.noforeignland.com` serves the API; the apex `noforeignland.com` hosts the marketing site. Use the `www` host verbatim.

## 4. Authentication

Two independent credentials are required on every request.

### 4.1 Integration key — `X-NFL-API-Key` header

- Identifies the **client software**, not the boat. [OBS]
- UUID format. The SignalK plugin ships a hardcoded key shared by every install of that plugin; its source comment states it is subject to noforeignland's rate limits and must not be reused by other projects. [OBS]
- A producer must obtain its own key by emailing `support@noforeignland.com`. [OBS]
- Treated as a secret in configuration; never committed, never logged.

### 4.2 Boat key — `boatApiKey` form field

- Identifies the **boat** whose track is updated. [OBS]
- Obtained on the website only (not in the mobile app): *Account → Settings → Boat tracking → API Key*. [OBS]
- Format: opaque string; treat as secret. [OBS]
- One boat key per boat; a producer serving several boats sends one request per boat. [INF]

## 5. Request body

Form-encoded fields:

| Field | Type | Required | Description | Conf. |
|---|---|---|---|---|
| `boatApiKey` | string | yes | Boat key (§4.2) | OBS |
| `timestamp` | integer (epoch ms) | yes | Timestamp of the **last** point in `track` | OBS |
| `track` | JSON string | yes | Array of points, see §5.1 | OBS |
| `pluginVersion` | string | no | Producer version; telemetry only | OBS/INF |
| `skVersion` | string | no | SignalK server version; telemetry only, send `"n/a"` or omit | OBS/INF |
| `nodeVersion` | string | no | Runtime version; telemetry only | OBS/INF |

Whether the three telemetry fields are validated server-side is **[UNK]** (§10, OD-1). A conforming producer should send `pluginVersion` with its own name and version (e.g. `vigie-nfl/0.1.0`) so noforeignland can attribute traffic.

### 5.1 `track` format

```json
[[1761037200000, 43.5012, 3.9241], [1761037260000, 43.5021, 3.9268]]
```

- Each point is a 3-tuple `[timestamp_ms, latitude, longitude]`. [OBS]
- `timestamp_ms`: integer epoch milliseconds, UTC. [OBS]
- `latitude`: decimal degrees, −90..90. `longitude`: decimal degrees, −180..180. The reference client drops any point failing these bounds before sending. [OBS]
- Points are ordered chronologically ascending. [INF — the client appends in log order; server ordering tolerance is UNK]
- A single request carries a whole segment (many points), which is what produces a coastline-following track rather than dot-to-dot lines. [OBS]
- Minimum one valid point; the client refuses to send an empty track. [OBS]
- Maximum points per request: **[UNK]** (OD-2). The reference client's default schedule (one send per 10 min, one point per 60 s minimum) bounds a typical batch at ~10 points, but offline caching can accumulate hours of points into one request.

### 5.2 Example request

```http
POST /home/api/v1/boat/tracking/track HTTP/1.1
Host: www.noforeignland.com
X-NFL-API-Key: <integration-key>
Content-Type: application/x-www-form-urlencoded
Accept-Encoding: identity

boatApiKey=<boat-key>&timestamp=1761037260000&track=%5B%5B1761037200000%2C43.5012%2C3.9241%5D%2C%5B1761037260000%2C43.5021%2C3.9268%5D%5D&pluginVersion=vigie-nfl%2F0.1.0
```

## 6. Response

```json
{ "status": "ok" }
```

```json
{ "status": "error", "message": "Invalid boat API key" }
```

| Element | Semantics | Conf. |
|---|---|---|
| HTTP 2xx | Track accepted **and stored**, regardless of body parse outcome. The reference client treats any 2xx as success even if the JSON body cannot be read, specifically to avoid resending and duplicating the track. | OBS |
| `status: "ok"` | Success. | OBS |
| `status: "error"` + `message` | Application-level rejection on a 2xx. Client-side problem; do not retry. | OBS |
| HTTP 4xx | Client error (bad key, malformed body). Do not retry. | OBS |
| HTTP 5xx | Server error. Retry with backoff. | OBS |
| Network error / timeout | Retry with backoff. | OBS |

The exact `message` vocabulary is **[UNK]** (OD-3).

## 7. Server-side semantics

| Behaviour | Statement | Conf. |
|---|---|---|
| Idempotency | None. Resending points already accepted duplicates them on the map. The producer must persist its own "sent" watermark. | OBS (client comment) |
| Stationary boat | Position reports identical to the current boat position are ignored by the server (documented for the email/Iridium channels; assumed to hold for the track endpoint). | OBS / INF |
| Boat "liveness" | The map flags boats that have not reported recently. The reference client forces one point every 24 h even when stationary to keep the boat shown as active. | OBS |
| Rate limiting | Exists, keyed on the integration key. Limits are not published. | OBS / UNK (OD-4) |
| Path editing | Users can reshape a path between fixes on the website; fixes themselves are immutable through the UI. No delete/replace API is known. | OBS / UNK (OD-5) |

## 8. Reference producer behaviour

A producer should reproduce the following reference-client logic to produce comparable tracks and comparable load on noforeignland.

### 8.1 Sampling (local, before any network)

| Parameter | Default | Purpose |
|---|---|---|
| Sampling period | 60 s | Evaluate position once per period |
| Minimum move | 80 m | Drop a sample if displacement from the last logged point is below this (equirectangular distance) |
| Minimum speed | 1.5 kn | Drop a sample below this speed (moored / at anchor) |
| Maximum velocity | 50 m/s (~97 kn) | Reject a sample implying a speed above this between consecutive points — GPS outlier filter |
| 24 h keepalive | on | Force-log one point if none was logged in 24 h, bypassing move/speed thresholds |

Position source: a single fused `navigation.position` (lat, lon, time). For an NMEA 0183 source this maps to `RMC` (preferred: position + time + SOG in one sentence) with `GGA`/`GLL` as fallbacks. In Vigie this is `device_tracker.<boat>` (own position after source arbitration, HA-SAIL-SPEC-001 §7.4) with its `sog` attribute.

### 8.2 Persistence

- Logged points are appended to a local file as newline-delimited JSON `{ "lat": …, "lon": …, "t": "<ISO8601>" }` until sent. [OBS]
- This provides offline buffering (no connectivity offshore) and crash safety. A producer may use any store but must guarantee at-most-once send per point (§7, idempotency).
- After a successful send the pending file is cleared or archived (option "keep files on disk"). [OBS]

### 8.3 Scheduling and retry

| Parameter | Default |
|---|---|
| Send schedule | cron `*/10 * * * *` (every 10 min) |
| Send while moving | yes (otherwise send only once stopped and connected) |
| Request timeout | 30 s, multiplied by attempt number |
| Retries | 3 attempts, on network error and 5xx only |

### 8.4 Observability

The reference client exposes: last point saved, last successful send, status string, status flag (0 ok / 1 error), position source. A producer should expose equivalent metrics or Home Assistant sensors.

### 8.5 Outage buffering (owner requirement, 2026-10-21)

**R-1.** Positions logged while the internet is unavailable are buffered and sent when it recovers, so the track has no gap. Requirements on the producer:

- Points logged per §8.1 go to a persistent buffer first, never straight to the network; the buffer survives a restart (power on board is intermittent).
- At each send, the whole buffer goes as one `track` (chunked per OD-2), oldest first. Points leave the buffer only after a 2xx (§6), so a failed send keeps them for the next attempt and a 2xx never repeats them (§7, idempotency).
- A 4xx or an error body (§6) does not retry the same request forever: the buffer is kept and the failure surfaced (§8.4), since a bad key needs the owner.
- The buffer is bounded. When full, it is thinned (for example every second point of the oldest half) rather than truncated, so a long offshore passage keeps its shape. Size to be fixed with OD-2.

How Vigie meets R-1 is open (HA-SAIL-SPEC-001 OD-28, issue #51).

## 9. Alternative channels (for completeness)

- **Email position report**: the external-providers help page documents `tracking@noforeignland.com` as the receiving address. Iridium reports are matched to a boat by the Iridium number in the boat's tracking settings, SPOT check-ins by the SPOT name; a generic "email us your location" format is described on the *Track using noforeignland* help page (not reviewed). Position only (no path). Not specified here.
- **GPX import**: manual upload on the website. Suitable for post-passage batch upload; no automation.
- **Feed URLs** (Garmin inReach KML, YB Tracking JSON): noforeignland pulls a public URL. Not usable for Vigie: Home Assistant would have to expose a public endpoint (HA-SAIL-SPEC-001 §12, no listener).
- **Partner integrations** (Saillogger, Boat Logbook): same mechanism as §3–§5, exposed as "paste your NFL boat API key" in their settings. Saillogger reports ~1 update/hour and suppresses repeats while stationary — a useful calibration for acceptable update rates.

## 10. Open decisions

| ID | Question | Impact | Proposed resolution |
|---|---|---|---|
| OD-1 | Are `pluginVersion` / `skVersion` / `nodeVersion` required or validated? | Request may be rejected if omitted | Send `pluginVersion` always; ask support when requesting the integration key |
| OD-2 | Maximum points / bytes per request | Long offline buffers may fail | Chunk sends at ≤ 1 000 points until confirmed |
| OD-3 | Error `message` vocabulary | Alerting precision | Log raw message; map to generic "rejected" |
| OD-4 | Rate limits per integration key | Scheduling | Keep ≥ 10 min between sends; ask support |
| OD-5 | Any delete / replace endpoint for erroneous points | Recovery from duplicates | Assume none; invest in idempotent sending instead |
| OD-6 | Server tolerance to out-of-order or backdated points | Buffer replay after outage (R-1) | Always send ascending; test with a backdated segment before relying on it |
| OD-7 | Producer host for Olivier's boat: Home Assistant vs standalone Go service on the boat computer | Architecture of the producer | Partly settled by HA-SAIL-SPEC-001 OD-27: Home Assistant is the producer, Vigie stays offline. With R-1 the remaining choice is HA-SAIL-SPEC-001 OD-28 |
| OD-8 | Which integration key to use during development | Must not reuse the SignalK plugin's shared key | Request a dedicated key before first live send; use a local mock server until then |

## 11. Go producer — design notes

For a producer aligned with the standard stack (Go, layered handler → service → repository):

- **Service layer**: `TrackLogger` (sampling + filters, §8.1) and `TrackSender` (batching, retry, watermark, §8.3). Keep the two decoupled by the persistence layer.
- **Repository**: append-only point store with a `sent_at` watermark; SQLite or a flat NDJSON file both satisfy §8.2. If running inside a larger backend, a PostgreSQL table with `(boat_id, ts)` primary key gives idempotency for free.
- **HTTP client**: `net/http` with `url.Values` for the body, explicit `Accept-Encoding: identity`, context timeout = 30 s × attempt, exponential backoff capped at 3 attempts, retry only on transport error or 5xx.
- **Config**: integration key and boat key from environment or secret store; thresholds from §8.1 as defaults.
- **Testing**: an `httptest.Server` mock implementing §6 responses (ok, error-body-on-2xx, 4xx, 5xx, truncated body) covers the reference client's known edge cases.
- **Versioning**: stamp `pluginVersion` from `-ldflags` at build time.

## 12. Cross-references

- Vigie (`ovander/ha-vigie`), HA-SAIL-SPEC-001 §2.2, X-12, OD-27, OD-28; issue #51 — Home Assistant integration for the boat's AIS/NMEA 0183 feed; Home Assistant is the producer (OD-7).
- `noforeignland/nfl-signalk` — reference client, v1.4.0, fork of `amirlanesman/signalk-to-nfl`.
- noforeignland help: `/help/tracking` and `/help/tracking/track-using-external-providers`.
- noforeignland blog: "Free Yacht Tracker", "Editing the Shape of Your Boat's Track".

## 13. Changelog

| Version | Date | Change |
|---|---|---|
| 0.2.0 | 2026-10-21 | Added to the Vigie repository (#51). New §8.5 R-1 outage buffering (owner requirement). §9 email channel corrected (`tracking@noforeignland.com`, matched by Iridium number or SPOT name), feed URLs noted as unusable. §2 notes what was checked in the npm package. OD-7 partly settled by Vigie OD-27; Vigie context added (§1, §8.1, §12). |
| 0.1.0 | 2026-10-21 | Initial draft from nfl-signalk v1.4.0 source review |
