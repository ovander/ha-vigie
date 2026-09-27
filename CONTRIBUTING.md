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
| `python -m tests.tools.scenario --preset head-on -o head-on.nmea` | D-07 scenario: own boat as `$GPRMC` (1 Hz) and targets as `!AIVDM`, timed format `<epoch> <sentence>`. One preset per TEST §3.4 geometry (`--list` shows them with their expected CPA/TCPA); custom scenarios as JSON (see the module docstring). |
| `python -m tests.tools.replay FILE --pty /tmp/ttyAIS [--speed 10] [--loop]` | Replays a timed or plain capture into a pseudo-terminal linked at `/tmp/ttyAIS`. Configure Vigie on that path. |
| `python -m tests.tools.replay FILE --device /dev/ttyUSB1 --baud 38400` | Same, into a real serial adapter (null-modem to the HA host) or one end of a socat pair. |
| `python -m tests.tools.capture --port /dev/serial/by-id/... --baud 38400 --duration 900` | Raw timestamped capture of the receiver (X-09) into `captures/` (git-ignored). Stop Vigie first; anonymise before committing (TEST-001 TP-03). |

`F-PERF` tests are marked `perf`: `pytest -m perf` runs them; they are excluded by default and
run nightly (`.github/workflows/nightly.yml`).

### E-1 replay bench (TEST-001 §5.1)

Home Assistant **Container** on a Linux host (a Raspberry Pi with Raspberry Pi OS for E-05).

1. Start the feed on the host, with the link in its own folder:
   `python -m tests.tools.replay head-on.nmea --pty /srv/vigie-bench/ttyAIS --loop`.
2. Start the container with the link folder and `/dev/pts` bind-mounted at the same paths,
   and the pseudo-terminals allowed (Unix98 PTYs have character major 136):

   ```bash
   docker run -d --name ha --network host -v /srv/ha-config:/config \
     -v /srv/vigie-bench:/srv/vigie-bench -v /dev/pts:/dev/pts \
     --device-cgroup-rule='c 136:* rmw' ghcr.io/home-assistant/home-assistant:stable
   ```

   Mapping one device with `--device /dev/pts/N:/dev/ttyAIS` also works, but only until the
   replay is restarted: a new PTY may get another number, which breaks E-04.
3. Install Vigie from the release tag through HACS, add the integration on
   `/srv/vigie-bench/ttyAIS` at 38 400 baud.
4. E-04: stop the replay (Ctrl-C), wait 30 s, start it again with the same command. Vigie
   retries at 1, 3, 7, 15, 31, 63 s after the loss and then every 60 s, so recovery can take
   up to a minute after the feed is back.

For E-01 on HA OS, wire two USB-serial adapters null-modem (TX↔RX, GND↔GND): one on the HA
host, one on a laptop running `replay ... --device /dev/ttyUSBx --baud 38400`.

### E-02 traffic bench (TEST-001 §5.1)

Same bench as E-1, with the README's collision-alert automation installed and the companion
app on a phone. Generate the presets (`python -m tests.tools.scenario --list`, then
`--preset NAME -o NAME.nmea`), replay each once at real speed without `--loop`, and fill in
the table in `docs/test-reports/P2-report.md` §5.

## Workflow

1. Open or pick an issue (label it with its phase and layer).
2. Branch from `main`, open a PR referencing the issue.
3. CI must be green (lint, unit, hassfest, hacs). Squash-merge.
4. Releases are tags `vX.Y.Z` (pre-releases `vX.Y.Z-beta.N`); the release workflow builds
   `vigie.zip` and stamps the version into `manifest.json`.

Commit messages follow Conventional Commits (`feat:`, `fix:`, `test:`, `docs:`, `chore:`).
