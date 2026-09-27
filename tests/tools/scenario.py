"""D-07 traffic scenario generator (TEST-001 §2, §6).

Own boat and targets move in straight lines at constant speed. Output is the timed format
of TEST-001 §2 (`<epoch> <sentence>`, CRLF): own boat as `$GPRMC` every second, each target
as `!AIVDM` position reports at its own interval. Every sentence is synthetic.

AIS payloads are encoded with pyais (MIT), a test-only dependency (SPEC §3.1, X-08).

    python -m tests.tools.scenario --list
    python -m tests.tools.scenario --preset head-on -o head-on.nmea
    python -m tests.tools.scenario my-scenario.json --duration 900 -o out.nmea

JSON scenario (target positions relative to own start, in NM):

    {"own": {"lat": 43.5, "lon": 7.25, "sog": 6.0, "cog": 0.0},
     "duration_s": 900,
     "targets": [{"mmsi": 235000001, "east_nm": 0, "north_nm": 2, "sog": 6, "cog": 180,
                  "class": "A", "interval_s": 10, "nav_status": 0,
                  "name": "MOANA", "ship_type": 37, "callsign": "F1234", "imo": 0,
                  "dimensions": [9, 3, 2, 2], "draught_m": 1.8, "destination": "SETE",
                  "static_offset_s": 30, "static_interval_s": 360}]}

Static keys are optional; a target without any sends no static report. Class B targets
send type 24 parts A and B, and an auxiliary craft gives "mothership_mmsi" instead of
"dimensions".
"""

from __future__ import annotations

import argparse
import functools
import json
import math
import operator
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from pyais.encode import encode_dict

NM_PER_DEG_LAT = 60.0
DEFAULT_START_EPOCH = 1_790_000_000.0  # synthetic: 2026-09-21T13:33:20Z


@dataclass(frozen=True)
class Track:
    """Straight-line constant-speed track starting at (lat, lon)."""

    lat: float
    lon: float
    sog_kn: float
    cog_deg: float

    def at(self, t: float) -> tuple[float, float]:
        """Position after `t` seconds (flat-earth, adequate below 20 NM, SPEC §8.1)."""
        distance = self.sog_kn * t / 3600.0
        course = math.radians(self.cog_deg)
        return relative(
            self.lat, self.lon, distance * math.sin(course), distance * math.cos(course)
        )


@dataclass(frozen=True)
class Target:
    mmsi: int
    track: Track
    ais_class: str = "A"  # "A" → message type 1, "B" → type 18
    interval_s: float = 10.0
    nav_status: int = 0  # Class A only; 1 = at anchor, 5 = moored
    heading: int | None = None
    # Static data (P3): sent as type 5 (Class A) or type 24 parts A and B (Class B), first
    # after `static_offset_s`, then every `static_interval_s`; nothing when none is given
    name: str | None = None
    ship_type: int = 0
    callsign: str | None = None
    imo: int = 0
    dimensions: tuple[int, int, int, int] = (0, 0, 0, 0)  # to bow, stern, port, starboard
    draught_m: float = 0.0
    destination: str | None = None
    mothership_mmsi: int | None = None  # auxiliary craft (MMSI 98xxxxxxx), Class B
    static_offset_s: float = 30.0
    static_interval_s: float = 360.0

    @property
    def has_static(self) -> bool:
        return bool(
            self.name
            or self.ship_type
            or self.callsign
            or self.imo
            or any(self.dimensions)
            or self.mothership_mmsi
        )


@dataclass(frozen=True)
class Scenario:
    own: Track
    targets: tuple[Target, ...] = field(default_factory=tuple)
    duration_s: int = 900
    start_epoch: float = DEFAULT_START_EPOCH
    own_interval_s: float = 1.0


def relative(lat: float, lon: float, east_nm: float, north_nm: float) -> tuple[float, float]:
    """Position `east_nm`, `north_nm` away from (lat, lon), local flat-earth frame."""
    new_lat = lat + north_nm / NM_PER_DEG_LAT
    new_lon = lon + east_nm / (NM_PER_DEG_LAT * math.cos(math.radians(lat)))
    return new_lat, (new_lon + 180.0) % 360.0 - 180.0


def _checksum(body: str) -> str:
    return f"{functools.reduce(operator.xor, map(ord, body), 0):02X}"


def _ddmm(value: float, deg_digits: int) -> str:
    value = abs(value)
    degrees = int(value)
    minutes = (value - degrees) * 60.0
    if round(minutes, 4) >= 60.0:
        degrees, minutes = degrees + 1, 0.0
    return f"{degrees:0{deg_digits}d}{minutes:07.4f}"


def rmc(epoch: float, lat: float, lon: float, sog_kn: float, cog_deg: float) -> str:
    """Valid `$GPRMC` sentence with checksum."""
    when = datetime.fromtimestamp(epoch, UTC)
    body = (
        f"GPRMC,{when:%H%M%S}.{when.microsecond // 10000:02d},A,"
        f"{_ddmm(lat, 2)},{'N' if lat >= 0 else 'S'},{_ddmm(lon, 3)},{'E' if lon >= 0 else 'W'},"
        f"{sog_kn:.1f},{cog_deg % 360:.1f},{when:%d%m%y},,,A"
    )
    return f"${body}*{_checksum(body)}"


def vdm(target: Target, t: float) -> str:
    """`!AIVDM` position report of `target` at scenario time `t`."""
    lat, lon = target.track.at(t)
    msg: dict[str, object] = {
        "type": 18 if target.ais_class == "B" else 1,
        "mmsi": target.mmsi,
        "lat": round(lat, 6),
        "lon": round(lon, 6),
        "speed": round(target.track.sog_kn, 1),
        "course": round(target.track.cog_deg % 360, 1),
        "heading": 511 if target.heading is None else target.heading,
    }
    if target.ais_class != "B":
        msg["status"] = target.nav_status
    channel = "A" if int(t / target.interval_s) % 2 == 0 else "B"
    return str(encode_dict(msg, talker_id="AI", sentence_type="VDM", radio_channel=channel)[0])


def static_reports(target: Target) -> list[str]:
    """`!AIVDM` static report(s) of `target`: type 5, or type 24 parts A and B."""
    bow, stern, port, starboard = target.dimensions
    dims = {"to_bow": bow, "to_stern": stern, "to_port": port, "to_starboard": starboard}
    common = {"mmsi": target.mmsi, "ship_type": target.ship_type, "callsign": target.callsign or ""}
    if target.ais_class == "B":
        part_b = {"type": 24, "partno": 1, **common}
        part_b.update(
            {"mothership_mmsi": target.mothership_mmsi} if target.mothership_mmsi else dims
        )
        messages = [
            {"type": 24, "mmsi": target.mmsi, "partno": 0, "shipname": target.name or ""},
            part_b,
        ]
    else:
        messages = [
            {
                "type": 5,
                **common,
                "shipname": target.name or "",
                "imo": target.imo,
                "draught": target.draught_m,
                "destination": target.destination or "",
                **dims,
            }
        ]
    return [
        str(line)
        for msg in messages
        for line in encode_dict(msg, talker_id="AI", sentence_type="VDM", radio_channel="A")
    ]


def generate(scenario: Scenario) -> list[tuple[float, str]]:
    """Timed sentences of the whole scenario, sorted by time."""
    lines: list[tuple[float, str]] = []
    steps = int(scenario.duration_s / scenario.own_interval_s)
    for i in range(steps + 1):
        t = i * scenario.own_interval_s
        lat, lon = scenario.own.at(t)
        lines.append(
            (
                scenario.start_epoch + t,
                rmc(scenario.start_epoch + t, lat, lon, scenario.own.sog_kn, scenario.own.cog_deg),
            )
        )
    for target in scenario.targets:
        for i in range(int(scenario.duration_s / target.interval_s) + 1):
            t = i * target.interval_s
            # Just after the own-boat sentence of the same second
            lines.append((scenario.start_epoch + t + 0.001, vdm(target, t)))
        if not target.has_static:
            continue
        t = target.static_offset_s
        while t <= scenario.duration_s:
            for k, sentence in enumerate(static_reports(target)):
                lines.append((scenario.start_epoch + t + 0.002 + k * 0.001, sentence))
            t += target.static_interval_s
    lines.sort(key=lambda line: line[0])
    return lines


def format_timed(lines: list[tuple[float, str]]) -> str:
    return "".join(f"{t:.3f} {sentence}\r\n" for t, sentence in lines)


def _preset(duration: int, *targets: tuple[float, float, float, float, int]) -> Scenario:
    """TEST §3.4 geometry: own boat at origin heading 000° at 6 kn.

    Each target is (east NM, north NM, SOG kn, COG °, nav status), MMSIs 235000001 upwards.
    """
    own = Track(43.5, 7.25, 6.0, 0.0)
    built = []
    for index, (east, north, sog, cog, status) in enumerate(targets):
        lat, lon = relative(own.lat, own.lon, east, north)
        built.append(Target(235000001 + index, Track(lat, lon, sog, cog), nav_status=status))
    return Scenario(own, tuple(built), duration)


# U-TRF-05: relative velocity (−6, −5) kn with own (0, 6) → target (−6, 1) kn
_NOT_URGENT = (2.0, 2.0, math.hypot(6.0, 1.0), math.degrees(math.atan2(-6.0, 1.0)) % 360, 0)
_HEAD_ON = (0.0, 2.0, 6.0, 180.0, 0)
_CROSSING = (1.0, 0.0, 12.0, 270.0, 0)
_ANCHORED = (0.0, 0.4, 0.0, 0.0, 1)  # nav status 1: at anchor
_OVERTAKING = (0.0, 1.0, 4.0, 0.0, 0)

# Durations run past every target's TCPA, so each alert both fires and clears (E-02)
PRESETS: dict[str, Scenario] = {
    "head-on": _preset(900, _HEAD_ON),
    "clear-crossing": _preset(600, (1.0, 0.0, 6.0, 270.0, 0)),
    "crossing": _preset(600, _CROSSING),
    "overtaking": _preset(2400, _OVERTAKING),
    "not-urgent": _preset(1500, _NOT_URGENT),
    "diverging": _preset(600, (0.0, -1.0, 3.0, 0.0, 0)),
    "parallel": _preset(600, (0.3, 0.0, 6.0, 0.0, 0)),
    "anchored": _preset(600, _ANCHORED),
    "multi-target": _preset(2400, _HEAD_ON, _CROSSING, _ANCHORED, _OVERTAKING),
}


def _named_traffic() -> Scenario:
    """P3 bench (TEST §5): named targets of both classes; names arrive 30 s after positions."""
    own = Track(43.5, 7.25, 6.0, 0.0)

    def at(east: float, north: float, sog: float, cog: float) -> Track:
        return Track(*relative(own.lat, own.lon, east, north), sog, cog)

    return Scenario(
        own,
        (
            # Class A cargo crossing ahead: CPA 0.45 NM, TCPA 16 min; a threat from 1 min
            Target(
                235000011,
                at(3.0, 2.0, 12.0, 270.0),
                name="CARGO ONE",
                ship_type=70,
                callsign="ABCD",
                imo=9123456,
                dimensions=(150, 30, 15, 15),
                draught_m=8.5,
                destination="MARSEILLE",
            ),
            # Class B yacht passing clear astern, and its tender (auxiliary craft)
            Target(
                235000012,
                at(-1.0, 0.0, 4.0, 90.0),
                "B",
                30.0,
                name="ALBATROS",
                ship_type=36,
                callsign="FAB1234",
                dimensions=(8, 4, 2, 2),
            ),
            Target(
                982350001,
                at(-1.0, 0.05, 4.0, 90.0),
                "B",
                30.0,
                name="ALBATROS TENDER",
                ship_type=37,
                mothership_mmsi=235000012,
            ),
            # No static data: stays unnamed
            Target(235000014, at(4.0, 0.0, 6.0, 0.0)),
        ),
        1200,
    )


PRESETS["named-traffic"] = _named_traffic()

# What the bench operator should see at the start (TEST §3.4, default thresholds 0.5 NM, 15 min)
PRESET_REFERENCE: dict[str, str] = {
    "head-on": "U-TRF-01  CPA 0.00 NM, TCPA 10.0 min, threat",
    "clear-crossing": "U-TRF-02  CPA 0.71 NM, TCPA 5.0 min, no threat (CPA)",
    "crossing": "U-TRF-03  CPA 0.45 NM, TCPA 4.0 min, threat",
    "overtaking": "U-TRF-04  CPA 0.00 NM, TCPA 30.0 min, no threat until TCPA < 15 min",
    "not-urgent": "U-TRF-05  CPA 0.26 NM, TCPA 21.6 min, threat once TCPA < 15 min (≈ 6.6 min in)",
    "diverging": "U-TRF-06  no CPA, TCPA negative, no threat",
    "parallel": "U-TRF-07  CPA 0.30 NM (current distance), no TCPA, no threat",
    "anchored": "U-TRF-08  CPA 0.00 NM, TCPA 4.0 min, no threat (anchored, excluded by default)",
    "multi-target": "U-TRF-11  4 targets; closest threat 235000002 (crossing, TCPA 4.0 min), "
    "then 235000001 (head-on), then 235000004 (overtaking); 235000003 anchored, never a threat",
    "named-traffic": "P3 bench  names from 30 s: CARGO ONE (cargo, 180 m, threat from 1 min), "
    "ALBATROS (sailing, 12 m) and ALBATROS TENDER (pleasure craft); 235000014 unnamed",
}


def load(path: Path) -> Scenario:
    spec = json.loads(path.read_text(encoding="utf-8"))
    own_spec = spec["own"]
    own = Track(own_spec["lat"], own_spec["lon"], own_spec["sog"], own_spec["cog"])
    targets = []
    for t in spec.get("targets", []):
        lat, lon = relative(own.lat, own.lon, t.get("east_nm", 0.0), t.get("north_nm", 0.0))
        targets.append(
            Target(
                mmsi=int(t["mmsi"]),
                track=Track(lat, lon, t["sog"], t["cog"]),
                ais_class=t.get("class", "A"),
                interval_s=float(t.get("interval_s", 10.0)),
                nav_status=int(t.get("nav_status", 0)),
                heading=t.get("heading"),
                name=t.get("name"),
                ship_type=int(t.get("ship_type", 0)),
                callsign=t.get("callsign"),
                imo=int(t.get("imo", 0)),
                dimensions=tuple(t.get("dimensions", (0, 0, 0, 0))),
                draught_m=float(t.get("draught_m", 0.0)),
                destination=t.get("destination"),
                mothership_mmsi=t.get("mothership_mmsi"),
                static_offset_s=float(t.get("static_offset_s", 30.0)),
                static_interval_s=float(t.get("static_interval_s", 360.0)),
            )
        )
    return Scenario(
        own,
        tuple(targets),
        int(spec.get("duration_s", 900)),
        float(spec.get("start_epoch", DEFAULT_START_EPOCH)),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("scenario", nargs="?", type=Path, help="JSON scenario file")
    parser.add_argument("--preset", choices=sorted(PRESETS), help="built-in scenario")
    parser.add_argument("--list", action="store_true", help="list the presets and exit")
    parser.add_argument("--duration", type=int, help="override the duration in seconds")
    parser.add_argument("-o", "--output", type=Path, help="output file (default: stdout)")
    args = parser.parse_args(argv)
    if args.list:
        width = max(map(len, PRESETS))
        for name, reference in PRESET_REFERENCE.items():
            print(f"{name:<{width}}  {reference}")
        return 0
    if (args.scenario is None) == (args.preset is None):
        parser.error("give either a scenario file or --preset")
    scenario = PRESETS[args.preset] if args.preset else load(args.scenario)
    if args.duration is not None:
        scenario = Scenario(
            scenario.own,
            scenario.targets,
            args.duration,
            scenario.start_epoch,
            scenario.own_interval_s,
        )
    text = format_timed(generate(scenario))
    if args.output:
        args.output.write_bytes(text.encode("ascii"))
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
