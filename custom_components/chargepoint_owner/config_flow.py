"""Config flow for ChargePoint integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
from homeassistant.exceptions import HomeAssistantError

from .api import ChargePointClient, ChargePointAuthError, ChargePointAPIError
from .const import (
    DOMAIN,
    CONF_API_KEY,
    CONF_API_PASSWORD,
    CONF_STATION_ID,
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)

STEP_CREDENTIALS_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_API_KEY): str,
        vol.Required(CONF_API_PASSWORD): str,
    }
)


class ChargePointConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for ChargePoint."""

    VERSION = 1

    def __init__(self) -> None:
        self._api_key: str = ""
        self._api_password: str = ""
        self._stations: list[dict] = []

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Step 1: Ask for API credentials only."""
        errors: dict[str, str] = {}

        if user_input is not None:
            self._api_key = user_input[CONF_API_KEY].strip()
            self._api_password = user_input[CONF_API_PASSWORD].strip()

            client = ChargePointClient(
                api_key=self._api_key,
                api_password=self._api_password,
            )

            try:
                stations = await self.hass.async_add_executor_job(
                    client.get_stations, None
                )
            except ChargePointAuthError:
                errors["base"] = "invalid_auth"
            except ChargePointAPIError:
                errors["base"] = "cannot_connect"
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Unexpected error fetching stations")
                errors["base"] = "unknown"
            else:
                if not stations:
                    errors["base"] = "no_stations"
                else:
                    self._stations = stations
                    return await self.async_step_pick_station()

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_CREDENTIALS_SCHEMA,
            errors=errors,
            description_placeholders={
                "api_docs_url": "https://na.chargepoint.com/UI/s3docs/docs/help/SetupWebServicesAPI.pdf"
            },
        )

    async def async_step_pick_station(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Step 2: Let the user pick which station to add."""
        errors: dict[str, str] = {}

        if user_input is not None:
            station_id = user_input[CONF_STATION_ID]
            scan_interval = user_input.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)

            await self.async_set_unique_id(station_id)
            self._abort_if_unique_id_configured()

            # Find a friendly title for this station
            title = station_id
            for st in self._stations:
                if st.get("stationID") == station_id:
                    ports = st.get("ports", [])
                    if ports and ports[0].get("stationName"):
                        title = ports[0]["stationName"]
                    elif st.get("Address"):
                        title = f"ChargePoint {st['Address']}"
                    break

            return self.async_create_entry(
                title=title,
                data={
                    CONF_API_KEY: self._api_key,
                    CONF_API_PASSWORD: self._api_password,
                    CONF_STATION_ID: station_id,
                    CONF_SCAN_INTERVAL: scan_interval,
                },
            )

        # Build a dropdown from the discovered stations
        station_options: dict[str, str] = {}
        for st in self._stations:
            sid = st.get("stationID", "")
            if not sid:
                continue
            ports = st.get("ports", [])
            label_parts = [sid]
            if ports and ports[0].get("stationName"):
                label_parts.append(ports[0]["stationName"])
            if st.get("Address"):
                label_parts.append(st["Address"])
            station_options[sid] = " — ".join(label_parts)

        if not station_options:
            return self.async_abort(reason="no_stations")

        return self.async_show_form(
            step_id="pick_station",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_STATION_ID): vol.In(station_options),
                    vol.Optional(
                        CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL
                    ): vol.All(int, vol.Range(min=30, max=3600)),
                }
            ),
            errors=errors,
        )

    @staticmethod
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> ChargePointOptionsFlow:
        return ChargePointOptionsFlow(config_entry)


class ChargePointOptionsFlow(config_entries.OptionsFlow):
    """Handle options (reconfigure scan interval)."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self.config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_SCAN_INTERVAL,
                        default=self.config_entry.options.get(
                            CONF_SCAN_INTERVAL,
                            self.config_entry.data.get(
                                CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
                            ),
                        ),
                    ): vol.All(int, vol.Range(min=30, max=3600)),
                }
            ),
        )


class CannotConnect(HomeAssistantError):
    """Error to indicate we cannot connect."""


class InvalidAuth(HomeAssistantError):
    """Error to indicate there is invalid auth."""
