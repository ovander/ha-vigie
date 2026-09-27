# Changelog

All notable changes to this project are documented here. Format: Keep a Changelog;
versioning: SemVer.

## [Unreleased]

### Changed
- Docs: SPEC v0.5 and TEST v0.3 record the P1 decisions (#3). OD-03 own GPS parsers; OD-06
  minimum Home Assistant 2026.2.0; OD-07 GPS first, VDO fallback, `include_own_vdo` option;
  OD-10 COG/heading without device class, state class `measurement_angle`; OD-12, TP-01 and
  TP-02 external replay tool and E-1 on HA Container. Pure `state.py`, `geo.py` and HA-free
  `hub.py`; availability, dead-band, config-flow and options details clarified; F-ENT-02
  corrected (knots are not auto-converted). Status columns added to the TEST tables.
  OD-13 and OD-14 stay open pending the receiver capture (#2).

### Added
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

### Fixed
- AIS decoder rejects payload armoring characters 0x58–0x5F (`X`…`_`), which the AIVDM
  specification does not allow; they were decoded as six-bit values 40–47 (#11).
