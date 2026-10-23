# P8 report — Track sharing (HA-SAIL-TEST-001 §9)

This report is a template. The automated results are filled in; the bench and on-board
checks are filled in when they are run, and the exit criterion is assessed then.

| Item | Value |
|---|---|
| Phase | P8 Track sharing (SPEC HA-SAIL-SPEC-001 v0.30 §9.10, §13; X-12 0.3.0) |
| Documents | SPEC v0.31, TEST v0.39 |
| Code | `ovander/ha-noforeignland` (C-15). No change in Vigie |
| Releases | [`v0.1.0-beta.1`](https://github.com/ovander/ha-noforeignland/releases/tag/v0.1.0-beta.1) (pre-release, 2026-10-23, `812caf7`): `noforeignland.zip`, manifest stamped `0.1.0-beta.1`, every other file identical to `main`. Tested against a simulated noforeignland only |
| CI | `lint`, `unit`, `hassfest`, `hacs` in `ovander/ha-noforeignland` |
| Automated tests | 46 (U-NFL, F-NFL, flows, translations), noforeignland mocked; 100 % coverage on the pure core |
| Exit criterion | **Not met yet**: E-25 needs noforeignland's integration key (X-12 OD-8) |

## 1. What was built

| PR | Issue | Content |
|---|---|---|
| ovander/ha-vigie#92 | #91 | WP29: the uploader specified (SPEC §9.10, C-15); OD-28, OD-41…OD-44 resolved by the owner; tests planned |
| ovander/ha-noforeignland#1, ovander/ha-vigie#94 | #93 | WP30: the uploader built and tested; TEST statuses; this report |
| ovander/ha-noforeignland#2, ovander/ha-vigie#95 | #93 | Changelog and README (step-by-step install, where the keys and options live, an *Entities* card) for `v0.1.0-beta.1`; the release recorded here |
| ovander/ha-noforeignland#3, this PR | #96 | WP31: the integration key built in, an optional override (OD-45) |

## 2. Test status (TEST §9, row P8)

| Group | Status |
|---|---|
| U-NFL-01…09 | Done (`tests/core/`, values by hand) |
| F-NFL-01…09 | Done (`tests/integration/`, noforeignland mocked with `aioclient_mock`) |
| E-25 | To do, with a test boat and the integration key |
| E-26 | To do, under way |

## 3. Decisions taken

| Item | Decision |
|---|---|
| OD-28 | A separate integration in its own repository; Vigie stays offline |
| OD-41 | `ovander/ha-noforeignland`, domain `noforeignland` |
| OD-42 | New phase P8 |
| OD-43 | The reference client's defaults, in the options; amended (owner): sent once an hour, a stationary point every 6 h |
| OD-44 | A *Sharing* switch |
| OD-45 | noforeignland's integration key built into the integration; an optional override |

## 4. Deviations from SPEC / TEST / CLAUDE.md

| # | Deviation | Where recorded |
|---|---|---|
| 1 | The repository was created by the owner (`gh repo create`): the session cannot create repositories | This report |
| 2 | A first commit (license, `.gitignore`, CLAUDE.md) went straight to the new repository's empty `main`, so the first PR had a base | ovander/ha-noforeignland#1 |
| 3 | A logged point is timed at the sampling, not at the source's last update (a still boat's tracker does not update) | SPEC v0.30 |

## 5. Bench and on-board checks

### 5.1 E-25 — bench, test boat

Before the run: a **test boat** on noforeignland (never the real boat's key), its API key,
noforeignland's integration key, Vigie on the bench with `multi-target` replayed
(`replay --tcp`, CONTRIBUTING.md), the uploader set up on `device_tracker.<boat>`, with *Send every* set to 10 min in its
options to keep the run short (the default is 60 min).

| Run | Date | Host / HA version | Uploader commit | Tester |
|---|---|---|---|---|
| | | | | |

| # | Check | Expected | Result |
|---|---|---|---|
| 1 | Replay 10 min | A point a minute; *Last send* at the 10-minute send; the test boat moves on noforeignland's map | |
| 2 | Cut the bench's internet 10 min, replay going on | *Status* `waiting`; *Buffered points* rises by about 10 | |
| 3 | Internet back | At the next send *Buffered points* falls to 0; the track on the map has no gap and no duplicate point | |
| 4 | *Sharing* off for 5 min | *Status* `paused`; nothing logged; no point on the map for that time | |
| 5 | A wrong boat key (Reconfigure) | *Status* `rejected` with noforeignland's message; a repair notice; points kept; the right key sends them | |
| 6 | Home Assistant restarted with buffered points | Sent at the next send, none lost | |

### 5.2 E-26 — under way

| # | Check | Expected | Result |
|---|---|---|---|
| 1 | At least 2 h under way, with a mobile-data gap of 30 min or more | The passage on noforeignland without a gap after the connection returns | |
| 2 | *Sharing* off in port | No point while off | |

## 6. Open items

- noforeignland's integration key (X-12 OD-8); the answers on OD-2 (points per request),
  OD-4 (rate limits) and OD-6 (backdated points).
- E-25 (with a test boat), E-26.
