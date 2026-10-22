# P5 report — Anchor watch (HA-SAIL-TEST-001 §9)

Template with the automated results and the bench pre-run filled in. The formal bench and
on-board tables are filled in when the checks are run; the exit criterion is assessed once
they are.

| Item | Value |
|---|---|
| Phase | P5 Anchor watch (SPEC HA-SAIL-SPEC-001 v0.18 §13) |
| Documents | SPEC v0.18, TEST v0.23, NFL-TRACK-API-001 v0.2.0 (X-12, not part of P5) |
| Code state | `main` at `3af0d5b` (WP15–WP18 and the 0.2.0-beta.1 changelog merged) |
| Release | [`v0.2.0-beta.1`](https://github.com/ovander/ha-vigie/releases/tag/v0.2.0-beta.1), pre-release, 2026-10-22, tag on `3af0d5b`; `vigie.zip` checked (manifest `0.2.0-beta.1`, anchor files, EN/FR translations). Run the formal checks below on this release |
| CI | `lint`, `unit`, `hassfest`, `hacs` green on every P5 PR; nightly `perf` green on `3af0d5b` (2026-10-21 and 2026-10-22), release workflow green |
| Automated tests | 517 passed, 1 skipped (U-GPS-08, #2), 3 `perf` tests run separately |
| Coverage | 99 % of the pure modules (`nmea/`, `state.py`, `geo.py`, `hub.py`, `traffic.py`, `anchor.py`; `anchor.py` 100 %); gate ≥ 90 % |
| Exit criterion | **Not met yet**: the formal bench check E-07 (§5.2), E-17 in port (§6) and E-24 at an anchorage (§7) |

## 1. What was built

| PR | Issue | Content |
|---|---|---|
| #48 | #47 | WP15: anchor watch specified (SPEC §8.4, §9.6, §10.4, §11.2), tests planned (TEST §3.7, §4.6, E-07, E-17, E-24), OD-21…OD-26 opened |
| #50 | #49 | WP16: pure module `anchor.py` (arm/re-drop, radius, drag alarm latched, position-loss alarm, maximum distance, snapshot); OD-21…OD-26 resolved, OD-27 (track sharing by Home Assistant) |
| #54 | #53 | WP17: switch, radius, alarm and distance entities; `drop_anchor` / `raise_anchor` actions; options; state saved about 1 s after a change; diagnostics; README alert; `anchor-drag` scenario |
| #56 | #55 | WP18: bench recipe, E-07 pre-run (§5.1), README anchor map card and anchor icons (findings of the pre-run), this report |

## 2. Test status (TEST §9, row P5)

| Group | Status |
|---|---|
| U-ANC-01…12 | Done (distances built from metres, exact by hand) |
| F-ANC-01…09 | Done (26 tests), incl. the README anchor automation run as published on the `anchor-drag` scenario |
| F-ENT-08 | Extended to the anchor entities (every attribute labelled, `reason` translated) |
| README anchor map card | Done — every entity of the card exists and has a position after the drop |
| E-07 bench | Pre-run in the official HA container passed (§5.1); formal run to do — §5.2 |
| E-17 in port | To run on board — §6 |
| E-24 at an anchorage | To run on board — §7 |

## 3. Decisions taken

| Item | Decision |
|---|---|
| OD-21 | New phase P5, after P3, independent of P4 |
| OD-22 | Switch + radius number + actions `drop_anchor` / `raise_anchor` |
| OD-23 | Drag alarm latched until disarmed or re-dropped |
| OD-24 | Alarm `no_position` after 60 s without position, cleared when a position inside returns |
| OD-25 | Anchor point = own position at arming or explicit coordinates, no bow offset; radius 50 m (10–500), 20 s outside |
| OD-26 | Armed state, point, radius, maximum distance and a latched alarm restored after a restart |
| OD-27 | The boat's track is shared online by Home Assistant, Vigie stays offline |
| OD-28 | **Open** — where the buffering track uploader lives (X-12 §8.5); not part of P5 |

## 4. Deviations from SPEC / TEST / CLAUDE.md

| # | Deviation | Where recorded |
|---|---|---|
| 1 | Issues and PRs created with the GitHub API instead of `gh` | PR descriptions |
| 2 | Restore uses Home Assistant's storage helper, not `RestoreEntity` (saved only every 15 min: a power cut right after anchoring would lose the watch) | SPEC §10.4 v0.17 |
| 3 | Actions registered from `async_setup_entry`, not `async_setup`: the latter needs a module-level `CONFIG_SCHEMA`, hence a Home Assistant import in `__init__.py`, which the pure-module rule forbids | PR #54 |
| 4 | WP17's functional tests were written after the code, not first | PR #54 |

## 5. Bench check (TEST §5.1 E-07, `anchor-drag`)

### 5.1 Pre-run in a sandbox container

| Item | Value |
|---|---|
| Date | 2026-10-21, 03:12–03:33 UTC |
| Home Assistant | official image `homeassistant/home-assistant:2026.2.3` (Docker Hub), `default_config`, `--network host` |
| Vigie | `main` at `a449836`, copied into `custom_components/` |
| Setup | Boat "Garnet" on a PTY; `vigie.drop_anchor` at 43.5, 7.25, radius 50 m (REST API) before the replay; `anchor-drag` replayed at real speed (15 min); README anchor automation with `system_log.write` instead of the phone |
| Reading | States polled every second through the REST API; dashboard with a map card and the four anchor entities rendered in headless Chromium, UI language French |

| # | Check | Observed | Result |
|---|---|---|---|
| 1 | Drop at the preset's point | Switch on, anchor 43.5, 7.25, radius 50 m, `armed_at` set; distance 37.8 m (the boat starts on its swing circle) | Pass |
| 2 | Swinging, 0–600 s | Largest distance shown 39.9 m; alarm off throughout | Pass |
| 3 | Drag alarm | On with reason `drag` at 699.3 s (expected 698 s ± 2); one log line from the automation: "Dragging: 54 m from the anchor (radius 50 m)." | Pass |
| 4 | After the replay (no more positions) | Alarm stays on with reason `drag` (latched); distance unavailable | Pass |
| 5 | HA restart while armed | Switch on with the same point, radius and `armed_at`; alarm on, `drag`; stored state written in `.storage/vigie.anchor.<entry>`; no second notification | Pass |
| 6 | Power cut 3 s after a re-drop (43.51, 7.26, 75 m), `docker kill` | After start: new point and radius 75 m restored, alarm cleared by the re-drop | Pass |
| 7 | No position after the restart | `no_position` exactly 60 s after start (03:30:13 → 03:31:13); automation logged "No position from the receiver: check the GPS and the power." | Pass |
| 8 | Map card | **Found:** the built-in card merged the boat and the anchor, 30 m apart, into one marker "2"; fixed with `cluster: false` and `default_zoom: 18`, which show the boat, its swinging track and the anchor separately | Pass after fix (#56) |

Findings:

- **Map card** (fixed in #56): see check 8. The README now has an anchor map card with
  both settings, tested against real entities.
- **Icons** (fixed in #56): the switch and the distance sensor showed the generic
  distance arrow on the map and in the entities card; they now show an anchor
  (`icons.json`), the radius a radius icon.
- The distance shown lags the raw distance by up to 1 m (dead-band, SPEC §10.2): it read
  49.7 m when the boat had just crossed 50 m. The alarm uses the raw distance; no change.
- Entity names follow the server language (English here), not the user's: Home Assistant
  behaviour, as in the P3 pre-run.
- Container CPU ≈ 0.04 %, memory ≈ 240 MiB at rest; the only ERROR in the log is HA core's
  alerts fetch (no internet).

### 5.2 Formal bench check

Same bench as E-1 (`CONTRIBUTING.md`, P5 bench). Install the README anchor automation and
the README anchor map card before the run.

```bash
python -m tests.tools.scenario --preset anchor-drag -o anchor-drag.nmea
python -m tests.tools.replay anchor-drag.nmea --pty /srv/vigie-bench/ttyAIS
```

Before starting the replay, run the action `vigie.drop_anchor` with latitude 43.5,
longitude 7.25, radius 50 (Developer tools → Actions). The replay lasts 15 min; the alarm
is due at 698 s.

| Run | Date | Host / HA version | Vigie commit | Tester |
|---|---|---|---|---|
| | | | | |

| # | Check | Expected | Result |
|---|---|---|---|
| 1 | After the drop | Switch on, anchor 43.5, 7.25, radius 50 m; anchor shown on the map card | |
| 2 | 0–10 min (swinging) | No alarm; distance between about 20 and 42 m | |
| 3 | ≈ 11 min 38 s (698 s) | Alarm on, *Dragging* (*Dérapage* in French), ± 2 s; one notification on the phone | |
| 4 | Back inside? | Not in this scenario; the alarm stays on until the watch is turned off | |
| 5 | Restart HA while the alarm is on | Watch, anchor point and alarm come back | |
| 6 | Stop the replay, wait 60 s | Alarm *Position lost* (*Position perdue*) if it was cleared before; notification | |
| 7 | Turn the switch off | Alarm off, distance unavailable | |

## 6. E-17 — in port, overnight (TEST §5.2)

| Run | Date | Place | Receiver model, baud | Tester |
|---|---|---|---|---|
| | | | | |

| # | Check | Expected | Result |
|---|---|---|---|
| 1 | Turn the switch on at the berth, radius 20 m, in the evening | Distance a few metres (GPS noise) | |
| 2 | Next morning (≥ 8 h) | No alarm overnight; note `max_distance_m` (GPS noise at the berth) | |
| 3 | Unplug the receiver 2 min | *Position lost* after 60 s, notification; clears when replugged | |
| 4 | Cut the Pi's power 10 s, power up | Watch and anchor point come back | |

## 7. E-24 — at an anchorage (TEST §5.3)

Daylight, good visibility, a crew member responsible for navigation. The anchor watch is
an aid only.

| Run | Date | Place, depth, chain out | Tester |
|---|---|---|---|
| | | | |

| # | Check | Expected | Result |
|---|---|---|---|
| 1 | Turn the switch on when the anchor is down (or `drop_anchor` with the chartplotter's position), radius 30 m | Anchor point within a few metres of the real one | |
| 2 | Lying at anchor ≥ 1 h | No alarm; `max_distance_m` below the radius | |
| 3 | Raise the anchor, motor slowly out of the radius without turning the watch off | Alarm within 20 s + 2 s of leaving the radius; phone notification | |
| 4 | Turn the switch off | Alarm cleared | |

## 8. Open items

- Formal bench check (§5.2; pre-run passed, §5.1), E-17 (§6) and E-24 (§7).
- OD-28 and the integration key from noforeignland (X-12 OD-8) before any work on #51.
- P1–P3 items still open: #2 receiver capture, TP-04, E-02 formal run, E-12/E-16, E-3.
