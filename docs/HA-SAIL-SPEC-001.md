# HA-SAIL-SPEC-001 — Sailing Boat Integration for Home Assistant

**High-level technical specification**

| Item | Value |
|---|---|
| Document ID | HA-SAIL-SPEC-001 |
| Version | 0.12 (draft) |
| Date | 2026-09-27 |
| Owner | Olivier (Garnet & Jade Consulting) |
| Status | Draft — open decisions in §14 |
| Project name / domain | **Vigie** / `vigie` (OD-01 resolved) |
| Repository | `ha-vigie` on GitHub (X-11) |

---

## Changelog

| Version | Date | Change |
|---|---|---|
| 0.12 | 2026-09-27 | WP13 (#36): static data on the entities (§9.2, §9.3, §9.4): ship type (translated category and code), call sign, IMO, length, beam, draught, destination on the closest target/threat sensors, `collision_risk` and the watch-list trackers; ship type and length in the `targets` list; static data that changes is written at once. |
| 0.11 | 2026-09-27 | WP12 (#34): §9.4 static store implemented; the hub delivers static reports separately (§6) and counts them (`ais_static`, §9.5); names from static data are preferred wherever a target's name is shown. |
| 0.10 | 2026-09-27 | P3 decisions and WP11 (#32). New OD-17, resolved: ship type as code plus category key. New OD-18, resolved: static data kept 30 min after its last report, at most 2 000 MMSIs. New OD-19, resolved: built-in map card configuration (own boat, watched targets); a custom card is left for after v1. New OD-20, resolved: fields name, call sign, IMO, ship type, length, beam, draught, destination (no ETA, no EPFD). §7.3 extended to types 5 and 24 and the static fields of type 19; §9.4 static data; §13 P3 exit criterion. |
| 0.9 | 2026-09-27 | WP9 (#27): §9.3 watched targets made precise (device per MMSI linked to the boat, attributes, availability, removal); §11.2 `watch_list` implemented. |
| 0.8 | 2026-09-27 | WP8 (#25): §9.2 traffic entities made precise (units, suggested nmi, state classes, attributes); CPA/TCPA in the `targets` list; §11.2 P2 threat options implemented. |
| 0.7 | 2026-09-27 | P2 decisions and WP7 (#23). OD-04 resolved: aggregate sensor + watch-list trackers + threat entities, no `geo_location`. New OD-15, resolved: `collision_risk` anti-flapping latch (§8.2). New OD-16, resolved: dead-reckon own boat and targets to now before CPA/TCPA (§8.1, §8.3). §8.1 made precise (local plane, ‖V‖ threshold 0.1 kn, diverging targets report TCPA < 0 and no CPA); §8.2 stationary exclusion applies to Class A only; §9.2 `collision_risk` unavailable without own position. |
| 0.6 | 2026-09-27 | WP5 (#15): §9.2 — distances in `sensor.ais_targets` follow the list rebuild (≤ 5 s); §9.5 — `diagnostics.py` also exports GPS rejects, internal errors and reconnects. No change of scope. |
| 0.5 | 2026-09-27 | P1 decisions (issue #3). OD-03 resolved: own GPS parsers. OD-06 resolved: minimum HA 2026.2.0. OD-07 resolved: GPS first, VDO fallback, `include_own_vdo` option. OD-10 resolved: angle entities without device class, state class `measurement_angle`. OD-12 resolved: external replay tool, no file source in the integration. Pure domain modules `state.py`, `geo.py` and a HA-free `hub.py` (§5); framing limits in `sentence.py` (§7.1); availability on disconnect and stale GPS clarified (§9.2, §9.5, §10.1); dead-band semantics, 5 m position dead-band (§10.2); config flow details (§11.1); P1 options incl. two expiry values and optional `own_mmsi` (§11.2); P0 test count corrected to 39. OD-13 and OD-14 stay open (need X-09, issue #2). |
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
│ Coordinator      coordinator.py (HA) · state.py · geo.py (pure)│  single source of truth
├──────────────────────────────────────────────────────────────┤
│ Protocol         nmea/sentence.py · parsers.py · ais_decoder  │  pure Python, no HA
├──────────────────────────────────────────────────────────────┤
│ Transport        hub.py (one serial reader, line framing)     │  asyncio I/O, no HA
└──────────────────────────────────────────────────────────────┘
```

Dependency rule: each layer depends only on the layer below it. Entities never parse NMEA; the traffic logic never sees sentence names.

Pure-Python modules (no `homeassistant` import, `mypy --strict`, covered by the NFR-02 check and the coverage gate): `nmea/`, `state.py`, `geo.py`, `hub.py`, `traffic.py`. The domain logic of the coordinator lives in `state.py` so it can be unit-tested; `coordinator.py` is a thin Home Assistant wrapper. `hub.py` depends only on asyncio and `pyserial-asyncio-fast`; the transport is injected, so tests use a fake transport (v0.5).

### 5.2 Component map

| ID | Component | File | Responsibility |
|---|---|---|---|
| C-01 | Transport hub | `hub.py` | Own the serial port (injected transport); read and frame lines; route `$…` to C-02, `!…` to C-03 (checksum pre-checked with C-02 so checksum errors are counted apart from AIS rejects); reconnect; diagnostics counters; 5 s probe for the config flow. No HA import. |
| C-02 | GPS sentence parsers | `nmea/sentence.py`, `nmea/parsers.py` | Checksum, field split, talker ID; typed decoding of §7.2 sentences. |
| C-03 | AIS decoder | `nmea/ais_decoder.py` | Delivered (X-02). Types 1/2/3/18/19, fragment reassembly, tag blocks, VDO flag. |
| C-04 | Coordinator | `state.py` (pure), `coordinator.py` (HA) | `state.py`: `OwnBoatState` (per-field value/timestamp/source, arbitration §7.4), `AisTargetTable` (§9.4), `WriteGate` (throttle and dead-band, §10.2), injectable clock. `coordinator.py`: owns hub and state, runs the update tick, pushes updates to entities. |
| C-05 | Traffic logic | `geo.py`, `traffic.py` | `geo.py` (P1): distance and bearing. `traffic.py` (P2): CPA/TCPA per target, closest-threat selection (§8). |
| C-06 | Config flow | `config_flow.py` | Setup and options UI (§11). |
| C-07 | Sensors | `sensor.py`, `binary_sensor.py` | Own-boat measurements, traffic summary, alert (§9). |
| C-08 | Trackers | `device_tracker.py` | Own boat position; watched AIS targets (§9.3). |
| C-10 | Entity base | `entity.py` | Shared device info, unique IDs and availability rule for all entities. |
| C-09 | Diagnostics | `sensor.py`, `diagnostics.py` | Health counters; HA diagnostics download. |

### 5.3 File layout

```
custom_components/vigie/
├── manifest.json
├── __init__.py
├── config_flow.py
├── const.py
├── hub.py              # pure asyncio, no HA
├── coordinator.py      # HA wrapper around state.py
├── state.py            # pure: OwnBoatState, AisTargetTable, WriteGate
├── geo.py              # pure: distance, bearing
├── traffic.py          # pure (P2)
├── entity.py
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
├── fixtures/        # D-04 malformed corpus, D-08 burst, raw captures (X-09)
├── nmea/            # pure-Python tests, no HA fixture
├── domain/          # pure-Python tests of state.py, geo.py, traffic.py
├── transport/       # hub tests with the fake transport, no HA fixture
├── integration/     # pytest-homeassistant-custom-component
└── tools/           # scenario.py, replay.py, capture.py (TEST §6)
```

## 6. Data flow

1. C-01 reads bytes, frames lines on `\r\n`, discards over-long or non-ASCII lines (limits in §7.1). A partial line pending at disconnect is discarded.
2. Routing by first character: `$` → C-02, `!` → C-03, `\` → strip tag block then re-route, anything else → counted as ignored.
3. Parsers return typed records or `None`; rejects are counted, never raised to the loop.
4. C-04 routes records:
   - GPS records and `VDO` reports → `OwnBoatState` (per-field timestamp and source).
   - `VDM` reports → `AisTargetTable` upsert.
   - Static reports (types 5, 24, and the static part of type 19) → `AisStaticStore` (§9.4); own-ship ones and the own MMSI are refused.
5. C-05 recomputes CPA/TCPA for affected targets whenever own state or a target changes.
6. C-04 notifies entities, each throttled per NFR-04 (§10.2). A connection change is pushed immediately, without waiting for the next tick.

Reading runs as one long-lived task created in `async_setup_entry` and cancelled in `async_unload_entry`. No polling: `iot_class: local_push`, entities have `should_poll = False`.

## 7. Protocol layer

### 7.1 Common sentence handling (C-02)

- Framing (`check_frame()` in `sentence.py`, called by C-01): printable ASCII only; at most 82 characters, `$`/`!` to checksum inclusive, measured after stripping any NMEA 4.0 tag block. The hub also caps its receive buffer (1 KiB) so a line with no terminator cannot grow without bound. Rejects are counted as framing errors.
- Checksum: XOR of all characters between `$`/`!` and `*`, compared to the two hex digits (upper or lower case). Missing or wrong checksum → reject.
- Talker ID is not significant for routing: `GPRMC`, `GNRMC`, `AIRMC` all decode as RMC; the talker is kept as metadata.
- Empty fields → `None`, never `0`.
- Sentences outside §7.2 (including proprietary `$P…`) are counted and ignored.
- GPS parsing uses our own parsers for the five §7.2 sentences, no third-party dependency (OD-03, resolved v0.5).

### 7.2 Supported GPS sentences (v1)

Final list to be confirmed against X-09.

| Sentence | Content | OwnBoatState fields |
|---|---|---|
| RMC | Position, SOG, COG, UTC date/time, status, magnetic variation | `position`, `sog`, `cog`, `utc`, `variation` |
| GGA | Position, fix quality, satellites, HDOP | `position`, `fix_quality`, `satellites`, `hdop` |
| VTG | COG true, SOG | `cog`, `sog` |
| GSA | Fix mode (2D/3D), DOP | `fix_mode`, `pdop` |
| HDT | True heading (if present) | `heading` |

RMC with status `V` (void) is not applied to position/SOG/COG. GGA with fix quality 0 produces no position. RMC two-digit years map to 20yy. Outputs are frozen dataclasses (`Rmc`, `Gga`, `Vtg`, `Gsa`, `Hdt`) with the units of CLAUDE.md (knots, degrees, decimal degrees N/E positive, variation E positive).

### 7.3 AIS (C-03)

Implemented and delivered as `ais_decoder.py` (X-02). Summary:

- Accepts any talker (`!AI`, `!AB`, `!BS`…) with `VDM` (other vessels) or `VDO` (own ship, flagged `own_ship`).
- Validates checksum and minimum payload length per type (168 bits for 1/2/3/18, 312 for 19), per the spec's warning that about 0.3 % of checksum-valid messages have wrong lengths (X-01).
- Reassembles multi-fragment messages by (talker, channel, sequence ID) with a 5 s timeout.
- Maps "not available" sentinels (lon 181°, lat 91°, SOG 1023, COG 3600, heading 511) to `None`.
- Output: `VesselPosition(mmsi, ais_class, msg_type, latitude, longitude, sog_knots, cog_deg, heading_deg, nav_status, name, own_ship, channel, received_at)`.
- Test suite: 39 tests (38 decoder tests and the NFR-02 import check), including 500 fuzzed messages per type compared against pyais (MIT, test-only dependency).
- Static data (P3, WP11): type 5 (Class A static and voyage data; 424 bits, accepted from 420 bits because many transmitters send 420 or 422), type 24 part A (name, ≥ 160 bits) and part B (ship type, call sign, dimensions, ≥ 168 bits; an auxiliary craft, MMSI 98xxxxxxx, sends its mothership's MMSI instead of dimensions), and the static fields of type 19. Output: `VesselStatic(mmsi, ais_class, msg_type, part, name, callsign, imo, ship_type, to_bow, to_stern, to_port, to_starboard, draught_m, destination, mothership_mmsi, own_ship, channel, received_at)` with `length_m` and `beam_m`; a type 19 `VesselPosition` carries its `static` part. Not available: IMO 0, ship type 0, draught 0, empty text → `None`; a dimension of 0 is kept, and length or beam is `None` only when both of its parts are 0. Type 24 parts 2 and 3 are not defined and are ignored. ETA and EPFD are not decoded (OD-20).
- Ship types are exposed as the ITU code and a category key (OD-17): `wing_in_ground` (20–29), `fishing` (30), `towing` (31, 32), `dredging` (33), `diving` (34), `military` (35), `sailing` (36), `pleasure_craft` (37), `high_speed` (40–49), `pilot` (50), `search_and_rescue` (51), `tug` (52), `port_tender` (53), `law_enforcement` (55), `medical` (58), `passenger` (60–69), `cargo` (70–79), `tanker` (80–89), `other` (every other code).
- The P0 decoder is reused and extended. The hub validates the checksum of `!` lines with C-02 before feeding the decoder, so `checksum_errors` and `ais_rejected` are counted separately (§9.5).

### 7.4 Own-boat source arbitration

When both GPS sentences and `VDO` are present, GPS sentences are preferred (higher rate, fix quality available); `VDO` is used only when GPS data is stale (older than the staleness timeout, §10.1). Arbitration is per field: GPS and VDO values are stored separately with their timestamps. The active position source is exposed as the `own_position_source` diagnostic sensor and as a tracker attribute. Heading is taken from `HDT` first, then `VDO` heading when not 511, else unavailable.

The option `include_own_vdo` (default on) disables VDO entirely; no other priority setting is offered (OD-07, resolved v0.5).

The own MMSI, used to keep the boat out of the target table (§9.4), is learned from `VDO` reports or set with the optional `own_mmsi` option (§11.2). With neither, no MMSI is excluded; a receive-only unit does not receive its own transmissions.

The design is neutral to OD-13: every path works with VDO present or absent.

## 8. Traffic logic (C-05)

### 8.1 Relative geometry

For each target with valid position, SOG and COG, and a valid own position/SOG/COG:

- Both vessels are first dead-reckoned from the time of their last report to now, along their SOG/COG (OD-16, resolved v0.7). A Class B target reporting every 3 min at 10 kn would otherwise be up to 0.5 NM behind its true position. Without SOG/COG a position is used as reported.
- Distance and bearing from own boat (haversine; flat-earth approximation acceptable below 20 NM).
- Positions projected to a local east/north plane in nautical miles around own position (equirectangular, cosine of the mean latitude; longitudes wrapped across 180°).
- Relative position `P = target − own`, relative velocity `V = v_target − v_own` (velocities from SOG/COG).
- `TCPA = −(P·V) / |V|²`. If `|V|` < 0.1 kn, TCPA is undefined (`None`) and CPA = current distance.
- `CPA = |P + V·TCPA|`, reported for TCPA ≥ 0 only. A diverging target (TCPA < 0) reports its negative TCPA and no CPA, and is "no risk".
- Without a position for either vessel there is no result; without SOG/COG for either, distance and bearing only (CPA/TCPA `None`).

### 8.2 Threat classification

A target is a **threat** when `CPA < cpa_threshold` (default 0.5 NM) and `0 ≤ TCPA < tcpa_threshold` (default 15 min). Targets with nav status `moored` or `at_anchor` and SOG < 0.5 kn are excluded from threats by default (option). Class B reports carry no nav status, so Class B targets are never excluded. Thresholds are configurable (§11.2).

The most urgent threat is the one with the smallest TCPA, then the smallest CPA.

`collision_risk` follows the threats with an anti-flapping latch (OD-15, resolved v0.7): it turns on as soon as one threat exists; once on, it stays on until no threat has been seen for 60 s, except that it clears at once when every target that was a threat during the episode has passed its CPA (TCPA < 0). One risk episode therefore triggers an automation once, even when a CPA or TCPA hovers around its threshold.

### 8.3 Limits

CPA/TCPA assume straight-line constant-speed motion from the last report (both vessels are dead-reckoned to now, §8.1). Class B targets report every 30 s to 3 min, so their predictions are coarser; the report age is exposed so the user can judge. This is an aid, not a collision-avoidance system (documented in the README).

## 9. Entity model

All entities belong to one HA device per config entry ("the boat"), except watched AIS targets, which get one device each. `has_entity_name = True`, translation keys, entry-scoped unique IDs (`{entry_id}_{key}`).

### 9.1 Own-boat sensors

| Key | Name | device_class | Native unit | state_class |
|---|---|---|---|---|
| `sog` | Speed over ground | speed | kn | measurement |
| `cog` | Course over ground | — | ° | measurement_angle |
| `heading` | Heading (true), optional | — | ° | measurement_angle |
| `fix_quality` | GNSS fix | enum | — | — (diagnostic) |
| `satellites` | Satellites in use | — | — | measurement (diagnostic) |
| `hdop` | Horizontal dilution | — | — | measurement (diagnostic) |

`device_tracker.<boat>` exposes own position (GPS source type) with SOG, COG, heading and position-source attributes.

Angles (OD-10, resolved v0.5): verified in HA 2026.2.3, state class `measurement_angle` exists and requires the unit `°`; the only angle device class, `wind_direction`, does not describe COG or heading, so no device class is set. Long-term statistics then use circular means.

Speed: HA does not convert knots automatically under either the metric or the US unit system. The native unit stays kn; a display unit chosen per entity (km/h, mph, m/s) is converted by HA.

### 9.2 Traffic sensors

| Entity | Content |
|---|---|
| `sensor.ais_targets` | Count of live targets. Attribute `targets`: compact list (MMSI, name, class, lat, lon, SOG, COG, distance, CPA, TCPA, age, and from P3 ship type category and length), capped at the 50 nearest (OD-04). Each entry carries `cpa_nm` and `tcpa_min` from the traffic logic (§8.1; `None` when undefined or diverging); distance comes from `geo.py`. The attribute is excluded from the recorder (`_unrecorded_attributes`). The count stays available when own position is unavailable: from the next rebuild of the list (≤ 5 s) distances are `None` and the list is ordered by report age. |
| `sensor.closest_target_distance` | Distance to the nearest target, dead-reckoned to now (device_class distance, native and suggested unit nmi — HA's metric system would otherwise show km —, state_class measurement, dead-band 0.01 NM). Attributes: MMSI, name, bearing, and the target's static data (§9.4). Unavailable without own position or without targets. |
| `sensor.closest_threat_cpa` / `_tcpa` | CPA (nmi, suggested nmi, dead-band 0.01 NM) and TCPA (min, device_class duration, dead-band 0.1 min) of the most urgent threat (§8.2); no state_class, since the underlying target changes. Attributes: MMSI, name, distance, bearing, CPA, TCPA, and the target's static data (§9.4). Unavailable when there is no threat or no own position. A change of target, or of its static data, is always written. |
| `binary_sensor.collision_risk` | On while at least one threat exists, with the anti-flapping latch of §8.2 (device_class safety). **Unavailable** when own position is unavailable: "off" would wrongly reassure. Attributes: `threat_count`, and MMSI, name and static data (§9.4) of the most urgent threat. Designed to drive automations (notification, buzzer, lights); trigger on `to: "on"`. |

### 9.3 Watched targets

`device_tracker.ais_<mmsi>` exists only for MMSIs in the user's watch list (options flow), for example friends' boats or a tender. Never auto-created for every target.

- Each watched MMSI gets its own device, named "AIS <mmsi>" and linked to the boat's device (`via_device`); unique ID `{entry_id}_ais_<mmsi>`.
- State: the target's last reported position (GPS source type, 5 m dead-band). Attributes: MMSI, name, class, SOG, COG, heading, nav status, report age, static data (§9.4), and — when own position is known — distance, bearing, CPA and TCPA (§8.1). Written on a 5 m move or when its static data changes.
- Unavailable while the target is not in the table: not heard yet, or expired (§9.4). A stale position is never shown (NFR-05). Its availability does not depend on own position.
- Removing an MMSI from the list removes its entity and its device when the entry reloads.

### 9.4 AIS target table

Keyed by MMSI. An entry expires after a timeout (options `expiry_class_a`, default 10 min, and `expiry_class_b`, default 15 min, the latter also applied to Class A targets with nav status `at_anchor` or `moored`). Own-ship `VDO` reports and reports from the own MMSI (§7.4) never enter the table. Names are filled from type 19, and from types 5 and 24 from P3; a known name is kept when later reports carry none.

Static data (§7.3) is kept per MMSI apart from the positions and merged into a target when it is read, so data that arrives before the first position report, or a target that expires and returns, keeps its name and type. Type 24 parts A and B are merged field by field. An MMSI's static data is dropped 30 min after its last static report, and at most 2 000 MMSIs are kept, the oldest dropped first (OD-18). Exposed fields: name, call sign, IMO, ship type (code and category), length, beam, draught and destination (OD-20). Wherever a target's name is shown, the static store's name comes first, then the last name a position report (type 19) carried. On the entities, static data is the attributes `ship_type` (category key of §7.3, translated in the UI), `ship_type_code`, `callsign`, `imo`, `length_m`, `beam_m`, `draught_m` and `destination`, `None` when unknown; the compact `targets` list carries only `ship_type` and `length_m`. Static data is part of what those entities compare before writing, so a name or type that arrives after the position is shown at the next tick.

### 9.5 Diagnostics (entity_category: diagnostic)

`sentences_per_min`, `checksum_errors`, `ais_rejected`, `last_sentence_age`, `own_position_source` (GPS / VDO), and a `connected` binary sensor (device class connectivity). `diagnostics.py` exports config (redacted) and counters for bug reports. From P3 the download also counts static reports (`ais_static`) and the MMSIs held in the static store.

- `checksum_errors` and `ais_rejected` are counters (state class `total_increasing`).
- `sentences_per_min` and `last_sentence_age` change constantly; they are disabled by default and written with a dead-band of 1 unit.
- `connected` and the counters stay available while the port is disconnected, so they can report the outage.
- The diagnostics download also carries the hub's other counters (GPS rejects, framing errors, internal errors, reconnects) and the own-boat fields with their source and age.
- Diagnostics redact the serial port path (by-id paths contain the adapter's serial number), `own_mmsi` and own position.

## 10. Runtime behaviour

### 10.1 Availability

Each state field carries its last-update time. Own-boat entities become `unavailable` when their source is older than the staleness timeout (option `stale_timeout`, default 10 s). A port disconnect makes own-boat and traffic entities unavailable immediately; `connected` and the diagnostic counters stay available (§9.5). Entities that depend on own position (closest-target and CPA/TCPA sensors, P2) go unavailable when own position is unavailable (CPA undefined); `sensor.ais_targets` stays available (§9.2).

### 10.2 Throttling and recorder load

- The coordinator runs one tick every `update_interval` (default 1 s). At each tick it expires targets, applies staleness, and each entity decides through its `WriteGate` whether to write. Entities write state at most once per `update_interval`, with the latest value. The tick is internal; HA never polls (`should_poll = False`).
- Dead-bands (0.1 kn, 1°, 0.01 NM, 5 m on own position) suppress insignificant writes. A dead-band compares the new value to the last *written* value, so slow drift is still written once it adds up. Angle dead-bands wrap around (359° → 1° is a 2° change).
- `sensor.ais_targets` attributes are rebuilt at most every 5 s; the README recommends excluding it from the recorder (large attributes).
- `state_class` is set only on true measurements.

### 10.3 Reconnection

Exponential backoff (1, 2, 4 … 60 s max) on serial errors and end-of-stream, logged once per outage (one warning at start, one info line on recovery). The backoff resets after a successful reopen. On first setup with the port unavailable, raise `ConfigEntryNotReady` so HA retries.

## 11. Configuration

### 11.1 Config flow (setup)

1. Boat name.
2. Serial port, discovered from the system (`/dev/serial/by-id/*`, listed in the executor; preferred for stability), manual entry allowed.
3. Baud rate: 38 400 default, 4 800 and custom offered. Nothing in the code assumes a rate (OD-14 stays open until X-09).
4. Validation: open the port and wait up to 5 s for one valid sentence. With no data, a confirmation step shows `no_data` and lets the user save anyway. If the probe shows only garbage, the form shows `wrong_baud` and suggests the other baud rate.
5. The config entry's unique ID is the serial port; configuring the same port twice is aborted.

### 11.2 Options flow

| Option | Default | Phase |
|---|---|---|
| `update_interval` | 1 s | P1 |
| `stale_timeout` | 10 s | P1 |
| `expiry_class_a` | 10 min | P1 |
| `expiry_class_b` (also anchored/moored) | 15 min | P1 |
| `include_own_vdo` | on | P1 |
| `own_mmsi` | empty (learned from VDO) | P1 |
| `cpa_threshold` | 0.5 NM (0.05–5, step 0.05) | P2 |
| `tcpa_threshold` | 15 min (1–60) | P2 |
| `exclude_stationary` (anchored/moored Class A below 0.5 kn) | on | P2 |
| `watch_list` (9-digit MMSIs, duplicates dropped) | empty | P2 |

Changing an option reloads the entry.

## 12. Quality, packaging, security

- **Tests:** defined in HA-SAIL-TEST-001 (X-10): unit (pure Python, no HA), functional (HA test harness with a fake serial transport), end-to-end (replay bench, in port, under way). NFR traceability and CI gates are specified there.
- **CI:** GitHub Actions running tests, `ruff`, `mypy`, `hassfest`, HACS validation.
- **Packaging:** `manifest.json` with `iot_class: local_push`, `integration_type: hub`, `config_flow: true`, explicit `requirements` (`pyserial-asyncio-fast`). Installed via HACS custom repository. The `nmea/` package can later move to PyPI (HA best practice).
- **Minimum Home Assistant version:** 2026.2.0 (OD-06, resolved v0.5), declared in `hacs.json`. Functional tests run against HA 2026.2.3 via `pytest-homeassistant-custom-component==0.13.316`. HA 2026.x requires Python 3.13; pure modules stay compatible with Python 3.12.
- **Workflow:** GitHub issue → PR → CI → review → versioned release.
- **Security:** no network listener, no credentials, no outbound traffic. Serial input treated as untrusted: bounded line length, strict parsing, exceptions contained per line.
- **Licensing:** Apache-2.0 (OD-11). Clean-room rule from §3.1 applies to all contributors.

## 13. Roadmap

| Phase | Content | Exit criterion |
|---|---|---|
| P0 | AIS decoder (C-03) | **Done** — X-02, 39 tests green |
| P1 | Raw capture (X-09); transport, GPS parsers, coordinator, own-boat entities, AIS target table, `sensor.ais_targets`, diagnostics | Capture replayed; own-boat entities match the receiver/chartplotter display |
| P2 | Traffic logic: CPA/TCPA, closest target/threat, `binary_sensor.collision_risk`, watched-target trackers | Scenario tests green; on-water check against a chartplotter's AIS page |
| P3 | AIS static data (types 5, 24): names, ship type, dimensions; Lovelace map card configuration (built-in map card: own boat and watched targets, OD-19) | U-AIS static tests, U-STA and the F-TRF static checks green; on board, names and ship types of 5 targets match the chartplotter (E-12); the receiver capture (#2) decodes its type 5/24 lines without rejects |
| P4 | Optional additional sources if instruments are added (wind, depth, log) and the performance layer (true wind, VMG, polars), via a second port or TCP | Requires new hardware; re-opens §2.2 |

## 14. Open decisions

| ID | Question | Options | Needed by |
|---|---|---|---|
| ~~OD-01~~ | ~~Integration domain name~~ | **Resolved v0.4:** Vigie / `vigie` | — |
| ~~OD-02~~ | ~~Instruments and AIS on one port or several?~~ | **Resolved v0.2:** one port, AIS receiver only (§3.3) | — |
| ~~OD-03~~ | ~~GPS parsing: own parsers or `pynmea2` (MIT)~~ | **Resolved v0.5:** own parsers (five sentences, typed, no dependency) (§7.1) | — |
| ~~OD-04~~ | ~~AIS exposure model~~ | **Resolved v0.7:** aggregate sensor + watch-list trackers + threat entities; no `geo_location` platform (one entity per target would flood the registry and recorder) | — |
| ~~OD-06~~ | ~~Minimum supported HA version~~ | **Resolved v0.5:** HA 2026.2.0; tests pinned to phcc 0.13.316 / HA 2026.2.3 (§12) | — |
| ~~OD-07~~ | ~~Own-boat source priority~~ | **Resolved v0.5:** GPS first, VDO fallback when GPS is stale; `include_own_vdo` option only (§7.4) | — |
| ~~OD-08~~ | ~~Instrument true wind vs computed~~ | **Withdrawn v0.2:** no wind source (§2.2) | — |
| ~~OD-10~~ | ~~Angle entities' device_class/state_class~~ | **Resolved v0.5:** no device class, state class `measurement_angle`, unit ° (§9.1) | — |
| ~~OD-11~~ | ~~License of this project~~ | **Resolved v0.4:** Apache-2.0 | — |
| ~~OD-12~~ | ~~Replay tool for development~~ | **Resolved v0.5:** external replay tool (`tests/tools/replay.py`, own pseudo-TTY or an existing device; `socat` optional); no file source in the integration (TEST §5.1) | — |
| OD-13 | Receiver type: receive-only or Class B transponder? | Determines whether `!AIVDO` exists; design handles both (§7.4) | P1 (from X-09, issue #2) |
| ~~OD-15~~ | ~~`collision_risk` anti-flapping~~ | **Resolved v0.7:** latch — on at the first threat; off after 60 s without a threat, or at once when every threat of the episode has passed its CPA (§8.2) | — |
| ~~OD-16~~ | ~~Positions used for CPA/TCPA~~ | **Resolved v0.7:** dead-reckon own boat and targets from their report times to now (§8.1, §8.3) | — |
| ~~OD-17~~ | ~~Ship type exposure~~ | **Resolved v0.10:** ITU code plus a category key, translated in the UI (§7.3) | — |
| ~~OD-18~~ | ~~Lifetime of static data~~ | **Resolved v0.10:** kept per MMSI 30 min after its last static report, at most 2 000 MMSIs, apart from the target table (§9.4) | — |
| ~~OD-19~~ | ~~Map card~~ | **Resolved v0.10:** document a built-in map card configuration (own boat, watched targets); the full picture stays in the `targets` attribute; a custom card (separate HACS plugin) is left for after v1 (§13) | — |
| ~~OD-20~~ | ~~Static fields exposed~~ | **Resolved v0.10:** name, call sign, IMO, ship type, length, beam, draught, destination; no ETA (no year, often stale), no EPFD (§7.3, §9.4) | — |
| OD-14 | Serial baud rate | 38 400 (typical AIS) vs 4 800; confirmed by X-09 and by the current smart0183serial setting. Baud rate is configurable, the probe suggests the other rate (§11.1) | P1 (from X-09, issue #2) |

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
| X-09 | Raw capture of the AIS receiver's serial output (to be produced; ≥ 15 min, ideally in port and under way; tracked in issue #2) | §3.3, §7.2, OD-13, OD-14, tests |
| X-10 | HA-SAIL-TEST-001 — Test protocol (unit, functional, end-to-end) | §12, §13 |
| X-11 | Repository `ha-vigie` — bootstrap kit (skeleton, CI, GitHub setup script) | §5.3, §12 |
