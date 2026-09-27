"""Transport hub: one serial reader, line framing, routing, reconnect (SPEC §5.2 C-01, §6).

Pure asyncio, no Home Assistant import (SPEC NFR-02). The serial port is reached through
an injected `OpenTransport` factory, so tests use a fake transport. The caller owns the
task running `Hub.run()` (in Home Assistant: a config-entry background task) and cancels
it on unload, then calls `Hub.close()`.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from collections import deque
from collections.abc import Awaitable, Callable, Iterator
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol

import serial_asyncio_fast

from .nmea.ais_decoder import AisDecoder, VesselPosition
from .nmea.parsers import GpsRecord, parse_gps
from .nmea.sentence import SentenceError, check_frame, parse_sentence, split_tag_block

_LOGGER = logging.getLogger(__name__)

READ_CHUNK = 4096
# Longest raw line kept in the receive buffer; anything longer is dropped (SPEC §7.1)
RAW_LINE_LIMIT = 1024
BACKOFF_INITIAL_S = 1.0
BACKOFF_MAX_S = 60.0
PROBE_TIMEOUT_S = 5.0
_RATE_WINDOW_S = 60.0


class Writer(Protocol):
    def close(self) -> None: ...

    async def wait_closed(self) -> None: ...


OpenTransport = Callable[[], Awaitable[tuple[asyncio.StreamReader, Writer | None]]]


class HubConnectionError(Exception):
    """The serial port could not be opened."""


def serial_transport(port: str, baudrate: int) -> OpenTransport:
    """Transport factory for a real serial port (pyserial-asyncio-fast).

    Opening raises OSError (serial.SerialException is a subclass) when the port is missing.
    """

    async def _open() -> tuple[asyncio.StreamReader, Writer | None]:
        return await serial_asyncio_fast.open_serial_connection(url=port, baudrate=baudrate)

    return _open


def backoff_delays(
    initial: float = BACKOFF_INITIAL_S, maximum: float = BACKOFF_MAX_S
) -> Iterator[float]:
    """Exponential reconnect delays: 1, 2, 4 … capped at 60 s (SPEC §10.3)."""
    delay = initial
    while True:
        yield min(delay, maximum)
        delay = min(delay * 2, maximum)


@dataclass
class HubStats:
    """Diagnostics counters (SPEC §9.5). Every raw line lands in exactly one outcome."""

    lines: int = 0  # non-blank raw lines received
    gps_ok: int = 0  # GPS records delivered
    ais_ok: int = 0  # AIS position reports delivered
    ignored: int = 0  # valid but produced no record (unsupported, fragment, not NMEA)
    checksum_errors: int = 0
    framing_errors: int = 0  # non-ASCII, over-long, bad tag block, buffer overflow
    ais_rejected: int = 0  # checksum-valid AIS rejected by the decoder
    gps_rejected: int = 0  # checksum-valid GPS sentence rejected by the parser
    internal_errors: int = 0  # unexpected exception while handling a line
    reconnects: int = 0
    last_sentence_at: float | None = None  # clock time of the last checksum-valid sentence
    _recent: deque[float] = field(default_factory=deque, repr=False)

    def sentences_per_min(self, now: float) -> int:
        """Checksum-valid sentences received in the last 60 s."""
        while self._recent and now - self._recent[0] > _RATE_WINDOW_S:
            self._recent.popleft()
        return len(self._recent)

    def record_sentence(self, now: float) -> None:
        self.last_sentence_at = now
        self._recent.append(now)
        self.sentences_per_min(now)  # prune


class Hub:
    """Owns the serial port: reads, frames and routes lines, reconnects on failure."""

    def __init__(
        self,
        open_transport: OpenTransport,
        *,
        on_gps: Callable[[GpsRecord], None],
        on_ais: Callable[[VesselPosition], None],
        on_connection: Callable[[bool], None],
        include_own: bool = True,
        name: str = "serial port",
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._open = open_transport
        self._on_gps = on_gps
        self._on_ais = on_ais
        self._on_connection = on_connection
        self._name = name
        self._clock = clock
        self._sleep = sleep
        self._decoder = AisDecoder(include_own=include_own, clock=clock)
        self._reader: asyncio.StreamReader | None = None
        self._writer: Writer | None = None
        self._buffer = bytearray()
        self._discarding = False  # dropping the rest of an over-long line
        self._internal_error_logged = False
        self.connected = False
        self.stats = HubStats()

    # --- Connection ----------------------------------------------------------

    async def connect(self) -> None:
        """Open the port now; raise HubConnectionError if it cannot be opened."""
        try:
            self._reader, self._writer = await self._open()
        except (OSError, ValueError) as err:  # ValueError: settings pyserial refuses
            raise HubConnectionError(f"cannot open {self._name}: {err}") from err
        self._buffer.clear()
        self._discarding = False
        self._set_connected(True)

    async def close(self) -> None:
        """Close the port. Idempotent; does not notify `on_connection`."""
        writer, self._writer, self._reader = self._writer, None, None
        self.connected = False
        if writer is not None:
            writer.close()
            with contextlib.suppress(Exception):
                await writer.wait_closed()

    async def run(self) -> None:
        """Read until cancelled, reconnecting with backoff after every outage."""
        if self._reader is None:
            try:
                await self.connect()
            except HubConnectionError as err:
                _LOGGER.warning("Cannot open %s (%s); retrying with backoff", self._name, err)
                await self._reconnect()
        while True:
            reason = await self._read_until_disconnect()
            await self._drop_connection()
            _LOGGER.warning("Lost %s (%s); reconnecting with backoff", self._name, reason)
            await self._reconnect()

    async def _reconnect(self) -> None:
        attempts = 0
        for delay in backoff_delays():
            await self._sleep(delay)
            attempts += 1
            try:
                await self.connect()
            except HubConnectionError as err:
                _LOGGER.debug("Reconnect attempt %d failed: %s", attempts, err)
                continue
            self.stats.reconnects += 1
            _LOGGER.info("Reconnected to %s after %d attempt(s)", self._name, attempts)
            return

    async def _drop_connection(self) -> None:
        # Close first so `connected` is already False when listeners are told
        await self.close()
        self._buffer.clear()  # a partial line never survives a disconnect (F-HUB-05)
        self._discarding = False
        self._on_connection(False)

    def _set_connected(self, connected: bool) -> None:
        if connected != self.connected:
            self.connected = connected
            self._on_connection(connected)

    # --- Reading and framing ---------------------------------------------------

    async def _read_until_disconnect(self) -> str:
        assert self._reader is not None  # set by connect()
        while True:
            try:
                chunk = await self._reader.read(READ_CHUNK)
            except OSError as err:
                return f"read error: {err}"
            if not chunk:
                return "end of stream"
            self._feed(chunk)

    def _feed(self, chunk: bytes) -> None:
        self._buffer += chunk
        while (nl := self._buffer.find(b"\n")) != -1:
            raw = bytes(self._buffer[:nl])
            del self._buffer[: nl + 1]
            if self._discarding:
                self._discarding = False
                continue
            self._handle_raw(raw)
        if len(self._buffer) > RAW_LINE_LIMIT:
            self._buffer.clear()
            if not self._discarding:
                self._discarding = True
                self.stats.lines += 1
                self.stats.framing_errors += 1

    def _handle_raw(self, raw: bytes) -> None:
        raw = raw.strip()
        if not raw:
            return
        self.stats.lines += 1
        try:
            self._route(raw)
        except Exception:  # consumer or decoder bug: contain it to this line
            self.stats.internal_errors += 1
            if not self._internal_error_logged:
                self._internal_error_logged = True
                _LOGGER.exception("Unexpected error while handling a line from %s", self._name)

    # --- Routing -------------------------------------------------------------

    def _route(self, raw: bytes) -> None:
        stats = self.stats
        try:
            line = check_frame(raw.decode("ascii"))
            _, sentence = split_tag_block(line)
            if not sentence.startswith(("$", "!")):
                stats.ignored += 1
                return
            parsed = parse_sentence(sentence)
        except UnicodeDecodeError:
            stats.framing_errors += 1
            return
        except SentenceError as err:
            if err.kind == "checksum":
                stats.checksum_errors += 1
            elif err.kind == "framing":
                stats.framing_errors += 1
            elif sentence.startswith("!"):  # malformed address
                stats.ais_rejected += 1
            else:
                stats.gps_rejected += 1
            return

        stats.record_sentence(self._clock())
        if parsed.start == "$":
            try:
                record = parse_gps(parsed)
            except SentenceError:
                stats.gps_rejected += 1
                return
            if record is None:
                stats.ignored += 1
                return
            stats.gps_ok += 1
            self._on_gps(record)
            return

        rejected_before = self._decoder.stats["rejected"]
        decoded = self._decoder.feed(sentence)
        if self._decoder.stats["rejected"] != rejected_before:
            stats.ais_rejected += 1
        elif isinstance(decoded, VesselPosition):
            stats.ais_ok += 1
            self._on_ais(decoded)
        else:  # nothing, or static data (not routed yet: P3 WP12)
            stats.ignored += 1


class ProbeResult(StrEnum):
    OK = "ok"  # at least one checksum-valid sentence
    NO_DATA = "no_data"  # nothing received
    GARBAGE = "garbage"  # bytes received, none of them a valid sentence (baud rate?)


async def probe(open_transport: OpenTransport, timeout: float = PROBE_TIMEOUT_S) -> ProbeResult:
    """Open the port and wait up to `timeout` s for one valid sentence (SPEC §11.1)."""
    try:
        reader, writer = await open_transport()
    except (OSError, ValueError) as err:
        raise HubConnectionError(str(err)) from err
    received = False
    try:
        async with asyncio.timeout(timeout):
            while line := await reader.readline():
                received = received or bool(line.strip())
                if _is_valid_sentence(line):
                    return ProbeResult.OK
    except (TimeoutError, OSError):
        pass
    except ValueError:  # a "line" longer than the reader limit: bytes, but no sentence
        received = True
    finally:
        if writer is not None:
            writer.close()
            with contextlib.suppress(Exception):
                await writer.wait_closed()
    return ProbeResult.GARBAGE if received else ProbeResult.NO_DATA


def _is_valid_sentence(raw: bytes) -> bool:
    try:
        line = check_frame(raw.strip().decode("ascii"))
        parse_sentence(split_tag_block(line)[1])
    except (UnicodeDecodeError, SentenceError):
        return False
    return True
