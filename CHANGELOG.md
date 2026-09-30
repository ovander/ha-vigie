# Changelog

All notable changes to this project are documented here. Format: Keep a Changelog;
versioning: SemVer.

## [Unreleased]

### Fixed
- README install section (#45): turn on beta versions in HACS (the only release is a
  pre-release), hard-reload the browser after the restart, minimum Home Assistant version,
  and what to check when Vigie does not appear in "Add integration".

## [0.1.0-beta.1] - 2026-09-28

First beta, the release candidate for the bench and on-board checks: serial AIS receiver,
own boat, AIS traffic, CPA/TCPA collision alerts, watch list and AIS static data (phases
P1–P3). Tested on synthetic data only; see `docs/test-reports/`.

### Added
- P3 bench material (#38): README map card configuration (own boat and watched targets)
  and ship-details table, both checked against real entities by tests; scenario targets
  can send AIS static data (type 5 / type 24), new preset `named-traffic`; P3 report
  template in `docs/test-reports/P3-report.md`. TEST v0.18.
  P3 bench pre-run in the Home Assistant container recorded in the report; the README map
  card labels watched targets with their ship name.
- Static data on the entities (#36): ship type (translated category and ITU code), call
  sign, IMO, length, beam, draught and destination on `collision_risk`, the closest
  target/threat sensors and the watch-list trackers; ship type and length in the
  `sensor.ais_targets` list. A name or type that arrives after the position shows at the
  next tick. F-TRF-09…11.
- AIS static data store (#34): names from types 5 and 24 now show in `collision_risk`, the
  `sensor.ais_targets` list and the watch-list trackers, whether the static report comes
  before or after the first position. Static data is kept per MMSI for 30 min after its
  last report (at most 2 000 MMSIs); diagnostics count static reports. U-STA-01…07, F-TRF-08.
- AIS static data decoding (#32): types 5 and 24 (parts A and B, auxiliary craft) and the
  static fields of type 19 — name, call sign, IMO, ship type with a category key,
  dimensions, draught, destination. Not shown in entities yet (P3 WP12/WP13). Records SPEC
  decisions OD-17…OD-20. U-AIS-15…22.
- P2 bench material (#29): README collision-alert automation (checked by a test that loads the
  README's YAML into Home Assistant), recorder and safety notes; scenario presets for every
  TEST §3.4 geometry with `--list`; P2 report template with the E-02, E-12, E-16 and E-3
  checklists in `docs/test-reports/P2-report.md`. TEST v0.14.
  E-02 pre-run in the Home Assistant container recorded in the report; the README alert
  message now rounds CPA/TCPA to the sensors' display precision.
- Watch-list trackers (#27): `device_tracker.ais_<mmsi>` for each MMSI in the new `watch_list`
  option, on its own device linked to the boat, unavailable while the target is not heard;
  removing an MMSI removes its tracker and device. F-TRF-05.
- Traffic entities (#25): `binary_sensor.collision_risk` (safety, anti-flapping latch,
  unavailable without own position), `sensor.closest_target_distance`,
  `sensor.closest_threat_cpa` and `sensor.closest_threat_tcpa` (nautical miles kept on metric
  systems), CPA/TCPA in the `sensor.ais_targets` list; options for the CPA and TCPA thresholds
  and the anchored/moored exclusion. F-TRF-01…04, 06, 07.
- Traffic logic (#23): `traffic.py` computes distance, bearing, CPA and TCPA on a local plane
  after dead-reckoning both vessels to now, classifies threats (thresholds, stationary Class A
  excluded), picks the most urgent threat, and latches the collision risk against flapping.
  Records SPEC decisions OD-04, OD-15, OD-16. U-TRF-01…11, 13, 14, 15.
- P1 report and E-1/E-2 checklists in `docs/test-reports/P1-report.md` (#19).
- Container pre-run of the E-1 checklist recorded in the P1 report; E-1 container recipe in
  `CONTRIBUTING.md` now bind-mounts `/dev/pts` so replay restarts keep working (#21).
- Test tooling (#17): scenario generator (D-07, head-on and crossing presets), timed replay
  into its own pseudo-terminal or a serial device, timestamped receiver capture (X-09), E-1
  bench recipe in `CONTRIBUTING.md`; nightly workflow running the F-PERF tests.
- Entities and diagnostics (#15): own-boat sensors (SOG, COG, heading, GNSS fix, satellites,
  HDOP), `device_tracker.<boat>` with SOG/COG/heading attributes and a 5 m dead-band,
  `sensor.ais_targets` with the 50 nearest targets (rebuilt at most every 5 s, not recorded),
  diagnostic sensors (sentence rate and age disabled by default, checksum errors, rejected AIS,
  position source) and the `connected` binary sensor; availability follows the connection and
  the staleness timeout; writes once per tick with dead-bands; diagnostics download with
  redaction; English and French names. D-08 burst fixture and nightly-only F-PERF tests.
- Home Assistant wiring (#13): `coordinator.py` owns the hub and the domain state, pushes
  updates on an internal tick and at once on connection changes; setup raises
  `ConfigEntryNotReady` when the port is missing, unload stops the reader and closes the port.
  Config flow lists `/dev/serial/by-id/*`, accepts a manual port and a custom baud rate,
  probes for 5 s (`no_data` confirmation, `wrong_baud` hint, `cannot_connect`); options flow
  for update interval, staleness, Class A/B expiry, VDO use and own MMSI, reloading the
  entry. English and French strings. Minimum Home Assistant 2026.2.0 in `hacs.json`.
  F-LIFE-01…05, 07.
- Transport hub (#9): `hub.py` (pure asyncio) reads the serial port through an injectable
  transport, frames lines (1 KiB cap, 82-char sentences), routes `$` to the GPS parsers and
  `!` to the AIS decoder after a checksum pre-check, strips tag blocks, contains per-line
  errors, keeps diagnostics counters, reconnects with 1 → 60 s backoff (one warning per
  outage, one info line on recovery) and offers a 5 s probe for the config flow. D-04
  malformed corpus fixture. F-HUB-01, 02, 04, 05.
- Domain core (#7): `state.py` (`OwnBoatState` with per-field timestamp and source, GPS
  first and VDO fallback, own MMSI learned or configured; `AisTargetTable` with class-dependent
  expiry, own-MMSI exclusion and nearest-first listing; `WriteGate` throttle and dead-band,
  circular for angles, metres for position) and `geo.py` (distance, bearing). U-COO-01…06 and
  U-TRF-12.
- GPS sentence layer (#5): `nmea/sentence.py` (framing limits, checksum, tag block, talker
  and field split, empty fields → `None`) and `nmea/parsers.py` (RMC, GGA, VTG, GSA, HDT as
  typed dataclasses, units normalised, RMC void not applied, `GpsParser` with counters).
  U-NMEA-01…06 and U-GPS-01…07; U-GPS-08 pending on the receiver capture (#2).
- Repository bootstrap: integration skeleton (`vigie` domain, config flow), CI (lint, unit,
  hassfest, HACS), release workflow, issue templates, documentation.
- AIS decoder (`nmea/ais_decoder.py`): Class A types 1/2/3 and Class B types 18/19,
  checksum and length validation, multi-fragment reassembly, tag blocks, own-ship `VDO`
  flag, injectable clock. 39 tests, 98.5 % coverage.

### Changed
- Docs: SPEC v0.5 and TEST v0.3 record the P1 decisions (#3). OD-03 own GPS parsers; OD-06
  minimum Home Assistant 2026.2.0; OD-07 GPS first, VDO fallback, `include_own_vdo` option;
  OD-10 COG/heading without device class, state class `measurement_angle`; OD-12, TP-01 and
  TP-02 external replay tool and E-1 on HA Container. Pure `state.py`, `geo.py` and HA-free
  `hub.py`; availability, dead-band, config-flow and options details clarified; F-ENT-02
  corrected (knots are not auto-converted). Status columns added to the TEST tables.
  OD-13 and OD-14 stay open pending the receiver capture (#2).

### Fixed
- Attribute labels (#41): every entity attribute has an English and French label, and
  navigation status and position source values are translated (they showed raw keys).
- Nightly report: the F-PERF-02 write baseline was dropped from the junit XML (#25).
- AIS decoder rejects payload armoring characters 0x58–0x5F (`X`…`_`), which the AIVDM
  specification does not allow; they were decoded as six-bit values 40–47 (#11).

[Unreleased]: https://github.com/ovander/ha-vigie/compare/v0.1.0-beta.1...HEAD
[0.1.0-beta.1]: https://github.com/ovander/ha-vigie/releases/tag/v0.1.0-beta.1
