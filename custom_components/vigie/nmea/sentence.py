"""NMEA 0183 sentence layer: framing, checksum, address and field split (SPEC §7.1).

Pure standard library, no I/O. Every function either returns a value or raises
SentenceError, whose `kind` tells the caller which diagnostics counter to bump.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

# Longest accepted sentence, from the start character to the checksum inclusive,
# after any tag block is stripped (SPEC §7.1).
MAX_SENTENCE_LEN = 82

ErrorKind = Literal["checksum", "framing", "format"]


class SentenceError(ValueError):
    """Sentence rejected; `kind` is "checksum", "framing" or "format"."""

    def __init__(self, kind: ErrorKind, message: str) -> None:
        super().__init__(message)
        self.kind: ErrorKind = kind


@dataclass(frozen=True, slots=True)
class Sentence:
    start: str  # "$" or "!"
    talker: str  # "GP", "GN", "AI"… or "P" for proprietary sentences
    sentence_type: str  # "RMC", "VDM"… (manufacturer code + type when proprietary)
    fields: tuple[str | None, ...]  # data fields after the address; empty → None


def nmea_checksum(body: str) -> int:
    """XOR of all characters between the start character and '*'."""
    value = 0
    for ch in body:
        value ^= ord(ch)
    return value


def split_tag_block(line: str) -> tuple[str | None, str]:
    """Split an NMEA 4.0 tag block prefix: '\\s:rcv,c:1*hh\\$GP…' → ('s:rcv,c:1*hh', '$GP…')."""
    if not line.startswith("\\"):
        return None, line
    end = line.find("\\", 1)
    if end == -1:
        raise SentenceError("framing", "unterminated tag block")
    return line[1:end], line[end + 1 :]


def check_frame(line: str) -> str:
    """Validate a framed line (without its CR/LF terminator) and return it unchanged.

    Rejects non-printable or non-ASCII characters and sentences longer than
    MAX_SENTENCE_LEN once the tag block is removed.
    """
    if not all(" " <= ch <= "~" for ch in line):
        raise SentenceError("framing", "non-printable or non-ASCII character")
    _, sentence = split_tag_block(line)
    if len(sentence) > MAX_SENTENCE_LEN:
        raise SentenceError("framing", f"sentence longer than {MAX_SENTENCE_LEN} characters")
    return line


def parse_sentence(line: str) -> Sentence:
    """Parse one sentence (no tag block, no terminator) after checking its checksum."""
    if not line or line[0] not in "$!":
        raise SentenceError("format", "missing '$' or '!' start character")
    star = line.rfind("*")
    if star == -1:
        raise SentenceError("checksum", "missing checksum")
    digits = line[star + 1 :]
    if len(digits) != 2 or any(c not in "0123456789ABCDEFabcdef" for c in digits):
        raise SentenceError("checksum", f"invalid checksum digits {digits!r}")
    body = line[1:star]
    actual = nmea_checksum(body)
    if actual != int(digits, 16):
        raise SentenceError("checksum", f"checksum mismatch {actual:02X} != {digits.upper()}")

    address, *data = body.split(",")
    if not address.isascii() or not address.isalnum():
        raise SentenceError("format", f"invalid address {address!r}")
    if address.startswith("P") and len(address) >= 4:
        talker, sentence_type = "P", address[1:]
    elif len(address) == 5:
        talker, sentence_type = address[:2], address[2:]
    else:
        raise SentenceError("format", f"invalid address {address!r}")
    return Sentence(
        start=line[0],
        talker=talker,
        sentence_type=sentence_type,
        fields=tuple(f or None for f in data),
    )
