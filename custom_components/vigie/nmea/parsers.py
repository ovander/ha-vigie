"""Typed decoding of the GPS sentences emitted by the receiver's GNSS (SPEC §7.2).

Supported: RMC, GGA, VTG, GSA, HDT, whatever the talker ID. Units are normalised here:
knots, degrees, decimal degrees (N/E positive), magnetic variation E positive.
Empty fields give None, never 0. Malformed sentences raise SentenceError("format").
Pure standard library, no I/O.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum

from .sentence import Sentence, SentenceError, check_frame, parse_sentence, split_tag_block

_KMH_PER_KNOT = 1.852


class FixQuality(StrEnum):
    """GGA fix quality indicator (field 6)."""

    NO_FIX = "no_fix"
    GPS = "gps"
    DGPS = "dgps"
    PPS = "pps"
    RTK = "rtk"
    FLOAT_RTK = "float_rtk"
    ESTIMATED = "estimated"
    MANUAL = "manual"
    SIMULATION = "simulation"


_FIX_QUALITY = dict(enumerate(FixQuality))


class FixMode(StrEnum):
    """GSA fix type (field 2)."""

    NO_FIX = "no_fix"
    FIX_2D = "2d"
    FIX_3D = "3d"


_FIX_MODE = {"1": FixMode.NO_FIX, "2": FixMode.FIX_2D, "3": FixMode.FIX_3D}


@dataclass(frozen=True, slots=True)
class Rmc:
    talker: str
    valid: bool  # status "A" and mode indicator not "N"
    latitude: float | None  # None when not valid
    longitude: float | None
    sog_knots: float | None
    cog_deg: float | None  # true
    utc: datetime | None
    variation_deg: float | None  # E positive


@dataclass(frozen=True, slots=True)
class Gga:
    talker: str
    latitude: float | None  # None when fix quality is 0
    longitude: float | None
    fix_quality: FixQuality | None
    satellites: int | None
    hdop: float | None


@dataclass(frozen=True, slots=True)
class Vtg:
    talker: str
    cog_deg: float | None  # true
    cog_magnetic_deg: float | None
    sog_knots: float | None


@dataclass(frozen=True, slots=True)
class Gsa:
    talker: str
    fix_mode: FixMode | None
    pdop: float | None
    hdop: float | None
    vdop: float | None


@dataclass(frozen=True, slots=True)
class Hdt:
    talker: str
    heading_deg: float | None  # true


GpsRecord = Rmc | Gga | Vtg | Gsa | Hdt

Fields = tuple[str | None, ...]


# --- Field helpers ----------------------------------------------------------


def _bad(message: str) -> SentenceError:
    return SentenceError("format", message)


def _need(fields: Fields, count: int, name: str) -> None:
    if len(fields) < count:
        raise _bad(f"{name}: expected at least {count} fields, got {len(fields)}")


def _float(raw: str | None, lo: float = -math.inf, hi: float = math.inf) -> float | None:
    if raw is None:
        return None
    try:
        value = float(raw)
    except ValueError as exc:
        raise _bad(f"not a number: {raw!r}") from exc
    if not math.isfinite(value) or not lo <= value <= hi:
        raise _bad(f"value out of range: {raw!r}")
    return value


def _int(raw: str | None) -> int | None:
    if raw is None:
        return None
    if not raw.isdigit():
        raise _bad(f"not an integer: {raw!r}")
    return int(raw)


def _angle(raw: str | None) -> float | None:
    return _float(raw, 0.0, 360.0)


def _coordinate(raw: str | None, hemi: str | None, deg_digits: int, axis: str) -> float | None:
    """Convert '(d)ddmm.mmm' plus hemisphere to signed decimal degrees."""
    if raw is None and hemi is None:
        return None
    positive, negative = ("N", "S") if axis == "lat" else ("E", "W")
    limit = 90.0 if axis == "lat" else 180.0
    if raw is None or hemi not in (positive, negative):
        raise _bad(f"invalid {axis} hemisphere {hemi!r}")
    whole, _, frac = raw.partition(".")
    if not (3 <= len(whole) <= deg_digits + 2 and whole.isdigit() and (frac.isdigit() or not frac)):
        raise _bad(f"invalid {axis} {raw!r}")
    minutes = float(whole[-2:] + "." + (frac or "0"))
    value = int(whole[:-2]) + minutes / 60.0
    if minutes >= 60.0 or value > limit:
        raise _bad(f"{axis} out of range {raw!r}")
    return -value if hemi == negative else value


def _utc(time_raw: str | None, date_raw: str | None) -> datetime | None:
    if time_raw is None or date_raw is None:
        return None
    whole, _, frac = time_raw.partition(".")
    if len(whole) != 6 or len(date_raw) != 6 or not (whole + date_raw).isdigit():
        raise _bad(f"invalid date/time {date_raw!r} {time_raw!r}")
    if frac and not frac.isdigit():
        raise _bad(f"invalid time {time_raw!r}")
    try:
        return datetime(
            2000 + int(date_raw[4:6]),  # two-digit year → 20yy (SPEC §7.2)
            int(date_raw[2:4]),
            int(date_raw[0:2]),
            int(whole[0:2]),
            int(whole[2:4]),
            int(whole[4:6]),
            round(float("0." + frac) * 1_000_000) if frac else 0,
            tzinfo=UTC,
        )
    except ValueError as exc:
        raise _bad(f"invalid date/time {date_raw!r} {time_raw!r}") from exc


def _mode_valid(fields: Fields, index: int) -> bool:
    """NMEA 2.3+ mode indicator: 'N' means data not valid."""
    return len(fields) <= index or fields[index] != "N"


# --- Sentence decoders -------------------------------------------------------


def _rmc(talker: str, f: Fields) -> Rmc:
    _need(f, 11, "RMC")
    if f[1] not in ("A", "V"):
        raise _bad(f"RMC: invalid status {f[1]!r}")
    var = _float(f[9], 0.0, 180.0)
    if var is not None:
        if f[10] not in ("E", "W"):
            raise _bad(f"RMC: invalid variation direction {f[10]!r}")
        var = -var if f[10] == "W" else var
    utc = _utc(f[0], f[8])
    lat = _coordinate(f[2], f[3], 2, "lat")
    lon = _coordinate(f[4], f[5], 3, "lon")
    sog = _float(f[6], 0.0)
    cog = _angle(f[7])
    if f[1] != "A" or not _mode_valid(f, 11):  # void: never applied (U-GPS-02)
        return Rmc(talker, False, None, None, None, None, utc, var)
    return Rmc(talker, True, lat, lon, sog, cog, utc, var)


def _gga(talker: str, f: Fields) -> Gga:
    _need(f, 8, "GGA")
    q = _int(f[5])
    if q is not None and q not in _FIX_QUALITY:
        raise _bad(f"GGA: unknown fix quality {q}")
    quality = _FIX_QUALITY[q] if q is not None else None
    lat = _coordinate(f[1], f[2], 2, "lat")
    lon = _coordinate(f[3], f[4], 3, "lon")
    if quality in (None, FixQuality.NO_FIX):
        lat = lon = None
    return Gga(talker, lat, lon, quality, _int(f[6]), _float(f[7], 0.0))


def _vtg(talker: str, f: Fields) -> Vtg:
    if len(f) >= 8:  # NMEA 2.x+: course,T,course,M,speed,N,speed,K[,mode]
        for index, unit in ((1, "T"), (3, "M"), (5, "N"), (7, "K")):
            if f[index] not in (unit, None):
                raise _bad(f"VTG: expected unit {unit!r}, got {f[index]!r}")
        cog, mag, knots, kmh = f[0], f[2], f[4], f[6]
        valid = _mode_valid(f, 8)
    elif len(f) == 4:  # legacy NMEA 1.5: course,course,speed,speed
        cog, mag, knots, kmh = f
        valid = True
    else:
        raise _bad(f"VTG: unexpected field count {len(f)}")
    sog = _float(knots, 0.0)
    if sog is None and (speed_kmh := _float(kmh, 0.0)) is not None:
        sog = speed_kmh / _KMH_PER_KNOT
    true_course, magnetic = _angle(cog), _angle(mag)
    if not valid:
        return Vtg(talker, None, None, None)
    return Vtg(talker, true_course, magnetic, sog)


def _gsa(talker: str, f: Fields) -> Gsa:
    _need(f, 17, "GSA")
    if f[1] is not None and f[1] not in _FIX_MODE:
        raise _bad(f"GSA: invalid fix type {f[1]!r}")
    mode = _FIX_MODE[f[1]] if f[1] is not None else None
    return Gsa(talker, mode, _float(f[14], 0.0), _float(f[15], 0.0), _float(f[16], 0.0))


def _hdt(talker: str, f: Fields) -> Hdt:
    _need(f, 1, "HDT")
    if len(f) > 1 and f[1] not in ("T", None):
        raise _bad(f"HDT: expected unit 'T', got {f[1]!r}")
    return Hdt(talker, _angle(f[0]))


_DECODERS: dict[str, Callable[[str, Fields], GpsRecord]] = {
    "RMC": _rmc,
    "GGA": _gga,
    "VTG": _vtg,
    "GSA": _gsa,
    "HDT": _hdt,
}


def parse_gps(sentence: Sentence) -> GpsRecord | None:
    """Decode a checksum-valid '$' sentence; None when the type is not supported."""
    decoder = _DECODERS.get(sentence.sentence_type)
    if sentence.start != "$" or sentence.talker == "P" or decoder is None:
        return None
    return decoder(sentence.talker, sentence.fields)


class GpsParser:
    """Feed raw lines with feed(); returns a GpsRecord or None.

    Mirrors AisDecoder: never raises, counts outcomes in `stats` ("ok", "ignored",
    "rejected", plus "checksum" and "framing" as subsets of "rejected").
    """

    def __init__(self) -> None:
        self.stats = {"ok": 0, "ignored": 0, "rejected": 0, "checksum": 0, "framing": 0}

    def feed(self, line: str) -> GpsRecord | None:
        try:
            line = check_frame(line.strip())
            record = parse_gps(parse_sentence(split_tag_block(line)[1]))
        except SentenceError as exc:
            self.stats["rejected"] += 1
            if exc.kind != "format":
                self.stats[exc.kind] += 1
            return None
        self.stats["ok" if record else "ignored"] += 1
        return record
