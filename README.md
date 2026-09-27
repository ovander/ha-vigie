# Vigie

**AIS traffic watch and collision alerts for Home Assistant.**

Vigie reads the NMEA 0183 output of a boat's AIS receiver over a serial port and turns it
into Home Assistant entities: own position and motion, surrounding AIS traffic, and
CPA/TCPA collision-risk alerts you can use in automations. Local only, no cloud.

> **Status: pre-alpha (phase P1 in progress).** The integration reads the receiver and creates
> own-boat, AIS traffic and diagnostic entities; it has not yet been checked against a real
> receiver. Collision alerts (CPA/TCPA) arrive in P2. See the roadmap below.

## ⚠️ Safety

Vigie is an **aid to watchkeeping, not a collision-avoidance system**. AIS does not show
every vessel, reports can be late or wrong, and CPA/TCPA assume constant course and speed.
Keep a proper lookout at all times (COLREGs Rule 5).

## What it will provide (v1)

- Own boat: position (device tracker), speed and course over ground, GNSS health.
- AIS traffic: number of targets, nearest target, a compact target list for map cards.
- Collision risk: CPA/TCPA of the most urgent target and a `collision_risk` binary sensor.
- Watch list: device trackers for chosen MMSIs (friends' boats, tender…).

## Requirements

- Home Assistant OS or Container with access to the receiver's serial port
  (USB adapter; prefer `/dev/serial/by-id/...`).
- An AIS receiver or Class B transponder with NMEA 0183 output (typically 38 400 baud).
- Do not run another integration on the same serial port.

## Installation (HACS)

1. HACS → ⋮ → Custom repositories → add `https://github.com/ovander/ha-vigie`, category *Integration*.
2. Install **Vigie**, restart Home Assistant.
3. Settings → Devices & services → Add integration → **Vigie**.

## Roadmap

| Phase | Content | Status |
|---|---|---|
| P0 | AIS decoder (Class A 1/2/3, Class B 18/19) | ✅ done |
| P1 | Serial transport, GPS parsing, own-boat entities, AIS target table | in progress |
| P2 | CPA/TCPA, collision-risk alert, watch-list trackers | planned |
| P3 | AIS static data (names, types, dimensions) | planned |
| P4 | Additional instruments (wind, depth) and sailing performance | later |

## Documentation

- [Technical specification](docs/HA-SAIL-SPEC-001.md)
- [Test protocol](docs/HA-SAIL-TEST-001.md)
- [Contributing](CONTRIBUTING.md)

## License

Apache-2.0. The AIS decoder is a clean-room implementation of the public
[AIVDM/AIVDO protocol description](https://gpsd.gitlab.io/gpsd/AIVDM.html) (gpsd).
