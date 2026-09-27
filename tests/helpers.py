"""Shared test helpers (no Home Assistant import)."""

from __future__ import annotations

import asyncio
import functools
import operator


def nmea(body: str, start: str = "$") -> str:
    """Wrap a sentence body with its start character and a valid checksum.

    Test sentences built with this helper are synthetic, never captured data.
    """
    cs = functools.reduce(operator.xor, map(ord, body), 0)
    return f"{start}{body}*{cs:02X}"


class FakeClock:
    """Injectable monotonic clock for deterministic tests."""

    def __init__(self, start: float = 1000.0) -> None:
        self.t = start

    def __call__(self) -> float:
        return self.t

    def advance(self, seconds: float) -> None:
        self.t += seconds


class FakeWriter:
    """Stands in for the serial StreamWriter; records that it was closed."""

    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True

    async def wait_closed(self) -> None:
        return None


class FakeSerial:
    """Fake `OpenTransport`: each successful open returns a fresh reader fed by the test.

    `available = False` makes open() fail like a missing port; `fail_opens = n` makes the
    next n opens fail. Nothing touches a real serial port.
    """

    def __init__(self) -> None:
        self.available = True
        self.fail_opens = 0
        self.opens = 0
        self.readers: list[asyncio.StreamReader] = []
        self.writers: list[FakeWriter] = []

    async def __call__(self) -> tuple[asyncio.StreamReader, FakeWriter]:
        self.opens += 1
        if not self.available or self.fail_opens > 0:
            self.fail_opens = max(0, self.fail_opens - 1)
            raise OSError(2, "fake port unavailable")
        reader, writer = asyncio.StreamReader(), FakeWriter()
        self.readers.append(reader)
        self.writers.append(writer)
        return reader, writer

    @property
    def reader(self) -> asyncio.StreamReader:
        return self.readers[-1]

    def feed_lines(self, *lines: str) -> None:
        self.reader.feed_data("".join(line + "\r\n" for line in lines).encode("utf-8"))

    def feed_bytes(self, data: bytes) -> None:
        self.reader.feed_data(data)

    def disconnect(self, exc: BaseException | None = None) -> None:
        """End of stream (unplug), or a read error when `exc` is given."""
        if exc is None:
            self.reader.feed_eof()
        else:
            self.reader.set_exception(exc)


async def settle(rounds: int = 20) -> None:
    """Let pending tasks run (yields to the loop; no real time passes)."""
    for _ in range(rounds):
        await asyncio.sleep(0)
