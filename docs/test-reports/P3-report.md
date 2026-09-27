# P3 report — Static data (HA-SAIL-TEST-001 §9)

Template with the automated results filled in. The bench and on-board tables are filled in
when the checks are run; the exit criterion is assessed once they are.

| Item | Value |
|---|---|
| Phase | P3 Static data (SPEC HA-SAIL-SPEC-001 v0.12 §13) |
| Documents | SPEC v0.12, TEST v0.18 |
| Code state | `main` after the WP14 merge — fill in the commit |
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
| Bench check (`named-traffic`) | To run — §5 |
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
- Bench check (§5) and E-12 extended (§6).
- P2 items still open: TP-04, E-02 formal run, E-12/E-16, E-3.
