"""Connection binary sensor (SPEC §9.5)."""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import VigieConfigEntry, VigieCoordinator
from .entity import VigieEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: VigieConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities([ConnectedBinarySensor(entry.runtime_data)])


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
