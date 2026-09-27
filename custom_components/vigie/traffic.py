"""Traffic logic: CPA/TCPA, threat classification, risk latch (SPEC §8, C-05).

Pure Python, no Home Assistant import (SPEC NFR-02). Distances in nautical miles,
speeds in knots, times in minutes (TCPA) or seconds (clock, dead reckoning).

Geometry: positions are projected on a local east/north plane around own position
(equirectangular, cosine of the mean latitude), accurate to well under 0.5 % up to
20 NM (SPEC §8.1, U-TRF-09). Both vessels are dead-reckoned from their report times to
`now` before CPA/TCPA are computed (SPEC §8.3, OD-16).
"""

from __future__ import annotations

import math
import time
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, replace

from .geo import bearing_deg, distance_nm

NM_PER_DEG_LAT = 60.0
# Below this relative speed TCPA is undefined and CPA is the current distance (SPEC §8.1)
MIN_RELATIVE_SPEED_KN = 0.1
# Class A targets at anchor or moored and slower than this are not threats (SPEC §8.2)
STATIONARY_SOG_KN = 0.5
STATIONARY_NAV_STATUS = frozenset({"at_anchor", "moored"})


@dataclass(frozen=True, slots=True)
class Kinematics:
    """A vessel's last report: position, motion, and the clock time of the report."""

    lat: float | None
    lon: float | None
    sog_kn: float | None
    cog_deg: float | None
    at: float  # clock time of the report, seconds

    @property
    def has_position(self) -> bool:
        return self.lat is not None and self.lon is not None

    @property
    def has_motion(self) -> bool:
        return self.sog_kn is not None and self.cog_deg is not None

    def dead_reckoned(self, now: float) -> Kinematics:
        """Position projected to `now` along SOG/COG; unchanged without motion data."""
        if not (self.has_position and self.has_motion) or now == self.at:
            return replace(self, at=now)
        assert self.lat is not None and self.lon is not None  # has_position
        assert self.sog_kn is not None and self.cog_deg is not None  # has_motion
        distance = self.sog_kn * (now - self.at) / 3600.0
        course = math.radians(self.cog_deg)
        lat, lon = displace(
            self.lat, self.lon, distance * math.sin(course), distance * math.cos(course)
        )
        return replace(self, lat=lat, lon=lon, at=now)


@dataclass(frozen=True, slots=True)
class Encounter:
    distance_nm: float
    bearing_deg: float  # true bearing from own boat to the target
    cpa_nm: float | None  # None when diverging (TCPA < 0) or motion unknown
    tcpa_min: float | None  # negative when diverging; None when undefined or unknown

    @property
    def passed(self) -> bool:
        """The closest point of approach lies in the past (diverging)."""
        return self.tcpa_min is not None and self.tcpa_min < 0


@dataclass(frozen=True, slots=True)
class ThreatSettings:
    cpa_nm: float = 0.5
    tcpa_min: float = 15.0
    exclude_stationary: bool = True


def displace(lat: float, lon: float, east_nm: float, north_nm: float) -> tuple[float, float]:
    """Position `east_nm`, `north_nm` away from (lat, lon) on the local plane."""
    new_lat = lat + north_nm / NM_PER_DEG_LAT
    mean_lat = math.radians((lat + new_lat) / 2)
    new_lon = lon + east_nm / (NM_PER_DEG_LAT * math.cos(mean_lat))
    return new_lat, _wrap_lon(new_lon)


def local_offset_nm(lat0: float, lon0: float, lat: float, lon: float) -> tuple[float, float]:
    """(east, north) of (lat, lon) seen from (lat0, lon0), in NM on the local plane."""
    dlon = _wrap_lon(lon - lon0)
    mean_lat = math.radians((lat0 + lat) / 2)
    return dlon * NM_PER_DEG_LAT * math.cos(mean_lat), (lat - lat0) * NM_PER_DEG_LAT


def _wrap_lon(lon: float) -> float:
    return (lon + 180.0) % 360.0 - 180.0


def _velocity(k: Kinematics) -> tuple[float, float]:
    assert k.sog_kn is not None and k.cog_deg is not None
    course = math.radians(k.cog_deg)
    return k.sog_kn * math.sin(course), k.sog_kn * math.cos(course)


def encounter(own: Kinematics, target: Kinematics, now: float | None = None) -> Encounter | None:
    """Geometry of one target relative to own boat (SPEC §8.1).

    With `now`, both are first dead-reckoned to that time (OD-16). Returns None when either
    position is unknown; CPA/TCPA are None when either motion is unknown (U-TRF-10).
    """
    if not (own.has_position and target.has_position):
        return None
    if now is not None:
        own, target = own.dead_reckoned(now), target.dead_reckoned(now)
    assert own.lat is not None and own.lon is not None
    assert target.lat is not None and target.lon is not None
    distance = distance_nm(own.lat, own.lon, target.lat, target.lon)
    bearing = bearing_deg(own.lat, own.lon, target.lat, target.lon)
    if not (own.has_motion and target.has_motion):
        return Encounter(distance, bearing, None, None)

    px, py = local_offset_nm(own.lat, own.lon, target.lat, target.lon)
    (tx, ty), (ox, oy) = _velocity(target), _velocity(own)
    vx, vy = tx - ox, ty - oy
    speed2 = vx * vx + vy * vy
    if speed2 < MIN_RELATIVE_SPEED_KN**2:
        return Encounter(distance, bearing, math.hypot(px, py), None)
    tcpa_h = -(px * vx + py * vy) / speed2
    if tcpa_h < 0:
        return Encounter(distance, bearing, None, tcpa_h * 60.0)
    cpa = math.hypot(px + vx * tcpa_h, py + vy * tcpa_h)
    return Encounter(distance, bearing, cpa, tcpa_h * 60.0)


def is_threat(
    e: Encounter, settings: ThreatSettings, *, nav_status: str | None, sog_kn: float | None
) -> bool:
    """CPA < threshold and 0 ≤ TCPA < threshold, stationary Class A excluded (SPEC §8.2)."""
    if e.cpa_nm is None or e.tcpa_min is None:
        return False
    if (
        settings.exclude_stationary
        and nav_status in STATIONARY_NAV_STATUS
        and (sog_kn or 0.0) < STATIONARY_SOG_KN
    ):
        return False
    return e.cpa_nm < settings.cpa_nm and 0.0 <= e.tcpa_min < settings.tcpa_min


def closest_threat[K](items: Iterable[tuple[K, Encounter]]) -> tuple[K, Encounter] | None:
    """Most urgent threat: smallest TCPA, then smallest CPA (U-TRF-11)."""

    def urgency(item: tuple[K, Encounter]) -> tuple[float, float]:
        e = item[1]
        return (
            e.tcpa_min if e.tcpa_min is not None else math.inf,
            e.cpa_nm if e.cpa_nm is not None else math.inf,
        )

    return min(items, key=urgency, default=None)


class RiskLatch:
    """State of `collision_risk` with anti-flapping (OD-15).

    On as soon as a threat exists. Once on, it stays on until no threat has been seen
    for `hold_s` seconds, except that it clears at once when every target that was a
    threat during this episode has passed its CPA (TCPA < 0).
    """

    def __init__(self, hold_s: float = 60.0, clock: Callable[[], float] = time.monotonic) -> None:
        self._hold = hold_s
        self._clock = clock
        self._active = False
        self._episode: set[int] = set()
        self._last_threat = 0.0

    @property
    def active(self) -> bool:
        return self._active

    def update(self, threats: set[int], encounters: Mapping[int, Encounter]) -> bool:
        """Feed the current threat MMSIs and every target's encounter; return the state."""
        now = self._clock()
        if threats:
            self._active = True
            self._episode |= threats
            self._last_threat = now
        elif self._active:
            passed = all(mmsi in encounters and encounters[mmsi].passed for mmsi in self._episode)
            if passed or now - self._last_threat >= self._hold - 1e-9:
                self._active = False
                self._episode = set()
        return self._active
