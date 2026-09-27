"""GPS parsers — U-GPS-01…08 (TEST §3.2, SPEC §7.2).

All sentences are synthetic (built with a computed checksum) except REF_RMC, the public
reference example from the NMEA 0183 documentation.
"""

from datetime import UTC, datetime

import pytest

from custom_components.vigie.nmea.parsers import (
    FixMode,
    FixQuality,
    Gga,
    GpsParser,
    Gsa,
    Hdt,
    Rmc,
    Vtg,
    parse_gps,
)
from custom_components.vigie.nmea.sentence import SentenceError, parse_sentence
from tests.helpers import nmea

REF_RMC = "$GPRMC,123519,A,4807.038,N,01131.000,E,022.4,084.4,230394,003.1,W*6A"


def _parse(body: str):
    return parse_gps(parse_sentence(nmea(body)))


def _rejected(body: str) -> None:
    with pytest.raises(SentenceError) as exc:
        _parse(body)
    assert exc.value.kind == "format"


# --- U-GPS-01 RMC valid ---------------------------------------------------


def test_u_gps_01_rmc_valid_reference():
    rec = GpsParser().feed(REF_RMC)
    assert isinstance(rec, Rmc)
    assert rec.valid is True
    assert rec.talker == "GP"
    assert rec.latitude == pytest.approx(48 + 7.038 / 60)
    assert rec.longitude == pytest.approx(11 + 31.0 / 60)
    assert rec.sog_knots == pytest.approx(22.4)
    assert rec.cog_deg == pytest.approx(84.4)
    assert rec.variation_deg == pytest.approx(-3.1)  # W is negative


def test_u_gps_01_rmc_utc_datetime_and_east_variation():
    rec = _parse("GNRMC,081502.50,A,4330.000,N,00715.500,E,5.2,271.0,270926,1.5,E,A")
    assert isinstance(rec, Rmc)
    assert rec.utc == datetime(2026, 9, 27, 8, 15, 2, 500000, tzinfo=UTC)
    assert rec.variation_deg == pytest.approx(1.5)
    assert rec.latitude == pytest.approx(43.5)
    assert rec.longitude == pytest.approx(7 + 15.5 / 60)


def test_u_gps_01_rmc_missing_date_gives_no_utc():
    rec = _parse("GPRMC,081502,A,4330.000,N,00715.500,E,5.2,271.0,,,")
    assert isinstance(rec, Rmc)
    assert rec.utc is None


@pytest.mark.parametrize(
    "body",
    [
        "GPRMC,081502,A,4330.000,N,00715.500,E,5.2,271.0,320926,,",  # day 32
        "GPRMC,25150X,A,4330.000,N,00715.500,E,5.2,271.0,270926,,",  # bad time
        "GPRMC,081502,A,4330.000,N,00715.500,E,5.2,271.0,270926,1.5,X",  # bad variation dir
        "GPRMC,081502,A,4330.000,N,00715.500,E,5.2,271.0,270926",  # too few fields
        "GPRMC,081502,A,4330.000,N,00715.500,E,fast,271.0,270926,,",  # not a number
        "GPRMC,081502,A,4330.000,N,00715.500,E,nan,271.0,270926,,",  # not finite
        "GPRMC,081502,A,4330.000,N,00715.500,E,-1.0,271.0,270926,,",  # negative speed
        "GPRMC,081502,A,4330.000,N,00715.500,E,5.2,360.5,270926,,",  # course out of range
        "GPRMC,081502,X,4330.000,N,00715.500,E,5.2,271.0,270926,,",  # bad status
    ],
)
def test_u_gps_01_rmc_malformed_rejected(body):
    _rejected(body)


# --- U-GPS-02 RMC void ----------------------------------------------------


def test_u_gps_02_rmc_void_not_applied():
    rec = _parse("GPRMC,081502,V,4330.000,N,00715.500,E,5.2,271.0,270926,,")
    assert isinstance(rec, Rmc)
    assert rec.valid is False
    assert (rec.latitude, rec.longitude, rec.sog_knots, rec.cog_deg) == (None, None, None, None)
    assert rec.utc == datetime(2026, 9, 27, 8, 15, 2, tzinfo=UTC)


def test_u_gps_02_rmc_mode_not_valid_is_void():
    rec = _parse("GPRMC,081502,A,4330.000,N,00715.500,E,5.2,271.0,270926,,,N")
    assert isinstance(rec, Rmc)
    assert rec.valid is False
    assert rec.latitude is None


# --- U-GPS-03 hemispheres and boundaries -----------------------------------


@pytest.mark.parametrize(
    "lat,ns,lon,ew,exp_lat,exp_lon",
    [
        ("3345.000", "S", "07030.000", "W", -33.75, -70.5),
        ("0000.000", "N", "00000.000", "E", 0.0, 0.0),
        ("0000.000", "S", "00000.000", "W", 0.0, 0.0),
        ("0030.000", "S", "00030.000", "W", -0.5, -0.5),
        ("9000.000", "N", "18000.000", "E", 90.0, 180.0),
        ("9000.000", "S", "18000.000", "W", -90.0, -180.0),
        ("4330.000", "N", "17959.999", "E", 43.5, 179 + 59.999 / 60),
        ("4330.000", "N", "17959.999", "W", 43.5, -(179 + 59.999 / 60)),
    ],
)
def test_u_gps_03_hemispheres_and_boundaries(lat, ns, lon, ew, exp_lat, exp_lon):
    rec = _parse(f"GPRMC,081502,A,{lat},{ns},{lon},{ew},0.0,0.0,270926,,")
    assert isinstance(rec, Rmc)
    assert rec.latitude == pytest.approx(exp_lat, abs=1e-9)
    assert rec.longitude == pytest.approx(exp_lon, abs=1e-9)


@pytest.mark.parametrize(
    "pos",
    [
        "9100.000,N,00000.000,E",  # latitude > 90
        "9000.001,N,00000.000,E",
        "0000.000,N,18000.001,E",  # longitude > 180
        "4360.000,N,00000.000,E",  # minutes >= 60
        "4330.000,X,00000.000,E",  # bad hemisphere
        "4330.000,,00000.000,E",  # value without hemisphere
        "4330.000,N,00000.000,N",  # N/S used for longitude
        "43.30000,N,00000.000,E",  # no degree/minute split
        "-4330.00,N,00000.000,E",  # negative
    ],
)
def test_u_gps_03_invalid_positions_rejected(pos):
    _rejected(f"GPRMC,081502,A,{pos},0.0,0.0,270926,,")


# --- U-GPS-04 GGA ---------------------------------------------------------


@pytest.mark.parametrize(
    "q,expected",
    [("1", FixQuality.GPS), ("2", FixQuality.DGPS), ("6", FixQuality.ESTIMATED)],
)
def test_u_gps_04_gga_fix_quality(q, expected):
    rec = _parse(f"GPGGA,123519,4807.038,N,01131.000,E,{q},08,0.9,545.4,M,46.9,M,,")
    assert isinstance(rec, Gga)
    assert rec.fix_quality is expected
    assert rec.satellites == 8
    assert rec.hdop == pytest.approx(0.9)
    assert rec.latitude == pytest.approx(48 + 7.038 / 60)


def test_u_gps_04_gga_quality_0_gives_no_position():
    rec = _parse("GPGGA,123519,4807.038,N,01131.000,E,0,00,99.9,,M,,M,,")
    assert isinstance(rec, Gga)
    assert rec.fix_quality is FixQuality.NO_FIX
    assert (rec.latitude, rec.longitude) == (None, None)
    assert rec.satellites == 0


def test_u_gps_04_gga_empty_fields():
    rec = _parse("GPGGA,,,,,,,,,,,,,,")
    assert isinstance(rec, Gga)
    assert (rec.fix_quality, rec.satellites, rec.hdop, rec.latitude) == (None, None, None, None)


@pytest.mark.parametrize(
    "body",
    [
        "GPGGA,123519,4807.038,N,01131.000,E,9,08,0.9",  # unknown quality
        "GPGGA,123519,4807.038,N,01131.000,E,1,8.5,0.9",  # satellites not an integer
        "GPGGA,123519,4807.038,N,01131.000,E,1,08",  # too few fields
    ],
)
def test_u_gps_04_gga_malformed_rejected(body):
    _rejected(body)


# --- U-GPS-05 VTG ---------------------------------------------------------


def test_u_gps_05_vtg_with_magnetic_course():
    rec = _parse("GPVTG,054.7,T,034.4,M,005.5,N,010.2,K")
    assert isinstance(rec, Vtg)
    assert rec.cog_deg == pytest.approx(54.7)
    assert rec.cog_magnetic_deg == pytest.approx(34.4)
    assert rec.sog_knots == pytest.approx(5.5)  # from the N field, not K


def test_u_gps_05_vtg_without_magnetic_course_with_mode():
    rec = _parse("GNVTG,054.7,T,,M,005.5,N,010.2,K,A")
    assert isinstance(rec, Vtg)
    assert rec.cog_magnetic_deg is None
    assert rec.sog_knots == pytest.approx(5.5)


def test_u_gps_05_vtg_only_kmh_is_converted():
    rec = _parse("GPVTG,054.7,T,,M,,N,018.52,K")
    assert isinstance(rec, Vtg)
    assert rec.sog_knots == pytest.approx(10.0)


def test_u_gps_05_vtg_legacy_format_without_unit_letters():
    rec = _parse("GPVTG,054.7,034.4,005.5,010.2")
    assert isinstance(rec, Vtg)
    assert (rec.cog_deg, rec.cog_magnetic_deg) == (pytest.approx(54.7), pytest.approx(34.4))
    assert rec.sog_knots == pytest.approx(5.5)


def test_u_gps_05_vtg_mode_not_valid():
    rec = _parse("GPVTG,054.7,T,,M,005.5,N,010.2,K,N")
    assert isinstance(rec, Vtg)
    assert (rec.cog_deg, rec.sog_knots) == (None, None)


@pytest.mark.parametrize(
    "body",
    ["GPVTG,054.7,T,,M,005.5,X,010.2,K", "GPVTG,054.7,T,,M,005.5", "GPVTG,054.7"],
)
def test_u_gps_05_vtg_malformed_rejected(body):
    _rejected(body)


# --- U-GPS-06 GSA ---------------------------------------------------------


@pytest.mark.parametrize(
    "mode,expected",
    [("1", FixMode.NO_FIX), ("2", FixMode.FIX_2D), ("3", FixMode.FIX_3D)],
)
def test_u_gps_06_gsa_fix_mode(mode, expected):
    rec = _parse(f"GPGSA,A,{mode},04,05,,09,12,,,24,,,,,2.5,1.3,2.1")
    assert isinstance(rec, Gsa)
    assert rec.fix_mode is expected
    assert (rec.pdop, rec.hdop, rec.vdop) == (
        pytest.approx(2.5),
        pytest.approx(1.3),
        pytest.approx(2.1),
    )


def test_u_gps_06_gsa_nmea41_system_id_and_empty_dop():
    rec = _parse("GNGSA,A,3,04,05,,09,12,,,24,,,,,,,,1")
    assert isinstance(rec, Gsa)
    assert rec.fix_mode is FixMode.FIX_3D
    assert rec.pdop is None


@pytest.mark.parametrize("body", ["GPGSA,A,4,,,,,,,,,,,,,2.5,1.3,2.1", "GPGSA,A,3,04"])
def test_u_gps_06_gsa_malformed_rejected(body):
    _rejected(body)


# --- U-GPS-07 HDT ---------------------------------------------------------


def test_u_gps_07_hdt_present():
    rec = _parse("HEHDT,274.07,T")
    assert isinstance(rec, Hdt)
    assert rec.heading_deg == pytest.approx(274.07)
    assert rec.talker == "HE"


def test_u_gps_07_hdt_empty():
    rec = _parse("GPHDT,,T")
    assert isinstance(rec, Hdt)
    assert rec.heading_deg is None


@pytest.mark.parametrize("body", ["GPHDT,361.0,T", "GPHDT"])
def test_u_gps_07_hdt_malformed_rejected(body):
    _rejected(body)


# --- Parser stats ---------------------------------------------------------


def test_parser_stats_count_ok_and_rejected():
    p = GpsParser()
    assert p.feed(REF_RMC) is not None
    assert p.feed(nmea("GPHDT,361.0,T")) is None
    assert p.stats == {"ok": 1, "ignored": 0, "rejected": 1, "checksum": 0, "framing": 0}


# --- U-GPS-08 -------------------------------------------------------------


@pytest.mark.skip(reason="Needs the real receiver capture D-05/D-06 (X-09), issue #2")
def test_u_gps_08_every_captured_dollar_line():
    """U-GPS-08: every `$` line of D-05/D-06 parses without exception; rejection rate reported."""
