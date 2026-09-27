# HA-SAIL-SPEC-001 — Sailing Boat Integration for Home Assistant

**High-level technical specification**

| Item | Value |
|---|---|
| Document ID | HA-SAIL-SPEC-001 |
| Version | 0.4 (draft) |
| Date | 2026-09-27 |
| Owner | Olivier (Garnet & Jade Consulting) |
| Status | Draft — open decisions in §14 |
| Project name / domain | **Vigie** / `vigie` (OD-01 resolved) |
| Repository | `ha-vigie` on GitHub (X-11) |

---

## Changelog

| Version | Date | Change |
|---|---|---|
| 0.4 | 2026-09-27 | OD-01 resolved: project named **Vigie**, domain `vigie`, repository `ha-vigie`. OD-11 resolved: Apache-2.0. Repository bootstrap delivered (X-11): skeleton integration, CI, docs; AIS decoder moved to `custom_components/vigie/nmea/` with injectable clock (TEST-001 TP-05). |
| 0.3 | 2026-09-27 | Test protocol split into companion document HA-SAIL-TEST-001 (X-10); §12 test bullet now points to it. No functional change. |
| 0.2 | 2026-09-27 | OD-02 resolved: a single serial port connected to the AIS receiver, which is the only data source (own position/speed included). Consequences: single-port design; own-boat data from the receiver's GPS sentences and/or `!AIVDO`; wind/depth/STW sensors and the true-wind/VMG layer removed from v1 (no source); traffic awareness (CPA/TCPA) promoted to v1 core value; OD-08 withdrawn; new OD-13 (receiver type), OD-14 (baud rate); new X-09 (raw capture). |
| 0.1 | 2026-09-27 | Initial draft. Architecture option 3 (clean-room integration) selected; AIS decoder (C-03) delivered and tested; smart0183serial excluded (§3). |

---

## 1. Purpose

Provide a Home Assistant custom integration that reads the NMEA 0183 output of the boat's **AIS receiver** over one serial port and turns it into meaningful, typed Home Assistant entities: own-boat position and motion, surrounding AIS traffic, and collision-risk indicators (CPA/TCPA).

The integration must run standalone on a boat-mounted Home Assistant instance (typically Raspberry Pi, HA OS) with no internet connection.

## 2. Scope

### 2.1 In scope (v1)

- One serial NMEA 0183 input: the AIS receiver (USB or RS-422 adapter).
- Checksum-validated parsing of the GPS sentences emitted by the receiver's internal GNSS (§7.2).
- AIS decoding of `!xxVDM` (other vessels) and `!xxVDO` (own ship, if emitted) position reports: Class A (types 1, 2, 3) and Class B (types 18, 19) (§7.3).
- Own-boat entities: position, SOG, COG, heading when available, GNSS health.
- AIS target table with expiry; aggregate traffic sensor; opt-in tracking of selected MMSIs.
- CPA/TCPA computation for each target and a closest-threat alert (§8).
- UI configuration (config flow + options flow), HACS-installable.

### 2.2 Out of scope (v1)

- Wind, depth, water speed and temperature sensors, and derived sailing performance (true wind, VMG, polars): **no source on board** (§3.3). The architecture keeps room for them (§13, P4).
- Navigation / charting (OpenCPN covers this).
- Transmitting NMEA or AIS (read-only integration).
- Multiple ports, TCP/UDP input, NMEA 2000.
- Cloud services of any kind.

## 3. Context and constraints

### 3.1 Why not extend ha-smart0183serial

Analysis of `SmartBoatInnovations/ha-smart0183serial` (last commit 2025-12-21) — see X-03:

1. **License.** The repository is under a proprietary "Smart Boat Innovations License" forbidding copying, modification, distribution and commercial use. Forking is not permitted.
2. **AIS is discarded.** `sensor.py` rejects every line not starting with `$` (line 334); `!AIVDM` is never processed. For a setup whose only source is an AIS receiver, this discards the main payload.
3. **Serial port exclusivity.** Only one process can own the port, so a companion integration cannot read the raw stream alongside it.
4. **Design limits.** No checksum validation (last field skipped), one sensor per positional field (`RMC_7`…), `state_class: measurement` applied to text fields, legacy `state`/`unit_of_measurement` properties, no coordinator, undeclared `serial_asyncio_fast` requirement.

**Decision:** clean-room implementation (option 3). No code, structure or data file (including `Smart0183serial.json`) from that repository may be copied. smart0183serial must be removed from the boat's HA instance before this integration is installed (same port).

### 3.2 Platform constraints

- Home Assistant core: Python 3.13+, single asyncio event loop. No blocking I/O on the loop.
- Target install: HA OS on Raspberry Pi 4/5 on board, 12 V supply, possibly intermittent power.
- AIS receivers typically output at 38 400 baud (OD-14). AIS traffic arrives in bursts of tens of sentences per second in busy waters; GPS sentences at about 1 Hz.
- The HA recorder (SQLite on SD card) must not be flooded by high-rate state changes (§10.2).

### 3.3 Data source

The AIS receiver is the **only** device on the serial connection and the only data source. Evidence and consequences:

- Position and speed were already visible through smart0183serial, which only processes `$` lines. The receiver therefore emits **GPS sentences** (`$GPRMC`/`$GNRMC` and similar) from its internal GNSS. This is the baseline own-boat source.
- If the unit is a Class B **transponder** (rather than a receive-only receiver), it may also emit `!AIVDO` own-ship reports. These are a secondary source (OD-13).
- Heading: only available if the unit receives or computes it (VDO heading field, `HDT`). Most small-boat setups report heading as not available (511); the design treats heading as optional.
- There is no wind, depth or log instrument. Any sensor depending on them is out of v1 scope.

The exact sentence set will be confirmed from a raw capture of the port (X-09), which also becomes the primary test fixture.

## 4. Non-functional requirements

| ID | Requirement |
|---|---|
| NFR-01 | No corrupted value reaches an entity: checksum and length validation on every sentence. |
| NFR-02 | Protocol layer (`nmea/`) has zero Home Assistant imports and is unit-testable in isolation. |
| NFR-03 | Transport survives disconnection (USB unplug, power dip) with automatic reconnect and backoff. |
| NFR-04 | Entity state writes throttled to ≤ 1 Hz per entity by default (configurable). |
| NFR-05 | Missing data surfaces as `unavailable` after a configurable staleness timeout, never as a frozen value. |
| NFR-06 | Unique IDs scoped to the config entry, so renames and reinstalls are safe. |
| NFR-07 | Integration load/unload/reload leaves no dangling tasks or open ports. |
| NFR-08 | Test coverage of the protocol layer ≥ 90 %, including real-world malformed samples from X-09. |
| NFR-09 | AIS bursts (≥ 50 sentences/s) are processed without backlog or event-loop stalls. |

## 5. Architecture

### 5.1 Layered view

```
┌──────────────────────────────────────────────────────────────┐
│ Entities         sensor · device_tracker · binary_sensor      │  HA presentation
├──────────────────────────────────────────────────────────────┤
│ Traffic logic    traffic.py (CPA/TCPA, closest threat)        │  derived domain logic
├──────────────────────────────────────────────────────────────┤
│ Coordinator      coordinator.py (OwnBoatState, AisTargetTable)│  single source of truth
├──────────────────────────────────────────────────────────────┤
│ Protocol         nmea/sentence.py · parsers.py · ais_decoder  │  pure Python, no HA
├──────────────────────────────────────────────────────────────┤
│ Transport        hub.py (one serial reader, line framing)     │  asyncio I/O
└──────────────────────────────────────────────────────────────┘
```

Dependency rule: each layer depends only on the layer below it. Entities never parse NMEA; the traffic logic never sees sentence names.

### 5.2 Component map

| ID | Component | File | Responsibility |
|---|---|---|---|
| C-01 | Transport hub | `hub.py` | Own the serial port; read lines; route `$…` to C-02, `!…` to C-03; reconnect; diagnostics counters. |
| C-02 | GPS sentence parsers | `nmea/sentence.py`, `nmea/parsers.py` | Checksum, field split, talker ID; typed decoding of §7.2 sentences. |
| C-03 | AIS decoder | `nmea/ais_decoder.py` | Delivered (X-02). Types 1/2/3/18/19, fragment reassembly, tag blocks, VDO flag. |
| C-04 | Coordinator | `coordinator.py` | Merge own-boat data into `OwnBoatState`; maintain `AisTargetTable`; throttle and push updates. |
| C-05 | Traffic logic | `traffic.py` | CPA/TCPA per target, distance and bearing, closest-threat selection (§8). |
| C-06 | Config flow | `config_flow.py` | Setup and options UI (§11). |
| C-07 | Sensors | `sensor.py`, `binary_sensor.py` | Own-boat measurements, traffic summary, alert (§9). |
| C-08 | Trackers | `device_tracker.py` | Own boat position; watched AIS targets (§9.3). |
| C-09 | Diagnostics | `sensor.py`, `diagnostics.py` | Health counters; HA diagnostics download. |

### 5.3 File layout

```
custom_components/vigie/
├── manifest.json
├── __init__.py
├── config_flow.py
├── const.py
├── hub.py
├── coordinator.py
├── traffic.py
├── sensor.py
├── binary_sensor.py
├── device_tracker.py
├── diagnostics.py
├── strings.json
├── translations/{en,fr}.json
└── nmea/
    ├── __init__.py
    ├── sentence.py
    ├── parsers.py
    └── ais_decoder.py
tests/
├── fixtures/        # raw captures (X-09)
├── nmea/            # pure-Python tests, no HA fixture
└── integration/     # pytest-homeassistant-custom-component
```

## 6. Data flow

1. C-01 reads bytes, frames lines on `\r\n`, discards over-long or non-ASCII lines.
2. Routing by first character: `$` → C-02, `!` → C-03, `\` → strip tag block then re-route, anything else → counted as ignored.
3. Parsers return typed records or `None`; rejects are counted, never raised to the loop.
4. C-04 routes records:
   - GPS records and `VDO` reports → `OwnBoatState` (per-field timestamp and source).
   - `VDM` reports → `AisTargetTable` upsert.
5. C-05 recomputes CPA/TCPA for affected targets whenever own state or a target changes.
6. C-04 notifies entities, each throttled per NFR-04 (§10.2).

Reading runs as one long-lived task created in `async_setup_entry` and cancelled in `async_unload_entry`. No polling: `iot_class: local_push`, entities have `should_poll = False`.

## 7. Protocol layer

### 7.1 Common sentence handling (C-02)

- Checksum: XOR of all characters between `$`/`!` and `*`, compared to the two hex digits. Missing or wrong checksum → reject.
- Talker ID is not significant for routing: `GPRMC`, `GNRMC`, `AIRMC` all decode as RMC; the talker is kept as metadata.
- Empty fields → `None`, never `0`.
- Sentences outside §7.2 (including proprietary `$P…`) are counted and ignored.

### 7.2 Supported GPS sentences (v1)

Final list to be confirmed against X-09.

| Sentence | Content | OwnBoatState fields |
|---|---|---|
| RMC | Position, SOG, COG, UTC date/time, status, magnetic variation | `position`, `sog`, `cog`, `utc`, `variation` |
| GGA | Position, fix quality, satellites, HDOP | `position`, `fix_quality`, `satellites`, `hdop` |
| VTG | COG true, SOG | `cog`, `sog` |
| GSA | Fix mode (2D/3D), DOP | `fix_mode`, `pdop` |
| HDT | True heading (if present) | `heading` |

RMC with status `V` (void) is not applied to position/SOG/COG.

### 7.3 AIS (C-03)

Implemented and delivered as `ais_decoder.py` (X-02). Summary:

- Accepts any talker (`!AI`, `!AB`, `!BS`…) with `VDM` (other vessels) or `VDO` (own ship, flagged `own_ship`).
- Validates checksum and minimum payload length per type (168 bits for 1/2/3/18, 312 for 19), per the spec's warning that about 0.3 % of checksum-valid messages have wrong lengths (X-01).
- Reassembles multi-fragment messages by (talker, channel, sequence ID) with a 5 s timeout.
- Maps "not available" sentinels (lon 181°, lat 91°, SOG 1023, COG 3600, heading 511) to `None`.
- Output: `VesselPosition(mmsi, ais_class, msg_type, latitude, longitude, sog_knots, cog_deg, heading_deg, nav_status, name, own_ship, channel, received_at)`.
- Test suite: 15 tests including 2 500 fuzzed messages per type compared against pyais (MIT, test-only dependency).

### 7.4 Own-boat source arbitration

When both GPS sentences and `VDO` are present, GPS sentences are preferred (higher rate, fix quality available); `VDO` is used only when GPS data is stale. The active source is exposed as an attribute. Heading is taken from `HDT` or `VDO` heading when not 511, else unavailable.

## 8. Traffic logic (C-05)

### 8.1 Relative geometry

For each target with valid position, SOG and COG, and a valid own position/SOG/COG:

- Distance and bearing from own boat (haversine; flat-earth approximation acceptable below 20 NM).
- Positions projected to a local east/north plane in metres around own position.
- Relative position `P = target − own`, relative velocity `V = v_target − v_own` (velocities from SOG/COG).
- `TCPA = −(P·V) / |V|²` (if `|V|` ≈ 0, TCPA undefined and CPA = current distance).
- `CPA = |P + V·TCPA|`, reported for TCPA ≥ 0 only (diverging targets are "no risk").

### 8.2 Threat classification

A target is a **threat** when `CPA < cpa_threshold` (default 0.5 NM) and `0 ≤ TCPA < tcpa_threshold` (default 15 min). Targets with nav status `moored` or `at_anchor` and SOG < 0.5 kn are excluded from threats by default (option). Thresholds are configurable (§11.2).

### 8.3 Limits

CPA/TCPA assume straight-line constant-speed motion from the last report. Class B targets report every 30 s to 3 min, so their predictions are coarser; the report age is exposed so the user can judge. This is an aid, not a collision-avoidance system (documented in the README).

## 9. Entity model

All entities belong to one HA device per config entry ("the boat"), except watched AIS targets, which get one device each. `has_entity_name = True`, translation keys, entry-scoped unique IDs (`{entry_id}_{key}`).

### 9.1 Own-boat sensors

| Key | Name | device_class | Native unit | state_class |
|---|---|---|---|---|
| `sog` | Speed over ground | speed | kn | measurement |
| `cog` | Course over ground | — (OD-10) | ° | — (OD-10) |
| `heading` | Heading (true), optional | — (OD-10) | ° | — (OD-10) |
| `fix_quality` | GNSS fix | enum | — | — (diagnostic) |
| `satellites` | Satellites in use | — | — | measurement (diagnostic) |
| `hdop` | Horizontal dilution | — | — | measurement (diagnostic) |

`device_tracker.<boat>` exposes own position (GPS source type) with SOG/COG attributes.

### 9.2 Traffic sensors

| Entity | Content |
|---|---|
| `sensor.ais_targets` | Count of live targets. Attributes: compact list (MMSI, name, class, lat, lon, SOG, COG, distance, CPA, TCPA, age), capped at the 50 nearest (OD-04). |
| `sensor.closest_target_distance` | Distance to the nearest target (NM, device_class distance). Attributes: MMSI, name. |
| `sensor.closest_threat_cpa` / `_tcpa` | CPA (NM) and TCPA (min) of the most urgent threat; unavailable when none. |
| `binary_sensor.collision_risk` | On while at least one threat exists (device_class safety). Designed to drive automations (notification, buzzer, lights). |

### 9.3 Watched targets

`device_tracker.ais_<mmsi>` exists only for MMSIs in the user's watch list (options flow), for example friends' boats or a tender. Never auto-created for every target.

### 9.4 AIS target table

Keyed by MMSI. An entry expires after a timeout (default 10 min Class A, 15 min Class B and anchored/moored). Own-ship `VDO` reports never enter the table. Names are filled from type 19 now and types 5/24 in P3.

### 9.5 Diagnostics (entity_category: diagnostic)

`sentences_per_min`, `checksum_errors`, `ais_rejected`, `last_sentence_age`, `own_position_source` (GPS / VDO), and a `connected` binary sensor. `diagnostics.py` exports config (redacted) and counters for bug reports.

## 10. Runtime behaviour

### 10.1 Availability

Each state field carries its last-update time. Own-boat entities become `unavailable` when their source is older than the staleness timeout (default 10 s). A port disconnect makes all entities unavailable immediately. Traffic entities go unavailable if own position is unavailable (CPA undefined).

### 10.2 Throttling and recorder load

- Entities write state at most once per `update_interval` (default 1 s), with the latest value.
- Dead-bands (0.1 kn, 1°, 0.01 NM) suppress insignificant writes.
- `sensor.ais_targets` attributes are rebuilt at most every 5 s; the README recommends excluding it from the recorder (large attributes).
- `state_class` is set only on true measurements.

### 10.3 Reconnection

Exponential backoff (1 s → 60 s max) on serial errors, logged once per outage. On first setup with the port unavailable, raise `ConfigEntryNotReady` so HA retries.

## 11. Configuration

### 11.1 Config flow (setup)

1. Boat name.
2. Serial port, discovered from the system (`/dev/serial/by-id/*` preferred for stability), manual entry allowed.
3. Baud rate: 38 400 default, 4 800 and custom offered (OD-14).
4. Validation: open the port and wait up to 5 s for one valid sentence; otherwise show `no_data` (user can still proceed). If the probe shows only garbage, suggest the other baud rate.

### 11.2 Options flow

Update interval, staleness timeout, AIS target expiry, CPA threshold, TCPA threshold, exclude anchored/moored from threats, include own `VDO`, watch list (MMSIs).

## 12. Quality, packaging, security

- **Tests:** defined in HA-SAIL-TEST-001 (X-10): unit (pure Python, no HA), functional (HA test harness with a fake serial transport), end-to-end (replay bench, in port, under way). NFR traceability and CI gates are specified there.
- **CI:** GitHub Actions running tests, `ruff`, `mypy`, `hassfest`, HACS validation.
- **Packaging:** `manifest.json` with `iot_class: local_push`, `integration_type: hub`, `config_flow: true`, explicit `requirements` (`pyserial-asyncio-fast`). Installed via HACS custom repository. The `nmea/` package can later move to PyPI (HA best practice).
- **Workflow:** GitHub issue → PR → CI → review → versioned release.
- **Security:** no network listener, no credentials, no outbound traffic. Serial input treated as untrusted: bounded line length, strict parsing, exceptions contained per line.
- **Licensing:** Apache-2.0 (OD-11). Clean-room rule from §3.1 applies to all contributors.

## 13. Roadmap

| Phase | Content | Exit criterion |
|---|---|---|
| P0 | AIS decoder (C-03) | **Done** — X-02, 15 tests green |
| P1 | Raw capture (X-09); transport, GPS parsers, coordinator, own-boat entities, AIS target table, `sensor.ais_targets`, diagnostics | Capture replayed; own-boat entities match the receiver/chartplotter display |
| P2 | Traffic logic: CPA/TCPA, closest target/threat, `binary_sensor.collision_risk`, watched-target trackers | Scenario tests green; on-water check against a chartplotter's AIS page |
| P3 | AIS static data (types 5, 24): names, ship type, dimensions; Lovelace map card configuration | — |
| P4 | Optional additional sources if instruments are added (wind, depth, log) and the performance layer (true wind, VMG, polars), via a second port or TCP | Requires new hardware; re-opens §2.2 |

## 14. Open decisions

| ID | Question | Options | Needed by |
|---|---|---|---|
| ~~OD-01~~ | ~~Integration domain name~~ | **Resolved v0.4:** Vigie / `vigie` | — |
| ~~OD-02~~ | ~~Instruments and AIS on one port or several?~~ | **Resolved v0.2:** one port, AIS receiver only (§3.3) | — |
| OD-03 | GPS parsing: own parsers or `pynmea2` (MIT) | Own = 5 sentences, no dependency (proposed given the reduced scope); pynmea2 = broader coverage | P1 |
| OD-04 | AIS exposure model | Aggregate sensor + watch-list trackers + threat entities (proposed) vs geo_location platform | P2 |
| OD-06 | Minimum supported HA version | Current stable at P1 start; affects available device classes | P1 |
| OD-07 | Own-boat source priority | GPS sentences first, VDO fallback (proposed, §7.4) vs configurable | P1 |
| ~~OD-08~~ | ~~Instrument true wind vs computed~~ | **Withdrawn v0.2:** no wind source (§2.2) | — |
| OD-10 | Angle entities' device_class/state_class | Verify angle-measurement support in the target HA version (OD-06) before relying on it | P1 |
| ~~OD-11~~ | ~~License of this project~~ | **Resolved v0.4:** Apache-2.0 | — |
| OD-12 | Replay tool for development | X-09 log replay into a pseudo-TTY (`socat`) vs built-in file source | P1 |
| OD-13 | Receiver type: receive-only or Class B transponder? | Determines whether `!AIVDO` exists; design handles both (§7.4) | P1 (from X-09) |
| OD-14 | Serial baud rate | 38 400 (typical AIS) vs 4 800; confirmed by X-09 and by the current smart0183serial setting | P1 |

(OD-05 and OD-09 from v0.1 were tied to NMEA 2000 and polars; both moved to P4 and are no longer open for v1.)

## 15. Corpus cross-references

| Ref | Document / artefact | Used in |
|---|---|---|
| X-01 | E. S. Raymond, *AIVDM/AIVDO protocol decoding*, gpsd, v1.58 — https://gpsd.gitlab.io/gpsd/AIVDM.html | §7.3, C-03 |
| X-02 | `ais_decoder.py` + `test_ais_decoder.py` (delivered 2026-09-27) | §7.3, P0 |
| X-03 | Code review of `SmartBoatInnovations/ha-smart0183serial` @ `5854e94` (license, sensor.py L334, checksum handling) | §3.1, §3.3 |
| X-04 | Home Assistant developer docs — integration architecture, config flow, DataUpdateCoordinator, entity guidelines — https://developers.home-assistant.io | §5, §9, §11 |
| X-05 | `ludeeus/integration_blueprint` — dev container and HACS layout reference | §12 |
| X-06 | Smart Boat Innovations integrations (ha-smart0183tcp, ha-smart-anchor) — prior art, not reused | §2 |
| X-08 | pyais (MIT) — test oracle only | §7.3 |
| X-09 | Raw capture of the AIS receiver's serial output (to be produced; ≥ 15 min, ideally in port and under way) | §3.3, §7.2, OD-13, OD-14, tests |
| X-10 | HA-SAIL-TEST-001 — Test protocol (unit, functional, end-to-end) | §12, §13 |
| X-11 | Repository `ha-vigie` — bootstrap kit (skeleton, CI, GitHub setup script) | §5.3, §12 |
