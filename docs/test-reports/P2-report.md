# P2 report — Traffic (HA-SAIL-TEST-001 §9)

Template with the automated results filled in. The E-stage tables are filled in on the
bench and on board; the exit criterion is assessed once they are.

| Item | Value |
|---|---|
| Phase | P2 Traffic (SPEC HA-SAIL-SPEC-001 v0.9 §13) |
| Documents | SPEC v0.9, TEST v0.14 |
| Code state | `main` after the WP10 merge (all P2 work packages merged) — fill in the commit |
| Release | none yet — E-02 can run from `main`; a beta tag is the owner's call |
| CI | `lint`, `unit`, `hassfest`, `hacs` green on every P2 PR |
| Nightly `perf` | first run pending |
| Automated tests | 360 passed, 1 skipped (U-GPS-08, #2), 3 `perf` tests run separately |
| Coverage | 98.9 % of the pure modules (`nmea/`, `state.py`, `geo.py`, `hub.py`, `traffic.py`; `traffic.py` 100 %); gate ≥ 90 % |
| Exit criterion | **Not met yet**: E-02, E-12, E-16 and E-3 below; E-21 needs at least 3 real encounters consistent with the chartplotter |

## 1. What was built

| PR | Issue | Content |
|---|---|---|
| #24 | #23 | WP7: `traffic.py` — local-plane CPA/TCPA with dead reckoning, threat classification (stationary Class A excluded by option), closest-threat selection, risk latch |
| #26 | #25 | WP8: `binary_sensor.collision_risk`, closest target distance, closest threat CPA/TCPA sensors; CPA/TCPA in the `targets` list; threshold options |
| #28 | #27 | WP9: watch-list `device_tracker.ais_<mmsi>` on their own devices, `watch_list` option |
| (this) | #29 | WP10: README automation example (tested as published), scenario presets for every TEST §3.4 geometry, this report |

## 2. Test status (TEST §9, row P2)

| Group | Status |
|---|---|
| U-TRF-01…15 | Done (hand values of TEST §3.4) |
| F-TRF-01…07 | Done |
| README automation | Done — the YAML block of `README.md` is loaded into the HA harness and sends one notification with CPA/TCPA on the U-TRF-03 crossing |
| Scenario presets | Done — each preset, decoded as the receiver's stream, gives its U-TRF CPA/TCPA/threat |
| E-02 | To run on the bench — §5 |
| E-12, E-16 | To run on board, in port — §6 |
| E-3 (E-20…E-23) | To run under way — §7 |

## 3. Decisions taken

| Item | Decision |
|---|---|
| OD-04 | Aggregate `ais_targets` sensor + watch-list trackers + threat entities; no `geo_location` platform |
| OD-15 | Risk latch: on at the first threat; off after 60 s without a threat, or at once when every threat of the episode has passed |
| OD-16 | Own boat and targets dead-reckoned from their report times to now |
| Availability | Traffic entities, `collision_risk` included, are unavailable while own position is unknown |
| TP-04 | **Open** — the E-21 reference (chartplotter AIS page, or a phone app fed by the same data) is to be confirmed by the owner |

## 4. Deviations from SPEC / TEST / CLAUDE.md

| # | Deviation | Where recorded |
|---|---|---|
| 1 | Issues and PRs created with the GitHub API instead of `gh` | PR descriptions |
| 2 | The README automation has no `from: "off"`: an alert is repeated when own position returns during an encounter, so that the first alert after start-up (`unavailable` → `on`) is never missed | README, this report |

## 5. E-02 replay bench (TEST §5.1)

Same bench as E-1 (`CONTRIBUTING.md`, P1 report §5). Before the run: a phone with the
Home Assistant companion app, and the README automation installed with the phone's notify
service. `python -m tests.tools.scenario --list` prints the expected values.

```bash
for p in head-on crossing clear-crossing not-urgent anchored multi-target; do
  python -m tests.tools.scenario --preset $p -o $p.nmea
done
python -m tests.tools.replay head-on.nmea --pty /srv/vigie-bench/ttyAIS
```

Replay each file once at real speed (no `--loop`: a loop makes the targets jump back to
their start). Read the
values in the first minute; tolerance CPA ± 0.02 NM, TCPA ± 0.2 min (TCPA falls by one
minute per minute of replay).

| Run | Date | Host / HA version | Vigie commit | Tester |
|---|---|---|---|---|
| | | | | |

| Preset | Expected (TEST §3.4, default thresholds) | CPA / TCPA read | `collision_risk` | Phone notification | Result |
|---|---|---|---|---|---|
| `head-on` (U-TRF-01) | CPA 0.00 NM, TCPA 10.0 min; on at once, off when passed (≈ 10 min) | | | | |
| `crossing` (U-TRF-03) | CPA 0.45 NM, TCPA 4.0 min; on at once, off when passed (≈ 4 min) | | | | |
| `clear-crossing` (U-TRF-02) | CPA 0.71 NM, TCPA 5.0 min; stays off | | | none expected | |
| `not-urgent` (U-TRF-05) | CPA 0.26 NM, TCPA 21.6 min; off, then on ≈ 6.6 min in, off when passed (≈ 21.6 min) | | | | |
| `anchored` (U-TRF-08) | CPA 0.00 NM, TCPA 4.0 min; stays off (exclusion on); with *Ignore anchored and moored targets* off, on | | | | |
| `multi-target` (U-TRF-11) | Closest threat 235000002 (crossing), then 235000001 (head-on), then 235000004 (overtaking, from ≈ 15 min); 235000003 never a threat; one notification per episode | | | | |

Also check on the dashboard: `sensor.<boat>_ais_targets` lists the targets with
`cpa_nm`/`tcpa_min`; the map card shows them; the closest-target distance falls as expected.

## 6. E-2 on board, in port (TEST §5.2)

| Run | Date | Place / conditions | Receiver model, baud | Tester |
|---|---|---|---|---|
| | | | | |

| ID | Steps | Expected | Result | Notes |
|---|---|---|---|---|
| E-12 | Compare `sensor.<boat>_ais_targets` and 5 MMSIs of its `targets` list with the chartplotter's AIS list (a public AIS site for cross-check only) | Count and the 5 MMSIs match | | Count Vigie / reference: |
| E-16 | 24 h soak in port; note HA memory (e.g. `docker stats` or the System Monitor integration) after 1 h and at 24 h; read the log and the diagnostics download at the end | Memory growth < 10 % after warm-up; no error flood; target count stable (no steady growth) | | Memory 1 h / 24 h: · Targets 1 h / 24 h: |

## 7. E-3 under way (TEST §5.3)

Daylight, good visibility, a crew member responsible for navigation. **No navigation decision
is made from Vigie during the tests.** E-21 reference: see TP-04 (§3).

| Run | Date | Area / conditions | Reference used (TP-04) | Crew on watch |
|---|---|---|---|---|
| | | | | |

| ID | Steps | Expected | Result | Notes |
|---|---|---|---|---|
| E-20 | Compare own SOG/COG with the chartplotter over 30 min | SOG ± 0.2 kn; COG ± 5° when SOG > 2 kn | | |
| E-21 | At least 3 crossing encounters with real traffic (opportunistic); for each, CPA/TCPA from Vigie and from the reference at the same moment | ± 0.1 NM, ± 1 min | | See the table below |
| E-22 | `collision_risk` with a real target meeting the thresholds | Fires; the alert reaches the phone; clears after passage | | |
| E-23 | Record a capture during the sail (`python -m tests.tools.capture`) | Added to the fixtures after anonymisation (TP-03) as a regression dataset | | File: |

E-21 encounters:

| # | Time (UTC) | MMSI / name | Vigie CPA / TCPA | Reference CPA / TCPA | Within tolerance |
|---|---|---|---|---|---|
| 1 | | | | | |
| 2 | | | | | |
| 3 | | | | | |

## 8. Open items

- TP-04 — reference for E-21 (owner).
- #2 — receiver capture: also the regression data for E-23.
- First nightly `perf` run on `main`.
- E-02 on the bench, E-12/E-16 in port, E-3 under way.
