# Vigie

**AIS traffic watch and collision alerts for Home Assistant.**

Vigie reads the NMEA 0183 output of a boat's AIS receiver over a serial port and turns it
into Home Assistant entities: own position and motion, surrounding AIS traffic, and
CPA/TCPA collision-risk alerts you can use in automations. Local only, no cloud.

> **Status: pre-alpha (phase P3).** The integration reads the receiver and creates own-boat,
> AIS traffic, collision-risk and diagnostic entities, with ship names, types and sizes. It
> has been tested on synthetic data only; the checks on board with a real receiver are
> still to do. See the roadmap below.

## ⚠️ Safety

Vigie is an **aid to watchkeeping, not a collision-avoidance system**. AIS does not show
every vessel, reports can be late or wrong, and CPA/TCPA assume constant course and speed.
Keep a proper lookout at all times (COLREGs Rule 5).

In particular, `collision_risk` stays **off** for a vessel without AIS, for a target the
receiver has not heard, and for an anchored or moored Class A target (unless you turn that
exclusion off). It is **unavailable**, not off, while own position is unknown. Never rely on
it as your only alarm.

## What it will provide (v1)

- Own boat: position (device tracker), speed and course over ground, GNSS health.
- AIS traffic: number of targets, nearest target, a compact target list for map cards.
- Collision risk: CPA/TCPA of the most urgent target and a `collision_risk` binary sensor.
- Watch list: device trackers for chosen MMSIs (friends' boats, tender…).
- Ship details from AIS static data: name, ship type, size, call sign, destination.

## Collision alert automation

`binary_sensor.<boat>_collision_risk` turns **on** when a target is predicted to pass closer
than the CPA threshold (default 0.5 NM) within the TCPA threshold (default 15 min). Once on,
it stays on for 60 s after the last threat, or turns off at once when every threat has
passed, so an automation on it runs once per encounter. Its attributes name the most urgent
target (`mmsi`, `name`) and count the threats (`threat_count`). Thresholds are in the
integration's options.

Example for a boat named *Garnet* and the Home Assistant companion app (replace
`mobile_app_my_phone` with your phone's notify service):

```yaml
automation:
  - alias: "Vigie: collision risk"
    mode: single
    triggers:
      - trigger: state
        entity_id: binary_sensor.garnet_collision_risk
        to: "on"
    actions:
      - action: notify.mobile_app_my_phone
        data:
          title: "⚠️ Collision risk"
          message: >-
            {% set r = 'binary_sensor.garnet_collision_risk' %}
            {{ state_attr(r, 'name') or 'MMSI ' ~ state_attr(r, 'mmsi') }}:
            CPA {{ states('sensor.garnet_closest_threat_cpa', rounded=True) }} NM
            in {{ states('sensor.garnet_closest_threat_tcpa', rounded=True) }} min.
            Check the lookout.
          data:
            ttl: 0            # Android: deliver now
            priority: high
            push:             # iOS: sound even when silenced (needs critical-alert permission)
              interruption-level: critical
```

Do not add `from: "off"`: the sensor is `unavailable` until own position is known, so the
first alert after start-up, or after a GPS outage, comes as `unavailable` → `on` and would be
missed. The price is a repeated alert when own position returns during an encounter.

### Recorder

Traffic entities change often. The `targets` list of `sensor.<boat>_ais_targets` is never
recorded, but its count and the watch-list trackers are. To spare an SD card, exclude what
you do not need in history, for example:

```yaml
recorder:
  exclude:
    entities:
      - sensor.garnet_ais_targets
      - sensor.garnet_closest_target_distance
```

Keep `binary_sensor.<boat>_collision_risk` recorded: its history shows when alerts fired.

## Ship details

AIS ships send their name, type and size every 6 minutes, apart from their positions, so
a new target can stay unnamed for a few minutes. Vigie keeps these details for 30 minutes
after the last report. `collision_risk`, the closest target and closest threat sensors
and the watch-list trackers carry them as attributes:

| Attribute | Content |
|---|---|
| `name` | Ship name |
| `ship_type` | Category, shown translated: sailing, pleasure craft, cargo, tanker, passenger, fishing, tug, high-speed craft… |
| `ship_type_code` | AIS ship type code (0–99) |
| `callsign`, `imo` | Radio call sign; IMO number (large ships) |
| `length_m`, `beam_m`, `draught_m` | Size in metres (draught: Class A only) |
| `destination` | Destination as entered by the crew (Class A only) |

A value is empty when the ship has not sent it. The `targets` list of
`sensor.<boat>_ais_targets` carries `ship_type` and `length_m` for every target.

## Map card

Home Assistant's built-in map card shows your boat and the watched targets (watch list in
the integration's options), each with its track. Replace the MMSIs with yours:

```yaml
type: map
title: Traffic
hours_to_show: 1
auto_fit: true
entities:
  - entity: device_tracker.garnet
  - entity: device_tracker.ais_235000011
    label_mode: attribute
    attribute: name
  - entity: device_tracker.ais_235000012
    label_mode: attribute
    attribute: name
```

`label_mode: attribute` labels each target with its ship name. Without it, every watched
target shows the same initials ("A2", from "AIS 2…"). A target shows no label until its
name has been received.

The built-in card can only draw entities, so it does not show every AIS target: the full
picture (up to the 50 nearest targets, with position, CPA and TCPA) is in the `targets`
attribute of `sensor.<boat>_ais_targets`, for cards that read attributes.

## Requirements

- Home Assistant 2026.2.0 or later.
- Home Assistant OS or Container with access to the receiver's serial port
  (USB adapter; prefer `/dev/serial/by-id/...`).
- An AIS receiver or Class B transponder with NMEA 0183 output (typically 38 400 baud).
- Do not run another integration on the same serial port.

## Installation (HACS)

1. HACS → ⋮ → Custom repositories → add `https://github.com/ovander/ha-vigie`, category
   *Integration*.
2. Open **Vigie** in HACS and download it. Vigie is in beta and HACS hides beta versions by
   default: in the download dialog, turn on **Show beta versions** and pick the latest
   `v…-beta.N`. Without it, HACS finds no release to install.
3. Restart Home Assistant (Settings → System → ⋮ → Restart Home Assistant).
4. Reload the browser page with a hard refresh (Ctrl+F5, or Cmd+Shift+R on a Mac); in the
   companion app, Settings → Companion app → Troubleshooting → Reset frontend cache.
   Otherwise the list of integrations can come from the browser's cache and miss Vigie.
5. Settings → Devices & services → Add integration → **Vigie**.

### If Vigie does not appear in "Add integration"

- **Version in HACS:** HACS → Vigie should show a `v…-beta.N` version. A commit ID or nothing
  installed means step 2 missed the beta version: ⋮ → Redownload with beta versions shown.
- **Files:** `/config/custom_components/vigie/` must exist and contain `manifest.json` with
  that version (check with the File editor, Samba or SSH add-on).
- **Home Assistant version:** Settings → About must show 2026.2.0 or later.
- **Log:** Settings → System → Logs, search for `vigie`. Include those lines if you open an
  issue.

## Roadmap

| Phase | Content | Status |
|---|---|---|
| P0 | AIS decoder (Class A 1/2/3, Class B 18/19) | ✅ done |
| P1 | Serial transport, GPS parsing, own-boat entities, AIS target table | built; on-board checks pending |
| P2 | CPA/TCPA, collision-risk alert, watch-list trackers | built; bench and on-board checks pending |
| P3 | AIS static data (names, types, dimensions), map card | built; on-board checks pending |
| P4 | Additional instruments (wind, depth) and sailing performance | later |

## Documentation

- [Technical specification](docs/HA-SAIL-SPEC-001.md)
- [Test protocol](docs/HA-SAIL-TEST-001.md)
- [Contributing](CONTRIBUTING.md)

## License

Apache-2.0. The AIS decoder is a clean-room implementation of the public
[AIVDM/AIVDO protocol description](https://gpsd.gitlab.io/gpsd/AIVDM.html) (gpsd).
