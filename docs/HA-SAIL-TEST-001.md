# HA-SAIL-TEST-001 — Test Protocol

**Sailing Boat Integration for Home Assistant — unit, functional and end-to-end testing**

| Item | Value |
|---|---|
| Document ID | HA-SAIL-TEST-001 |
| Version | 0.19 (draft) |
| Date | 2026-09-27 |
| Parent specification | HA-SAIL-SPEC-001 v0.5 |
| Owner | Olivier (Garnet & Jade Consulting) |
| Status | Draft — open points in §10 |

---

## Changelog

| Version | Date | Change |
|---|---|---|
| 0.19 | 2026-09-28 | #41: new F-ENT-08 (every attribute of every entity has a translated label, enumerated values translated), after the P3 bench pre-run found untranslated labels. |
| 0.18 | 2026-09-27 | WP14 (#38): D-07 targets can carry static data (type 5 or type 24 A/B, offset and 6 min interval, JSON keys) and the new preset `named-traffic` for the P3 bench check; the E-02 presets send none. E-12 extended to names and ship types (P3). README map card checked against real entities. P3 report template `docs/test-reports/P3-report.md`. |
| 0.17 | 2026-09-27 | WP13 (#36): F-TRF-09 (static data on every entity that describes a target, `None` when unknown; `targets` list), F-TRF-10 (static data after the position, and a later change, written without any other change), F-TRF-11 (19 ship-type categories translated in the three files, French strings loaded by HA). |
| 0.16 | 2026-09-27 | WP12 (#34): new §3.6 `U-STA` (static store: type 5, type 24 parts merged, merge without erasing, type 19 and auxiliary craft, independence from the target table, 30 min expiry, 2 000-MMSI cap, own ship refused); F-HUB-01 extended to static routing and the `ais_static` counter; new F-TRF-08 (names from types 5/24 in every entity, static data before or after the first position; diagnostics). |
| 0.15 | 2026-09-27 | P3 tests defined (§9) and WP11 (#32): U-AIS-04 rewritten (types without a decoder are ignored; type 5 is now decoded); U-AIS-15…22 for types 5 and 24 and the static fields of type 19 (reference sentence, short type 5, parts A/B, auxiliary craft, sentinels, fuzz vs oracle, ship-type categories, VDO); F-HUB-01 checks that static data is not delivered as a position until WP12; D-01 and D-03 extended. |
| 0.14 | 2026-09-27 | WP10 (#29): D-07 presets for every §3.4 geometry (`clear-crossing`, `overtaking`, `not-urgent`, `diverging`, `parallel`, `anchored`, `multi-target`) and `--list`, each checked against its U-TRF hand values; E-02 made concrete (presets, tolerance, notification through the README automation, which is itself tested as published); P2 report template `docs/test-reports/P2-report.md`. |
| 0.13 | 2026-09-27 | WP9 (#27): F-TRF-05 implemented (`tests/integration/test_watch_list.py`), with availability after expiry, independence from own position and MMSI validation. |
| 0.12 | 2026-09-27 | WP8 (#25): F-TRF-01, 02, 03, 04, 06, 07 implemented (`tests/integration/test_traffic_entities.py`, D-07 scenarios in simulated time); pure `assess()` unit-tested in `tests/domain/test_traffic.py`; nightly junit report now keeps the F-PERF-02 baseline (`junit_family = xunit1`). |
| 0.11 | 2026-09-27 | WP7 (#23): U-TRF-01…11 and U-TRF-13 implemented (`tests/domain/test_traffic.py`) with the hand-computed values of §3.4; new U-TRF-14 (risk latch, SPEC OD-15) and U-TRF-15 (dead reckoning, SPEC OD-16); U-TRF-05 time advance made concrete; F-TRF-06 tied to the latch; Status column added to the scenario table. |
| 0.10 | 2026-09-27 | WP6 (#17): `tests/tools/scenario.py` (D-07, presets for U-TRF-01 and U-TRF-03), `tests/tools/replay.py` (own PTY or existing device, speed factor, loop), `tests/tools/capture.py` (X-09) with tests, including an end-to-end PTY → `serial_transport` → hub check of the E-1 path; nightly workflow running F-PERF; §6 and §7 updated. |
| 0.9 | 2026-09-27 | WP5 (#15): F-ENT-01…07, F-LIFE-08 and the entity halves of F-HUB-03 and F-LIFE-06 implemented (`tests/integration/test_entities.py`, `test_diagnostics.py`); F-PERF-01…03 implemented (`tests/integration/test_perf.py`, marker `perf`, excluded from the PR gate); D-08 committed as `tests/fixtures/burst_60s.nmea`; translation-consistency check (`tests/test_translations.py`). F-ENT-04 clarified: distances in `sensor.ais_targets` become `None` at the next list rebuild (≤ 5 s). Suite: 258 tests + 3 perf. |
| 0.8 | 2026-09-27 | WP4 (#13): F-LIFE-01…05 and F-LIFE-07 implemented in the HA harness (`tests/integration/test_config_flow.py`, `tests/integration/test_init.py`, fake transport patched in `conftest.py`); F-LIFE-06 options half done, entity unique-ID half in WP5. `pytest-homeassistant-custom-component==0.13.316` added; functional tests run in the `unit` CI job (`asyncio_mode = auto`). Suite: 226 tests. |
| 0.7 | 2026-09-27 | U-AIS-14 extended (#11): payloads with armoring characters in the invalid gap 0x58–0x5F (`X`, `_`) are rejected; the range edges `W`, `` ` ``, `w` stay valid. D-04 uses `X` again for its invalid-armoring line. |
| 0.6 | 2026-09-27 | WP3 (#9): F-HUB-01, 02, 04, 05 implemented at hub level (`tests/transport/test_hub.py`, fake transport, injected clock and sleep); hub half of F-HUB-03 done, entity half in WP5; D-04 corpus committed as `tests/fixtures/malformed.nmea`; `pytest-asyncio==1.3.0` added (same pin as phcc 0.13.316). Suite: 203 tests, 98.8 % coverage of the pure modules. |
| 0.5 | 2026-09-27 | WP2 (#7): U-COO-01…06 and U-TRF-12 implemented (`tests/domain/test_state.py`), plus `geo.py` checks (`tests/domain/test_geo.py`); NFR-02 check and coverage gate cover `state.py` and `geo.py`. Suite: 176 tests, 99.0 % coverage of the pure modules. |
| 0.4 | 2026-09-27 | WP1 (#5): U-NMEA-01…06 and U-GPS-01…07 implemented (`tests/nmea/test_sentence.py`, `tests/nmea/test_parsers.py`); U-GPS-08 pending on #2; NFR-02 check covers `sentence.py` and `parsers.py`. Suite: 134 tests, 98.7 % coverage of `nmea/`. |
| 0.3 | 2026-09-27 | P1 decisions (issue #3), aligned with SPEC v0.5. TP-01 and TP-02 resolved (E-1 on HA Container on Linux, own-PTY replay tool, null-modem pair for E-01 on HA OS). Status column added to the P1 tables. U-NMEA-06 framing moved to a pure function; U-COO-05 dead-band compares to the last written value; F-HUB-01/02/04/05 run at hub level with the fake transport; F-HUB-03, F-ENT-04 availability rules clarified; F-ENT-02 corrected (HA does not auto-convert knots); synthetic stand-ins for D-05/D-06 until X-09 (issue #2); F-PERF marked `perf` and run nightly; coverage gate extended to all pure modules. |
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
| D-01 | Spec reference sentences | X-01 (gpsd AIVDM doc) | Type 1 example, type 5 two-fragment example (decoded from P3: U-AIS-15) | U-AIS |
| D-02 | Public samples | Common test corpora | Type 18 and type 19 samples | U-AIS |
| D-03 | Synthetic AIS | Generated with pyais encoder (test-only dependency) | Randomised types 1/2/3/18/19, and 5 and 24 (parts A, B, auxiliary craft) from P3, incl. N/A sentinels, fixed seeds | U-AIS fuzz |
| D-04 | Malformed corpus | Hand-crafted | Bad checksum, missing `*`, truncated payload, wrong field count, invalid armoring char, fill bits > 5, fragment out of range, over-long line, non-ASCII bytes, wrong-baud garbage | U-NMEA, U-AIS, F-HUB |
| D-05 | Raw capture — in port | SPEC X-09 | ≥ 15 min, receiver's real output, moored | U (regression), F, E |
| D-06 | Raw capture — under way | SPEC X-09 | ≥ 30 min under way, ideally with traffic | F, E |
| D-07 | Traffic scenarios | Scripted generator (`python -m tests.tools.scenario`; one preset per §3.4 geometry: `head-on`, `clear-crossing`, `crossing`, `overtaking`, `not-urgent`, `diverging`, `parallel`, `anchored`, `multi-target`; `named-traffic` for P3; `--list` prints their expected values) | Own boat + targets on defined tracks, emitted as timed RMC + VDM sentences; targets with static data also send type 5 (Class A) or type 24 A/B (Class B) | U-TRF, F-TRF, E-02, P3 bench |
| D-08 | Burst file | Derived from D-03 | ≥ 50 sentences/s for 60 s | F-PERF, E-05 |

Until X-09 exists (issue #2), tests that name D-05/D-06 run on synthetic stand-ins: a mixed stream built from D-03/D-07 for F-HUB-01 and F-ENT-01, a 10-minute D-07 scenario for F-PERF-02. Each is re-run on the real capture under issue #2. Synthetic sentences are never presented as captured data. D-04 lives in `tests/fixtures/malformed.nmea` and D-08 in `tests/fixtures/burst_60s.nmea` (generated from D-03 with a fixed seed).

D-05 and D-06 are **anonymised before being committed**: own MMSI in `VDO` and the home berth position may be kept only if the owner agrees (TP-03). Fixtures live in `tests/fixtures/`, one sentence per line, UTF-8, `\r\n` preserved.

**Timed replay format.** For replays that need real timing, capture with timestamps (`ts '%.s'` or a small Python recorder) so each line is `<epoch_seconds> <sentence>`. The replay tool honours the original spacing, scaled by a speed factor.

## 3. Unit tests (`tests/nmea/`, `tests/domain/`)

Pure pytest, **no Home Assistant import** (enforced: a CI step fails if importing any pure module — `nmea/`, `state.py`, `geo.py`, `hub.py`, `traffic.py` — loads `homeassistant` — SPEC NFR-02). `tests/nmea/` covers the protocol layer, `tests/domain/` covers `state.py`, `geo.py` and `traffic.py`.

### 3.1 Sentence layer — `U-NMEA` (SPEC §7.1, C-02)

| ID | Case | Expected | Status |
|---|---|---|---|
| U-NMEA-01 | Valid checksum, upper- and lower-case hex | Accepted | Done |
| U-NMEA-02 | Wrong checksum / missing `*` / one hex digit | Rejected, counted | Done |
| U-NMEA-03 | Talker variants `GP`, `GN`, `AI`, `II` on RMC | Same parser, talker kept as metadata | Done |
| U-NMEA-04 | Empty fields | `None`, never `0` | Done |
| U-NMEA-05 | Proprietary `$P…` and unsupported sentence IDs | Ignored, counted, no exception | Done |
| U-NMEA-06 | Line > 82 chars (outside tag block), non-ASCII bytes | Rejected at framing by `check_frame()` in `nmea/sentence.py` (pure, called by the hub; SPEC §7.1) | Done |

### 3.2 GPS parsers — `U-GPS` (SPEC §7.2)

| ID | Case | Expected | Status |
|---|---|---|---|
| U-GPS-01 | RMC valid (`A`) | Position in decimal degrees (N/E positive), SOG kn, COG °, UTC datetime, variation signed (E positive) | Done |
| U-GPS-02 | RMC void (`V`) | Position/SOG/COG not produced | Done |
| U-GPS-03 | Hemisphere conversion: S and W, and 0°/180° boundaries | Correct signs, no wrap errors | Done |
| U-GPS-04 | GGA fix quality 0/1/2/6, satellites, HDOP | Typed values; quality 0 → no position | Done |
| U-GPS-05 | VTG with and without magnetic course, with `N`/`K` units | SOG in kn from the `N` field | Done |
| U-GPS-06 | GSA 2D/3D, PDOP | Fix mode enum | Done |
| U-GPS-07 | HDT present / empty | Heading or `None` | Done |
| U-GPS-08 | Every D-05/D-06 `$` line | No exception; rejection rate reported | Pending (#2) |

### 3.3 AIS decoder — `U-AIS` (SPEC §7.3, C-03)

**Status: implemented** (`tests/nmea/test_ais_decoder.py`; static data from P3 in `tests/nmea/test_ais_static.py`; the NFR-02 import check in `tests/nmea/test_no_ha_import.py`). Current coverage and additions:

| ID | Case | Status |
|---|---|---|
| U-AIS-01 | D-01 type 1 reference, D-02 types 18/19 vs oracle | Done |
| U-AIS-02 | Type 19 ship name (`@` terminator, trailing spaces) | Done |
| U-AIS-03 | Bad checksum rejected and counted | Done |
| U-AIS-04 | Message types without a decoder (e.g. 4, 21) ignored without rejection (rewritten v0.15: type 5 is decoded from P3) | Done |
| U-AIS-05 | Tag block prefix; non-AIS `$` line ignored | Done |
| U-AIS-06 | Truncated payload rejected (length check) | Done |
| U-AIS-07 | `VDO` flagged `own_ship`; excluded when `include_own=False` | Done |
| U-AIS-08 | Two-fragment reassembly (type 19 split) | Done |
| U-AIS-09 | Fuzz: 500 messages × 5 types vs oracle | Done |
| U-AIS-10 | Fragment timeout: first fragment alone, clock advanced > 5 s, second fragment → no message; `received_at` follows the injected clock | Done |
| U-AIS-11 | Interleaved fragments on channels A and B with same sequence ID | Done |
| U-AIS-12 | Sentinels individually (lon 181, lat 91, SOG 1023, SOG 1022, COG 3600, heading 511), types 1 and 18 | Done |
| U-AIS-14 | D-04 malformed cases: unterminated tag block, missing/non-hex checksum, invalid armoring (incl. the 0x58–0x5F gap), wrong field count, bad fragment/fill values, sequence ID reused with another count | Done |
| U-AIS-13 | Every D-05/D-06 `!` line | Pending (#2) |
| U-AIS-15 | D-01 type 5 reference (two fragments): MMSI, IMO, call sign, name, ship type, dimensions, draught, destination | Done |
| U-AIS-16 | Type 5 length: 424, 422 and 420 bits accepted; 418 rejected | Done |
| U-AIS-17 | Type 24 part A (name; 160 and 168 bits), part B (ship type, call sign, dimensions), auxiliary craft (mothership MMSI, no dimensions), part B too short rejected, parts 2/3 ignored | Done |
| U-AIS-18 | Type 19 position carries its static part (name, ship type, dimensions); types 1 and 18 carry none | Done |
| U-AIS-19 | Static "not available" values (IMO, ship type, draught 0, empty text → `None`; length/beam `None` only when both parts are 0); name padding and `@` terminator | Done |
| U-AIS-20 | Fuzz: 500 messages each of type 5, 24A, 24B and 24B auxiliary craft vs oracle | Done |
| U-AIS-21 | Ship-type category of every code 0…255 (SPEC OD-17) | Done |
| U-AIS-22 | Static `VDO` flagged `own_ship`; excluded when `include_own=False` | Done |

Note for U-AIS-10: `AisDecoder` takes an optional `clock` parameter (default `time.monotonic`), used for fragment expiry and `received_at` (TP-05, resolved v0.2).

### 3.4 Traffic logic — `U-TRF` (SPEC §8, C-05)

Reference scenarios, computed by hand in a local east/north frame (NM, kn), own boat at origin heading 000° at 6 kn unless stated. Thresholds: CPA 0.5 NM, TCPA 15 min (SPEC §8.2 defaults).

| ID | Scenario | Target relative position | Target motion | Expected CPA | Expected TCPA | Threat? | Status |
|---|---|---|---|---|---|---|---|
| U-TRF-01 | Head-on | 2 NM north | 180° at 6 kn | 0.00 NM | 10.0 min | **Yes** | Done |
| U-TRF-02 | Crossing, passes clear | 1 NM east | 270° at 6 kn | 0.71 NM | 5.0 min | No (CPA) | Done |
| U-TRF-03 | Crossing, close | 1 NM east | 270° at 12 kn | 0.45 NM | 4.0 min | **Yes** | Done |
| U-TRF-04 | Overtaking a slower boat | 1 NM north | 000° at 4 kn | 0.00 NM | 30.0 min | No (TCPA) | Done |
| U-TRF-05 | Close but not yet urgent | 2 NM NE (2 E, 2 N) | relative velocity (−6, −5) kn | 0.26 NM | 21.6 min | No (TCPA) — becomes Yes as time advances (7 min later, both dead-reckoned: CPA 0.26 NM, TCPA 14.6 min) | Done |
| U-TRF-06 | Diverging | 1 NM south | 000° at 3 kn | — | negative | No | Done |
| U-TRF-07 | Parallel, same speed | 0.3 NM east | 000° at 6 kn | 0.30 NM (current distance) | undefined | No | Done |
| U-TRF-08 | Anchored target on own track | 0.4 NM north | nav status `at_anchor`, SOG 0 | 0.00 NM | 4.0 min | No by default (exclusion option); Yes with option off | Done |

Additional cases:

| ID | Case | Expected | Status |
|---|---|---|---|
| U-TRF-09 | Geodesy: flat-earth vs haversine at 43.5° N for 1, 5, 20 NM | Error < 0.5 % up to 20 NM (SPEC §8.1) | Done |
| U-TRF-10 | Target or own SOG/COG unavailable | CPA/TCPA `None`, target excluded from threats, no exception | Done |
| U-TRF-11 | Closest-threat selection among several threats | Smallest TCPA wins; tie → smallest CPA | Done |
| U-TRF-12 | Stale target (report age > expiry) | Removed from the table (SPEC §9.4) | Done |
| U-TRF-13 | Crossing the antimeridian and the equator | No sign or wrap errors | Done |
| U-TRF-14 | Risk latch (SPEC OD-15): threat, then no threat without the CPA having passed; all threats passed; target vanished | On until 60 s without a threat; off at once when every threat of the episode has passed; a vanished target holds 60 s | Done |
| U-TRF-15 | Dead reckoning (SPEC OD-16): 10 min at 6 kn; target report 3 min old at 10 kn; no SOG/COG | Moved 1 NM along COG; old report projected to now (1.5 NM, TCPA 9.0 min); position unchanged without motion | Done |

Tolerances: CPA ± 0.01 NM, TCPA ± 0.1 min.

### 3.5 Coordinator logic — `U-COO` (SPEC §7.4, §10)

The merge logic is written as plain classes in `state.py` (no HA) wrapped by the HA coordinator, so it can be unit-tested (`tests/domain/`).

| ID | Case | Expected | Status |
|---|---|---|---|
| U-COO-01 | SOG from RMC then VTG | Most recent valid value wins, source recorded | Done |
| U-COO-02 | GPS fresh + VDO present | GPS used; VDO ignored for own state | Done |
| U-COO-03 | GPS stale (> timeout) + VDO fresh | Falls back to VDO; `own_position_source = VDO` | Done |
| U-COO-04 | VDM with own MMSI | Not inserted in the target table | Done |
| U-COO-05 | Dead-band: SOG 5.00 → 5.04 → 5.12 | 5.00 is written; 5.04 is suppressed (< 0.1 kn from the last *written* value); 5.12 is written | Done |
| U-COO-06 | Throttle: 10 updates in 1 s | One write per `update_interval` with the latest value | Done |

### 3.6 Static data store — `U-STA` (SPEC §9.4, OD-18)

`AisStaticStore` in `state.py` (`tests/domain/test_static.py`).

| ID | Case | Expected | Status |
|---|---|---|---|
| U-STA-01 | Type 5 stored and read back | All fields; category, length, beam; update time | Done |
| U-STA-02 | Type 24 part A then B, and B then A | Merged into one record | Done |
| U-STA-03 | Later report without a field; newer value; type 19 static part; auxiliary craft | Known values kept, newer values win; mothership MMSI kept, no length | Done |
| U-STA-04 | Static data first, no position for 20 min | Still there (independent of the target table) | Done |
| U-STA-05 | 30 min after the last static report (refreshed by a new one); maximum age configurable | Dropped; never returned once stale, even before `expire()` | Done |
| U-STA-06 | Capacity (default 2 000, tested with 3) | The MMSI updated longest ago is dropped; an update makes an MMSI the newest | Done |
| U-STA-07 | Own-ship report; own MMSI | Refused | Done |

## 4. Functional tests (`tests/integration/`)

Run inside Home Assistant's test harness (`pytest-homeassistant-custom-component==0.13.316`, HA 2026.2.3 — SPEC OD-06). The serial port is replaced by a **fake transport** that feeds lines from a fixture or scenario (D-04 to D-08), under control of the test (pause, disconnect, burst). Time is controlled with the harness's time-travel helpers, so no test sleeps in real time.

### 4.1 Setup and lifecycle — `F-LIFE`

| ID | Case | Expected | SPEC | Status |
|---|---|---|---|---|
| F-LIFE-01 | Config flow, port lists `/dev/serial/by-id/*`, valid data within 5 s | Entry created | §11.1 | Done |
| F-LIFE-02 | Config flow, no data | `no_data` error shown, user can proceed | §11.1 | Done |
| F-LIFE-03 | Config flow, garbage (wrong baud) | Hint to try the other baud rate | §11.1 | Done |
| F-LIFE-04 | Setup with port missing | `ConfigEntryNotReady`, retried | §10.3 | Done |
| F-LIFE-05 | Unload | Reader task cancelled, port closed, no pending tasks (harness checks lingering tasks) | NFR-07 | Done |
| F-LIFE-06 | Reload after options change | New options applied, entities keep unique IDs | NFR-06 | Done |
| F-LIFE-07 | Options flow: every option round-trips | Stored and applied | §11.2 | Done |
| F-LIFE-08 | Diagnostics download | Config redacted, counters present | §9.5 | Done |

### 4.2 Hub and transport — `F-HUB`

| ID | Case | Expected | SPEC | Status |
|---|---|---|---|---|
| F-HUB-01 | Mixed stream from D-05 (synthetic stand-in until #2) | `$` lines reach GPS parsers, `!` lines reach AIS decoder; static reports (types 5, 24) reach the static callback and `ais_static`, type 19 stays a position with its static part | §6, §9.4 | Done (synthetic; real data: #2) |
| F-HUB-02 | D-04 malformed corpus injected in a valid stream | Valid data unaffected; counters match the number of bad lines | NFR-01 | Done |
| F-HUB-03 | Disconnect mid-stream | Own-boat and traffic entities unavailable immediately; `connected` off (and available); diagnostic counters available | §10.1 | Done |
| F-HUB-04 | Reconnect after 1, 5, 30 s | Backoff sequence respected (1, 2, 4 … 60 s, reset after reopen); one warning per outage, one info line on recovery | NFR-03, §10.3 | Done |
| F-HUB-05 | Partial line at disconnect | Discarded, no crash | NFR-01 | Done |

F-HUB-01, 02, 04 and 05 prove hub behaviour (routing, counters, backoff, framing), which does not depend on Home Assistant: they run against `hub.py` directly with the fake transport and injected clock/sleep, under `tests/transport/`, and need no HA harness. F-HUB-03 is split: the hub signals the disconnect immediately (hub level), and the entity states are checked in the HA harness.

### 4.3 Entities — `F-ENT`

| ID | Case | Expected | SPEC | Status |
|---|---|---|---|---|
| F-ENT-01 | D-05 replay (synthetic stand-in until #2) | All §9.1 entities created with correct device_class, native unit, state_class, translation key | §9.1 | Done (synthetic; real data: #2) |
| F-ENT-02 | HA unit system switched to metric/imperial; display unit set per entity | Native stays kn under both unit systems (HA does not auto-convert knots); a per-entity display unit (km/h, mph) is converted correctly | §9 | Done |
| F-ENT-03 | Own position | `device_tracker.<boat>` updates, SOG/COG attributes | §9.1 | Done |
| F-ENT-04 | GPS silent > staleness timeout | Own-boat entities unavailable; `sensor.ais_targets` stays available, with `distance` `None` from the next list rebuild (≤ 5 s) (entities depending on own position, P2, unavailable) | §10.1, NFR-05 | Done |
| F-ENT-05 | Heading never provided | `heading` unavailable, no error | §7.4 | Done |
| F-ENT-06 | Two config entries (two boats, two fake ports) | No unique-ID collision | NFR-06 | Done |
| F-ENT-07 | Every entity checked in the entity registry | Unique ID prefixed by entry ID | NFR-06 | Done |
| F-ENT-08 | Every entity filled by the `named-traffic` scenario (threat, watched targets) | Every attribute has a label in `strings.json`, `en.json` and `fr.json`; `nav_status` and `position_source` values translated; the own-boat tracker keeps its name and entity ID | §9, CLAUDE.md | Done |

### 4.4 Traffic behaviour — `F-TRF`

Driven by D-07 scenarios replayed in accelerated time.

| ID | Case | Expected | SPEC | Status |
|---|---|---|---|---|
| F-TRF-01 | U-TRF-05 scenario played over time | `binary_sensor.collision_risk` turns **on** when TCPA crosses 15 min, **off** after CPA passes | §8.2, §9.2 | Done |
| F-TRF-02 | U-TRF-01 head-on | Closest threat CPA/TCPA sensors match U-TRF-01 values within tolerance | §9.2 | Done |
| F-TRF-03 | 60 targets | `sensor.ais_targets` = 60, attribute list capped at 50 nearest | §9.2 | Done |
| F-TRF-04 | Target stops reporting | Removed after expiry (Class A 10 min, Class B 15 min) | §9.4 | Done |
| F-TRF-05 | Watch list with 2 MMSIs | Exactly 2 AIS trackers created; removal from list removes them | §9.3 | Done |
| F-TRF-06 | Automation triggered on `collision_risk`; CPA hovering around the threshold during the episode | Automation runs once per risk episode (no flapping, latch of SPEC §8.2 / U-TRF-14) | §9.2 | Done |
| F-TRF-07 | Anchored target exclusion toggled | Threat state follows the option | §8.2 | Done |
| F-TRF-08 | Type 5 before and after the first position; type 24 part A | The name shows in `collision_risk`, the `targets` list and the watch-list tracker; diagnostics count static reports and stored MMSIs | §9.4, OD-18 | Done |
| F-TRF-09 | Type 5 cargo ship as the closest target and threat, on the watch list; same without static data | Ship type (`cargo`, code 70), call sign, IMO, length, beam, draught, destination on `collision_risk`, the closest target/threat sensors and the tracker, `None` when unknown; `targets` row has ship type and length only | §9.2–9.4, OD-17, OD-20 | Done |
| F-TRF-10 | Stationary threat: static data arrives after the position, then its destination changes | `collision_risk` and the tracker are written although their state and position do not change | §9.4 | Done |
| F-TRF-11 | Ship-type translations | Every category in `strings.json`, `en.json`, `fr.json` for every entity with the attribute; French strings loaded by HA | CLAUDE.md, OD-17 | Done |

### 4.5 Load and recorder — `F-PERF`

Marked `@pytest.mark.perf`, excluded from the default run and executed by the nightly workflow (§7). Time is simulated; timing assertions use the harness clock except the event-loop lag of F-PERF-01.

| ID | Case | Expected | SPEC | Status |
|---|---|---|---|---|
| F-PERF-01 | D-08 burst (≥ 50 sentences/s, 60 s) | No backlog: all lines processed within 1 s of arrival; event loop lag < 100 ms | NFR-09 | Done |
| F-PERF-02 | 10 min of D-06 at real rate (synthetic D-07 stream until #2) | State writes per entity ≤ 1/s; total writes counted and recorded as baseline | NFR-04, §10.2 | Done (synthetic baseline; D-06: #2) |
| F-PERF-03 | `sensor.ais_targets` attributes | Rebuilt ≤ every 5 s; serialized size under HA's attribute limit | §10.2 | Done |

## 5. End-to-end tests

E2E runs on a real Home Assistant instance, in three stages of increasing realism. Each stage has a written checklist; results are recorded in the test report (§9).

### 5.1 Stage E-1 — Replay bench (desk, no receiver)

Setup (TP-01, TP-02, SPEC OD-12 — resolved v0.3):

- **Where:** Home Assistant **Container** on a Linux host — a dev box for quick checks, a Raspberry Pi with Raspberry Pi OS for E-05 on target hardware. HA OS restricts host tools, so it is used only for E-01.
- **Feed:** `tests/tools/replay.py --pty /tmp/ttyAIS <capture>` creates its own pseudo-TTY and links it to `/tmp/ttyAIS`; the integration is configured on that path (the container needs the PTY mapped). `socat` is optional: `socat -d -d pty,raw,echo=0,link=/tmp/ttyAIS pty,raw,echo=0,link=/tmp/ttyAIS_feed` then `replay.py --device /tmp/ttyAIS_feed`.
- **E-01 on HA OS:** two USB-serial adapters wired null-modem; the Pi reads one, a laptop runs `replay.py --device /dev/ttyUSBx` on the other.
- The integration contains no file or replay source of its own.

| ID | Case | Expected |
|---|---|---|
| E-01 | Install via HACS custom repository from the release tag, configure through the UI | Integration works with no manual file copy |
| E-02 | Replay the D-07 presets `head-on`, `crossing`, `clear-crossing`, `not-urgent`, `anchored`, `multi-target` at real speed, with the README automation installed | Dashboard shows the targets; CPA/TCPA match U-TRF within ± 0.02 NM, ± 0.2 min; `collision_risk` fires (and clears) exactly where the preset says; one notification per episode is delivered to the phone. Checklist in `docs/test-reports/P2-report.md` |
| E-03 | Replay D-06 for its full duration | No error in HA log; own track in the map/logbook matches the capture |
| E-04 | Kill the replay tool (or the feed side of `socat`), restart after 30 s | Unavailable → recovered without HA restart |
| E-05 | D-08 burst at real speed on the Pi | CPU and event-loop lag within F-PERF-01 limits on the target hardware |
| E-06 | HA restart during replay | Integration reloads, entities come back, no duplicates |

### 5.2 Stage E-2 — On board, in port (real receiver)

Prerequisite: smart0183serial removed (SPEC §3.1).

| ID | Case | Expected |
|---|---|---|
| E-10 | Configure on `/dev/serial/by-id/…` of the receiver | Valid data within 5 s at the confirmed baud rate (OD-14) |
| E-11 | Own position | Within 20 m of the chartplotter/receiver display; SOG ≈ 0, COG noise acceptable |
| E-12 | AIS targets in the marina | Count and a sample of 5 MMSIs match the chartplotter's AIS list (or a public AIS site, for cross-check only). From P3: for the same 5 targets (at least one Class A and one Class B, read ≥ 6 min after start), name, ship type and length also match |
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
| pytest-homeassistant-custom-component 0.13.316 | Functional tests (HA harness, time travel, lingering-task checks); pins HA 2026.2.3 |
| pyais (MIT) | Test-only oracle and synthetic AIS generator (D-03, D-07) |
| `tests/tools/scenario.py` | Generates timed RMC + VDM streams from track definitions (D-07); JSON scenarios or presets. Usage in `CONTRIBUTING.md` |
| `tests/tools/replay.py` | Timed replay of captures to its own PTY (`--pty`) or an existing device (`--device`), with speed factor |
| `tests/tools/capture.py` | Timestamped raw capture of a serial port (X-09) into `captures/` (git-ignored) |
| socat | Optional pseudo-TTY pair for E-1 |
| ruff, mypy, hassfest, HACS action | Static checks and packaging validation in CI |

## 7. CI gates

Every PR must pass:

1. `ruff` and `mypy` clean.
2. Unit tests (`U-*`) green; **coverage ≥ 90 % on the pure modules: `nmea/`, `state.py`, `geo.py`, `hub.py`, `traffic.py`** (NFR-08).
3. Functional tests (`F-*`) green, excluding `F-PERF` (marker `perf`, run nightly by `.github/workflows/nightly.yml` (job `perf`, junit report kept as an artifact) — timing-sensitive on shared runners). They run in the `unit` CI job.
4. No HA import in any pure module (NFR-02 check).
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
| P1 Base | U-NMEA, U-GPS, U-AIS-13, U-COO, U-TRF-12, F-LIFE, F-HUB, F-ENT, F-PERF, E-1 (E-01, E-03…E-06), E-2 (E-10, E-11, E-13) | All green; D-05 replay matches receiver display. Tests needing X-09 (U-GPS-08, U-AIS-13, real-data runs of F-HUB-01, F-ENT-01, F-PERF-02) tracked in issue #2 |
| P2 Traffic | U-TRF, F-TRF, E-02, E-12, E-16, E-3 | All green; at least 3 real encounters in E-21 consistent with the chartplotter |
| P3 Static data | U-AIS-04, U-AIS-15…22; U-STA (static store, WP12); F-TRF static checks (entities, WP13); E-12 extended to names and ship types | All green; on board, names and ship types of 5 targets match the chartplotter (E-12); U-AIS-13 on the receiver capture (#2) decodes its type 5/24 lines without rejects |

**Test report** per release: version, commit, CI run link, coverage figures, E-stage checklists with date/location/conditions, deviations and their tickets. Stored in the repository under `docs/test-reports/`.

## 10. Open points

| ID | Question | Proposal | Needed by |
|---|---|---|---|
| ~~TP-01~~ | ~~Where do E-1 benches run?~~ | **Resolved v0.3:** HA Container on Linux (dev box; Pi with Raspberry Pi OS for E-05); HA OS only for E-01 (§5.1) | — |
| ~~TP-02~~ | ~~PTY replay on HA OS~~ | **Resolved v0.3:** E-1 runs on HA Container with `replay.py --pty`; E-01 on HA OS uses a null-modem pair of USB-serial adapters (§5.1) | — |
| TP-03 | Anonymisation of captures | Replace own MMSI and home berth position with fixed test values before committing | Before committing D-05 |
| TP-04 | Chartplotter as reference for E-21 | Confirm a chartplotter or app on board displays AIS CPA/TCPA; otherwise use a phone app fed by the same data | P2 |
| ~~TP-05~~ | ~~Clock injection in `ais_decoder.py`~~ | **Resolved v0.2:** `clock` parameter added | — |

## 11. Cross-references

| Ref | Document / artefact |
|---|---|
| SPEC | HA-SAIL-SPEC-001 v0.5 — sections cited inline |
| X-01 | gpsd, *AIVDM/AIVDO protocol decoding* v1.58 (D-01) |
| X-02 | `ais_decoder.py` + `test_ais_decoder.py` (U-AIS-01…09) |
| X-04 | Home Assistant developer docs — testing guidelines for custom integrations |
| X-08 | pyais (MIT) — test oracle and generator only |
| X-09 | Raw captures of the receiver output (D-05, D-06); issue #2 |
