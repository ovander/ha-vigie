"""Shared test helpers (no Home Assistant import)."""

from __future__ import annotations

import functools
import operator


def nmea(body: str, start: str = "$") -> str:
    """Wrap a sentence body with its start character and a valid checksum.

    Test sentences built with this helper are synthetic, never captured data.
    """
    cs = functools.reduce(operator.xor, map(ord, body), 0)
    return f"{start}{body}*{cs:02X}"
