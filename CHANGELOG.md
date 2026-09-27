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
