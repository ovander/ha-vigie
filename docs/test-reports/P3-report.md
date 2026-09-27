# P3 report — Static data (HA-SAIL-TEST-001 §9)

Template with the automated results filled in. The bench and on-board tables are filled in
when the checks are run; the exit criterion is assessed once they are.

| Item | Value |
|---|---|
| Phase | P3 Static data (SPEC HA-SAIL-SPEC-001 v0.12 §13) |
| Documents | SPEC v0.12, TEST v0.18 |
| Code state | `main` at `b30231e` (all P3 work packages merged) |
| Release | none yet; a beta tag is the owner's call |
| CI | `lint`, `unit`, `hassfest`, `hacs` green on every P3 PR |
| Automated tests | 438 passed, 1 skipped (U-GPS-08, #2), 3 `perf` tests run separately |
| Coverage | 99 % of the pure modules (`nmea/`, `state.py`, `geo.py`, `hub.py`, `traffic.py`); gate ≥ 90 % |
| Exit criterion | **Not met yet**: the bench check (§5), E-12 extended (§6) and U-AIS-13 on the receiver capture (#2) |

## 1. What was built

| PR | Issue | Content |
|---|---|---|
| #33 | #32 | WP11: decoder for types 5 and 24 (parts A, B, auxiliary craft) and the static fields of type 19; ship-type categories; P3 decisions recorded |
| #35 | #34 | WP12: static store per MMSI (merge, 30 min, 2 000 MMSIs), hub routing, names from types 5/24 everywhere |
| #37 | #36 | WP13: ship type (translated), call sign, IMO, length, beam, draught, destination on the entities; late static data written at once |
| #39 | #38 | WP14: README map card and ship details (both tested against real entities), `named-traffic` scenario, this report |

## 2. Test status (TEST §9, row P3)

| Group | Status |
|---|---|
| U-AIS-04, U-AIS-15…22 | Done (incl. the gpsd type 5 reference sentence and fuzz against pyais) |
| U-STA-01…07 | Done |
| F-HUB-01 (static routing), F-TRF-08…11 | Done |
| README map card | Done — every entity of the card exists and shows its target after the `named-traffic` scenario |
| Bench check (`named-traffic`) | Pre-run in the official HA container passed (§5.1); formal run on the bench to do — §5.2 |
| E-12 extended (names and ship types) | To run in port — §6 |
| U-AIS-13 on the receiver capture | Pending on #2 — must decode the type 5/24 lines without rejects |

## 3. Decisions taken

| Item | Decision |
|---|---|
| OD-17 | Ship type as ITU code plus a category key (19 keys), translated in the UI |
| OD-18 | Static data kept per MMSI 30 min after its last report, at most 2 000 MMSIs, apart from the target table |
| OD-19 | Built-in map card configuration (own boat, watched targets); a custom card is left for after v1 |
| OD-20 | Fields: name, call sign, IMO, ship type, length, beam, draught, destination; no ETA, no EPFD |

## 4. Deviations from SPEC / TEST / CLAUDE.md

| # | Deviation | Where recorded |
|---|---|---|
| 1 | Issues and PRs created with the GitHub API instead of `gh` | PR descriptions |
| 2 | Type 5 accepted from 420 bits (nominal 424) because many transmitters send 420 or 422 | SPEC §7.3, U-AIS-16 |
| 3 | The `targets` list and the watch-list trackers now take the name from the static store (WP12), not from the position report | SPEC §9.4 |

## 5. Bench check (TEST §5.1 bench, `named-traffic`)

### 5.1 Pre-run in a sandbox container

| Item | Value |
|---|---|
| Date | 2026-09-27, 22:00–22:21 UTC |
| Home Assistant | official image `homeassistant/home-assistant:2026.2.3` (Docker Hub), `default_config`, `--network host` |
| Vigie | `main` at `b30231e`, copied into `custom_components/` (manifest `0.3.0-bench`) |
| Setup | Boat "Garnet" on a PTY, watch list 235000011 and 235000012; the own boat's start position fed during configuration, then `named-traffic` replayed at real speed (20 min). README collision automation with `system_log.write` instead of the phone |
| Reading | States polled every 2 s through the REST API; dashboard with the README map card and more-info dialogs rendered in headless Chromium, UI language French; translations fetched with `frontend/get_translations` |

| # | Check | Observed | Result |
|---|---|---|---|
| 1 | Before 30 s | 4 targets, all unnamed; both watched trackers located (before the replay: unavailable, not heard yet) | Pass |
| 2 | After 30 s | Every name in the `targets` list at 30 s: CARGO ONE (cargo, 180 m), ALBATROS (sailing, 12 m), ALBATROS TENDER (pleasure craft, no length: auxiliary craft), 235000014 without name or type | Pass |
| 3 | Tracker `ais_235000011` | CARGO ONE, cargo (70), ABCD, 9123456, 180 × 30 m, draught 8.5 m, MARSEILLE | Pass |
| 4 | Tracker `ais_235000012` | ALBATROS, sailing (36), FAB1234, 12 × 4 m; IMO, draught, destination empty (Class B) | Pass |
| 5 | `collision_risk` | On at 60 s (TCPA crosses 15 min), off at 962 s (CPA at 16.0 min); one alert: "CARGO ONE: CPA 0.45 NM in 15.0 min. Check the lookout." | Pass |
| 6 | Map card | Garnet and both watched targets with their tracks (no tiles: no internet in the sandbox). **Found:** both targets labelled "A2" (initials of "AIS 2…"); fixed in the README with `label_mode: attribute` / `attribute: name`, which shows "CARGO ONE" and "ALBATROS" | Pass after fix |
| 7 | UI in French | More-info → Attributes: *Type de navire : Cargo*; categories served in French (*Voilier*, *Plaisance*) | Pass, see finding below |

Findings:

- **Map card labels** (fixed in this PR): see check 6; the README map card test now requires
  an attribute label on watched targets.
- **Attribute labels not translated** (not fixed, existing since P2): only `ship_type` has a
  translated label and values. The other attributes show Home Assistant's automatic English
  labels ("Callsign", "Imo", "Length m", "Nav status", "Tcpa min") and `nav_status` shows
  raw values (`under_way_engine`), in English and French alike. Proposed follow-up: names
  for every attribute and the `nav_status` values in the three translation files.
- Entity names follow the server language (English here), not the user's: Home Assistant
  behaviour, not Vigie's.
- Container CPU ≈ 0.4 %, memory ≈ 320 MiB; the only ERROR in the log is HA core's alerts
  fetch (no internet).

### 5.2 Formal bench check

Same bench as E-1/E-02 (`CONTRIBUTING.md`). Add the two named MMSIs to the watch list and
the README map card to a dashboard before the run.

```bash
python -m tests.tools.scenario --preset named-traffic -o named-traffic.nmea
python -m tests.tools.replay named-traffic.nmea --pty /srv/vigie-bench/ttyAIS
```

Watch list: `235000011, 235000012`. The scenario lasts 20 min; names arrive 30 s after the
first positions, then every 6 min.

| Run | Date | Host / HA version | Vigie commit | Tester |
|---|---|---|---|---|
| | | | | |

| # | Check | Expected | Result |
|---|---|---|---|
| 1 | Before 30 s | 4 targets, all unnamed; trackers of 235000011 and 235000012 on the map | |
| 2 | After 30 s | `targets` list: CARGO ONE (cargo, 180 m), ALBATROS (sailing, 12 m), ALBATROS TENDER (pleasure craft), 235000014 without name or type | |
| 3 | Tracker `ais_235000011` | name CARGO ONE, ship type *Cargo* (*Cargo* in French), call sign ABCD, IMO 9123456, 180 × 30 m, draught 8.5 m, destination MARSEILLE | |
| 4 | Tracker `ais_235000012` | name ALBATROS, ship type *Sailing* (*Voilier*), call sign FAB1234, 12 × 4 m | |
| 5 | `collision_risk` from ≈ 1 min | on; attributes name CARGO ONE, ship type cargo; the README alert names the ship | |
| 6 | Map card | own boat and both watched targets with their tracks | |
| 7 | UI language French | ship types shown in French in the more-info dialog | |

## 6. E-12 extended, on board in port (TEST §5.2)

Record the capture for #2 first (`python -m tests.tools.capture`), while Vigie is stopped.

| Run | Date | Place | Receiver model, baud | Tester |
|---|---|---|---|---|
| | | | | |

| # | MMSI | Name: Vigie / chartplotter | Ship type: Vigie / chartplotter | Length: Vigie / chartplotter | Match |
|---|---|---|---|---|---|
| 1 | | | | | |
| 2 | | | | | |
| 3 | | | | | |
| 4 | | | | | |
| 5 | | | | | |

Wait at least 6 min after start before reading names (static reports repeat every 6 min).
Pick at least one Class A and one Class B target.

## 7. Open items

- #2 — receiver capture: U-AIS-13 over the type 5/24 lines, and the P1/P2 items it carries.
- Formal bench check (§5.2; pre-run passed, §5.1) and E-12 extended (§6).
- Translated labels for every attribute and `nav_status` values (finding of §5.1).
- P2 items still open: TP-04, E-02 formal run, E-12/E-16, E-3.
