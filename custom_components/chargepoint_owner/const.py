"""Constants for the ChargePoint integration."""

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
CHARGEPOINT_WSDL = "https://webservices.chargepoint.com/cp_api_5.0.wsdl"
CHARGEPOINT_ENDPOINT = "https://webservices.chargepoint.com/webservices/chargepoint/services/5.0"
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
