"""Home Assistant coordinator: owns the hub and the domain state (SPEC §5.2 C-04, §6).

Push-based (`iot_class: local_push`): the hub delivers records as they arrive and the
domain state is updated immediately. Entities are notified once per `update_interval`
by an internal tick, which also expires targets and lets stale values age out, and at
once when the connection changes (SPEC §10.1, §10.2). Home Assistant never polls.
"""

from __future__ import annotations

import asyncio
import contextlib
import time
from collections.abc import Callable
from datetime import datetime, timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers.event import async_track_time_interval

from .const import (
    CONF_BAUDRATE,
    CONF_EXPIRY_CLASS_A,
    CONF_EXPIRY_CLASS_B,
    CONF_INCLUDE_OWN_VDO,
    CONF_OWN_MMSI,
    CONF_SERIAL_PORT,
    CONF_STALE_TIMEOUT,
    CONF_UPDATE_INTERVAL,
    DEFAULT_OPTIONS,
    DOMAIN,
)
from .hub import Hub, serial_transport
from .nmea.ais_decoder import VesselPosition
from .nmea.parsers import GpsRecord
from .state import AisTargetTable, OwnBoatState

type VigieConfigEntry = ConfigEntry[VigieCoordinator]


def _monotonic() -> float:
    # Looked up at call time so the test harness's frozen clock applies
    return time.monotonic()


class VigieCoordinator:
    """Single source of truth for one boat (one config entry, one serial port)."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        options = {**DEFAULT_OPTIONS, **entry.options}
        self.port: str = entry.data[CONF_SERIAL_PORT]
        self.update_interval_s = int(options[CONF_UPDATE_INTERVAL])
        use_vdo = bool(options[CONF_INCLUDE_OWN_VDO])
        own_mmsi = options.get(CONF_OWN_MMSI)
        self.own = OwnBoatState(
            stale_timeout_s=float(options[CONF_STALE_TIMEOUT]),
            use_vdo=use_vdo,
            own_mmsi=int(own_mmsi) if own_mmsi is not None else None,
            clock=_monotonic,
        )
        self.targets = AisTargetTable(
            expiry_a_s=float(options[CONF_EXPIRY_CLASS_A]) * 60,
            expiry_b_s=float(options[CONF_EXPIRY_CLASS_B]) * 60,
            clock=_monotonic,
        )
        self.hub = Hub(
            serial_transport(self.port, int(entry.data[CONF_BAUDRATE])),
            on_gps=self._on_gps,
            on_ais=self._on_ais,
            on_connection=self._on_connection,
            include_own=use_vdo,
            name=self.port,
            clock=_monotonic,
        )
        self.reader_task: asyncio.Task[None] | None = None
        self._listeners: list[Callable[[], None]] = []
        self._unsub_tick: CALLBACK_TYPE | None = None

    @property
    def connected(self) -> bool:
        return self.hub.connected

    @staticmethod
    def now() -> float:
        """The monotonic clock shared by the hub, the domain state and the entities."""
        return _monotonic()

    async def async_start(self) -> None:
        """Open the port (raises HubConnectionError) and start reading."""
        await self.hub.connect()
        self._unsub_tick = async_track_time_interval(
            self.hass, self._tick, timedelta(seconds=self.update_interval_s)
        )
        self.reader_task = self.entry.async_create_background_task(
            self.hass, self.hub.run(), f"{DOMAIN} reader {self.port}"
        )

    async def async_stop(self) -> None:
        """Stop the tick and the reader, close the port (NFR-07)."""
        if self._unsub_tick is not None:
            self._unsub_tick()
            self._unsub_tick = None
        if self.reader_task is not None:
            self.reader_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self.reader_task
        await self.hub.close()
        self._listeners.clear()

    @callback
    def async_add_listener(self, update_callback: Callable[[], None]) -> CALLBACK_TYPE:
        """Call `update_callback` on every tick and connection change; returns unsubscribe."""
        self._listeners.append(update_callback)

        @callback
        def remove() -> None:
            with contextlib.suppress(ValueError):
                self._listeners.remove(update_callback)

        return remove

    # --- Hub callbacks (run in the event loop) --------------------------------

    def _on_gps(self, record: GpsRecord) -> None:
        self.own.apply_gps(record)

    def _on_ais(self, position: VesselPosition) -> None:
        if position.own_ship:
            self.own.apply_vdo(position)
        else:
            self.targets.upsert(position, self.own.own_mmsi)

    def _on_connection(self, connected: bool) -> None:
        self._notify()

    # --- Tick -------------------------------------------------------------------

    @callback
    def _tick(self, _now: datetime) -> None:
        self.targets.expire()
        self._notify()

    def _notify(self) -> None:
        for update_callback in list(self._listeners):
            update_callback()
