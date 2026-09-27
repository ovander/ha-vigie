"""Tests for ais_decoder. pyais (MIT) is used only as an independent oracle."""

import random

import pytest
from pyais import decode as oracle_decode
from pyais.encode import encode_dict

from custom_components.vigie.nmea.ais_decoder import AisDecoder

# Reference sentences from the gpsd AIVDM document and common test corpora
SPEC_TYPE1 = "!AIVDM,1,1,,B,177KQJ5000G?tO`K>RA1wUbN0TKH,0*5C"
SAMPLE_TYPE18 = "!AIVDM,1,1,,A,B5NJ;PP005l4ot5Isbl03wsUkP06,0*76"
SAMPLE_TYPE19 = "!AIVDM,1,1,,B,C5N3SRgPEnJGEBT>NhWAwwo862PaLELTBJ:V00000000S0D:R220,0*0B"


def _cmp(ours, ref):
    assert ours.mmsi == ref.mmsi
    for mine, theirs, tol in (
        (ours.latitude, ref.lat, 1e-6),
        (ours.longitude, ref.lon, 1e-6),
        (ours.sog_knots, ref.speed, 1e-6),
        (ours.cog_deg, ref.course, 1e-6),
    ):
        if mine is None:
            assert theirs is None or theirs in (91.0, 181.0, 102.3, 360.0)
        else:
            assert mine == pytest.approx(theirs, abs=tol)
    if ours.heading_deg is not None:
        assert ours.heading_deg == ref.heading


@pytest.mark.parametrize(
    "line,cls", [(SPEC_TYPE1, "A"), (SAMPLE_TYPE18, "B"), (SAMPLE_TYPE19, "B")]
)
def test_reference_sentences(line, cls):
    pos = AisDecoder().feed(line)
    assert pos is not None and pos.ais_class == cls
    _cmp(pos, oracle_decode(line))


def test_type19_name():
    pos = AisDecoder().feed(SAMPLE_TYPE19)
    assert pos.name == oracle_decode(SAMPLE_TYPE19).shipname


def test_bad_checksum_rejected():
    d = AisDecoder()
    assert d.feed(SPEC_TYPE1[:-2] + "00") is None
    assert d.stats["rejected"] == 1


def test_tag_block_and_other_sentences():
    d = AisDecoder()
    assert d.feed("\\s:rcv1,c:1700000000*00\\" + SPEC_TYPE1) is not None
    assert d.feed("$GPRMC,123519,A,4807.038,N,01131.000,E,022.4,084.4,230394,003.1,W*6A") is None


def test_truncated_payload_rejected():
    import functools
    import operator

    body = "AIVDM,1,1,,B,177KQJ5000G?tO`K>RA1wUbN,0"
    cs = functools.reduce(operator.xor, map(ord, body))
    d = AisDecoder()
    assert d.feed(f"!{body}*{cs:02X}") is None
    assert d.stats["rejected"] == 1


def test_vdo_flag():
    import functools
    import operator

    body = "AIVDO,1,1,,B,177KQJ5000G?tO`K>RA1wUbN0TKH,0"
    cs = functools.reduce(operator.xor, map(ord, body))
    line = f"!{body}*{cs:02X}"
    assert AisDecoder().feed(line).own_ship is True
    assert AisDecoder(include_own=False).feed(line) is None


def test_multifragment_reassembly():
    # A type 19 split over two fragments
    msg = {
        "type": 19,
        "mmsi": 227123456,
        "speed": 6.4,
        "lon": 3.9312,
        "lat": 43.5321,
        "course": 212.3,
        "heading": 210,
        "shipname": "SEA BREEZE",
    }
    lines = encode_dict(msg, talker_id="AI", radio_channel="A")
    whole = "".join(x.split(",")[5] for x in lines)
    fill = lines[-1].split(",")[6].split("*")[0]
    half = len(whole) // 2
    import functools
    import operator

    frags = []
    for i, (p, f) in enumerate(((whole[:half], "0"), (whole[half:], fill)), 1):
        body = f"AIVDM,2,{i},7,A,{p},{f}"
        frags.append(f"!{body}*{functools.reduce(operator.xor, map(ord, body)):02X}")
    d = AisDecoder()
    assert d.feed(frags[0]) is None
    pos = d.feed(frags[1])
    assert pos.mmsi == 227123456 and pos.name == "SEA BREEZE"
    assert pos.sog_knots == pytest.approx(6.4) and pos.cog_deg == pytest.approx(212.3)


@pytest.mark.parametrize("msg_type", [1, 2, 3, 18, 19])
def test_fuzz_against_oracle(msg_type):
    rng = random.Random(msg_type)
    d = AisDecoder()
    for _ in range(500):
        msg = {
            "type": msg_type,
            "mmsi": rng.randint(200000000, 775999999),
            "lon": round(rng.uniform(-180, 180), 4),
            "lat": round(rng.uniform(-90, 90), 4),
            "speed": round(rng.uniform(0, 102), 1),
            "course": round(rng.uniform(0, 359.9), 1),
            "heading": rng.choice([rng.randint(0, 359), 511]),
        }
        if msg_type in (1, 2, 3):
            msg["status"] = rng.randint(0, 15)
        if msg_type == 19:
            msg["shipname"] = rng.choice(["", "ALBATROS", "LE PETIT PRINCE"])
        for line in encode_dict(msg, talker_id="AI"):
            pos = d.feed(line)
        assert pos is not None
        _cmp(pos, oracle_decode(*encode_dict(msg, talker_id="AI")))
    assert d.stats["rejected"] == 0


# --- Added for HA-SAIL-TEST-001 U-AIS-10..12 --------------------------------


def _nmea(body):
    import functools
    import operator

    return f"!{body}*{functools.reduce(operator.xor, map(ord, body)):02X}"


def _split_type19(seq="7", channel="A"):
    msg = {
        "type": 19,
        "mmsi": 227000001,
        "speed": 5.0,
        "lon": 3.9,
        "lat": 43.5,
        "course": 90.0,
        "heading": 90,
        "shipname": "VIGIE TEST",
    }
    lines = encode_dict(msg, talker_id="AI", radio_channel=channel)
    whole = "".join(line.split(",")[5] for line in lines)
    fill = lines[-1].split(",")[6].split("*")[0]
    half = len(whole) // 2
    return (
        _nmea(f"AIVDM,2,1,{seq},{channel},{whole[:half]},0"),
        _nmea(f"AIVDM,2,2,{seq},{channel},{whole[half:]},{fill}"),
    )


def test_u_ais_10_fragment_timeout():
    now = [1000.0]
    d = AisDecoder(fragment_timeout=5.0, clock=lambda: now[0])
    first, second = _split_type19()
    assert d.feed(first) is None
    now[0] += 6.0  # first fragment expires
    assert d.feed(second) is None  # orphan: no stale reassembly
    now[0] += 6.0  # orphan second fragment expires too
    assert d.feed(first) is None
    assert d.feed(second) is not None  # fresh pair within timeout decodes


def test_u_ais_10_received_at_uses_clock():
    d = AisDecoder(clock=lambda: 42.0)
    assert d.feed(SPEC_TYPE1).received_at == 42.0


def test_u_ais_11_interleaved_channels_same_seq():
    a1, a2 = _split_type19(seq="3", channel="A")
    b1, b2 = _split_type19(seq="3", channel="B")
    d = AisDecoder()
    assert d.feed(a1) is None
    assert d.feed(b1) is None
    pa, pb = d.feed(a2), d.feed(b2)
    assert pa.channel == "A" and pb.channel == "B"
    assert pa.name == pb.name == "VIGIE TEST"


@pytest.mark.parametrize(
    "field,value,attr",
    [
        ("lon", 181.0, "longitude"),
        ("lat", 91.0, "latitude"),
        ("speed", 102.3, "sog_knots"),
        ("course", 360.0, "cog_deg"),
        ("heading", 511, "heading_deg"),
    ],
)
@pytest.mark.parametrize("msg_type", [1, 18])
def test_u_ais_12_sentinels_map_to_none(msg_type, field, value, attr):
    msg = {
        "type": msg_type,
        "mmsi": 227000002,
        "lon": 3.9,
        "lat": 43.5,
        "speed": 5.0,
        "course": 90.0,
        "heading": 90,
    }
    msg[field] = value
    pos = AisDecoder().feed(encode_dict(msg, talker_id="AI")[0])
    assert getattr(pos, attr) is None


def test_u_ais_12_sog_1022_is_max_not_none():
    msg = {
        "type": 1,
        "mmsi": 227000003,
        "lon": 3.9,
        "lat": 43.5,
        "speed": 102.2,
        "course": 90.0,
        "heading": 90,
    }
    pos = AisDecoder().feed(encode_dict(msg, talker_id="AI")[0])
    assert pos.sog_knots == pytest.approx(102.2)


# --- Sentence-layer rejects (coverage of error paths, NFR-01) ----------------


@pytest.mark.parametrize(
    "line",
    [
        # tag block unterminated
        "\\s:rcv1,c:1700000000*00!AIVDM,1,1,,B,177KQJ5000G?tO`K>RA1wUbN0TKH,0*5C",
        "!AIVDM,1,1,,B,177KQJ5000G?tO`K>RA1wUbN0TKH,0",  # no checksum
        "!AIVDM,1,1,,B,177KQJ5000G?tO`K>RA1wUbN0TKH,0*ZZ",  # non-hex checksum
        _nmea("AIVDM,1,1,,B,177KQJ5000G?tO`K>RA1wUbN0TK~,0"),  # invalid armoring char
        _nmea("AIVDM,1,1,,B,177KQJ5000G?tO`K>RA1wUbN0TKX,0"),  # 0x58: gap 0x58-0x5F
        _nmea("AIVDM,1,1,,B,177KQJ5000G?tO`K>RA1wUbN0TK_,0"),  # 0x5F: gap 0x58-0x5F
        _nmea("AIVDM,1,1,,B,177KQJ5000G?tO`K>RA1wUbN0TKH"),  # wrong field count
        _nmea("AIVDM,x,1,,B,177KQJ5000G?tO`K>RA1wUbN0TKH,0"),  # non-numeric count
        _nmea("AIVDM,1,2,,B,177KQJ5000G?tO`K>RA1wUbN0TKH,0"),  # index > count
        _nmea("AIVDM,1,1,,B,177KQJ5000G?tO`K>RA1wUbN0TKH,7"),  # fill bits > 5
    ],
)
def test_malformed_sentences_rejected(line):
    d = AisDecoder()
    assert d.feed(line) is None
    assert d.stats["rejected"] == 1


@pytest.mark.parametrize("ch", ["W", "`", "w"])  # 0x57, 0x60, 0x77: edges of the valid ranges
def test_u_ais_14_armoring_range_edges_accepted(ch):
    d = AisDecoder()
    assert d.feed(_nmea(f"AIVDM,1,1,,B,177KQJ5000G?tO`K>RA1wUbN0TK{ch},0")) is not None
    assert d.stats["rejected"] == 0


def test_sequence_id_reused_with_different_count():
    first, _second = _split_type19(seq="5")
    d = AisDecoder()
    assert d.feed(first) is None
    three = _nmea("AIVDM,3,1,5,A,15M67FC000G?ufbE`FepT@3n00Sa,0")
    assert d.feed(three) is None  # group reset, no crash
    assert d.stats["rejected"] == 0
