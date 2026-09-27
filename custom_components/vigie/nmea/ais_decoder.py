"""Clean-room AIVDM/AIVDO decoder for vessel position reports.

Scope: Class A position reports (message types 1, 2, 3) and Class B
position reports (types 18, 19). Extracts MMSI, position, speed over
ground, course over ground and true heading.

Written from the public specification "AIVDM/AIVDO protocol decoding"
(E. S. Raymond, gpsd, v1.58): https://gpsd.gitlab.io/gpsd/AIVDM.html
Pure standard library, no I/O: feed it lines, get VesselPosition objects.
Designed to be called from an asyncio serial/TCP reader in a Home
Assistant integration (the decoder itself never blocks).
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass

# --- Sentinel "not available" raw values (spec, CNB section) -------------
_LON_NA = 181 * 600000  # 0x6791AC0
_LAT_NA = 91 * 600000  # 0x3412140
_SOG_NA = 1023  # 1022 means >= 102.2 kn
_COG_NA = 3600
_HDG_NA = 511

# Expected payload lengths in bits. Shorter payloads are rejected:
# per the spec ~0.3% of checksum-valid messages have a wrong length and
# would otherwise decode as spurious zeros.
_MIN_BITS = {1: 168, 2: 168, 3: 168, 18: 168, 19: 312}

CLASS_A_TYPES = frozenset({1, 2, 3})
CLASS_B_TYPES = frozenset({18, 19})

NAV_STATUS = {
    0: "under_way_engine",
    1: "at_anchor",
    2: "not_under_command",
    3: "restricted_manoeuvrability",
    4: "constrained_by_draught",
    5: "moored",
    6: "aground",
    7: "fishing",
    8: "under_way_sailing",
    11: "towing_astern",
    12: "pushing_ahead",
    14: "ais_sart_active",
    15: "undefined",
}


@dataclass(frozen=True, slots=True)
class VesselPosition:
    mmsi: int
    ais_class: str  # "A" or "B"
    msg_type: int
    latitude: float | None  # decimal degrees, N positive
    longitude: float | None  # decimal degrees, E positive
    sog_knots: float | None  # speed over ground
    cog_deg: float | None  # course over ground, true
    heading_deg: int | None  # true heading
    nav_status: str | None  # Class A only
    name: str | None  # type 19 only
    own_ship: bool  # True for !xxVDO
    channel: str
    received_at: float  # decoder clock (time.monotonic by default)


class AisDecodeError(ValueError):
    """Sentence rejected (bad checksum, malformed, wrong length...)."""


# --- NMEA sentence layer --------------------------------------------------


def _strip_tag_block(line: str) -> str:
    # NMEA 4.0 tag blocks: "\s:rcvr,c:123*hh\!AIVDM,..."
    if line.startswith("\\"):
        end = line.find("\\", 1)
        if end == -1:
            raise AisDecodeError("unterminated tag block")
        return line[end + 1 :]
    return line


def _check_checksum(sentence: str) -> str:
    """Validate '*hh' and return the body between '!' and '*'."""
    if not sentence.startswith("!"):
        raise AisDecodeError("not an encapsulated sentence")
    star = sentence.rfind("*")
    if star == -1 or len(sentence) < star + 3:
        raise AisDecodeError("missing checksum")
    body = sentence[1:star]
    try:
        expected = int(sentence[star + 1 : star + 3], 16)
    except ValueError as exc:
        raise AisDecodeError("invalid checksum digits") from exc
    actual = 0
    for ch in body:
        actual ^= ord(ch)
    if actual != expected:
        raise AisDecodeError(f"checksum mismatch {actual:02X} != {expected:02X}")
    return body


# --- Payload armoring -------------------------------------------------------


def _dearmor(payload: str, fill_bits: int) -> tuple[int, int]:
    """Return (bits as one big int, bit length)."""
    value = 0
    for ch in payload:
        code = ord(ch)
        # Valid six-bit armoring: '0'..'W' (0x30-0x57) → 0..39, '`'..'w' (0x60-0x77) → 40..63
        if 0x30 <= code <= 0x57:
            v = code - 48
        elif 0x60 <= code <= 0x77:
            v = code - 56
        else:
            raise AisDecodeError(f"invalid armoring character {ch!r}")
        value = (value << 6) | v
    nbits = 6 * len(payload) - fill_bits
    return value >> fill_bits, nbits


class _Bits:
    __slots__ = ("_v", "n")

    def __init__(self, value: int, nbits: int) -> None:
        self._v, self.n = value, nbits

    def u(self, start: int, length: int) -> int:
        shift = self.n - start - length
        return (self._v >> shift) & ((1 << length) - 1)

    def i(self, start: int, length: int) -> int:
        v = self.u(start, length)
        return v - (1 << length) if v & (1 << (length - 1)) else v

    def text(self, start: int, length: int) -> str:
        out = []
        for pos in range(start, start + length, 6):
            c = self.u(pos, 6)
            out.append(chr(c + 64) if c < 32 else chr(c))
        s = "".join(out)
        at = s.find("@")  # '@' terminates; drop trailing garbage
        if at != -1:
            s = s[:at]
        return s.rstrip()


# --- Field decoding -------------------------------------------------------


def _lon(raw: int) -> float | None:
    return None if raw == _LON_NA or abs(raw) > 180 * 600000 else raw / 600000.0


def _lat(raw: int) -> float | None:
    return None if raw == _LAT_NA or abs(raw) > 90 * 600000 else raw / 600000.0


def _sog(raw: int) -> float | None:
    return None if raw == _SOG_NA else raw / 10.0


def _cog(raw: int) -> float | None:
    return None if raw >= _COG_NA else raw / 10.0


def _hdg(raw: int) -> int | None:
    return None if raw == _HDG_NA or raw > 359 else raw


def _decode(bits: _Bits, own: bool, channel: str, now: float) -> VesselPosition | None:
    msg_type = bits.u(0, 6)
    if msg_type not in _MIN_BITS:
        return None  # not a position report we handle
    if bits.n < _MIN_BITS[msg_type]:
        raise AisDecodeError(f"type {msg_type}: {bits.n} bits, expected {_MIN_BITS[msg_type]}")
    mmsi = bits.u(8, 30)

    if msg_type in CLASS_A_TYPES:  # Common Navigation Block
        return VesselPosition(
            mmsi=mmsi,
            ais_class="A",
            msg_type=msg_type,
            latitude=_lat(bits.i(89, 27)),
            longitude=_lon(bits.i(61, 28)),
            sog_knots=_sog(bits.u(50, 10)),
            cog_deg=_cog(bits.u(116, 12)),
            heading_deg=_hdg(bits.u(128, 9)),
            nav_status=NAV_STATUS.get(bits.u(38, 4), "reserved"),
            name=None,
            own_ship=own,
            channel=channel,
            received_at=now,
        )

    # Types 18 / 19 share the same layout up to bit 138
    name = (bits.text(143, 120) or None) if msg_type == 19 else None
    return VesselPosition(
        mmsi=mmsi,
        ais_class="B",
        msg_type=msg_type,
        latitude=_lat(bits.i(85, 27)),
        longitude=_lon(bits.i(57, 28)),
        sog_knots=_sog(bits.u(46, 10)),
        cog_deg=_cog(bits.u(112, 12)),
        heading_deg=_hdg(bits.u(124, 9)),
        nav_status=None,
        name=name,
        own_ship=own,
        channel=channel,
        received_at=now,
    )


# --- Stateful decoder (multi-fragment reassembly) --------------------------


class AisDecoder:
    """Feed raw lines with feed(); returns a VesselPosition or None.

    Keeps state only for multi-fragment messages, keyed by
    (talker, channel, sequence id), and drops incomplete groups after
    `fragment_timeout` seconds. `clock` is injectable for deterministic
    tests and defaults to time.monotonic.
    """

    def __init__(
        self,
        fragment_timeout: float = 5.0,
        include_own: bool = True,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._clock = clock
        self._pending: dict[tuple[str, str, str], tuple[float, list[tuple[str, int] | None]]] = {}
        self._timeout = fragment_timeout
        self._include_own = include_own
        self.stats = {"ok": 0, "ignored": 0, "rejected": 0}

    def feed(self, line: str) -> VesselPosition | None:
        try:
            result = self._feed(line.strip())
        except AisDecodeError:
            self.stats["rejected"] += 1
            return None
        self.stats["ok" if result else "ignored"] += 1
        return result

    def _feed(self, line: str) -> VesselPosition | None:
        sentence = _strip_tag_block(line)
        if len(sentence) < 7 or sentence[3:6] not in ("VDM", "VDO"):
            return None  # not AIS, not an error
        body = _check_checksum(sentence)
        fields = body.split(",")
        if len(fields) != 7:
            raise AisDecodeError(f"expected 7 fields, got {len(fields)}")
        talker_type, count_s, index_s, seq, channel, payload, fill_s = fields
        own = talker_type.endswith("VDO")
        if own and not self._include_own:
            return None
        try:
            count, index, fill = int(count_s), int(index_s), int(fill_s)
        except ValueError as exc:
            raise AisDecodeError("bad fragment/fill fields") from exc
        if not (1 <= index <= count <= 9 and 0 <= fill <= 5):
            raise AisDecodeError("fragment/fill out of range")

        now = self._clock()
        if count == 1:
            return _decode(_Bits(*_dearmor(payload, fill)), own, channel, now)

        self._expire(now)
        key = (talker_type, channel, seq)
        started, frags = self._pending.setdefault(key, (now, [None] * count))
        if len(frags) != count:  # id reused with other count
            started, frags = now, [None] * count
            self._pending[key] = (started, frags)
        frags[index - 1] = (payload, fill)
        if any(f is None for f in frags):
            return None
        del self._pending[key]
        complete = [f for f in frags if f is not None]
        # Fill bits only apply to the last fragment
        full = "".join(p for p, _ in complete)
        return _decode(_Bits(*_dearmor(full, complete[-1][1])), own, channel, now)

    def _expire(self, now: float) -> None:
        stale = [k for k, (t, _) in self._pending.items() if now - t > self._timeout]
        for k in stale:
            del self._pending[k]
