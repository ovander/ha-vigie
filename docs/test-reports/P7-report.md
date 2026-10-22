# P7 report — Anchor card (HA-SAIL-TEST-001 §9)

This report is a template. The automated results and the bench pre-run are filled in; the
formal bench check is filled in when it is run, and the exit criterion is assessed then.

| Item | Value |
|---|---|
| Phase | P7 Anchor card (SPEC HA-SAIL-SPEC-001 v0.26 §9.8, §13) |
| Documents | SPEC v0.26, TEST v0.33 |
| Code | Vigie `main` (no change to the integration in P7: tests and docs only); card `ovander/ha-vigie-card` (WP25, WP26) |
| Releases | Card [`v0.2.0-beta.1`](https://github.com/ovander/ha-vigie-card/releases/tag/v0.2.0-beta.1) (anchor card, own boat line) and [`v0.2.0-beta.2`](https://github.com/ovander/ha-vigie-card/releases/tag/v0.2.0-beta.2) (decimal degrees, version in the file), both pre-releases. The swing track, the editor and the pre-run fixes are not released yet: the next card beta is the owner's call |
| CI | Vigie `lint`, `unit`, `hassfest`, `hacs`. Card `check` (typecheck, unit and headless Chromium tests, build, `dist` up to date, smoke test of the built file with its version) and `hacs`. The card's release workflow also checks the stamped version |
| Automated tests | Vigie: 523 passed, 1 skipped (U-GPS-08, #2). Card: 95 (U-CARD, U-ACARD, F-CARD, F-ACARD, editors, pre-run regressions) and the smoke test |
| Exit criterion | **Not met yet**: the formal E-09 (§5.2) is still to run |

## 1. What was built

| PR | Issue | Content |
|---|---|---|
| ovander/ha-vigie#75 | #74 | WP24: anchor card specified (SPEC §9.8, C-13); tests planned; OD-34…OD-38 opened |
| ovander/ha-vigie#78, ovander/ha-vigie-card#7, ovander/ha-vigie-card#8 | #76, #77 | WP25: OD-34…OD-38 resolved; anchor fixtures recorded from Vigie; the anchor card (status, gauge, details, map, drop / raise with confirmation / radius); own boat line and details on both cards (owner's lab finding #77) |
| ovander/ha-vigie#79, ovander/ha-vigie-card#10, ovander/ha-vigie-card#11 | #76, #77 | Docs for both cards; the release file carries its version; own position in decimal degrees (owner) |
| ovander/ha-vigie-card#13, this PR | #80 | WP26: swing track from Home Assistant's history, visual editor, tracker history fixture, E-09 pre-run and its three fixes, this report |

## 2. Test status (TEST §9, row P7)

| Group | Status |
|---|---|
| U-ACARD-01…08 | Done (card `test/unit/`, hand values) |
| F-ACARD-01…11 | Done (card `test/browser/`, headless Chromium, states and tracker history recorded from Vigie) |
| Anchor fixtures (Vigie) | Done: `tests/integration/test_card_fixtures.py` writes and checks `anchor-drag.json` |
| Smoke test of the built file | Done (CI and release) |
| E-09 | Pre-run passed after fixes (§5.1); the formal run is still to do (§5.2) |

## 3. Decisions taken

| Item | Decision |
|---|---|
| OD-34 | A second card `custom:vigie-anchor-card` in `ha-vigie-card`, in the same file |
| OD-35 | Exactly three calls: `switch.turn_on`, `switch.turn_off` after a confirmation, `number.set_value`; the traffic card stays read only |
| OD-36 | Swing track from Home Assistant's history since `armed_at`, then the live updates |
| OD-37 | No sound; the alert is the phone notification |
| OD-38 | New phase P7 |
| OD-39 | Recentering the circle: on the swing (fitted circle) and by hand on the map, with a fourth call `vigie.drop_anchor` and `keep_since`. Built in WP27 (#81) |
| #77 (owner) | Own boat position, SOG, COG, heading and position state on both cards; position also in decimal degrees in the details |

## 4. Deviations from SPEC / TEST / CLAUDE.md

| # | Deviation | Where recorded |
|---|---|---|
| 1 | Issues and PRs were created with the GitHub API instead of `gh` | PR descriptions |
| 2 | U-ACARD-05 and -07 moved from WP26 to WP25, with the map and the details they test | TEST v0.31 |
| 3 | The owner's requests during P7 (own boat on the cards, decimal degrees, recentering) were handled as issues #77 and #81 inside the phase, not as separate phases | SPEC v0.24–v0.26 |
| 4 | `v0.2.0-beta.1` of the card carries no version string (the stamped constant was dropped as unused). It is fixed from `v0.2.0-beta.2`; the published tag was not moved | card CHANGELOG |

## 5. Bench check (TEST §5.1 E-09)

### 5.1 Pre-run in a sandbox container

| Item | Value |
|---|---|
| Date | 2026-10-22, 16:47–17:15 UTC |
| Home Assistant | Official image `homeassistant/home-assistant:2026.2.3`, `default_config` (recorder and history on), `--network host` |
| Vigie | `main` at `b42e45e`, copied into `custom_components/` |
| Card | `feat/anchor-track` build (`ff1bf41`, then `e27133b` with the fixes), served from `/config/www/` as a dashboard resource |
| Setup | Boat *Garnet* on a PTY replaying `anchor-drag` at real speed. As in E-07, `vigie.drop_anchor` was called at 43.5, 7.25 with radius 50 just before the replay. Dashboard: the anchor card configured with one line (`switch:` only), and the four anchor entities next to it |
| Reading | Headless Chromium at 1280 × 900 in English, and at 390 × 844 (phone) in French. The card was read from its shadow DOM and driven by clicking its buttons. Map tiles are not reachable from the sandbox (plain background) |

| # | Check | Observed | Result |
|---|---|---|---|
| 1 | Watch off | *Anchor watch off*; own boat line `43° 30.020′ N 7° 15.003′ E`, *Position current*; *Drop anchor here* enabled | Pass |
| 2 | 60 s after the drop | *Watching*, `29 / 50 m`, gauge normal, swing track 47 points | Pass |
| 3 | 300 s | `32 / 50 m`, bearing 353°, largest distance 38.5 m, track 226 points drawn around the circle | Pass |
| 4 | Page reloaded at 300 s | Track redrawn at once from Home Assistant's history (230 points) | Pass |
| 5 | Radius − at 400 s, + at 420 s | `number.garnet_anchor_radius` 45 then 50 in Home Assistant; card `29 / 45 m`, then `/ 50 m` | Pass |
| 6 | Drag alarm | Vigie's alarm on at 698.9 s (expected 698 s ± 2), reason `drag`. The card shows *Dragging since …* in red, `55 / 50 m`, red gauge and red circle. **Found:** the boat was cut at the map's edge; and the time read `05:01 PM` (12 h, from the language) where Home Assistant can be set to 24 h. Both fixed: the view takes in the boat outside the circle, and times follow Home Assistant's 12/24 h setting | Pass after fix |
| 7 | Raise anchor | The confirmation reads "Stop the anchor watch of Garnet?". *Cancel* leaves the switch on; confirming turns it off. The card goes back to *Anchor watch off* and the track is cleared | Pass |
| 8 | Drop anchor here | Switch on, anchor at 43.500518, 7.25, i.e. the boat's position (tracker 43.500498, the boat moving at 0.5 kn) | Pass |
| 9 | Own boat details | *Position (dd)* `43.500498, 7.250000` | Pass |
| 10 | Visual editor | Home Assistant's form with the Vigie fields and their labels; one-line configuration | Pass |
| 11 | French, phone width | *Veille*, `Distance maximale 3,5 m`, `Vitesse fond 0,5 nd`, *Lever l'ancre*; everything fits at 390 px | Pass |
| 12 | Outside the circle before the alarm | **Found:** a green *Watching* next to a red gauge at `87 / 50 m` during the alarm's 20 s confirmation. Fixed: new amber status *Outside the circle*; re-checked in Home Assistant | Pass after fix |

Each finding was reproduced by a test in the card repository before it was fixed (U-ACARD-02, F-ACARD-02, and the time format test), then re-checked in the container. The browser console showed no error other than the blocked tiles; the file announced itself as `VIGIE-CARD 0.0.0-dev` (a development build).

### 5.2 Formal bench check

Run on the bench (`CONTRIBUTING.md`, two-Pi bench or container), with the card release that carries WP26, installed through HACS. Use a phone and a tablet. Install the README anchor automation before the run.

| Run | Date | Host / HA version | Vigie commit | Card version | Tester |
|---|---|---|---|---|---|
| | | | | | |

| # | Check | Expected | Result |
|---|---|---|---|
| 1 | `vigie.drop_anchor` at 43.5, 7.25, radius 50, then replay `anchor-drag` | *Watching*; status, distance and gauge follow `sensor.<boat>_anchor_distance` | |
| 2 | Radius − then + before 600 s | 45 then 50 m in Home Assistant | |
| 3 | 0–10 min | Swing track drawn; reloading the page keeps it | |
| 4 | ≈ 11 min 18 s (678 s) | *Outside the circle* (amber), boat in view | |
| 5 | ≈ 11 min 38 s (698 s) | *Dragging* in red on both screens (± 2 s); phone notification | |
| 6 | *Raise anchor*: cancel, then confirm | Watch on after cancel, off after confirm | |
| 7 | *Drop anchor here* | Watch on at the boat's position | |
| 8 | Network cut | Everything but the tiles still drawn | |
| 9 | Phone in French | Every card string and figure in French | |

## 6. Open items

- Formal E-09 (§5.2) with a card release that carries WP26.
- WP27: recentering the circle (OD-39, #81).
- Earlier phases: #2 receiver capture, TP-04, E-02 formal run, E-12/E-16, E-3, P5 E-07/E-17/E-24, P6 E-08.
