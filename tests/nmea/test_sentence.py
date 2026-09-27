"""Sentence layer — U-NMEA-01…06 (TEST §3.1, SPEC §7.1)."""

import pytest

from custom_components.vigie.nmea.parsers import GpsParser, Rmc
from custom_components.vigie.nmea.sentence import (
    MAX_SENTENCE_LEN,
    SentenceError,
    check_frame,
    nmea_checksum,
    parse_sentence,
    split_tag_block,
)
from tests.helpers import nmea

# Public reference example from the NMEA 0183 documentation (also in the gpsd docs)
REF_RMC = "$GPRMC,123519,A,4807.038,N,01131.000,E,022.4,084.4,230394,003.1,W*6A"


def test_checksum_of_reference_sentence():
    assert nmea_checksum(REF_RMC[1:-3]) == 0x6A


# --- U-NMEA-01 ------------------------------------------------------------


@pytest.mark.parametrize("line", [REF_RMC, REF_RMC[:-2] + "6a"])
def test_u_nmea_01_valid_checksum_upper_and_lower_hex(line):
    s = parse_sentence(line)
    assert (s.start, s.talker, s.sentence_type) == ("$", "GP", "RMC")
    assert s.fields[0] == "123519"


def test_u_nmea_01_encapsulated_sentence_accepted():
    s = parse_sentence("!AIVDM,1,1,,B,177KQJ5000G?tO`K>RA1wUbN0TKH,0*5C")
    assert (s.start, s.talker, s.sentence_type) == ("!", "AI", "VDM")


# --- U-NMEA-02 ------------------------------------------------------------


@pytest.mark.parametrize(
    "line",
    [
        REF_RMC[:-2] + "6B",  # wrong checksum
        REF_RMC[:-3],  # missing "*hh"
        REF_RMC[:-1],  # one hex digit
        REF_RMC[:-2] + "ZZ",  # non-hex digits
        REF_RMC + "0",  # three digits
    ],
)
def test_u_nmea_02_bad_checksum_rejected(line):
    with pytest.raises(SentenceError) as exc:
        parse_sentence(line)
    assert exc.value.kind == "checksum"


def test_u_nmea_02_bad_checksum_counted():
    p = GpsParser()
    assert p.feed(REF_RMC[:-2] + "6B") is None
    assert p.feed(REF_RMC[:-3]) is None
    assert p.stats["rejected"] == 2
    assert p.stats["checksum"] == 2
    assert p.stats["ok"] == 0


# --- U-NMEA-03 ------------------------------------------------------------


@pytest.mark.parametrize("talker", ["GP", "GN", "AI", "II"])
def test_u_nmea_03_talker_variants_same_parser(talker):
    line = nmea(f"{talker}RMC,123519,A,4807.038,N,01131.000,E,022.4,084.4,230394,003.1,W")
    rec = GpsParser().feed(line)
    assert isinstance(rec, Rmc)
    assert rec.talker == talker
    assert rec.latitude == pytest.approx(48 + 7.038 / 60)


# --- U-NMEA-04 ------------------------------------------------------------


def test_u_nmea_04_empty_fields_are_none():
    s = parse_sentence(nmea("GPRMC,123519,A,,,,,,,230394,,"))
    assert s.fields[2] is None
    assert s.fields[-1] is None


def test_u_nmea_04_empty_values_never_zero():
    rec = GpsParser().feed(nmea("GPRMC,123519,A,4807.038,N,01131.000,E,,,230394,,"))
    assert isinstance(rec, Rmc)
    assert rec.sog_knots is None
    assert rec.cog_deg is None
    assert rec.variation_deg is None


# --- U-NMEA-05 ------------------------------------------------------------


@pytest.mark.parametrize(
    "line",
    [
        nmea("PGRME,15.0,M,45.0,M,25.0,M"),  # proprietary
        nmea("GPGSV,3,1,11,03,03,111,00,04,15,270,00,06,01,010,00,13,06,292,00"),
        nmea("GPZDA,160012.71,11,03,2004,-1,00"),
        "!AIVDM,1,1,,B,177KQJ5000G?tO`K>RA1wUbN0TKH,0*5C",  # AIS goes to the AIS decoder
    ],
)
def test_u_nmea_05_unsupported_ignored_and_counted(line):
    p = GpsParser()
    assert p.feed(line) is None
    assert p.stats == {"ok": 0, "ignored": 1, "rejected": 0, "checksum": 0, "framing": 0}


def test_u_nmea_05_proprietary_talker_metadata():
    s = parse_sentence(nmea("PGRME,15.0,M,45.0,M,25.0,M"))
    assert (s.talker, s.sentence_type) == ("P", "GRME")


@pytest.mark.parametrize(
    "line",
    [
        "GPRMC,123519,A*00",  # no start character
        nmea("GPRM"),  # address too short
        nmea("G$RMC,1"),  # invalid address characters
        nmea(""),  # empty body
    ],
)
def test_u_nmea_05_malformed_address_rejected(line):
    with pytest.raises(SentenceError) as exc:
        parse_sentence(line)
    assert exc.value.kind == "format"


# --- U-NMEA-06 ------------------------------------------------------------


def test_u_nmea_06_max_length_accepted():
    body = "GPTXT," + "A" * (MAX_SENTENCE_LEN - len("$GPTXT,*hh"))
    line = nmea(body)
    assert len(line) == MAX_SENTENCE_LEN
    assert check_frame(line) == line


def test_u_nmea_06_over_long_line_rejected():
    body = "GPTXT," + "A" * (MAX_SENTENCE_LEN - len("$GPTXT,*hh") + 1)
    with pytest.raises(SentenceError) as exc:
        check_frame(nmea(body))
    assert exc.value.kind == "framing"


def test_u_nmea_06_tag_block_not_counted_in_length():
    body = "GPTXT," + "A" * (MAX_SENTENCE_LEN - len("$GPTXT,*hh"))
    line = "\\s:receiver-with-a-long-name,c:1700000000*00\\" + nmea(body)
    assert check_frame(line) == line


@pytest.mark.parametrize(
    "line",
    [
        "$GPRMC,123519,A,4807.038,N,01131.000,E,022.4,084.4,230394,003.1,Wé*6A",
        "$GPRMC,123519,A\x00,4807.038*6A",
        "$GPRMC,123519,A\t,4807.038*6A",
    ],
)
def test_u_nmea_06_non_ascii_rejected_at_framing(line):
    with pytest.raises(SentenceError) as exc:
        check_frame(line)
    assert exc.value.kind == "framing"


def test_u_nmea_06_framing_counted_by_parser():
    p = GpsParser()
    assert p.feed("$GPÿRMC*00") is None
    assert p.stats["framing"] == 1
    assert p.stats["rejected"] == 1


# --- Tag blocks -----------------------------------------------------------


def test_split_tag_block():
    assert split_tag_block("\\s:r1,c:1*00\\" + REF_RMC) == ("s:r1,c:1*00", REF_RMC)
    assert split_tag_block(REF_RMC) == (None, REF_RMC)


def test_unterminated_tag_block_rejected():
    with pytest.raises(SentenceError) as exc:
        split_tag_block("\\s:r1,c:1*00" + REF_RMC)
    assert exc.value.kind == "framing"


def test_parser_accepts_tag_block_prefix():
    rec = GpsParser().feed("\\s:r1,c:1700000000*00\\" + REF_RMC + "\r\n")
    assert isinstance(rec, Rmc)
