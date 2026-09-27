"""Constants for the Vigie integration."""

DOMAIN = "vigie"

# Config entry data (SPEC §11.1)
CONF_SERIAL_PORT = "serial_port"
CONF_BAUDRATE = "baudrate"

DEFAULT_SERIAL_PORT = "/dev/ttyUSB0"
DEFAULT_BAUDRATE = 38400
BAUDRATES = (38400, 4800)  # offered in the form; custom values allowed (OD-14)
SERIAL_BY_ID_GLOB = "/dev/serial/by-id/*"

# Options (SPEC §11.2)
CONF_UPDATE_INTERVAL = "update_interval"  # seconds
CONF_STALE_TIMEOUT = "stale_timeout"  # seconds
CONF_EXPIRY_CLASS_A = "expiry_class_a"  # minutes
CONF_EXPIRY_CLASS_B = "expiry_class_b"  # minutes, also anchored/moored Class A
CONF_INCLUDE_OWN_VDO = "include_own_vdo"
CONF_OWN_MMSI = "own_mmsi"
CONF_CPA_THRESHOLD = "cpa_threshold"  # NM
CONF_TCPA_THRESHOLD = "tcpa_threshold"  # minutes
CONF_EXCLUDE_STATIONARY = "exclude_stationary"  # anchored/moored Class A never threats
CONF_WATCH_LIST = "watch_list"  # MMSIs with their own device_tracker (SPEC §9.3)

DEFAULT_OPTIONS: dict[str, int | float | bool] = {
    CONF_UPDATE_INTERVAL: 1,
    CONF_STALE_TIMEOUT: 10,
    CONF_EXPIRY_CLASS_A: 10,
    CONF_EXPIRY_CLASS_B: 15,
    CONF_INCLUDE_OWN_VDO: True,
    CONF_CPA_THRESHOLD: 0.5,
    CONF_TCPA_THRESHOLD: 15,
    CONF_EXCLUDE_STATIONARY: True,
}
