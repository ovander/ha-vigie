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
- Anchor watch: swing radius, dragging and position-lost alarm, distance to the anchor.

## Collision alert automation

`binary_sensor.<boat>_collision_risk` turns **on** when a target is predicted to pass closer
than the CPA threshold (default 0.5 NM) within the TCPA threshold (default 15 min). Once on,
it stays on for 60 s after the last threat, or turns off at once when every threat has
passed, so an automation on it runs once per encounter. Its attributes name the most urgent
target (`mmsi`, `name`) and count the threats (`threat_count`). Thresholds are in the
integration's options.

**The simplest way: the blueprint.** Click
[![Import blueprint](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fovander%2Fha-vigie%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Fvigie%2Fcollision_alert.yaml),
confirm the import, then **Create automation**: pick your boat's *Collision risk* sensor, your phone (the Home Assistant
companion app) and whether the alert is critical (on by default: it rings even when the phone
is silenced; on iOS, allow critical alerts for the companion app). Save. Nothing to type.

The same automation written by hand, for a boat named *Garnet* and the Home Assistant companion app
(replace `mobile_app_my_phone` with your phone's notify service):

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

## Anchor watch

Turn on `switch.<boat>_anchor_watch` when the anchor is down: the anchor point is the
boat's position at that moment, so turn it on while you are above the anchor, or give the
anchor's position yourself with the `vigie.drop_anchor` action (for example read on the
chartplotter). Set the swing radius on `number.<boat>_anchor_radius` (10–500 m, default
50 m): chain out plus boat length plus a margin for GPS noise.

The boat has usually dropped back by the time the watch is turned on, so the circle is
centred a chain length from the anchor. Move it without restarting the watch with
`vigie.drop_anchor` and `keep_since: true` and the anchor's position: the time at anchor
and the radius are kept, the largest distance starts again. The anchor card below does it
for you, from the swing or by tapping the map. A recentering is refused while the anchor
alarm is on.

`binary_sensor.<boat>_anchor_alarm` turns on when

- the boat has stayed outside the radius for 20 s (*Dragging*). It stays on until you
  turn the watch off or drop the anchor again, even if the boat swings back inside;
- no position has been received for 60 s while the watch is on (*Position lost*). It
  clears by itself when a position inside the radius comes back.

Both delays are options. `sensor.<boat>_anchor_distance` shows the distance to the anchor,
with the bearing and the largest distance since the anchor was dropped. The watch, the
anchor point and an alarm that is on survive a restart of Home Assistant or a power cut.

**The simplest way: the blueprint.** Click
[![Import blueprint](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fovander%2Fha-vigie%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Fvigie%2Fanchor_alarm.yaml),
confirm the import, then **Create automation**: pick your boat's *Anchor alarm* sensor, your phone (the Home Assistant
companion app) and whether the alert is critical (on by default: it rings even when the phone
is silenced; on iOS, allow critical alerts for the companion app). Save. Nothing to type.

The same automation written by hand, for a boat named *Garnet* (same phone as above):

```yaml
automation:
  - alias: "Vigie: anchor alarm"
    mode: single
    triggers:
      - trigger: state
        entity_id: binary_sensor.garnet_anchor_alarm
        to: "on"
    actions:
      - action: notify.mobile_app_my_phone
        data:
          title: "⚓ Anchor alarm"
          message: >-
            {% if state_attr('binary_sensor.garnet_anchor_alarm', 'reason') == 'drag' %}
            Dragging: {{ states('sensor.garnet_anchor_distance', rounded=True) }} m
            from the anchor (radius {{ states('number.garnet_anchor_radius') | int }} m).
            {% else %}
            No position from the receiver: check the GPS and the power.
            {% endif %}
          data:
            ttl: 0
            priority: high
            push:
              interruption-level: critical
```

To see the boat swing around its anchor, add a map card with the boat and the anchor
point (the `latitude`/`longitude` of `sensor.<boat>_anchor_distance`). The boat and the
anchor are only metres apart: `cluster: false` keeps two markers instead of one numbered
bubble, and `default_zoom: 18` lets the card zoom in close enough to separate them:

```yaml
type: map
title: Anchor
hours_to_show: 2
auto_fit: true
cluster: false
default_zoom: 18
entities:
  - entity: device_tracker.garnet
  - entity: sensor.garnet_anchor_distance
    label_mode: icon
```

For the cockpit, the **anchor card** of
[Vigie cards](https://github.com/ovander/ha-vigie-card) (`custom:vigie-anchor-card`, the
same HACS download as the traffic map below, 0.2.0-beta.1 or later) shows the watch's
state in large type, the distance against the radius with a gauge, the swing circle and
your boat, and has three buttons: **Drop anchor here**, **Raise anchor** (only after a
confirmation) and the radius **−** / **+**. After 10 minutes at anchor, **Recenter** moves
the circle to the centre of the swing, where the anchor is; **Move the anchor** lets you
tap it on the map. Both show the new circle and ask before changing anything. One line is
enough:

```yaml
type: custom:vigie-anchor-card
switch: switch.garnet_anchor_watch
```

The card makes no sound: the automation above, with its critical notification, is what
wakes the crew.

As for collisions, the anchor watch is an aid: keep a watch on deck.

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

### Traffic map card

The traffic map of [Vigie cards](https://github.com/ovander/ha-vigie-card)
(`custom:vigie-traffic-card`, installed separately through HACS, category *Dashboard*)
draws that full picture: every target oriented on its course, threats in red with their
point of closest approach, range rings, the anchor and its swing circle, your boat's
position, speed and course, details on tap. It has a visual editor:

```yaml
type: custom:vigie-traffic-card
entity: sensor.garnet_ais_targets
own: device_tracker.garnet
collision_risk: binary_sensor.garnet_collision_risk
anchor: sensor.garnet_anchor_distance
```

Like the rest of Vigie, it is an aid to awareness, not a navigation display.

### Ready-made Vigie dashboard

The simplest way to see both cards: once *Vigie cards* is downloaded (its README walks
through it step by step), create a dashboard (*Settings → Dashboards → + Add dashboard →
New dashboard from scratch*), open it, click the pencil, then **⋮ → Raw configuration
editor**, and replace everything with:

```yaml
strategy:
  type: custom:vigie
```

The dashboard finds your boat by itself and shows the traffic map and the anchor card,
one tab per boat; nothing to rename. Needs Vigie cards
0.2.0-beta.4 or later.

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

### Changing the serial port or the baud rate

Settings → Devices & services → **Vigie** → ⋮ → **Reconfigure**: pick another port (a
`/dev/serial/by-id/…` path, a typed one, or `socket://<computer>:<port>` for the bench) or
another baud rate. Vigie listens up to 5 s to check it, as at setup, then restarts on it;
the entities, their history, the options and the anchor watch are kept. A port another
Vigie boat uses is refused.

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
| P5 | Anchor watch | built; bench and on-board checks pending |
| P6 | AIS traffic map card (every target on one map) | built ([ha-vigie-card](https://github.com/ovander/ha-vigie-card)); bench check pending |
| P7 | Anchor card (the anchor watch in the cockpit, with drop / raise / radius) | in progress ([ha-vigie-card](https://github.com/ovander/ha-vigie-card)) |
| P8 | Sharing the boat's track on noforeignland, kept through internet outages (separate integration [ha-noforeignland](https://github.com/ovander/ha-noforeignland); Vigie stays offline) | built; live checks wait for noforeignland's key |

## Documentation

- [Technical specification](docs/HA-SAIL-SPEC-001.md)
- [Test protocol](docs/HA-SAIL-TEST-001.md)
- [Contributing](CONTRIBUTING.md)

## License

Apache-2.0. The AIS decoder is a clean-room implementation of the public
[AIVDM/AIVDO protocol description](https://gpsd.gitlab.io/gpsd/AIVDM.html) (gpsd).
