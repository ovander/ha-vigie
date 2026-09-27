"""AIS static and voyage data — U-AIS-15…22 (TEST §3.3, SPEC §7.3, OD-17, OD-20).

pyais (MIT) is used only as an independent oracle and generator (SPEC §3.1).
"""

import functools
import operator
import random

import pytest
from pyais import decode as oracle_decode
from pyais.encode import encode_dict

from custom_components.vigie.nmea.ais_decoder import (
    SHIP_TYPE_CATEGORIES,
    AisDecoder,
    VesselPosition,
    VesselStatic,
    ship_type_category,
)

# D-01: the type 5 example of the gpsd AIVDM document (two fragments)
SPEC_TYPE5 = (
    "!AIVDM,2,1,3,B,55P5TL01VIaAL@7WKO@mBplU@<PDhh000000001S;AJ::4A80?4i@E53,0*3E",
    "!AIVDM,2,2,3,B,1@0000000000000,2*55",
)


def _nmea(body: str) -> str:
    return f"!{body}*{functools.reduce(operator.xor, map(ord, body)):02X}"


def _payload(msg: dict) -> tuple[str, int]:
    lines = encode_dict(msg, talker_id="AI")
    whole = "".join(line.split(",")[5] for line in lines)
    return whole, int(lines[-1].split(",")[6][0])


def _lines(payload: str, fill: int, talker: str = "AIVDM") -> list[str]:
    """Split a payload into 60-character fragments, as receivers do."""
    chunks = [payload[i : i + 60] for i in range(0, len(payload), 60)]
    n = len(chunks)
    return [
        _nmea(f"{talker},{n},{i},{'5' if n > 1 else ''},A,{c},{fill if i == n else 0}")
        for i, c in enumerate(chunks, 1)
    ]


def _feed(d: AisDecoder, lines: list[str] | tuple[str, ...]):
    out = None
    for line in lines:
        out = d.feed(line)
    return out


def _bits(msg: dict) -> tuple[int, int]:
    """Encoded payload of `msg` as (value, bit length)."""
    payload, fill = _payload(msg)
    value = 0
    for ch in payload:
        code = ord(ch)
        value = (value << 6) | (code - 48 if code < 0x60 else code - 56)
    return value >> fill, 6 * len(payload) - fill


def _armored(value: int, nbits: int) -> list[str]:
    chars = (nbits + 5) // 6
    pad = chars * 6 - nbits
    value <<= pad
    armored = "".join(
        chr(v + 48 if v < 40 else v + 56)
        for v in ((value >> (6 * (chars - 1 - k))) & 63 for k in range(chars))
    )
    return _lines(armored, pad)


def _trim_bits(msg: dict, nbits: int) -> list[str]:
    """Encode `msg` and keep only its first `nbits` bits (short transmitters)."""
    value, total = _bits(msg)
    return _armored(value >> (total - nbits), nbits)


# --- U-AIS-04 (rewritten): other message types are ignored, not rejected ------------------


def test_u_ais_04_other_types_ignored_without_rejection():
    d = AisDecoder()
    base_station = {"type": 4, "mmsi": 2275000, "lon": 7.25, "lat": 43.5}
    aid_to_nav = {"type": 21, "mmsi": 992271001, "name": "BUOY", "lon": 7.2, "lat": 43.4}
    for msg in (base_station, aid_to_nav):
        assert _feed(d, encode_dict(msg, talker_id="AI")) is None
    assert d.stats == {"ok": 0, "ignored": 2, "rejected": 0}


# --- U-AIS-15: type 5 reference sentence -------------------------------------------------


def test_u_ais_15_type5_reference():
    d = AisDecoder()
    assert d.feed(SPEC_TYPE5[0]) is None  # first fragment
    s = d.feed(SPEC_TYPE5[1])
    assert isinstance(s, VesselStatic)
    assert (s.mmsi, s.ais_class, s.msg_type, s.part) == (369190000, "A", 5, None)
    assert (s.name, s.callsign, s.imo) == ("MT.MITCHELL", "WDA9674", 6710932)
    assert s.ship_type == 99
    assert (s.to_bow, s.to_stern, s.to_port, s.to_starboard) == (90, 90, 10, 10)
    assert (s.length_m, s.beam_m) == (180, 20)
    assert s.draught_m == pytest.approx(6.0)
    assert s.destination == "SEATTLE"
    assert s.mothership_mmsi is None
    assert (s.own_ship, s.channel) == (False, "B")
    assert d.stats == {"ok": 1, "ignored": 1, "rejected": 0}


# --- U-AIS-16: type 5 length ---------------------------------------------------------------

TYPE5 = {
    "type": 5,
    "mmsi": 227000002,
    "shipname": "CARGO ONE",
    "ship_type": 70,
    "callsign": "ABCD",
    "imo": 9123456,
    "to_bow": 150,
    "to_stern": 30,
    "to_port": 15,
    "to_starboard": 15,
    "draught": 8.5,
    "destination": "MARSEILLE",
}


@pytest.mark.parametrize("nbits", [424, 422, 420])
def test_u_ais_16_type5_short_transmitters_accepted(nbits):
    s = _feed(AisDecoder(), _trim_bits(TYPE5, nbits))
    assert isinstance(s, VesselStatic)
    assert (s.name, s.destination, s.draught_m) == ("CARGO ONE", "MARSEILLE", pytest.approx(8.5))


def test_u_ais_16_type5_too_short_rejected():
    d = AisDecoder()
    assert _feed(d, _trim_bits(TYPE5, 418)) is None
    assert d.stats["rejected"] == 1


# --- U-AIS-17: type 24 parts A and B -------------------------------------------------------


def test_u_ais_17_type24_part_a_name():
    s = _feed(
        AisDecoder(),
        encode_dict(
            {"type": 24, "mmsi": 227000001, "partno": 0, "shipname": "ALBATROS"}, talker_id="AI"
        ),
    )
    assert isinstance(s, VesselStatic)
    assert (s.mmsi, s.ais_class, s.msg_type, s.part, s.name) == (
        227000001,
        "B",
        24,
        "A",
        "ALBATROS",
    )
    # Part A carries nothing else: unknown, not zero
    assert (s.ship_type, s.callsign, s.length_m, s.beam_m) == (None, None, None, None)


def test_u_ais_17_type24_part_a_160_bits_accepted():
    msg = {"type": 24, "mmsi": 227000001, "partno": 0, "shipname": "ALBATROS"}
    assert _feed(AisDecoder(), _trim_bits(msg, 160)).name == "ALBATROS"


def test_u_ais_17_type24_part_b_type_callsign_dimensions():
    msg = {
        "type": 24,
        "mmsi": 227000001,
        "partno": 1,
        "ship_type": 36,
        "callsign": "FAB1234",
        "to_bow": 8,
        "to_stern": 4,
        "to_port": 2,
        "to_starboard": 2,
        "vendorid": "ABC",
    }
    s = _feed(AisDecoder(), encode_dict(msg, talker_id="AI"))
    assert (s.part, s.name, s.ship_type, s.callsign) == ("B", None, 36, "FAB1234")
    assert (s.length_m, s.beam_m, s.mothership_mmsi) == (12, 4, None)


def test_u_ais_17_type24_part_b_auxiliary_craft_mothership():
    msg = {
        "type": 24,
        "mmsi": 982270001,
        "partno": 1,
        "ship_type": 37,
        "callsign": "TENDER",
        "mothership_mmsi": 227000001,
    }
    s = _feed(AisDecoder(), encode_dict(msg, talker_id="AI"))
    assert s.mothership_mmsi == 227000001
    assert (s.to_bow, s.to_stern, s.length_m) == (None, None, None)  # not dimensions


def test_u_ais_17_type24_length_and_reserved_part():
    d = AisDecoder()
    part_b = {"type": 24, "mmsi": 227000001, "partno": 1, "ship_type": 36}
    assert _feed(d, _trim_bits(part_b, 162)) is None
    assert d.stats["rejected"] == 1
    value, total = _bits({"type": 24, "mmsi": 227000001, "partno": 0, "shipname": "X"})
    shift = total - 40  # part number: bits 38-39
    reserved = _armored(value & ~(3 << shift) | (2 << shift), total)
    assert _feed(d, reserved) is None  # part numbers 2 and 3 are not defined
    assert d.stats["rejected"] == 1 and d.stats["ignored"] == 1


# --- U-AIS-18: type 19 static fields -------------------------------------------------------


def test_u_ais_18_type19_carries_static_part():
    msg = {
        "type": 19,
        "mmsi": 227000001,
        "lon": 7.25,
        "lat": 43.5,
        "speed": 5.0,
        "course": 90.0,
        "shipname": "SEA BREEZE",
        "ship_type": 36,
        "to_bow": 9,
        "to_stern": 3,
        "to_port": 2,
        "to_starboard": 1,
    }
    pos = _feed(AisDecoder(), encode_dict(msg, talker_id="AI"))
    assert isinstance(pos, VesselPosition) and pos.name == "SEA BREEZE"
    s = pos.static
    assert isinstance(s, VesselStatic)
    assert (s.mmsi, s.ais_class, s.msg_type, s.name, s.ship_type) == (
        227000001,
        "B",
        19,
        "SEA BREEZE",
        36,
    )
    assert (s.length_m, s.beam_m, s.callsign) == (12, 3, None)


def test_u_ais_18_class_a_and_18_positions_have_no_static_part():
    for msg in ({"type": 1, "mmsi": 227000001}, {"type": 18, "mmsi": 227000001}):
        assert _feed(AisDecoder(), encode_dict(msg, talker_id="AI")).static is None


# --- U-AIS-19: "not available" values ------------------------------------------------------


def test_u_ais_19_static_sentinels_map_to_none():
    msg = {"type": 5, "mmsi": 227000003}  # everything else zero / empty
    s = _feed(AisDecoder(), encode_dict(msg, talker_id="AI"))
    assert (s.name, s.callsign, s.imo, s.ship_type, s.draught_m, s.destination) == (
        None,
        None,
        None,
        None,
        None,
        None,
    )
    assert (s.to_bow, s.to_stern, s.to_port, s.to_starboard) == (0, 0, 0, 0)
    assert (s.length_m, s.beam_m) == (None, None)


def test_u_ais_19_reference_point_at_the_bow_keeps_the_length():
    msg = {**TYPE5, "to_bow": 0, "to_stern": 25, "to_port": 0, "to_starboard": 0}
    s = _feed(AisDecoder(), encode_dict(msg, talker_id="AI"))
    assert (s.length_m, s.beam_m) == (25, None)


def test_u_ais_19_name_padding_and_terminator():
    s = _feed(AisDecoder(), encode_dict({**TYPE5, "shipname": "MOANA  @@@@"}, talker_id="AI"))
    assert s.name == "MOANA"


# --- U-AIS-20: fuzz against the oracle -----------------------------------------------------

_NAMES = ["", "ALBATROS", "LE PETIT PRINCE", "MSC ISABELLA", "A"]


def _check_against_oracle(s: VesselStatic, ref) -> None:
    def text(value):
        return (value or "").rstrip("@ ").rstrip() or None

    assert s.mmsi == ref.mmsi
    if hasattr(ref, "shipname"):
        assert s.name == text(ref.shipname)
    if hasattr(ref, "callsign"):
        assert s.callsign == text(ref.callsign)
    if hasattr(ref, "ship_type"):
        assert s.ship_type == (int(ref.ship_type) or None)
    if hasattr(ref, "to_bow"):
        assert (s.to_bow, s.to_stern, s.to_port, s.to_starboard) == (
            ref.to_bow,
            ref.to_stern,
            ref.to_port,
            ref.to_starboard,
        )
    if hasattr(ref, "imo"):
        assert s.imo == (ref.imo or None)
    if hasattr(ref, "draught"):
        assert s.draught_m == (pytest.approx(ref.draught) if ref.draught else None)
    if hasattr(ref, "destination"):
        assert s.destination == text(ref.destination)
    if hasattr(ref, "mothership_mmsi"):
        assert s.mothership_mmsi == ref.mothership_mmsi


def _random_static(rng: random.Random, kind: str) -> dict:
    dims = {
        "to_bow": rng.randint(0, 511),
        "to_stern": rng.randint(0, 511),
        "to_port": rng.randint(0, 63),
        "to_starboard": rng.randint(0, 63),
    }
    mmsi = rng.randint(200000000, 775999999)
    if kind == "5":
        return {
            "type": 5,
            "mmsi": mmsi,
            "shipname": rng.choice(_NAMES),
            "callsign": rng.choice(["", "F1234", "WDA9674"]),
            "imo": rng.choice([0, rng.randint(1000000, 9999999)]),
            "ship_type": rng.randint(0, 99),
            "draught": round(rng.uniform(0, 25.5), 1),
            "destination": rng.choice(["", "MARSEILLE", "LE HAVRE"]),
            **dims,
        }
    if kind == "24A":
        return {"type": 24, "mmsi": mmsi, "partno": 0, "shipname": rng.choice(_NAMES)}
    aux = kind == "24B-aux"
    msg = {
        "type": 24,
        "mmsi": rng.randint(982000000, 982999999) if aux else mmsi,
        "partno": 1,
        "ship_type": rng.randint(0, 99),
        "callsign": rng.choice(["", "FAB1234"]),
    }
    msg.update({"mothership_mmsi": mmsi} if aux else dims)
    return msg


@pytest.mark.parametrize("kind", ["5", "24A", "24B", "24B-aux"])
def test_u_ais_20_fuzz_static_against_oracle(kind):
    rng = random.Random(kind)
    d = AisDecoder()
    for _ in range(500):
        lines = encode_dict(_random_static(rng, kind), talker_id="AI")
        s = _feed(d, lines)
        assert isinstance(s, VesselStatic), lines
        _check_against_oracle(s, oracle_decode(*lines))
    assert d.stats["rejected"] == 0


# --- U-AIS-21: ship type categories (OD-17) -----------------------------------------------


@pytest.mark.parametrize(
    "code,category",
    [
        (0, None),  # not available
        (None, None),
        (20, "wing_in_ground"),
        (30, "fishing"),
        (31, "towing"),
        (32, "towing"),
        (33, "dredging"),
        (34, "diving"),
        (35, "military"),
        (36, "sailing"),
        (37, "pleasure_craft"),
        (40, "high_speed"),
        (49, "high_speed"),
        (50, "pilot"),
        (51, "search_and_rescue"),
        (52, "tug"),
        (53, "port_tender"),
        (55, "law_enforcement"),
        (58, "medical"),
        (60, "passenger"),
        (69, "passenger"),
        (70, "cargo"),
        (79, "cargo"),
        (80, "tanker"),
        (89, "tanker"),
        (1, "other"),  # reserved
        (54, "other"),  # anti-pollution
        (99, "other"),
        (100, "other"),  # outside the table
    ],
)
def test_u_ais_21_ship_type_category(code, category):
    assert ship_type_category(code) == category


def test_u_ais_21_every_code_maps_to_a_known_category():
    assert {ship_type_category(c) for c in range(1, 256)} == set(SHIP_TYPE_CATEGORIES)


# --- U-AIS-22: own-ship static reports -------------------------------------------------------


def test_u_ais_22_vdo_static_flagged_and_excludable():
    payload, fill = _payload(TYPE5)
    vdo = _lines(payload, fill, talker="AIVDO")
    assert _feed(AisDecoder(), vdo).own_ship is True
    assert _feed(AisDecoder(include_own=False), vdo) is None
