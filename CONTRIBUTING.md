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
pytest --cov --cov-report=term-missing --cov-fail-under=90
```

## Architecture rules

- `nmea/`, `state.py`, `geo.py`, `hub.py` (and `traffic.py` in P2) are pure Python: **no Home
  Assistant import** (checked in CI).
- Each layer depends only on the layer below (SPEC §5.1).
- Every change to behaviour references the spec section or open decision it implements.

## Tests

Three levels — unit, functional, end-to-end — defined in `docs/HA-SAIL-TEST-001.md`.
A bug found at a higher level gets a regression test at the lowest level that reproduces it.

### Test tooling (`tests/tools/`, test-only)

Run from the repository root with the test requirements installed.

| Tool | Use |
|---|---|
| `python -m tests.tools.scenario --preset head-on -o head-on.nmea` | D-07 scenario: own boat as `$GPRMC` (1 Hz) and targets as `!AIVDM`, timed format `<epoch> <sentence>`. Presets `head-on` (U-TRF-01) and `crossing` (U-TRF-03); custom scenarios as JSON (see the module docstring). |
| `python -m tests.tools.replay FILE --pty /tmp/ttyAIS [--speed 10] [--loop]` | Replays a timed or plain capture into a pseudo-terminal linked at `/tmp/ttyAIS`. Configure Vigie on that path. |
| `python -m tests.tools.replay FILE --device /dev/ttyUSB1 --baud 38400` | Same, into a real serial adapter (null-modem to the HA host) or one end of a socat pair. |
| `python -m tests.tools.capture --port /dev/serial/by-id/... --baud 38400 --duration 900` | Raw timestamped capture of the receiver (X-09) into `captures/` (git-ignored). Stop Vigie first; anonymise before committing (TEST-001 TP-03). |

`F-PERF` tests are marked `perf`: `pytest -m perf` runs them; they are excluded by default and
run nightly (`.github/workflows/nightly.yml`).

### E-1 replay bench (TEST-001 §5.1)

Home Assistant **Container** on a Linux host (a Raspberry Pi with Raspberry Pi OS for E-05).

1. Start the feed on the host: `python -m tests.tools.replay head-on.nmea --pty /tmp/ttyAIS --loop`.
   It prints the `/dev/pts/N` behind the link.
2. Give the container that device, e.g. `--device /dev/pts/N:/dev/ttyAIS` (Docker) or a
   bind-mount of `/dev/pts` plus the link; restart the container after re-creating the PTY.
3. Install Vigie from the release tag through HACS, add the integration on `/dev/ttyAIS`.
4. E-04: stop the replay (Ctrl-C), wait 30 s, start it again (same device mapping).

For E-01 on HA OS, wire two USB-serial adapters null-modem (TX↔RX, GND↔GND): one on the HA
host, one on a laptop running `replay ... --device /dev/ttyUSBx --baud 38400`.

## Workflow

1. Open or pick an issue (label it with its phase and layer).
2. Branch from `main`, open a PR referencing the issue.
3. CI must be green (lint, unit, hassfest, hacs). Squash-merge.
4. Releases are tags `vX.Y.Z` (pre-releases `vX.Y.Z-beta.N`); the release workflow builds
   `vigie.zip` and stamps the version into `manifest.json`.

Commit messages follow Conventional Commits (`feat:`, `fix:`, `test:`, `docs:`, `chore:`).
