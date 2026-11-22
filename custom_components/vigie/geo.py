"""Spherical geometry helpers: distance and bearing (SPEC §8.1).

Pure standard library, no Home Assistant import (SPEC NFR-02). Positions are
decimal degrees, N/E positive.
"""

from __future__ import annotations

import math

EARTH_RADIUS_M = 6_371_008.8  # IUGG mean radius
METRES_PER_NM = 1852.0


def distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in metres (haversine)."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = phi2 - phi1
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlmb / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(min(1.0, math.sqrt(a)))


def distance_nm(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in nautical miles."""
    return distance_m(lat1, lon1, lat2, lon2) / METRES_PER_NM


def bearing_deg(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Initial true bearing from point 1 to point 2, in [0, 360)."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dlmb = math.radians(lon2 - lon1)
    y = math.sin(dlmb) * math.cos(phi2)
    x = math.cos(phi1) * math.sin(phi2) - math.sin(phi1) * math.cos(phi2) * math.cos(dlmb)
    return math.degrees(math.atan2(y, x)) % 360.0


def format_dm(lat: float, lon: float) -> str:
    """Position in degrees and decimal minutes, as on a chartplotter (#111):
    `43° 30.000′ N 7° 15.500′ E`. Minutes to three decimals (about 2 m), point as the
    decimal separator whatever the language; 59.9996′ rounds up to the next degree."""
    return f"{_dm(lat, 'N', 'S')} {_dm(lon, 'E', 'W')}"


def _dm(value: float, positive: str, negative: str) -> str:
    thousandths = round(abs(value) * 60_000)  # minutes × 1000, rounded once
    degrees, rest = divmod(thousandths, 60_000)
    hemisphere = positive if value >= 0 else negative
    return f"{degrees}° {rest / 1000:06.3f}′ {hemisphere}"
