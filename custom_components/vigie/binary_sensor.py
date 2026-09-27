"""Binary sensors: connection (SPEC §9.5) and collision risk (SPEC §8.2, §9.2)."""

from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import STATIC_ATTRIBUTES, VigieConfigEntry, VigieCoordinator
from .entity import VigieEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: VigieConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    async_add_entities([ConnectedBinarySensor(coordinator), CollisionRiskBinarySensor(coordinator)])


class ConnectedBinarySensor(VigieEntity, BinarySensorEntity):
    """On while the serial port is open; stays available to report the outage."""

    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _always_available = True

    def __init__(self, coordinator: VigieCoordinator) -> None:
        super().__init__(coordinator, "connected")

    def current_value(self) -> bool:
        return self.coordinator.connected

    @property
    def is_on(self) -> bool:
        return self.coordinator.connected


class CollisionRiskBinarySensor(VigieEntity, BinarySensorEntity):
    """On while a threat exists, with the anti-flapping latch (SPEC §8.2, OD-15).

    Unavailable, never "off", when own position is unknown: the risk cannot be assessed.
    """

    _attr_device_class = BinarySensorDeviceClass.SAFETY

    def __init__(self, coordinator: VigieCoordinator) -> None:
        super().__init__(coordinator, "collision_risk")

    def current_value(self) -> bool | None:
        if not self.coordinator.picture.own_known:
            return None
        return self.coordinator.risk.active

    def gate_value(self) -> Any:
        # Written when the state, the number of threats, the most urgent one or its static
        # data changes
        picture = self.coordinator.picture
        urgent = picture.closest_threat
        static = None if urgent is None else self.coordinator.statics.get(urgent[0])
        return (self.current_value(), len(picture.threats), urgent and urgent[0], static)

    @property
    def is_on(self) -> bool:
        return self.coordinator.risk.active

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        picture = self.coordinator.picture
        urgent = picture.closest_threat
        if urgent is None:
            none = dict.fromkeys(STATIC_ATTRIBUTES)
            return {"threat_count": 0, "mmsi": None, "name": None, **none}
        mmsi = urgent[0]
        return {
            "threat_count": len(picture.threats),
            "mmsi": mmsi,
            "name": self.coordinator.target_name(mmsi),
            **self.coordinator.static_attributes(mmsi),
        }
