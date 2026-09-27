# HA-SAIL-TEST-001 — Test Protocol

**Sailing Boat Integration for Home Assistant — unit, functional and end-to-end testing**

| Item | Value |
|---|---|
| Document ID | HA-SAIL-TEST-001 |
| Version | 0.2 (draft) |
| Date | 2026-09-27 |
| Parent specification | HA-SAIL-SPEC-001 v0.4 |
| Owner | Olivier (Garnet & Jade Consulting) |
| Status | Draft — open points in §10 |

---

## Changelog

| Version | Date | Change |
|---|---|---|
| 0.2 | 2026-09-27 | TP-05 resolved (injectable clock); U-AIS-10…12 implemented; malformed-sentence cases from D-04 added to the AIS suite; NFR-02 import check implemented. Suite: 39 tests, 98.5 % coverage of `nmea/`. |
| 0.1 | 2026-09-27 | Initial protocol: three test levels, test data corpus, CPA/TCPA reference scenarios (hand-computed), traceability to SPEC-001 NFRs, CI gates and phase exit criteria. |

---

## 1. Purpose and principles

This document defines how HA-SAIL-SPEC-001 (hereafter "SPEC") is verified. It follows the SPEC's layering (SPEC §5.1): each layer is tested at the lowest level that can prove it.

| Level | Prefix | What it proves | Runs where | Needs HA? | Needs hardware? |
|---|---|---|---|---|---|
| Unit | `U-` | Protocol and domain logic are correct in isolation | CI, laptop | No | No |
| Functional | `F-` | The integration behaves correctly inside Home Assistant | CI, laptop | Test harness | No |
| End-to-end | `E-` | The real chain (receiver → serial → HA → automations) works on board | Dev HA, the boat | Real instance | Replay, then real receiver |

Principles:

- **No test depends on the network or on live AIS traffic.** Everything reproducible runs from recorded or generated data.
- **Hand-computed expected values** for domain logic (CPA/TCPA). An oracle library (pyais) is allowed for the AIS decoder only as a cross-check, never as the source of expected values for our own logic.
- **Every NFR in SPEC §4 maps to at least one test** (§8).
- **A defect found at a higher level gets a regression test at the lowest level that can reproduce it.**

## 2. Test data corpus

| ID | Dataset | Source | Content | Used by |
|---|---|---|---|---|
| D-01 | Spec reference sentences | X-01 (gpsd AIVDM doc) | Type 1 example, type 5 two-fragment example | U-AIS |
| D-02 | Public samples | Common test corpora | Type 18 and type 19 samples | U-AIS |
| D-03 | Synthetic AIS | Generated with pyais encoder (test-only dependency) | Randomised types 1/2/3/18/19 incl. N/A sentinels, fixed seeds | U-AIS fuzz |
| D-04 | Malformed corpus | Hand-crafted | Bad checksum, missing `*`, truncated payload, wrong field count, invalid armoring char, fill bits > 5, fragment out of range, over-long line, non-ASCII bytes, wrong-baud garbage | U-NMEA, U-AIS, F-HUB |
| D-05 | Raw capture — in port | SPEC X-09 | ≥ 15 min, receiver's real output, moored | U (regression), F, E |
| D-06 | Raw capture — under way | SPEC X-09 | ≥ 30 min under way, ideally with traffic | F, E |
| D-07 | Traffic scenarios | Scripted generator (`tests/tools/scenario.py`) | Own boat + targets on defined tracks, emitted as timed RMC + VDM sentences | U-TRF, F-TRF, E-02 |
| D-08 | Burst file | Derived from D-03 | ≥ 50 sentences/s for 60 s | F-PERF, E-05 |

D-05 and D-06 are **anonymised before being committed**: own MMSI in `VDO` and the home berth position may be kept only if the owner agrees (TP-03). Fixtures live in `tests/fixtures/`, one sentence per line, UTF-8, `\r\n` preserved.

**Timed replay format.** For replays that need real timing, capture with timestamps (`ts '%.s'` or a small Python recorder) so each line is `<epoch_seconds> <sentence>`. The replay tool honours the original spacing, scaled by a speed factor.

## 3. Unit tests (`tests/nmea/`, `tests/domain/`)

Pure pytest, **no Home Assistant import** (enforced: a CI step fails if `homeassistant` is importable from `nmea/` or `traffic.py` tests — SPEC NFR-02).

### 3.1 Sentence layer — `U-NMEA` (SPEC §7.1, C-02)

| ID | Case | Expected |
|---|---|---|
| U-NMEA-01 | Valid checksum, upper- and lower-case hex | Accepted |
| U-NMEA-02 | Wrong checksum / missing `*` / one hex digit | Rejected, counted |
| U-NMEA-03 | Talker variants `GP`, `GN`, `AI`, `II` on RMC | Same parser, talker kept as metadata |
| U-NMEA-04 | Empty fields | `None`, never `0` |
| U-NMEA-05 | Proprietary `$P…` and unsupported sentence IDs | Ignored, counted, no exception |
| U-NMEA-06 | Line > 82 chars (outside tag block), non-ASCII bytes | Rejected at framing |

### 3.2 GPS parsers — `U-GPS` (SPEC §7.2)

| ID | Case | Expected |
|---|---|---|
| U-GPS-01 | RMC valid (`A`) | Position in decimal degrees (N/E positive), SOG kn, COG °, UTC datetime, variation signed (E positive) |
| U-GPS-02 | RMC void (`V`) | Position/SOG/COG not produced |
| U-GPS-03 | Hemisphere conversion: S and W, and 0°/180° boundaries | Correct signs, no wrap errors |
| U-GPS-04 | GGA fix quality 0/1/2/6, satellites, HDOP | Typed values; quality 0 → no position |
| U-GPS-05 | VTG with and without magnetic course, with `N`/`K` units | SOG in kn from the `N` field |
| U-GPS-06 | GSA 2D/3D, PDOP | Fix mode enum |
| U-GPS-07 | HDT present / empty | Heading or `None` |
| U-GPS-08 | Every D-05/D-06 `$` line | No exception; rejection rate reported |

### 3.3 AIS decoder — `U-AIS` (SPEC §7.3, C-03)

**Status: implemented** (`tests/nmea/test_ais_decoder.py`, 38 tests green, plus the NFR-02 import check in `tests/nmea/test_no_ha_import.py`). Current coverage and additions:

| ID | Case | Status |
|---|---|---|
| U-AIS-01 | D-01 type 1 reference, D-02 types 18/19 vs oracle | Done |
| U-AIS-02 | Type 19 ship name (`@` terminator, trailing spaces) | Done |
| U-AIS-03 | Bad checksum rejected and counted | Done |
| U-AIS-04 | Type 5 (non-position) ignored without rejection | Done |
| U-AIS-05 | Tag block prefix; non-AIS `$` line ignored | Done |
| U-AIS-06 | Truncated payload rejected (length check) | Done |
| U-AIS-07 | `VDO` flagged `own_ship`; excluded when `include_own=False` | Done |
| U-AIS-08 | Two-fragment reassembly (type 19 split) | Done |
| U-AIS-09 | Fuzz: 500 messages × 5 types vs oracle | Done |
| U-AIS-10 | Fragment timeout: first fragment alone, clock advanced > 5 s, second fragment → no message; `received_at` follows the injected clock | Done |
| U-AIS-11 | Interleaved fragments on channels A and B with same sequence ID | Done |
| U-AIS-12 | Sentinels individually (lon 181, lat 91, SOG 1023, SOG 1022, COG 3600, heading 511), types 1 and 18 | Done |
| U-AIS-14 | D-04 malformed cases: unterminated tag block, missing/non-hex checksum, invalid armoring, wrong field count, bad fragment/fill values, sequence ID reused with another count | Done |
| U-AIS-13 | Every D-05/D-06 `!` line | **To add** once X-09 exists |

Note for U-AIS-10: `AisDecoder` takes an optional `clock` parameter (default `time.monotonic`), used for fragment expiry and `received_at` (TP-05, resolved v0.2).

### 3.4 Traffic logic — `U-TRF` (SPEC §8, C-05)

Reference scenarios, computed by hand in a local east/north frame (NM, kn), own boat at origin heading 000° at 6 kn unless stated. Thresholds: CPA 0.5 NM, TCPA 15 min (SPEC §8.2 defaults).

| ID | Scenario | Target relative position | Target motion | Expected CPA | Expected TCPA | Threat? |
|---|---|---|---|---|---|---|
| U-TRF-01 | Head-on | 2 NM north | 180° at 6 kn | 0.00 NM | 10.0 min | **Yes** |
| U-TRF-02 | Crossing, passes clear | 1 NM east | 270° at 6 kn | 0.71 NM | 5.0 min | No (CPA) |
| U-TRF-03 | Crossing, close | 1 NM east | 270° at 12 kn | 0.45 NM | 4.0 min | **Yes** |
| U-TRF-04 | Overtaking a slower boat | 1 NM north | 000° at 4 kn | 0.00 NM | 30.0 min | No (TCPA) |
| U-TRF-05 | Close but not yet urgent | 2 NM NE (2 E, 2 N) | relative velocity (−6, −5) kn | 0.26 NM | 21.6 min | No (TCPA) — becomes Yes as time advances |
| U-TRF-06 | Diverging | 1 NM south | 000° at 3 kn | — | negative | No |
| U-TRF-07 | Parallel, same speed | 0.3 NM east | 000° at 6 kn | 0.30 NM (current distance) | undefined | No |
| U-TRF-08 | Anchored target on own track | 0.4 NM north | nav status `at_anchor`, SOG 0 | 0.00 NM | 4.0 min | No by default (exclusion option); Yes with option off |

Additional cases:

| ID | Case | Expected |
|---|---|---|
| U-TRF-09 | Geodesy: flat-earth vs haversine at 43.5° N for 1, 5, 20 NM | Error < 0.5 % up to 20 NM (SPEC §8.1) |
| U-TRF-10 | Target or own SOG/COG unavailable | CPA/TCPA `None`, target excluded from threats, no exception |
| U-TRF-11 | Closest-threat selection among several threats | Smallest TCPA wins; tie → smallest CPA |
| U-TRF-12 | Stale target (report age > expiry) | Removed from the table (SPEC §9.4) |
| U-TRF-13 | Crossing the antimeridian and the equator | No sign or wrap errors |

Tolerances: CPA ± 0.01 NM, TCPA ± 0.1 min.

### 3.5 Coordinator logic — `U-COO` (SPEC §7.4, §10)

The merge logic is written as a plain class (no HA) wrapped by the HA coordinator, so it can be unit-tested.

| ID | Case | Expected |
|---|---|---|
| U-COO-01 | SOG from RMC then VTG | Most recent valid value wins, source recorded |
| U-COO-02 | GPS fresh + VDO present | GPS used; VDO ignored for own state |
| U-COO-03 | GPS stale (> timeout) + VDO fresh | Falls back to VDO; `own_position_source = VDO` |
| U-COO-04 | VDM with own MMSI | Not inserted in the target table |
| U-COO-05 | Dead-band: SOG 5.00 → 5.04 → 5.12 | Only the last change triggers a write |
| U-COO-06 | Throttle: 10 updates in 1 s | One write per `update_interval` with the latest value |

## 4. Functional tests (`tests/integration/`)

Run inside Home Assistant's test harness (`pytest-homeassistant-custom-component`). The serial port is replaced by a **fake transport** that feeds lines from a fixture or scenario (D-04 to D-08), under control of the test (pause, disconnect, burst). Time is controlled with the harness's time-travel helpers, so no test sleeps in real time.

### 4.1 Setup and lifecycle — `F-LIFE`

| ID | Case | Expected | SPEC |
|---|---|---|---|
| F-LIFE-01 | Config flow, port lists `/dev/serial/by-id/*`, valid data within 5 s | Entry created | §11.1 |
| F-LIFE-02 | Config flow, no data | `no_data` error shown, user can proceed | §11.1 |
| F-LIFE-03 | Config flow, garbage (wrong baud) | Hint to try the other baud rate | §11.1 |
| F-LIFE-04 | Setup with port missing | `ConfigEntryNotReady`, retried | §10.3 |
| F-LIFE-05 | Unload | Reader task cancelled, port closed, no pending tasks (harness checks lingering tasks) | NFR-07 |
| F-LIFE-06 | Reload after options change | New options applied, entities keep unique IDs | NFR-06 |
| F-LIFE-07 | Options flow: every option round-trips | Stored and applied | §11.2 |
| F-LIFE-08 | Diagnostics download | Config redacted, counters present | §9.5 |

### 4.2 Hub and transport — `F-HUB`

| ID | Case | Expected | SPEC |
|---|---|---|---|
| F-HUB-01 | Mixed stream from D-05 | `$` lines reach GPS parsers, `!` lines reach AIS decoder | §6 |
| F-HUB-02 | D-04 malformed corpus injected in a valid stream | Valid data unaffected; counters match the number of bad lines | NFR-01 |
| F-HUB-03 | Disconnect mid-stream | All entities unavailable immediately; `connected` off | §10.1 |
| F-HUB-04 | Reconnect after 1, 5, 30 s | Backoff sequence respected; one log line per outage | NFR-03, §10.3 |
| F-HUB-05 | Partial line at disconnect | Discarded, no crash | NFR-01 |

### 4.3 Entities — `F-ENT`

| ID | Case | Expected | SPEC |
|---|---|---|---|
| F-ENT-01 | D-05 replay | All §9.1 entities created with correct device_class, native unit, state_class, translation key | §9.1 |
| F-ENT-02 | HA unit system switched to metric/imperial | Speeds converted by HA (km/h, mph), native stays kn | §9 |
| F-ENT-03 | Own position | `device_tracker.<boat>` updates, SOG/COG attributes | §9.1 |
| F-ENT-04 | GPS silent > staleness timeout | Own-boat entities unavailable; traffic entities unavailable | §10.1, NFR-05 |
| F-ENT-05 | Heading never provided | `heading` unavailable, no error | §7.4 |
| F-ENT-06 | Two config entries (two boats, two fake ports) | No unique-ID collision | NFR-06 |
| F-ENT-07 | Every entity checked in the entity registry | Unique ID prefixed by entry ID | NFR-06 |

### 4.4 Traffic behaviour — `F-TRF`

Driven by D-07 scenarios replayed in accelerated time.

| ID | Case | Expected | SPEC |
|---|---|---|---|
| F-TRF-01 | U-TRF-05 scenario played over time | `binary_sensor.collision_risk` turns **on** when TCPA crosses 15 min, **off** after CPA passes | §8.2, §9.2 |
| F-TRF-02 | U-TRF-01 head-on | Closest threat CPA/TCPA sensors match U-TRF-01 values within tolerance | §9.2 |
| F-TRF-03 | 60 targets | `sensor.ais_targets` = 60, attribute list capped at 50 nearest | §9.2 |
| F-TRF-04 | Target stops reporting | Removed after expiry (Class A 10 min, Class B 15 min) | §9.4 |
| F-TRF-05 | Watch list with 2 MMSIs | Exactly 2 AIS trackers created; removal from list removes them | §9.3 |
| F-TRF-06 | Automation triggered on `collision_risk` | Automation runs once per risk episode (no flapping) | §9.2 |
| F-TRF-07 | Anchored target exclusion toggled | Threat state follows the option | §8.2 |

### 4.5 Load and recorder — `F-PERF`

| ID | Case | Expected | SPEC |
|---|---|---|---|
| F-PERF-01 | D-08 burst (≥ 50 sentences/s, 60 s) | No backlog: all lines processed within 1 s of arrival; event loop lag < 100 ms | NFR-09 |
| F-PERF-02 | 10 min of D-06 at real rate | State writes per entity ≤ 1/s; total writes counted and recorded as baseline | NFR-04, §10.2 |
| F-PERF-03 | `sensor.ais_targets` attributes | Rebuilt ≤ every 5 s; serialized size under HA's attribute limit | §10.2 |

## 5. End-to-end tests

E2E runs on a real Home Assistant instance, in three stages of increasing realism. Each stage has a written checklist; results are recorded in the test report (§9).

### 5.1 Stage E-1 — Replay bench (desk, no receiver)

Setup: HA dev container or a spare Raspberry Pi with HA OS; the replay tool writes a timed capture into a pseudo-TTY created with `socat` (`socat -d -d pty,raw,echo=0,link=/tmp/ttyAIS pty,raw,echo=0,link=/tmp/ttyAIS_feed`); the integration is configured on `/tmp/ttyAIS` (TP-02).

| ID | Case | Expected |
|---|---|---|
| E-01 | Install via HACS custom repository from the release tag, configure through the UI | Integration works with no manual file copy |
| E-02 | Replay D-07 head-on and crossing scenarios at real speed | Dashboard shows target, CPA/TCPA values match U-TRF within tolerance; `collision_risk` fires; a test notification is delivered to the phone |
| E-03 | Replay D-06 for its full duration | No error in HA log; own track in the map/logbook matches the capture |
| E-04 | Kill the feed side of `socat`, restart after 30 s | Unavailable → recovered without HA restart |
| E-05 | D-08 burst at real speed on the Pi | CPU and event-loop lag within F-PERF-01 limits on the target hardware |
| E-06 | HA restart during replay | Integration reloads, entities come back, no duplicates |

### 5.2 Stage E-2 — On board, in port (real receiver)

Prerequisite: smart0183serial removed (SPEC §3.1).

| ID | Case | Expected |
|---|---|---|
| E-10 | Configure on `/dev/serial/by-id/…` of the receiver | Valid data within 5 s at the confirmed baud rate (OD-14) |
| E-11 | Own position | Within 20 m of the chartplotter/receiver display; SOG ≈ 0, COG noise acceptable |
| E-12 | AIS targets in the marina | Count and a sample of 5 MMSIs match the chartplotter's AIS list (or a public AIS site, for cross-check only) |
| E-13 | Unplug USB 10 s, replug | Automatic recovery; `connected` sensor reflects the outage |
| E-14 | Cut the 12 V supply to the receiver only | Entities unavailable; recovery on power-up |
| E-15 | Cut power to the Pi (simulated brown-out) | HA restarts, integration recovers, no database corruption reported |
| E-16 | 24 h soak in port | No memory growth trend (> 10 % after warm-up), no error flood in logs, target table size stable |

### 5.3 Stage E-3 — Under way (acceptance)

Performed in daylight, good visibility, with a crew member responsible for navigation. **The integration is an aid only; no navigation decision is made from it during tests.**

| ID | Case | Expected |
|---|---|---|
| E-20 | Own SOG/COG vs chartplotter over 30 min | SOG ± 0.2 kn, COG ± 5° when SOG > 2 kn |
| E-21 | Crossing encounters with real traffic (at least 3, opportunistic) | CPA/TCPA consistent with the chartplotter's AIS target page (± 0.1 NM, ± 1 min) |
| E-22 | `collision_risk` alert | Fires when a real target meets the thresholds; alert reaches the phone; clears after passage |
| E-23 | Record a new D-06 capture during the sail | Added to fixtures (after anonymisation) as a regression dataset |

## 6. Tooling

| Tool | Purpose |
|---|---|
| pytest, pytest-cov | All levels; coverage report |
| pytest-homeassistant-custom-component | Functional tests (HA harness, time travel, lingering-task checks) |
| pyais (MIT) | Test-only oracle and synthetic AIS generator (D-03, D-07) |
| `tests/tools/scenario.py` | Generates timed RMC + VDM streams from track definitions (D-07) |
| `tests/tools/replay.py` | Timed replay of captures to a PTY with speed factor |
| `tests/tools/capture.py` | Timestamped capture of a serial port (X-09) |
| socat | Pseudo-TTY pair for E-1 |
| ruff, mypy, hassfest, HACS action | Static checks and packaging validation in CI |

## 7. CI gates

Every PR must pass:

1. `ruff` and `mypy` clean.
2. Unit tests (`U-*`) green; **coverage ≥ 90 % on `nmea/` and `traffic.py`** (NFR-08).
3. Functional tests (`F-*`) green, excluding `F-PERF` (run nightly — timing-sensitive on shared runners).
4. No HA import in `nmea/` or `traffic.py` (NFR-02 check).
5. `hassfest` and HACS validation pass.

A release tag additionally requires: nightly `F-PERF` green on the last commit, and the E-1 checklist completed for the release candidate.

## 8. Traceability — SPEC NFRs to tests

| NFR (SPEC §4) | Verified by |
|---|---|
| NFR-01 No corrupted value | U-NMEA-02, U-NMEA-06, U-AIS-03, U-AIS-06, F-HUB-02, F-HUB-05 |
| NFR-02 Protocol layer HA-free | CI gate 4, all `U-*` run without HA |
| NFR-03 Reconnect with backoff | F-HUB-04, E-04, E-13, E-14 |
| NFR-04 ≤ 1 Hz writes | U-COO-06, F-PERF-02 |
| NFR-05 Unavailable when stale | F-ENT-04, F-HUB-03 |
| NFR-06 Entry-scoped unique IDs | F-LIFE-06, F-ENT-06, F-ENT-07 |
| NFR-07 Clean unload | F-LIFE-05, E-06 |
| NFR-08 Coverage ≥ 90 % | CI gate 2 |
| NFR-09 Burst handling | F-PERF-01, E-05 |

Functional requirements map by SPEC section: §7.2 → U-GPS; §7.3 → U-AIS; §7.4 → U-COO; §8 → U-TRF, F-TRF; §9 → F-ENT, F-TRF; §10 → F-HUB, F-PERF; §11 → F-LIFE.

## 9. Phase exit criteria and reporting

| SPEC phase | Required tests | Exit criterion |
|---|---|---|
| P0 AIS decoder | U-AIS-01…12, U-AIS-14 | **Met** (39 tests green, 98.5 % coverage) |
| P1 Base | U-NMEA, U-GPS, U-AIS-13, U-COO, F-LIFE, F-HUB, F-ENT, F-PERF, E-1 (E-01, E-03…E-06), E-2 (E-10, E-11, E-13) | All green; D-05 replay matches receiver display |
| P2 Traffic | U-TRF, F-TRF, E-02, E-12, E-16, E-3 | All green; at least 3 real encounters in E-21 consistent with the chartplotter |
| P3 Static data | Additions to U-AIS for types 5/24, F-TRF name checks | Defined when P3 starts |

**Test report** per release: version, commit, CI run link, coverage figures, E-stage checklists with date/location/conditions, deviations and their tickets. Stored in the repository under `docs/test-reports/`.

## 10. Open points

| ID | Question | Proposal | Needed by |
|---|---|---|---|
| TP-01 | Where do E-1 benches run? | Spare Raspberry Pi with HA OS mirrors the boat; dev container for quick checks | P1 |
| TP-02 | PTY replay on HA OS | HA OS restricts host tools; run `socat` + replay in a dev add-on, or run E-1 on HA Container on a Linux box | P1 |
| TP-03 | Anonymisation of captures | Replace own MMSI and home berth position with fixed test values before committing | Before committing D-05 |
| TP-04 | Chartplotter as reference for E-21 | Confirm a chartplotter or app on board displays AIS CPA/TCPA; otherwise use a phone app fed by the same data | P2 |
| ~~TP-05~~ | ~~Clock injection in `ais_decoder.py`~~ | **Resolved v0.2:** `clock` parameter added | — |

## 11. Cross-references

| Ref | Document / artefact |
|---|---|
| SPEC | HA-SAIL-SPEC-001 v0.4 — sections cited inline |
| X-01 | gpsd, *AIVDM/AIVDO protocol decoding* v1.58 (D-01) |
| X-02 | `ais_decoder.py` + `test_ais_decoder.py` (U-AIS-01…09) |
| X-04 | Home Assistant developer docs — testing guidelines for custom integrations |
| X-08 | pyais (MIT) — test oracle and generator only |
| X-09 | Raw captures of the receiver output (D-05, D-06) |
