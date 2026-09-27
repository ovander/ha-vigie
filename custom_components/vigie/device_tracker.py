"""Position trackers: own boat (SPEC §9.1) and watched AIS targets (SPEC §9.3)."""

from __future__ import annotations

from typing import Any

from homeassistant.components.device_tracker import SourceType, TrackerEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import DOMAIN
from .coordinator import VigieConfigEntry, VigieCoordinator
from .entity import VigieEntity
from .state import COG, HEADING, POSITION, SOG, position_delta_m

POSITION_DEADBAND_M = 5.0  # SPEC §10.2


async def async_setup_entry(
    hass: HomeAssistant,
    entry: VigieConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    _remove_unwatched(hass, entry, coordinator.watch_list)
    async_add_entities(
        [
            OwnBoatTracker(coordinator),
            *(WatchedTargetTracker(coordinator, mmsi) for mmsi in coordinator.watch_list),
        ]
    )


def _remove_unwatched(
    hass: HomeAssistant, entry: VigieConfigEntry, watched: tuple[int, ...]
) -> None:
    """Drop the trackers and devices of MMSIs taken off the watch list (SPEC §9.3)."""
    prefix = f"{entry.entry_id}_ais_"
    keep = {f"{prefix}{mmsi}" for mmsi in watched}
    entities = er.async_get(hass)
    for ent in er.async_entries_for_config_entry(entities, entry.entry_id):
        stale = ent.unique_id.startswith(prefix) and ent.unique_id not in keep
        if ent.domain == "device_tracker" and stale:
            entities.async_remove(ent.entity_id)
    keep_devices = {(DOMAIN, f"{entry.entry_id}_{mmsi}") for mmsi in watched}
    boat = (DOMAIN, entry.entry_id)
    devices = dr.async_get(hass)
    for device in dr.async_entries_for_config_entry(devices, entry.entry_id):
        if boat not in device.identifiers and not device.identifiers & keep_devices:
            devices.async_update_device(device.id, remove_config_entry_id=entry.entry_id)


class OwnBoatTracker(VigieEntity, TrackerEntity):
    """`device_tracker.<boat>`: own position with SOG/COG attributes."""

    _attr_name = None  # the boat's device name
    _attr_source_type = SourceType.GPS

    def __init__(self, coordinator: VigieCoordinator) -> None:
        super().__init__(
            coordinator, "position", deadband=POSITION_DEADBAND_M, delta=position_delta_m
        )
        self._attr_translation_key = None

    def current_value(self) -> tuple[float, float] | None:
        field = self.coordinator.own.get(POSITION)
        if field is None:
            return None
        position: tuple[float, float] = field.value
        return position

    @property
    def latitude(self) -> float | None:
        position = self.current_value()
        return None if position is None else position[0]

    @property
    def longitude(self) -> float | None:
        position = self.current_value()
        return None if position is None else position[1]

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        own = self.coordinator.own
        values = {key: own.get(key) for key in (SOG, COG, HEADING)}
        source = own.position_source
        return {
            **{key: None if field is None else field.value for key, field in values.items()},
            "position_source": None if source is None else str(source),
        }


class WatchedTargetTracker(VigieEntity, TrackerEntity):
    """`device_tracker.ais_<mmsi>`: a watched AIS target on its own device (SPEC §9.3).

    Unavailable while the target is not in the table (not heard yet, or expired), so a
    stale position is never shown (NFR-05). Its position does not need our own.
    """

    _attr_name = None  # the target's device name, "AIS <mmsi>"
    _attr_source_type = SourceType.GPS

    def __init__(self, coordinator: VigieCoordinator, mmsi: int) -> None:
        super().__init__(
            coordinator, f"ais_{mmsi}", deadband=POSITION_DEADBAND_M, delta=position_delta_m
        )
        self.mmsi = mmsi
        self._attr_translation_key = None
        entry_id = coordinator.entry.entry_id
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{entry_id}_{mmsi}")},
            translation_key="watched_target",
            translation_placeholders={"mmsi": str(mmsi)},
            model="AIS target",
            via_device=(DOMAIN, entry_id),
        )

    def current_value(self) -> tuple[float, float] | None:
        target = self.coordinator.targets.get(self.mmsi)
        if target is None:
            return None
        lat, lon = target.report.latitude, target.report.longitude
        return None if lat is None or lon is None else (lat, lon)

    @property
    def available(self) -> bool:
        return self.coordinator.connected and self.current_value() is not None

    @property
    def latitude(self) -> float | None:
        position = self.current_value()
        return None if position is None else position[0]

    @property
    def longitude(self) -> float | None:
        position = self.current_value()
        return None if position is None else position[1]

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        target = self.coordinator.targets.get(self.mmsi)
        attrs: dict[str, Any] = {"mmsi": self.mmsi}
        if target is None:
            return attrs
        report = target.report
        e = self.coordinator.picture.encounters.get(self.mmsi)
        attrs.update(
            {
                "name": target.name,
                "class": target.ais_class,
                "sog": report.sog_knots,
                "cog": report.cog_deg,
                "heading": report.heading_deg,
                "nav_status": report.nav_status,
                "age_s": round(self.coordinator.now() - target.last_seen),
                "distance_nm": None if e is None else round(e.distance_nm, 2),
                "bearing": None if e is None else round(e.bearing_deg),
                "cpa_nm": None if e is None or e.cpa_nm is None else round(e.cpa_nm, 2),
                "tcpa_min": None if e is None or e.tcpa_min is None else round(e.tcpa_min, 1),
            }
        )
        return attrs
