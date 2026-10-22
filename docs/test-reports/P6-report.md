# P6 report — Traffic map card (HA-SAIL-TEST-001 §9)

Template with the automated results and the bench pre-run filled in. The formal bench check
is filled in when it is run; the exit criterion is assessed then.

| Item | Value |
|---|---|
| Phase | P6 Traffic map card (SPEC HA-SAIL-SPEC-001 v0.21 §9.7, §13) |
| Documents | SPEC v0.21, TEST v0.28 |
| Code state | Vigie `main` at `d7725a4` (WP19–WP23 and the 0.3.0-beta.1 changelog merged); card `main` at `6e051d8` (WP21–WP23 and the 0.1.0-beta.1 changelog merged) |
| Release | Vigie [`v0.3.0-beta.1`](https://github.com/ovander/ha-vigie/releases/tag/v0.3.0-beta.1), pre-release, 2026-10-22, tag on `d7725a4`; `vigie.zip` checked (manifest `0.3.0-beta.1`, `heading`/`threat` row fields). Card [`v0.1.0-beta.1`](https://github.com/ovander/ha-vigie-card/releases/tag/v0.1.0-beta.1), pre-release, 2026-10-22, tag on `6e051d8`; `vigie-traffic-card.js` checked (the committed build with the version stamped `0.1.0-beta.1`). Run the formal check below on these releases |
| CI | Vigie `lint`, `unit`, `hassfest`, `hacs` green on every P6 PR, release workflow green; nightly `perf` last green on `3af0d5b` (before WP20), the three `perf` tests run locally on `d7725a4` and passed — the tag was pushed before the first nightly on it (2026-10-23 02:17 UTC). Card `check` (typecheck, unit and headless Chromium tests, build, `dist` up to date, smoke test of the built file) and `hacs` (README `images` check skipped until the screenshot, §6), release workflow green |
| Automated tests | Vigie: 522 passed, 1 skipped (U-GPS-08, #2). Card: 57 (U-CARD, F-CARD, editor, untrusted-name check, pre-run regressions) and the smoke test |
| Exit criterion | **Not met yet**: the formal E-08 (§5.2) |

## 1. What was built

| PR | Issue | Content |
|---|---|---|
| ovander/ha-vigie#61 | #60 | WP19: card specified (SPEC §9.7, C-12), tests planned, OD-29…OD-33 opened |
| ovander/ha-vigie#63 | #62 | WP20: `heading` and `threat` in every `targets` row (F-TRF-12); OD-29…OD-33 resolved |
| ovander/ha-vigie-card#1 | #64 | WP21: card repository — skeleton, configuration (U-CARD-06), EN/FR strings (U-CARD-07), CI, HACS packaging, release workflow |
| ovander/ha-vigie-card#2, ovander/ha-vigie#66 | #65 | WP22: the map (Leaflet): own boat, targets, threats with CPA point, rings, anchor, details, follow mode; U-CARD-01…05, F-CARD-01…07, 09 against states recorded from Vigie; smoke test |
| ovander/ha-vigie-card#3, ovander/ha-vigie#68 | #67 | WP23: visual editor (F-CARD-08), E-08 pre-run and its five fixes, Vigie README section, this report |

## 2. Test status (TEST §9, row P6)

| Group | Status |
|---|---|
| U-CARD-01…07 | Done (card `test/unit/`, hand values) |
| F-CARD-01…09 | Done (card `test/browser/`, headless Chromium, Vigie fixtures) |
| F-TRF-12 (Vigie side) | Done |
| F-PERF-03 with the new row fields | Done (50 rows under the attribute size limit) |
| Smoke test of the built file | Done (CI) — caught a bundling bug in WP22 |
| E-08 | Pre-run passed after fixes (§5.1); formal run to do (§5.2) |

## 3. Decisions taken

| Item | Decision |
|---|---|
| OD-29 | Own repository `ha-vigie-card`, HACS *Dashboard* category |
| OD-30 | Leaflet (BSD-2) bundled; TypeScript and Lit |
| OD-31 | Data from the `targets` rows, with `heading` and `threat` from Vigie |
| OD-32 | OpenStreetMap tiles by default, configurable, optional OpenSeaMap overlay; no offline tiles (boat online through Starlink) |
| OD-33 | Phase P6, independent of P4 |

## 4. Deviations from SPEC / TEST / CLAUDE.md

| # | Deviation | Where recorded |
|---|---|---|
| 1 | Issues and PRs created with the GitHub API instead of `gh`; the card repository was created by the owner (the session cannot create repositories) | PR descriptions |
| 2 | F-CARD runs in Vitest browser mode with Playwright instead of Web Test Runner (one test runner for unit and browser tests) | TEST v0.27 §4.7 |
| 3 | `dist/vigie-traffic-card.js` is committed in the card repository: HACS installs it from the repository until a release carries it; CI checks it is the build of the sources | card README, CLAUDE.md |
| 4 | The card's HACS check skips `images` until the README has a screenshot with real map tiles (§6) | card CI workflow |
| 5 | TypeScript pinned to 6.0.3: the Rollup TypeScript plugin uses the compiler API that TypeScript 7's native rewrite may not offer | ovander/ha-vigie-card#1 |

## 5. Bench check (TEST §5.1 E-08)

### 5.1 Pre-run in a sandbox container

| Item | Value |
|---|---|
| Date | 2026-10-22, 09:19–09:45 UTC |
| Home Assistant | official image `homeassistant/home-assistant:2026.2.3`, `default_config`, `--network host` |
| Vigie | `main` at `8062767`, copied into `custom_components/` |
| Card | `feat/editor` build, served from `/config/www/vigie-traffic-card.js` as a dashboard resource (`module`) |
| Setup | Two boats on PTYs: *Garnet* replaying `multi-target` (anchor dropped at the start, radius 300 m), *Jade* replaying `named-traffic`; one dashboard view per boat with the card (`collision_risk`, `anchor`) and the closest-threat CPA/TCPA sensors next to it |
| Reading | Headless Chromium on the dashboard, English and French; card contents read from its shadow DOM. Map tiles are not reachable from the sandbox (plain background) |

| # | Check | Observed | Result |
|---|---|---|---|
| 1 | Card loads as a resource, both boats | `custom:vigie-traffic-card` rendered, "4 AIS targets" on each, no error in the browser console except blocked tiles | Pass |
| 2 | First view | **Found:** world zoom, every boat on one spot. Fixed (fit waits for the card's size); then the 2 NM ring fills the map | Pass after fix |
| 3 | Threats and CPA | Garnet: 2 threats, `235000002: CPA 0.45 NM in 2.0 min` while `closest_threat_cpa` showed 0.447 NM; Jade: `CARGO ONE: CPA 0.45 NM in 13.6 min` vs 0.448 NM / 13.6 min | Pass |
| 4 | Names | CARGO ONE, ALBATROS, ALBATROS TENDER and 235000014 as in P3 | Pass |
| 5 | Anchor | Garnet's anchor and 300 m circle drawn; red once the boat had motored out (drag alarm) | Pass |
| 6 | Details on tap | **Found:** the popup was pushed out of view by follow mode at the next update. Fixed (follow paused while a popup is open); then the popup stays in view through updates | Pass after fix |
| 7 | Labels across updates | **Found:** every label faded out and in at each update (Leaflet fade animation). Fixed (fade off) | Pass after fix |
| 8 | French UI | **Found:** `0.45`, `13.6` while Home Assistant shows `0,45`. Fixed (user's locale); then `CARGO ONE : CPA 0,45 NM dans 9,5 min`, `12,0 nd` | Pass after fix |
| 9 | Visual editor | **Found:** blank, `ha-form` crashed asking a label for its layout grid. Fixed; then every field in French, Vigie entity pickers, a change sent back as YAML | Pass after fix |

Each finding was reproduced by a browser test in the card repository before the fix.

### 5.2 Formal bench check

On the bench (`CONTRIBUTING.md`, two-Pi bench or container) with Vigie `v0.3.0-beta.1` and
the card `v0.1.0-beta.1` installed through HACS (*Dashboard*, custom repository
`https://github.com/ovander/ha-vigie-card`). Add the card from the dashboard editor
(*Vigie traffic map*), with the collision risk and the anchor distance, on a phone and on a
tablet.

| Run | Date | Host / HA version | Vigie commit | Card version | Tester |
|---|---|---|---|---|---|
| | | | | | |

| # | Check | Expected | Result |
|---|---|---|---|
| 1 | Replay `multi-target` | 4 targets drawn where `--list` puts them; 2 threats red, CPA labels match `closest_threat_cpa`/`_tcpa` (± 0.02 NM, ± 0.2 min) | |
| 2 | Replay `named-traffic` | CARGO ONE, ALBATROS, ALBATROS TENDER, 235000014; CARGO ONE red from about 1 min | |
| 3 | Map tiles | OpenStreetMap tiles under the boats; with an OpenSeaMap overlay configured, sea marks drawn | |
| 4 | Tap a target, wait 30 s | Details stay in view and update | |
| 5 | Pan away, then ⌖ | Follow stops, then resumes | |
| 6 | Anchor watch on, alarm | Circle drawn, red on alarm | |
| 7 | Network cut (router off) | Boat, targets, vectors and rings still drawn | |
| 8 | Phone in French | Every card string and number in French | |
| 9 | Screenshot for the card's README | Saved (§6) | |

## 6. Open items

- Formal E-08 (§5.2), on the boat's Home Assistant with map tiles.
- README screenshot with real tiles: from the formal E-08, or from the sandbox once
  `tile.openstreetmap.org` is allowed in its network settings; then remove `images` from
  the card's HACS check.
- First nightly `perf` run on `d7725a4` (2026-10-23).
- Earlier phases: #2 receiver capture, TP-04, E-02 formal run, E-12/E-16, E-3, P5 E-07/E-17/E-24.
