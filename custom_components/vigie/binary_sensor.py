"""Binary sensors: connection (SPEC §9.5), collision risk (SPEC §8.2, §9.2), anchor alarm
(SPEC §8.4, §9.6)."""

from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import STATIC_ATTRIBUTES, VigieConfigEntry, VigieCoordinator
from .entity import VigieEntity


def _round(value: float | None, digits: int) -> float | None:
    return None if value is None else round(value, digits)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: VigieConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(
        [
            ConnectedBinarySensor(coordinator),
            CollisionRiskBinarySensor(coordinator),
            AnchorAlarmBinarySensor(coordinator),
        ]
    )


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
    # The threat's CPA and TCPA, for the notification (WP34); their sensors keep the history
    _unrecorded_attributes = frozenset({"cpa_nm", "tcpa_min"})

    def __init__(self, coordinator: VigieCoordinator) -> None:
        super().__init__(coordinator, "collision_risk")

    def current_value(self) -> bool | None:
        if not self.coordinator.picture.own_known:
            return None
        return self.coordinator.risk.active

    def gate_value(self) -> Any:
        # Written when the state, the number of threats, the most urgent one, its static
        # data or its CPA/TCPA (as rounded in the attributes) changes
        picture = self.coordinator.picture
        urgent = picture.closest_threat
        if urgent is None:
            return (self.current_value(), 0, None, None, None)
        mmsi, e = urgent
        static = self.coordinator.statics.get(mmsi)
        cpa = (_round(e.cpa_nm, 2), _round(e.tcpa_min, 1))
        return (self.current_value(), len(picture.threats), mmsi, static, cpa)

    @property
    def is_on(self) -> bool:
        return self.coordinator.risk.active

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        picture = self.coordinator.picture
        urgent = picture.closest_threat
        if urgent is None:
            none = dict.fromkeys(STATIC_ATTRIBUTES)
            return {
                "threat_count": 0,
                "mmsi": None,
                "name": None,
                "cpa_nm": None,
                "tcpa_min": None,
                **none,
            }
        mmsi, e = urgent
        return {
            "threat_count": len(picture.threats),
            "mmsi": mmsi,
            "name": self.coordinator.target_name(mmsi),
            "cpa_nm": _round(e.cpa_nm, 2),
            "tcpa_min": _round(e.tcpa_min, 1),
            **self.coordinator.static_attributes(mmsi),
        }


class AnchorAlarmBinarySensor(VigieEntity, BinarySensorEntity):
    """On while the anchor alarm is on: drag (latched) or no position (SPEC §8.4).

    Always available: while armed, a missing position is itself an alarm, so "unavailable"
    never hides one. Off when disarmed.
    """

    _attr_device_class = BinarySensorDeviceClass.SAFETY
    _always_available = True
    # The distance, for the notification (WP34); the distance sensor keeps the history
    _unrecorded_attributes = frozenset({"distance_m"})

    def __init__(self, coordinator: VigieCoordinator) -> None:
        super().__init__(coordinator, "anchor_alarm")

    def current_value(self) -> Any:
        status = self.coordinator.anchor_status
        return (status.alarm, status.reason)

    def gate_value(self) -> Any:
        # Also written when the distance moves by a metre or the radius changes
        status = self.coordinator.anchor_status
        return (status.alarm, status.reason, _round(status.distance_m, 0), status.radius_m)

    @property
    def is_on(self) -> bool:
        return self.coordinator.anchor_status.alarm

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        status = self.coordinator.anchor_status
        return {
            "reason": status.reason,
            # None when disarmed or without position, like the distance sensor
            "distance_m": _round(status.distance_m, 0),
            "radius_m": status.radius_m if status.armed else None,
        }
