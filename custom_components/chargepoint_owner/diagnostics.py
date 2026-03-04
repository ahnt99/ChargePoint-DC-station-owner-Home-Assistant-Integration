"""Diagnostics support for ChargePoint — dumps all available API data."""
from __future__ import annotations

import logging
from typing import Any

from zeep.helpers import serialize_object

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .api import ChargePointClient, ChargePointAPIError
from .const import DOMAIN, COORDINATOR, CONF_API_KEY, CONF_API_PASSWORD

_LOGGER = logging.getLogger(__name__)

# Fields to redact from diagnostic output
TO_REDACT = {CONF_API_KEY, CONF_API_PASSWORD, "userID", "credentialID",
             "rfidSerialNumber", "driverName", "api_key", "api_password"}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry — calls every API method and dumps results."""
    client: ChargePointClient = ChargePointClient(
        api_key=entry.data[CONF_API_KEY],
        api_password=entry.data[CONF_API_PASSWORD],
    )
    station_id: str = entry.data["station_id"]

    results: dict[str, Any] = {
        "station_id": station_id,
        "coordinator_data": async_redact_data(
            hass.data[DOMAIN][entry.entry_id][COORDINATOR].data, TO_REDACT
        ),
    }

    # Helper to run a blocking call and serialize the raw zeep response
    async def probe(label: str, fn, *args):
        try:
            raw = await hass.async_add_executor_job(fn, *args)
            if hasattr(raw, "__dict__") or hasattr(raw, "_raw_elements"):
                results[label] = serialize_object(raw)
            else:
                results[label] = raw
        except ChargePointAPIError as exc:
            results[label] = {"error": str(exc)}
        except Exception as exc:  # noqa: BLE001
            results[label] = {"error": str(exc)}

    # Raw zeep responses for every relevant API method
    await probe("raw_getStations", client._get_raw_stations, station_id)
    await probe("raw_getStationStatus", client._get_raw_station_status, station_id)
    await probe("raw_getLoad", client._get_raw_load, station_id)
    await probe("raw_getChargingSessionData", client._get_raw_session_data, station_id)
    await probe("raw_getAlarms", client._get_raw_alarms, station_id)
    await probe("raw_getOrgsAndStationGroups", client._get_raw_orgs)

    return async_redact_data(results, TO_REDACT)
