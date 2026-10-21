"""Home Assistant coordinator: owns the hub and the domain state (SPEC §5.2 C-04, §6).

Push-based (`iot_class: local_push`): the hub delivers records as they arrive and the
domain state is updated immediately. Entities are notified once per `update_interval`
by an internal tick, which also expires targets and lets stale values age out, and at
once when the connection changes (SPEC §10.1, §10.2). Home Assistant never polls.

The tick also runs the anchor watch (SPEC §8.4). Its state is kept with Home Assistant's
storage helper and written within a second of a change, so it survives a power cut
(SPEC §10.4, OD-26).
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .anchor import AnchorStatus, AnchorWatch
from .const import (
    CONF_ANCHOR_CONFIRM,
    CONF_ANCHOR_POSITION_TIMEOUT,
    CONF_BAUDRATE,
    CONF_CPA_THRESHOLD,
    CONF_EXCLUDE_STATIONARY,
    CONF_EXPIRY_CLASS_A,
    CONF_EXPIRY_CLASS_B,
    CONF_INCLUDE_OWN_VDO,
    CONF_OWN_MMSI,
    CONF_SERIAL_PORT,
    CONF_STALE_TIMEOUT,
    CONF_TCPA_THRESHOLD,
    CONF_UPDATE_INTERVAL,
    CONF_WATCH_LIST,
    DEFAULT_OPTIONS,
    DOMAIN,
)
from .hub import Hub, serial_transport
from .nmea.ais_decoder import VesselPosition, VesselStatic
from .nmea.parsers import GpsRecord
from .state import COG, POSITION, SOG, AisStaticStore, AisTargetTable, OwnBoatState, StaticInfo
from .traffic import (
    EMPTY_PICTURE,
    Kinematics,
    RiskLatch,
    TargetReport,
    ThreatSettings,
    TrafficPicture,
    assess,
)

type VigieConfigEntry = ConfigEntry[VigieCoordinator]

_LOGGER = logging.getLogger(__name__)

ANCHOR_STORE_VERSION = 1
ANCHOR_SAVE_DELAY_S = 1  # power on board can be cut at any time (SPEC §3.2)

STATIC_ATTRIBUTES = (
    "ship_type",
    "ship_type_code",
    "callsign",
    "imo",
    "length_m",
    "beam_m",
    "draught_m",
    "destination",
)


class NoOwnPosition(ValueError):
    """The anchor cannot be dropped at own position: there is none."""


def anchor_store(hass: HomeAssistant, entry_id: str) -> Store[dict[str, Any]]:
    return Store(hass, ANCHOR_STORE_VERSION, f"{DOMAIN}.anchor.{entry_id}")


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
            on_static=self._on_static,
            on_connection=self._on_connection,
            include_own=use_vdo,
            name=self.port,
            clock=_monotonic,
        )
        self.statics = AisStaticStore(clock=_monotonic)
        self.threat_settings = ThreatSettings(
            cpa_nm=float(options[CONF_CPA_THRESHOLD]),
            tcpa_min=float(options[CONF_TCPA_THRESHOLD]),
            exclude_stationary=bool(options[CONF_EXCLUDE_STATIONARY]),
        )
        self.watch_list: tuple[int, ...] = tuple(int(m) for m in options.get(CONF_WATCH_LIST, ()))
        self.picture: TrafficPicture = EMPTY_PICTURE
        self.risk = RiskLatch(clock=_monotonic)
        self.anchor = AnchorWatch(
            confirm_s=float(options[CONF_ANCHOR_CONFIRM]),
            position_timeout_s=float(options[CONF_ANCHOR_POSITION_TIMEOUT]),
            clock=_monotonic,
        )
        self._anchor_store = anchor_store(hass, entry.entry_id)
        self._anchor_saved: Any = None
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
        """Restore the anchor watch, open the port (raises HubConnectionError), read."""
        await self._async_restore_anchor()
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
        if position.static is not None:  # type 19
            self._on_static(position.static)

    def _on_static(self, report: VesselStatic) -> None:
        self.statics.update(report, self.own.own_mmsi)

    def _on_connection(self, connected: bool) -> None:
        self._notify()

    # --- Tick -------------------------------------------------------------------

    @callback
    def _tick(self, _now: datetime) -> None:
        self.targets.expire()
        self.statics.expire()
        self.update_traffic()
        self.update_anchor()
        self._notify()

    @property
    def anchor_status(self) -> AnchorStatus:
        return self.anchor.status

    def update_anchor(self) -> None:
        """Check the anchor watch against own position (SPEC §8.4); save what changed."""
        position = self.own.get(POSITION) if self.connected else None
        if position is None:
            self.anchor.update(None)
        else:
            self.anchor.update(position.value, fix_at=position.updated_at)
        self._save_anchor()

    def drop_anchor(
        self,
        latitude: float | None = None,
        longitude: float | None = None,
        radius_m: float | None = None,
    ) -> None:
        """Arm or re-drop the anchor at the given point, else at own position.

        Raises NoOwnPosition without either, ValueError for invalid values.
        """
        if latitude is None and longitude is None:
            position = self.own.get(POSITION) if self.connected else None
            if position is None:
                raise NoOwnPosition("no own position to drop the anchor at")
            latitude, longitude = position.value
        self.anchor.arm(latitude, longitude, radius_m, armed_at=dt_util.utcnow().timestamp())
        self._anchor_changed()

    def raise_anchor(self) -> None:
        self.anchor.disarm()
        self._anchor_changed()

    def set_anchor_radius(self, radius_m: float) -> None:
        """Raises ValueError outside 10–500 m."""
        self.anchor.set_radius(radius_m)
        self._anchor_changed()

    def _anchor_changed(self) -> None:
        self.update_anchor()
        self._notify()

    def _anchor_data(self) -> dict[str, Any]:
        return {"radius_m": self.anchor.radius_m, "watch": self.anchor.to_dict()}

    def _save_anchor(self) -> None:
        key = self._anchor_key()
        if key != self._anchor_saved:
            self._anchor_saved = key
            self._anchor_store.async_delay_save(self._anchor_data, ANCHOR_SAVE_DELAY_S)

    async def _async_restore_anchor(self) -> None:
        data = await self._anchor_store.async_load()
        if data:
            try:
                self.anchor.set_radius(data["radius_m"])
                self.anchor.restore(data.get("watch"))
            except (KeyError, TypeError, ValueError) as err:
                _LOGGER.warning("Anchor watch not restored, stored state invalid: %s", err)
        self._anchor_saved = self._anchor_key()

    def _anchor_key(self) -> Any:
        """What decides a save: the maximum distance grows at every swing, so whole metres."""
        watch = self.anchor.to_dict()
        if watch is not None:
            watch["max_distance_m"] = int(watch["max_distance_m"])
        return (self.anchor.radius_m, watch)

    def update_traffic(self) -> None:
        """Recompute CPA/TCPA for every target and the collision risk (SPEC §8)."""
        now = self.now()
        self.picture = assess(
            self._own_kinematics(), self._target_reports(), self.threat_settings, now
        )
        if self.picture.own_known:  # without own position the risk is unknown, not "off"
            self.risk.update(set(self.picture.threats), self.picture.encounters)

    def static_info(self, mmsi: int) -> StaticInfo | None:
        return self.statics.get(mmsi)

    def static_attributes(self, mmsi: int) -> dict[str, Any]:
        """Static data shown on the entities of one target (SPEC §9.4, OD-17, OD-20)."""
        info = self.statics.get(mmsi)
        if info is None:
            return dict.fromkeys(STATIC_ATTRIBUTES)
        return {
            "ship_type": info.ship_category,
            "ship_type_code": info.ship_type,
            "callsign": info.callsign,
            "imo": info.imo,
            "length_m": info.length_m,
            "beam_m": info.beam_m,
            "draught_m": info.draught_m,
            "destination": info.destination,
        }

    def target_name(self, mmsi: int) -> str | None:
        """Name from static data (types 5, 24, 19), else the last one a position carried."""
        info = self.statics.get(mmsi)
        if info is not None and info.name:
            return info.name
        target = self.targets.get(mmsi)
        return None if target is None else target.name

    def _own_kinematics(self) -> Kinematics | None:
        position = self.own.get(POSITION)
        if position is None:
            return None
        sog, cog = self.own.get(SOG), self.own.get(COG)
        lat, lon = position.value
        return Kinematics(
            lat,
            lon,
            None if sog is None else sog.value,
            None if cog is None else cog.value,
            position.updated_at,
        )

    def _target_reports(self) -> list[TargetReport]:
        return [
            TargetReport(
                t.mmsi,
                Kinematics(
                    t.report.latitude,
                    t.report.longitude,
                    t.report.sog_knots,
                    t.report.cog_deg,
                    t.last_seen,
                ),
                t.report.nav_status,
            )
            for t in self.targets.targets()
        ]

    def _notify(self) -> None:
        for update_callback in list(self._listeners):
            update_callback()
