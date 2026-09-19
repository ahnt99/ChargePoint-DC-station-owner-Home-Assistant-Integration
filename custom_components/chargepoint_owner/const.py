"""Constants for the ChargePoint integration."""
from __future__ import annotations

import os

DOMAIN = "chargepoint_owner"

# Configuration keys
CONF_API_KEY = "api_key"
CONF_API_PASSWORD = "api_password"
CONF_STATION_ID = "station_id"
CONF_SCAN_INTERVAL = "scan_interval"

# Defaults
DEFAULT_SCAN_INTERVAL = 60  # seconds
DEFAULT_NAME = "ChargePoint"

# ChargePoint SOAP API
# The WSDL is bundled as a local file (cp_api_5.0.wsdl) so client setup never
# depends on fetching it live. This makes the integration resilient to transient
# network outages and to ChargePoint temporarily taking the WSDL URL offline
# (a live fetch failure would otherwise leave the zeep client in a broken state
# that is cached forever). The endpoint is still overridden below to the live
# URL, so only the *schema* is local — all calls still hit ChargePoint.
# If ChargePoint ever ships a new WSDL, re-download it and replace the file.
CHARGEPOINT_WSDL = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "cp_api_5.0.wsdl"
)
CHARGEPOINT_ENDPOINT = "https://webservices.chargepoint.com/webservices/chargepoint/services/5.1"
WSSE_NS = "http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd"
PASSWORD_TYPE = "http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-username-token-profile-1.0#PasswordText"

# Port statuses
STATUS_AVAILABLE = "AVAILABLE"
STATUS_INUSE = "INUSE"
STATUS_UNKNOWN = "UNKNOWN"
STATUS_OFFLINE = "OFFLINE"

# Sensor unique ID suffixes
SENSOR_SUFFIX_STATUS = "status"
SENSOR_SUFFIX_ENERGY = "energy_kwh"
SENSOR_SUFFIX_LOAD = "load_kw"
SENSOR_SUFFIX_SESSION_TIME = "session_time"

# Coordinator key
COORDINATOR = "coordinator"
