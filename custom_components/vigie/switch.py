"""Switch: anchor watch on/off (SPEC §9.6, OD-22)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import DOMAIN
from .coordinator import NoOwnPosition, VigieConfigEntry, VigieCoordinator
from .entity import VigieEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: VigieConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities([AnchorWatchSwitch(entry.runtime_data)])


class AnchorWatchSwitch(VigieEntity, SwitchEntity):
    """On = armed. Turning it on drops the anchor at own position with the set radius."""

    _always_available = True  # the watch can be raised even while the port is down

    def __init__(self, coordinator: VigieCoordinator) -> None:
        super().__init__(coordinator, "anchor_watch")

    def current_value(self) -> Any:
        anchor = self.coordinator.anchor
        return (anchor.armed, anchor.anchor, anchor.radius_m, anchor.armed_at)

    @property
    def is_on(self) -> bool:
        return self.coordinator.anchor.armed

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        anchor = self.coordinator.anchor
        lat, lon = anchor.anchor or (None, None)
        armed_at = anchor.armed_at
        return {
            "anchor_latitude": lat,
            "anchor_longitude": lon,
            "radius_m": anchor.radius_m,
            "armed_at": None if armed_at is None else datetime.fromtimestamp(armed_at, UTC),
        }

    async def async_turn_on(self, **kwargs: Any) -> None:
        try:
            self.coordinator.drop_anchor()
        except NoOwnPosition as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key="no_own_position"
            ) from err

    async def async_turn_off(self, **kwargs: Any) -> None:
        self.coordinator.raise_anchor()
