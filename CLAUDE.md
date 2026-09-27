# CLAUDE.md — ha-vigie

Standing instructions for Claude Code in this repository. Read this file, then
`docs/HA-SAIL-SPEC-001.md` (SPEC) and `docs/HA-SAIL-TEST-001.md` (TEST) before any change.

## Project in one paragraph

Vigie is a Home Assistant custom integration (domain `vigie`) that reads the NMEA 0183
output of a boat's AIS receiver over **one serial port** — the receiver is the only data
source (SPEC §3.3) — and exposes own-boat position/motion, AIS traffic and CPA/TCPA
collision-risk alerts. Phase P0 (AIS decoder) is done. Current work follows the SPEC §13
roadmap, one phase at a time.

## Sources of truth, in order

1. SPEC and TEST in `docs/`. When code and docs disagree, the docs win unless the
   owner decides otherwise.
2. The existing code — read it before proposing changes. Do not describe or assume code
   you have not opened.
3. Home Assistant developer docs for platform APIs (SPEC X-04).

## Hard rules

- **Clean room (SPEC §3.1).** Never copy code, structure or data files from
  `ha-smart0183serial` or any non-permissively licensed project. pyais (MIT) is allowed
  **only** as a test oracle/generator, never as a runtime dependency.
- **Layering (SPEC §5.1).** `custom_components/vigie/nmea/`, `state.py`, `geo.py`, `hub.py`
  and `traffic.py` are pure Python: **no `homeassistant` import**, not even indirectly. The CI test
  `tests/nmea/test_no_ha_import.py` enforces this; extend it to every new pure module.
  HA types in `__init__.py` stay under `TYPE_CHECKING`.
- **Scope.** Implement only what the current phase requires. No wind, depth, STW or
  performance features (SPEC §2.2, P4). No network listeners, no outbound traffic.
- **Open decisions.** Items marked OD-xx (SPEC §14) or TP-xx (TEST §10) are not yours to
  settle silently. If work depends on one, stop and ask, stating the options and your
  recommendation. If the owner decides, record it (see "Docs discipline").
- **Never weaken a gate** to get green: no lowering the coverage threshold, no
  `# type: ignore` / `noqa` without a one-line justification, no skipped tests without an
  issue reference.

## Engineering conventions

- Python 3.13 in CI. Pure modules must also run on 3.12; HA-side code follows the minimum HA
  version (2026.2.0, SPEC OD-06), which requires 3.13. Type hints everywhere; `mypy --strict`
  on pure modules (extend `[tool.mypy] files` in `pyproject.toml` as modules are added).
- Style: ruff (config in `pyproject.toml`), line length 100.
- asyncio only on the HA side; never block the event loop. File-system globbing (serial
  port discovery) runs in the executor.
- Units are normalised in parsers (knots, metres, °C, decimal degrees N/E positive);
  missing values are `None`, never `0`.
- Entities: `has_entity_name = True`, translation keys, unique IDs `{entry_id}_{key}`,
  `should_poll = False`, device classes and native units per SPEC §9. Every user-visible
  string exists in `strings.json`, `translations/en.json` and `translations/fr.json`.
- Diagnostics counters instead of log floods; log a given outage once (SPEC §10.3).

## Tests

- Every test that implements a TEST case carries its ID in the name or docstring,
  e.g. `test_u_gps_02_rmc_void_not_applied`. Update the TEST status column ("Done") in the
  same PR.
- Unit tests (`tests/nmea/`, `tests/domain/`) and hub tests (`tests/transport/`) never import
  Home Assistant.
- Functional tests (`tests/integration/`) use `pytest-homeassistant-custom-component==0.13.316`,
  a fake serial transport and the harness's time helpers — never real sleeps, never a real
  serial port.
- CPA/TCPA expected values come from TEST §3.4 (hand-computed), not from an oracle.
- Local gate before every push, identical to CI:

```bash
ruff check . && ruff format --check . && mypy
pytest --cov --cov-report=term-missing --cov-fail-under=90
```

## Git workflow (main is protected)

- One GitHub issue per work package, in the phase milestone, labelled `phase:Px` +
  `layer:*` (create with `gh issue create`).
- Branch `feat/<short-name>` / `fix/<short-name>` / `test/...` / `docs/...` from `main`.
- Conventional Commits. Small, reviewable PRs; body lists the SPEC sections and TEST IDs
  covered and ends with `Closes #<issue>`.
- Open PRs with `gh pr create`; never push to `main`, never force-push, never merge
  with red CI. Merging is the owner's call unless told otherwise.

## Docs discipline

Any change to behaviour, scope, entity model or a resolved decision updates the docs in
the same PR: bump the document version, add a changelog row, strike the resolved OD/TP
with its resolution, keep cross-references (X-xx) consistent between SPEC and TEST.
Update `CHANGELOG.md` (Keep a Changelog) under `[Unreleased]`.

## Useful facts

- Repo: `github.com/ovander/ha-vigie`. CI checks required on `main`: `lint`, `unit`,
  `hassfest`, `hacs`.
- Release: tag `vX.Y.Z` (pre-release `vX.Y.Z-beta.N`) → workflow builds `vigie.zip` and
  stamps the manifest version. Do not tag unless asked.
- Real captures of the receiver (SPEC X-09) are not in the repo yet. Until they are, use
  synthetic fixtures and mark the tests that need real data (`U-GPS-08`, `U-AIS-13`) as
  pending with a reference to issue #2.
- F-PERF tests carry `@pytest.mark.perf` and run nightly, not in the PR gate (TEST §7).
