"""Sensors: own boat (SPEC §9.1), AIS traffic (§9.2), diagnostics (§9.5)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import DEGREE, EntityCategory, UnitOfSpeed, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import VigieConfigEntry, VigieCoordinator
from .entity import VigieEntity
from .nmea.parsers import FixQuality
from .state import COG, FIX_QUALITY, HDOP, HEADING, POSITION, SATELLITES, SOG, Source, angle_delta

TARGETS_LIMIT = 50  # nearest targets listed in the attribute (SPEC §9.2, OD-04)
TARGETS_REBUILD_S = 5.0  # attribute rebuilt at most this often (SPEC §10.2)


def _own(key: str) -> Callable[[VigieCoordinator], Any]:
    def value(coordinator: VigieCoordinator) -> Any:
        field = coordinator.own.get(key)
        return None if field is None else field.value

    return value


def _fix_quality(coordinator: VigieCoordinator) -> str | None:
    field = coordinator.own.get(FIX_QUALITY)
    return None if field is None else str(field.value)


def _position_source(coordinator: VigieCoordinator) -> str | None:
    source = coordinator.own.position_source
    return None if source is None else str(source)


def _sentence_age(coordinator: VigieCoordinator) -> int | None:
    last = coordinator.hub.stats.last_sentence_at
    return None if last is None else round(coordinator.now() - last)


@dataclass(frozen=True, kw_only=True)
class VigieSensorDescription(SensorEntityDescription):
    value_fn: Callable[[VigieCoordinator], Any]
    deadband: float | None = None
    circular: bool = False  # angle dead-band wraps around north
    always_available: bool = False


SENSORS: tuple[VigieSensorDescription, ...] = (
    # Own boat (SPEC §9.1)
    VigieSensorDescription(
        key=SOG,
        translation_key=SOG,
        device_class=SensorDeviceClass.SPEED,
        native_unit_of_measurement=UnitOfSpeed.KNOTS,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value_fn=_own(SOG),
        deadband=0.1,
    ),
    VigieSensorDescription(
        key=COG,
        translation_key=COG,
        native_unit_of_measurement=DEGREE,
        state_class=SensorStateClass.MEASUREMENT_ANGLE,  # OD-10
        suggested_display_precision=0,
        value_fn=_own(COG),
        deadband=1.0,
        circular=True,
    ),
    VigieSensorDescription(
        key=HEADING,
        translation_key=HEADING,
        native_unit_of_measurement=DEGREE,
        state_class=SensorStateClass.MEASUREMENT_ANGLE,  # OD-10
        suggested_display_precision=0,
        value_fn=_own(HEADING),
        deadband=1.0,
        circular=True,
    ),
    VigieSensorDescription(
        key=FIX_QUALITY,
        translation_key=FIX_QUALITY,
        device_class=SensorDeviceClass.ENUM,
        options=[str(q) for q in FixQuality],
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=_fix_quality,
    ),
    VigieSensorDescription(
        key=SATELLITES,
        translation_key=SATELLITES,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=_own(SATELLITES),
    ),
    VigieSensorDescription(
        key=HDOP,
        translation_key=HDOP,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=_own(HDOP),
    ),
    # Diagnostics (SPEC §9.5)
    VigieSensorDescription(
        key="sentences_per_min",
        translation_key="sentences_per_min",
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda c: c.hub.stats.sentences_per_min(c.now()),
        deadband=1,
        always_available=True,
    ),
    VigieSensorDescription(
        key="checksum_errors",
        translation_key="checksum_errors",
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda c: c.hub.stats.checksum_errors,
        always_available=True,
    ),
    VigieSensorDescription(
        key="ais_rejected",
        translation_key="ais_rejected",
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda c: c.hub.stats.ais_rejected,
        always_available=True,
    ),
    VigieSensorDescription(
        key="last_sentence_age",
        translation_key="last_sentence_age",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=_sentence_age,
        deadband=1,
        always_available=True,
    ),
    VigieSensorDescription(
        key="own_position_source",
        translation_key="own_position_source",
        device_class=SensorDeviceClass.ENUM,
        options=[str(s) for s in Source],
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=_position_source,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: VigieConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(
        [
            *(VigieSensor(coordinator, description) for description in SENSORS),
            AisTargetsSensor(coordinator),
        ]
    )


class VigieSensor(VigieEntity, SensorEntity):
    entity_description: VigieSensorDescription

    def __init__(self, coordinator: VigieCoordinator, description: VigieSensorDescription) -> None:
        super().__init__(
            coordinator,
            description.key,
            deadband=description.deadband,
            **({"delta": angle_delta} if description.circular else {}),
        )
        self.entity_description = description
        self._always_available = description.always_available

    def current_value(self) -> Any:
        return self.entity_description.value_fn(self.coordinator)

    @property
    def native_value(self) -> Any:
        return self.current_value()


class AisTargetsSensor(VigieEntity, SensorEntity):
    """Number of live AIS targets; `targets` lists the 50 nearest (SPEC §9.2)."""

    _attr_state_class = SensorStateClass.MEASUREMENT
    # Large and changing: kept out of the recorder (SPEC §10.2)
    _unrecorded_attributes = frozenset({"targets"})

    def __init__(self, coordinator: VigieCoordinator) -> None:
        super().__init__(coordinator, "ais_targets")
        self._targets: list[dict[str, Any]] = []
        self._rebuilt_at: float | None = None

    def current_value(self) -> Any:
        return len(self.coordinator.targets)

    @property
    def available(self) -> bool:
        # Does not depend on own position: distances are None without it (SPEC §10.1)
        return self.coordinator.connected

    @property
    def native_value(self) -> int:
        return len(self.coordinator.targets)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"targets": self._targets}

    def _should_write(self) -> bool:
        rebuilt = self._rebuild_targets()
        return super()._should_write() or rebuilt

    def _rebuild_targets(self) -> bool:
        """Rebuild the list at most every 5 s; True when it changed."""
        now = self.coordinator.now()
        if self._rebuilt_at is not None and now - self._rebuilt_at < TARGETS_REBUILD_S - 1e-6:
            return False
        position = self.coordinator.own.get(POSITION)
        lat, lon = position.value if position else (None, None)
        targets = [
            {
                "mmsi": t.mmsi,
                "name": t.name,
                "class": t.ais_class,
                "lat": _round(t.report.latitude, 5),
                "lon": _round(t.report.longitude, 5),
                "sog": _round(t.report.sog_knots, 1),
                "cog": _round(t.report.cog_deg, 1),
                "distance_nm": _round(distance, 2),
                "age_s": round(now - t.last_seen),
            }
            for t, distance in self.coordinator.targets.nearest(lat, lon, TARGETS_LIMIT)
        ]
        if targets:  # the first list with data starts the 5 s rhythm
            self._rebuilt_at = now
        changed = targets != self._targets
        self._targets = targets
        return changed


def _round(value: float | None, digits: int) -> float | None:
    return None if value is None else round(value, digits)
