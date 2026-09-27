"""Own-boat position tracker (SPEC §9.1)."""

from __future__ import annotations

from typing import Any

from homeassistant.components.device_tracker import SourceType, TrackerEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import VigieConfigEntry, VigieCoordinator
from .entity import VigieEntity
from .state import COG, HEADING, POSITION, SOG, position_delta_m

POSITION_DEADBAND_M = 5.0  # SPEC §10.2


async def async_setup_entry(
    hass: HomeAssistant,
    entry: VigieConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities([OwnBoatTracker(entry.runtime_data)])


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
