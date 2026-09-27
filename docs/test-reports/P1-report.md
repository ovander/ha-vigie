# P1 report — Base (HA-SAIL-TEST-001 §9)

| Item | Value |
|---|---|
| Phase | P1 Base (SPEC HA-SAIL-SPEC-001 v0.6 §13) |
| Documents | SPEC v0.6, TEST v0.10 |
| Code state | `main` at `76bad9f` (all P1 work packages merged) |
| Release | none yet — E-01 needs a release tag (e.g. `v0.1.0-beta.1`) |
| CI | `lint`, `unit`, `hassfest`, `hacs` green on every P1 PR and on `main` |
| Nightly `perf` | first run pending (workflow merged in #18); a release needs it green |
| Automated tests | 278 passed, 1 skipped (U-GPS-08, #2), 3 `perf` tests run separately |
| Coverage | 98.8 % of the pure modules (`nmea/`, `state.py`, `geo.py`, `hub.py`); gate ≥ 90 % |
| Exit criterion | **Not met yet**: E-1 and E-2 runs below, and the D-05 replay (#2) |

## 1. What was built

| PR | Issue | Content |
|---|---|---|
| #4 | #3 | P1 decisions recorded (SPEC v0.5, TEST v0.3) |
| #6 | #5 | WP1: `nmea/sentence.py` (framing, checksum, tag blocks, fields) and `nmea/parsers.py` (RMC, GGA, VTG, GSA, HDT) |
| #8 | #7 | WP2: `state.py` (own-boat state with GPS→VDO fallback, AIS target table, throttle/dead-band) and `geo.py` |
| #10 | #9 | WP3: `hub.py` serial reader: framing, routing, counters, 1→60 s reconnect backoff, 5 s probe; D-04 fixture |
| #12 | #11 | Fix: AIS decoder rejects payload armoring characters 0x58–0x5F |
| #14 | #13 | WP4: setup/unload, coordinator, config flow (port discovery, probe), options flow |
| #16 | #15 | WP5: 14 entities per boat, diagnostics download, English/French names; D-08 fixture; F-PERF tests |
| #18 | #17 | WP6: scenario, replay and capture tools; nightly `perf` workflow; E-1 recipe in `CONTRIBUTING.md` |

Entities per boat: SOG, COG, heading, GNSS fix, satellites, HDOP, `device_tracker.<boat>`,
`sensor.ais_targets` (50 nearest in an unrecorded attribute), sentences per minute and last
sentence age (disabled by default), checksum errors, rejected AIS messages, position source,
`connected`.

## 2. Test status (TEST §9, row P1)

| Group | Status |
|---|---|
| U-NMEA-01…06, U-GPS-01…07, U-COO-01…06, U-TRF-12 | Done |
| U-GPS-08, U-AIS-13 | Pending on the receiver capture (#2) |
| F-LIFE-01…08, F-HUB-01…05, F-ENT-01…07 | Done; F-HUB-01 and F-ENT-01 on synthetic data until #2 |
| F-PERF-01…03 | Done locally (`pytest -m perf`); F-PERF-02 baseline on synthetic data until #2 |
| E-1 (E-01, E-03…E-06) | Pre-run in the official HA container passed (§5.1: E-01 without HACS, E-04, E-05 on x86, E-06; E-03 partial); formal run to do — §5.2 |
| E-2 (E-10, E-11, E-13) | To run on board — §6 |

F-PERF-02 synthetic baseline (10 min, 1 RMC + 50 AIS per second): 600 SOG writes, 300 COG
writes, 125 `sensor.ais_targets` writes; no entity wrote twice within 1 s.

## 3. Decisions taken

| Item | Decision |
|---|---|
| OD-03 | Own GPS parsers, no third-party dependency |
| OD-06 | Minimum HA 2026.2.0; tests on HA 2026.2.3 (`pytest-homeassistant-custom-component==0.13.316`) |
| OD-07 | GPS first, VDO fallback per field when GPS is stale; `include_own_vdo` option |
| OD-10 | COG/heading: no device class, state class `measurement_angle`, unit ° |
| OD-12, TP-01, TP-02 | Own replay tool with its own PTY (socat optional); E-1 on HA Container on Linux; E-01 on HA OS via a null-modem pair of USB-serial adapters |
| Smaller choices | Two expiry options (Class A; Class B and anchored/moored); optional `own_mmsi`; 5 m position dead-band; noisy diagnostics disabled by default; target list excluded from the recorder |

Still open: OD-13 (VDO present?) and OD-14 (baud rate), both settled by #2, with the code
neutral to either answer; TP-03 (anonymisation) before committing D-05/D-06; TP-04 for P2.

## 4. Deviations from SPEC / TEST / CLAUDE.md

| # | Deviation | Where recorded |
|---|---|---|
| 1 | Work pushed from the session branch `claude/stoic-euler-vgqeyf` (and `fix/ais-armoring`) instead of `feat/…`; GitHub API used instead of `gh` | PR descriptions |
| 2 | F-HUB-01/02/04/05 run against the hub with the fake transport, not inside the HA harness (approved); F-HUB-03 also checked on entities | TEST v0.3 §4.2 |
| 3 | `sensor.ais_targets` distances become `None` at the next list rebuild, up to 5 s after own position goes stale | SPEC v0.6 §9.2, TEST v0.9 F-ENT-04 |
| 4 | Config flow: wrong baud rate gives a hint naming the other rate, without a "save anyway" | SPEC §11.1 (compliant) |
| 5 | Throttle = coordinator tick once per interval + per-entity dead-bands; the tracker writes only on ≥ 5 m moves, so SOG/COG attributes on it can lag while at anchor (the SOG/COG sensors update) | SPEC v0.5 §10.2 |
| 6 | `mypy --strict` covers the pure modules only; HA source and HA-side modules skipped | `pyproject.toml` comments |
| 7 | P0 decoder changed once (#12, at the owner's request) | TEST v0.7 |
| 8 | Two-digit RMC years read as 20yy | SPEC v0.5 §7.2 |

## 5. E-1 replay bench (TEST §5.1)

### 5.1 Pre-run in a sandbox container (#21)

Not the formal E-1: an x86 sandbox, no HACS, no Raspberry Pi. It exercises the same chain
(PTY → serial library → integration → entities) in the official image, before the bench.

| Item | Value |
|---|---|
| Date | 2026-09-27, 17:52–17:57 UTC |
| Home Assistant | official image `homeassistant/home-assistant:2026.2.3` (Docker Hub), `default_config`, `--network host` |
| Host | x86 Linux sandbox, 4 vCPU, 16 GB |
| Vigie | `main` at `76bad9f`, installed by unpacking `vigie.zip` built as `release.yml` does (manifest stamped `0.1.0-bench`) |
| Feed | `tests.tools.replay --pty` on the host; link folder and `/dev/pts` bind-mounted, `--device-cgroup-rule='c 136:* rmw'` |
| Data | `scenario --preset head-on` (1 RMC/s own boat at 6 kn 000°, 1 target 2 NM ahead at 6 kn 180°), then D-08 `burst_60s.nmea` |
| Driver | HA REST API (onboarding, config flow, states, diagnostics), as the UI does |

| ID | Result | Observed |
|---|---|---|
| E-01 | Pass (without HACS) | Loaded as a custom integration (only HA's standard "not tested by Home Assistant" warning). Config flow: port list empty in the container (no `/dev/serial/by-id`), default `/dev/ttyUSB0` offered; entry "Garnet" created in 0.7 s, the probe finding a valid sentence at once. |
| Entities | Pass | SOG 6.0 kn, COG 0°, `device_tracker.garnet` moving north with `sog`/`cog`/`position_source: gps`, `ais_targets` = 1 at 1.86 NM and closing. GNSS fix, satellites, HDOP unavailable (no GGA in the scenario) and heading unavailable (no HDT, F-ENT-05), as expected. |
| E-03 | Partial | About 3 min of clean running; full-length run left to the bench (D-06 or a long scenario). |
| E-04 | Pass | Feed killed at 17:53:22: within a second `connected` off, own-boat and traffic entities unavailable, error counters still available, one WARNING line (the PTY hang-up is reported by the serial library as a read error). Feed restarted after 30 s; reconnected at the 6th attempt (17:54:25, +63 s, as the backoff schedule says) with one INFO line; no HA restart. |
| E-05 | Pass on x86 (Pi still to do) | D-08 at real speed (51 sentences/s, 60 s): container CPU ≈ 2 %, no slow-callback or blocking-call warnings, 0 checksum/framing/rejected/internal errors, 81 targets tracked. |
| E-06 | Pass | `docker restart` during the replay: HA back in 4 s, same 12 visible entity IDs; registry holds 14 unique Vigie entities (the 2 off-by-default diagnostics disabled) on one device "Garnet"; HA shut down with exit code 0. |
| Diagnostics | Pass | Download works; serial port redacted; counters present. |

Other observations:

- The only ERROR in the HA log came from HA core's alerts fetch (`alerts.home-assistant.io`,
  no internet in the sandbox), not from Vigie.
- Sentences written while the port is closed are lost: when the feed was switched, about 45
  AIS lines sent before Vigie reopened the port never arrived. Expected, as with a real
  receiver.
- The recipe with `--device /dev/pts/N` breaks on a replay restart; `CONTRIBUTING.md` now uses
  the bind-mount recipe above.
- The GHCR image could not be pulled in the sandbox (blob host blocked by its proxy); Docker
  Hub `homeassistant/home-assistant` is the same image.

### 5.2 Formal E-1 run

Setup: Linux host with Home Assistant **Container** (Raspberry Pi with Raspberry Pi OS for
E-05); repository checked out, `pip install -r requirements_test.txt`. Details in
`CONTRIBUTING.md`.

```bash
python -m tests.tools.scenario --preset head-on -o head-on.nmea
python -m tests.tools.scenario --preset crossing -o crossing.nmea
python -m tests.tools.scenario my-traffic.json --duration 3600 -o long.nmea  # E-03 stand-in until D-06 (#2)
python -m tests.tools.replay head-on.nmea --pty /tmp/ttyAIS --loop
# container: bind-mount the link folder and /dev/pts, --device-cgroup-rule='c 136:* rmw' (CONTRIBUTING.md)
```

| Run | Date | Host / HA version | Tester |
|---|---|---|---|
| | | | |

| ID | Steps | Expected | Result | Notes |
|---|---|---|---|---|
| E-01 | Install from the release tag via HACS custom repository; add Vigie on `/dev/ttyAIS` at 38 400 | Probe passes, entry created, no manual file copy | | |
| E-03 | Replay a long file for its full duration (D-06 when #2 exists; `long.nmea` until then) | No error in the HA log; own track on the map/logbook matches the file | | |
| E-04 | Ctrl-C the replay, wait 30 s, restart it on the same device path | `connected` off and entities unavailable during the gap; recovery without HA restart; one warning and one "Reconnected" line in the log | | |
| E-05 | On the Pi: replay `tests/fixtures/burst_60s.nmea` at `--speed 1` | No event-loop or "took too long" warnings; CPU noted; lag < 100 ms (F-PERF-01) | | CPU: |
| E-06 | Restart HA during a replay | Integration reloads; same entity IDs; no duplicate device | | |
| (P2 prep) | Head-on replay | `sensor.ais_targets` distance of the target falls from ≈ 2 NM toward 0 over 10 min | | E-02 proper needs P2 |

## 6. E-2 on board, in port (TEST §5.2)

Prerequisite: `ha-smart0183serial` removed (SPEC §3.1). Record the capture for #2 with
`python -m tests.tools.capture --port /dev/serial/by-id/… --baud 38400 --duration 900` before
installing Vigie (only one program can own the port).

| Run | Date | Place / conditions | Receiver model, baud | Tester |
|---|---|---|---|---|
| | | | | |

| ID | Steps | Expected | Result | Notes |
|---|---|---|---|---|
| E-10 | Configure on `/dev/serial/by-id/…` of the receiver | Valid data within 5 s at the confirmed baud rate (OD-14) | | Baud: / VDO seen (OD-13): |
| E-11 | Compare own position with the chartplotter/receiver | Within 20 m; SOG ≈ 0; COG noise acceptable | | |
| E-13 | Unplug USB 10 s, replug | Automatic recovery; `connected` shows the outage | | |

## 7. Open items

- #2 — receiver capture: U-GPS-08, U-AIS-13, F-HUB-01 / F-ENT-01 / F-PERF-02 on real data,
  OD-13, OD-14, SPEC §7.2 sentence list, P1 exit criterion (D-05 replay matches the display).
- First nightly `perf` run on `main`.
- Formal E-1 on the bench, including E-05 on the Raspberry Pi and a full-length E-03.
- Release tag for E-01 (owner's call).
