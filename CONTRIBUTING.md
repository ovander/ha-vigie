# Contributing to Vigie

## Clean-room rule

Vigie is written from public specifications only. **Do not copy code, structure or data
files from other NMEA/AIS integrations whose license does not allow it** — in particular
`ha-smart0183serial`, which is under a proprietary license (SPEC §3.1). Permissively
licensed libraries (e.g. pyais, MIT) may be used as test oracles; say so in the PR.

## Development setup

```bash
python3.13 -m venv .venv && source .venv/bin/activate
pip install -r requirements_test.txt
ruff check . && ruff format --check . && mypy
pytest --cov --cov-fail-under=90
```

## Architecture rules

- `custom_components/vigie/nmea/` is pure Python: **no Home Assistant import** (checked in CI).
- Each layer depends only on the layer below (SPEC §5.1).
- Every change to behaviour references the spec section or open decision it implements.

## Tests

Three levels — unit, functional, end-to-end — defined in `docs/HA-SAIL-TEST-001.md`.
A bug found at a higher level gets a regression test at the lowest level that reproduces it.

## Workflow

1. Open or pick an issue (label it with its phase and layer).
2. Branch from `main`, open a PR referencing the issue.
3. CI must be green (lint, unit, hassfest, hacs). Squash-merge.
4. Releases are tags `vX.Y.Z` (pre-releases `vX.Y.Z-beta.N`); the release workflow builds
   `vigie.zip` and stamps the version into `manifest.json`.

Commit messages follow Conventional Commits (`feat:`, `fix:`, `test:`, `docs:`, `chore:`).
