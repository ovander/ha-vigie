"""Diagnostics download (SPEC §9.5): configuration (redacted) and counters."""

from __future__ import annotations

from dataclasses import fields
from datetime import datetime
from typing import Any

from homeassistant.components.diagnostics import REDACTED, async_redact_data
from homeassistant.core import HomeAssistant

from .const import CONF_OWN_MMSI, CONF_SERIAL_PORT
from .coordinator import VigieConfigEntry
from .state import (
    COG,
    FIX_MODE,
    FIX_QUALITY,
    HDOP,
    HEADING,
    PDOP,
    POSITION,
    SATELLITES,
    SOG,
    UTC_TIME,
    VARIATION,
)

# by-id paths contain the adapter's serial number; MMSI and position identify the boat
TO_REDACT = {CONF_SERIAL_PORT, CONF_OWN_MMSI}
OWN_KEYS = (POSITION, SOG, COG, HEADING, UTC_TIME, VARIATION, FIX_QUALITY, SATELLITES, HDOP)
OWN_KEYS += (FIX_MODE, PDOP)


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: VigieConfigEntry
) -> dict[str, Any]:
    coordinator = entry.runtime_data
    now = coordinator.now()
    stats = coordinator.hub.stats
    counters = {f.name: getattr(stats, f.name) for f in fields(stats) if not f.name.startswith("_")}
    counters["sentences_per_min"] = stats.sentences_per_min(now)
    last = counters.pop("last_sentence_at")
    counters["last_sentence_age_s"] = None if last is None else round(now - last, 1)

    own: dict[str, Any] = {}
    for key in OWN_KEYS:
        field = coordinator.own.get(key)
        if field is None:
            own[key] = None
            continue
        value = field.value
        if key == POSITION:
            value = REDACTED
        elif isinstance(value, datetime):
            value = value.isoformat()
        elif isinstance(value, str):
            value = str(value)  # enum members as plain strings
        own[key] = {
            "value": value,
            "source": str(field.source),
            "sentence": field.sentence,
            "age_s": round(now - field.updated_at, 1),
        }

    classes = [t.ais_class for t in coordinator.targets.targets()]
    return {
        "entry": {
            "data": async_redact_data(dict(entry.data), TO_REDACT),
            "options": async_redact_data(dict(entry.options), TO_REDACT),
        },
        "connected": coordinator.connected,
        "update_interval_s": coordinator.update_interval_s,
        "stats": counters,
        "own_state": own,
        "own_mmsi_known": coordinator.own.own_mmsi is not None,
        "targets": {
            "count": len(classes),
            "class_a": classes.count("A"),
            "class_b": classes.count("B"),
        },
    }
