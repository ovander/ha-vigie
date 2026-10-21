"""Number: anchor watch radius (SPEC §9.6, OD-25)."""

from __future__ import annotations

from homeassistant.components.number import NumberDeviceClass, NumberEntity, NumberMode
from homeassistant.const import EntityCategory, UnitOfLength
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .anchor import MAX_RADIUS_M, MIN_RADIUS_M
from .coordinator import VigieConfigEntry, VigieCoordinator
from .entity import VigieEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: VigieConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities([AnchorRadiusNumber(entry.runtime_data)])


class AnchorRadiusNumber(VigieEntity, NumberEntity):
    """Swing radius; applies at once while armed, kept across restarts (SPEC §10.4)."""

    _attr_device_class = NumberDeviceClass.DISTANCE
    _attr_native_unit_of_measurement = UnitOfLength.METERS
    _attr_native_min_value = MIN_RADIUS_M
    _attr_native_max_value = MAX_RADIUS_M
    _attr_native_step = 5
    _attr_mode = NumberMode.BOX
    _attr_entity_category = EntityCategory.CONFIG
    _always_available = True

    def __init__(self, coordinator: VigieCoordinator) -> None:
        super().__init__(coordinator, "anchor_radius")

    def current_value(self) -> float:
        return self.coordinator.anchor.radius_m

    @property
    def native_value(self) -> float:
        return self.coordinator.anchor.radius_m

    async def async_set_native_value(self, value: float) -> None:
        # HA has already checked the range (min/max above)
        self.coordinator.set_anchor_radius(value)
