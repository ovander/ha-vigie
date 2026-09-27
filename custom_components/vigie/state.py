"""Domain core: own-boat state, AIS target table, write gating (SPEC §7.4, §9.4, §10.2).

Pure Python, no Home Assistant import (SPEC NFR-02); the HA coordinator wraps these
classes. Every class takes an injectable monotonic `clock` for deterministic tests.
"""

from __future__ import annotations

import math
import time
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from .geo import distance_m, distance_nm
from .nmea.ais_decoder import VesselPosition
from .nmea.parsers import Gga, GpsRecord, Gsa, Hdt, Rmc, Vtg

Clock = Callable[[], float]

# Own-boat state keys
POSITION = "position"  # (latitude, longitude)
SOG = "sog"
COG = "cog"
HEADING = "heading"
UTC_TIME = "utc"
VARIATION = "variation"
FIX_QUALITY = "fix_quality"
SATELLITES = "satellites"
HDOP = "hdop"
FIX_MODE = "fix_mode"
PDOP = "pdop"

# Tolerance for comparisons that should be exact on paper (0.1 kn, 1 s…)
_EPS = 1e-9

# Class A targets expire as slowly as Class B when they report being stationary
_SLOW_NAV_STATUS = frozenset({"at_anchor", "moored"})


class Source(StrEnum):
    GPS = "gps"
    VDO = "vdo"


@dataclass(frozen=True, slots=True)
class FieldValue:
    value: Any
    updated_at: float  # clock time of the update
    source: Source
    sentence: str  # "RMC", "GGA", "VTG", "GSA", "HDT" or "VDO"


class OwnBoatState:
    """Own-boat fields with per-field timestamp and source (SPEC §7.4).

    GPS and VDO values are stored separately. `get()` returns the GPS value while it is
    fresh, else the VDO value while it is fresh, else None. A field is fresh while its
    age is at most `stale_timeout_s`. Missing values in a record never overwrite
    known ones: they simply age out.
    """

    def __init__(
        self,
        stale_timeout_s: float = 10.0,
        *,
        use_vdo: bool = True,
        own_mmsi: int | None = None,
        clock: Clock = time.monotonic,
    ) -> None:
        self._stale = stale_timeout_s
        self._use_vdo = use_vdo
        self._configured_mmsi = own_mmsi
        self._learned_mmsi: int | None = None
        self._clock = clock
        self._fields: dict[Source, dict[str, FieldValue]] = {Source.GPS: {}, Source.VDO: {}}

    @property
    def own_mmsi(self) -> int | None:
        """Configured own MMSI, else the one learned from VDO reports."""
        if self._configured_mmsi is not None:
            return self._configured_mmsi
        return self._learned_mmsi

    @property
    def position_source(self) -> Source | None:
        pos = self.get(POSITION)
        return pos.source if pos else None

    def get(self, key: str) -> FieldValue | None:
        now = self._clock()
        sources = (Source.GPS, Source.VDO) if self._use_vdo else (Source.GPS,)
        for source in sources:
            fv = self._fields[source].get(key)
            if fv is not None and now - fv.updated_at <= self._stale + _EPS:
                return fv
        return None

    def apply_gps(self, rec: GpsRecord) -> frozenset[str]:
        """Merge a GPS record; return the keys it updated."""
        values: dict[str, Any] = {}
        if isinstance(rec, Rmc):
            values[UTC_TIME] = rec.utc
            values[VARIATION] = rec.variation_deg
            if rec.valid:
                values[POSITION] = _position(rec.latitude, rec.longitude)
                values[SOG] = rec.sog_knots
                values[COG] = rec.cog_deg
        elif isinstance(rec, Gga):
            values[POSITION] = _position(rec.latitude, rec.longitude)
            values[FIX_QUALITY] = rec.fix_quality
            values[SATELLITES] = rec.satellites
            values[HDOP] = rec.hdop
        elif isinstance(rec, Vtg):
            values[SOG] = rec.sog_knots
            values[COG] = rec.cog_deg
        elif isinstance(rec, Gsa):
            values[FIX_MODE] = rec.fix_mode
            values[PDOP] = rec.pdop
        elif isinstance(rec, Hdt):
            values[HEADING] = rec.heading_deg
        return self._store(Source.GPS, type(rec).__name__.upper(), values)

    def apply_vdo(self, pos: VesselPosition) -> frozenset[str]:
        """Merge an own-ship VDO report; VDM reports and disabled VDO are ignored."""
        if not pos.own_ship or not self._use_vdo:
            return frozenset()
        self._learned_mmsi = pos.mmsi
        values = {
            POSITION: _position(pos.latitude, pos.longitude),
            SOG: pos.sog_knots,
            COG: pos.cog_deg,
            HEADING: pos.heading_deg,
        }
        return self._store(Source.VDO, "VDO", values)

    def _store(self, source: Source, sentence: str, values: dict[str, Any]) -> frozenset[str]:
        now = self._clock()
        updated = frozenset(k for k, v in values.items() if v is not None)
        for key in updated:
            self._fields[source][key] = FieldValue(values[key], now, source, sentence)
        return updated


def _position(lat: float | None, lon: float | None) -> tuple[float, float] | None:
    return None if lat is None or lon is None else (lat, lon)


# --- AIS target table --------------------------------------------------------


@dataclass(slots=True)
class AisTarget:
    mmsi: int
    ais_class: str  # "A" or "B"
    report: VesselPosition  # latest position report
    name: str | None  # kept when later reports carry none
    last_seen: float  # clock time of the latest report


class AisTargetTable:
    """Live AIS targets keyed by MMSI, with class-dependent expiry (SPEC §9.4)."""

    def __init__(
        self,
        expiry_a_s: float = 600.0,
        expiry_b_s: float = 900.0,
        *,
        clock: Clock = time.monotonic,
    ) -> None:
        self._expiry_a = expiry_a_s
        self._expiry_b = expiry_b_s
        self._clock = clock
        self._targets: dict[int, AisTarget] = {}

    def __len__(self) -> int:
        return len(self._targets)

    def __contains__(self, mmsi: object) -> bool:
        return mmsi in self._targets

    def get(self, mmsi: int) -> AisTarget | None:
        return self._targets.get(mmsi)

    def targets(self) -> list[AisTarget]:
        return list(self._targets.values())

    def upsert(self, pos: VesselPosition, own_mmsi: int | None = None) -> bool:
        """Insert or update a target; own-ship reports and the own MMSI are refused."""
        if pos.own_ship or pos.mmsi == own_mmsi:
            return False
        previous = self._targets.get(pos.mmsi)
        name = pos.name or (previous.name if previous else None)
        self._targets[pos.mmsi] = AisTarget(pos.mmsi, pos.ais_class, pos, name, self._clock())
        return True

    def expire(self) -> list[int]:
        """Remove targets not heard within their expiry; return the removed MMSIs."""
        now = self._clock()
        stale = [
            mmsi for mmsi, t in self._targets.items() if now - t.last_seen > self._expiry(t) + _EPS
        ]
        for mmsi in stale:
            del self._targets[mmsi]
        return stale

    def nearest(
        self, lat: float | None, lon: float | None, limit: int = 50
    ) -> list[tuple[AisTarget, float | None]]:
        """Targets with their distance (NM) from (lat, lon), nearest first, capped.

        Targets without a position, or all targets when own position is unknown, get
        distance None and are listed after the others, most recently heard first.
        """
        by_recency = sorted(self._targets.values(), key=lambda t: t.last_seen, reverse=True)
        located: list[tuple[AisTarget, float | None]] = []
        unlocated: list[tuple[AisTarget, float | None]] = []
        for t in by_recency:
            r = t.report
            if lat is None or lon is None or r.latitude is None or r.longitude is None:
                unlocated.append((t, None))
            else:
                located.append((t, distance_nm(lat, lon, r.latitude, r.longitude)))
        located.sort(key=lambda item: item[1] if item[1] is not None else math.inf)
        return (located + unlocated)[:limit]

    def _expiry(self, t: AisTarget) -> float:
        slow = t.ais_class == "B" or t.report.nav_status in _SLOW_NAV_STATUS
        return self._expiry_b if slow else self._expiry_a


# --- Write gating --------------------------------------------------------------


def angle_delta(a: float, b: float) -> float:
    """Smallest difference between two angles in degrees (359° → 1° is 2°)."""
    d = abs(a - b) % 360.0
    return min(d, 360.0 - d)


def position_delta_m(a: tuple[float, float], b: tuple[float, float]) -> float:
    """Distance in metres between two (latitude, longitude) positions."""
    return distance_m(a[0], a[1], b[0], b[1])


def _abs_delta(a: float, b: float) -> float:
    return abs(a - b)


class WriteGate:
    """Decide whether an entity writes its state now (SPEC §10.2, NFR-04).

    At most one write per `interval_s`. A value is written when it differs from the last
    *written* value by at least `deadband` (measured with `delta`), or when it changes
    to or from None. Without a dead-band, any change is written.
    """

    def __init__(
        self,
        interval_s: float = 1.0,
        deadband: float | None = None,
        *,
        delta: Callable[[Any, Any], float] = _abs_delta,
        clock: Clock = time.monotonic,
    ) -> None:
        self._interval = interval_s
        self._deadband = deadband
        self._delta = delta
        self._clock = clock
        self._written = False
        self._last_value: Any = None
        self._last_time = 0.0

    def reset(self) -> None:
        """Forget the last write: the next call writes whatever it gets."""
        self._written = False

    def should_write(self, value: Any) -> bool:
        now = self._clock()
        if self._written:
            if now - self._last_time < self._interval - _EPS:
                return False
            if not self._changed(value):
                return False
        self._written = True
        self._last_value = value
        self._last_time = now
        return True

    def _changed(self, value: Any) -> bool:
        last = self._last_value
        if value is None or last is None or self._deadband is None:
            return bool(value != last)
        return self._delta(value, last) >= self._deadband - _EPS
