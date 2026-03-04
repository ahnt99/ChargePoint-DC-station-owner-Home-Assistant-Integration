"""The ChargePoint Station Owner integration."""
from __future__ import annotations

import logging

from zeep.helpers import serialize_object

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall

from .api import ChargePointClient, ChargePointAPIError
from .coordinator import ChargePointCoordinator
from .const import (
    DOMAIN,
    CONF_API_KEY,
    CONF_API_PASSWORD,
    CONF_STATION_ID,
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    COORDINATOR,
)

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.BINARY_SENSOR, Platform.SWITCH]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up ChargePoint from a config entry."""
    client = ChargePointClient(
        api_key=entry.data[CONF_API_KEY],
        api_password=entry.data[CONF_API_PASSWORD],
    )
    coordinator = ChargePointCoordinator(
        hass=hass,
        client=client,
        station_id=entry.data[CONF_STATION_ID],
        scan_interval=entry.options.get(
            CONF_SCAN_INTERVAL,
            entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
        ),
    )

    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        COORDINATOR: coordinator,
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    # Register probe service (only once)
    if not hass.services.has_service(DOMAIN, "probe_api"):
        async def handle_probe(call: ServiceCall) -> None:
            """Call every API method and log the full raw response."""
            target_entry_id = call.data.get("entry_id")
            entries = (
                [hass.config_entries.async_get_entry(target_entry_id)]
                if target_entry_id
                else hass.config_entries.async_entries(DOMAIN)
            )
            for e in entries:
                if e is None:
                    continue
                c = ChargePointClient(
                    api_key=e.data[CONF_API_KEY],
                    api_password=e.data[CONF_API_PASSWORD],
                )
                sid = e.data[CONF_STATION_ID]

                _LOGGER.info("=== ChargePoint API Probe for station %s ===", sid)

                # List all WSDL operations
                try:
                    methods = await hass.async_add_executor_job(
                        c.list_available_methods
                    )
                    _LOGGER.info("Available WSDL methods: %s", methods)
                except Exception as exc:  # noqa: BLE001
                    _LOGGER.warning("Could not list methods: %s", exc)

                # Probe each method
                probes = [
                    ("getStations",            c._get_raw_stations,      sid),
                    ("getStationStatus",        c._get_raw_station_status, sid),
                    ("getLoad",                c._get_raw_load,          sid),
                    ("getChargingSessionData", c._get_raw_session_data,  sid),
                    ("getAlarms",              c._get_raw_alarms,        sid),
                    ("getOrgsAndStationGroups",c._get_raw_orgs),
                ]
                for label, fn, *args in probes:
                    try:
                        raw = await hass.async_add_executor_job(fn, *args)
                        _LOGGER.info("%s response:\n%s", label, serialize_object(raw))
                    except ChargePointAPIError as exc:
                        _LOGGER.warning("%s failed: %s", label, exc)
                    except Exception as exc:  # noqa: BLE001
                        _LOGGER.warning("%s unexpected error: %s", label, exc)

                _LOGGER.info("=== Probe complete for station %s ===", sid)

        hass.services.async_register(DOMAIN, "probe_api", handle_probe)

    return True


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok
