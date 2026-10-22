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
| `python -m tests.tools.scenario --preset head-on -o head-on.nmea` | D-07 scenario: own boat as `$GPRMC` (1 Hz) and targets as `!AIVDM`, timed format `<epoch> <sentence>`. One preset per TEST §3.4 geometry (`--list` shows them with their expected CPA/TCPA), plus `named-traffic` with AIS static data (P3); custom scenarios as JSON, targets optionally with static data (see the module docstring). |
| `python -m tests.tools.replay FILE --pty /tmp/ttyAIS [--speed 10] [--loop]` | Replays a timed or plain capture into a pseudo-terminal linked at `/tmp/ttyAIS`. Configure Vigie on that path. |
| `python -m tests.tools.replay FILE --device /dev/ttyUSB1 --baud 38400` | Same, into a real serial adapter (null-modem to the HA host) or one end of a socat pair. |
| `python -m tests.tools.replay FILE --tcp 10110 [--loop]` | Same, served over TCP from this computer (Mac, PC, Linux): set Vigie's serial port to `socket://<this computer's IP>:10110`. No cable; one client at a time, each from the start of the file. |
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
host, one on a laptop running `replay ... --device /dev/ttyUSBx --baud 38400`. A second
Raspberry Pi can take the laptop's place: see the two-Pi bench below.

### Two-Pi bench (HA OS on the target Pi)

Runs every bench check on the boat's own hardware: the HA Pi runs HA OS with Vigie from
HACS, a second Pi with Raspberry Pi OS plays the scenarios into a serial link.

```
 Bench Pi (Raspberry Pi OS)                         HA Pi (HA OS + Vigie)
 replay --device … --baud 38400                     Vigie entry "Bench" on that port
 [USB-serial adapter] TX ──────────────────────► RX [USB-serial adapter]
                      GND ─────────────────────── GND
```

**Link.** Either of:

- an FTDI USB null-modem cable (two USB-serial chips back to back, TX/RX already crossed,
  e.g. FTDI *USB-NMC-2.5M*): plug-and-play, each Pi sees `/dev/serial/by-id/usb-FTDI_…`;
- two 3.3 V USB-to-TTL adapters (FT232 or CP2102) and jumper wires: bench TX → HA RX and
  GND ↔ GND (data flows one way; crossing the other pair does no harm). The bench Pi's own
  UART can replace its adapter: GPIO pin 8 (TXD) and pin 6 (GND), enabled with
  `sudo raspi-config` → Interface Options → Serial Port → login shell **No**, serial
  hardware **Yes**, reboot; the port is then `/dev/serial0`.

A plain USB A-to-A cable does not work (two USB hosts; it only ties the 5 V supplies
together), and "USB data link" cables do not appear as serial ports. Use 3.3 V TTL only:
never wire an RS-232 adapter (±12 V) to a Pi's GPIO pins.

**Bench Pi.** The bench tools need only `pyserial` and `pyais`:

```bash
sudo apt install -y git python3-venv
sudo usermod -aG dialout $USER     # once, then log out and back in
git clone https://github.com/ovander/ha-vigie && cd ha-vigie
git checkout v0.2.0-beta.1         # the release installed on the HA Pi
python3 -m venv .venv && . .venv/bin/activate
pip install pyserial pyais
for p in head-on crossing clear-crossing not-urgent anchored multi-target named-traffic anchor-drag; do
  python -m tests.tools.scenario --preset $p -o $p.nmea
done
python -m tests.tools.scenario --preset multi-target --duration 3600 -o long.nmea
ls -l /dev/serial/by-id/           # the adapter; nothing listed: try another cable (some carry power only)
python -m tests.tools.replay head-on.nmea --baud 38400 --loop \
  --device /dev/serial/by-id/usb-FTDI_FT232R_USB_UART_XXXXXXXX-if00-port0
```

Type the real device name (Tab completes it after `/dev/serial/by-id/u`): a placeholder
such as `<adapter>` is read by bash as a redirection.

**HA Pi.** Keep the entry on the real AIS receiver. Add a second one for the bench, with the
replay running: Settings → Devices & services → Add integration → Vigie, boat name
*Bench*, the bench adapter's `/dev/serial/by-id/…` (not the receiver's), 38400 baud. Its
entities are `…bench_…`. Give the bench its own copies of the README automations, with the
`bench` entity IDs, so bench alerts are labelled as such on the phone.

**What it covers, and what differs from the container recipe:**

- E-02 (six presets), the P3 check (`named-traffic`, watch list 235000011 and 235000012 on
  the *Bench* entry), E-03 (`long.nmea` without `--loop`), E-06 and E-07 (`anchor-drag`,
  P5 bench above) run as written.
- E-05 measures HA OS on the Pi itself: replay `tests/fixtures/burst_60s.nmea --speed 1`
  and read the CPU under Settings → System → Hardware.
- E-04 differs on a real link: stopping the replay is *silence* on an open port, not a lost
  port. After about 10 s the *Bench* entities go unavailable while `connected` stays on,
  which is correct. To test the reconnect path, unplug the adapter from the HA Pi for 30 s
  instead: `connected` turns off, then Vigie recovers within about a minute.
- Note in the report that the bench was HA OS on a Raspberry Pi with a serial link.

### E-02 traffic bench (TEST-001 §5.1)

Same bench as E-1, with the README's collision-alert automation installed and the companion
app on a phone. Generate the presets (`python -m tests.tools.scenario --list`, then
`--preset NAME -o NAME.nmea`), replay each once at real speed without `--loop`, and fill in
the table in `docs/test-reports/P2-report.md` §5.

### P3 bench (named targets)

Same bench, with the MMSIs 235000011 and 235000012 on the watch list and the README map
card on a dashboard: replay `--preset named-traffic` once and fill in
`docs/test-reports/P3-report.md` §5.

### P5 bench (anchor watch, E-07)

Same bench, with the README's anchor-alarm automation installed and
`sensor.<boat>_anchor_distance` added to the map card. The simulated boat lies 30 m from
its anchor, so drop the anchor at the preset's coordinates, not with the switch: in
Developer tools → Actions, run `vigie.drop_anchor` with latitude 43.5, longitude 7.25 and
radius 50, then replay `--preset anchor-drag` once at real speed (15 min). The alarm is due
at 698 s (`--list`). Fill in `docs/test-reports/P5-report.md` §5.

### Network bench from a laptop (`--tcp`)

Home Assistant anywhere on the network (HA OS on a Pi, a VM, a container), the scenarios
on a Mac or PC, no serial cable:

1. On the laptop, in the repository with the test requirements installed:
   `python -m tests.tools.scenario --preset anchor-drag -o anchor-drag.nmea`, then
   `python -m tests.tools.replay anchor-drag.nmea --tcp 10110`. On macOS, allow incoming
   connections for Python if the firewall asks.
2. In Home Assistant, add Vigie (or reconfigure the bench boat) with the serial port
   `socket://<laptop IP>:10110` (any baud rate).
3. The replay starts when Vigie connects, and starts again from the beginning if Vigie
   reconnects (Home Assistant restarted, the entry reloaded). Without `--loop` the tool
   stops after one full replay: Vigie then sees the port gone.

For the anchor card (P7, E-09): with the anchor card on a dashboard, start the replay (Vigie
connects at once) and within a few seconds run `vigie.drop_anchor` at 43.5, 7.25 with
radius 50 (Developer tools → Actions), then watch the swing, *Outside the circle* at 678 s and *Dragging* at 698 s. To try
recentering, drop it 20 m north instead (latitude 43.50018) and press *Recenter* after
10 minutes: the circle moves back to 43.5, 7.25. Checklist in
`docs/test-reports/P7-report.md` §5.2.

## Workflow

1. Open or pick an issue (label it with its phase and layer).
2. Branch from `main`, open a PR referencing the issue.
3. CI must be green (lint, unit, hassfest, hacs). Squash-merge.
4. Releases are tags `vX.Y.Z` (pre-releases `vX.Y.Z-beta.N`); the release workflow builds
   `vigie.zip` and stamps the version into `manifest.json`.

Commit messages follow Conventional Commits (`feat:`, `fix:`, `test:`, `docs:`, `chore:`).
