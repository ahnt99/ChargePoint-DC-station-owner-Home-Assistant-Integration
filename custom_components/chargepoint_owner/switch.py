"""Switch platform for ChargePoint integration — load shed control."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import ChargePointCoordinator
from .entity import ChargePointPortEntity
from .api import ChargePointClient, ChargePointAPIError
from .const import DOMAIN, COORDINATOR

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up ChargePoint switches."""
    coordinator: ChargePointCoordinator = hass.data[DOMAIN][entry.entry_id][COORDINATOR]

    entities = []
    for port_key, port_data in coordinator.data.get("ports", {}).items():
        station_id = port_data.get("stationID", coordinator.station_id)
        port_number = port_data.get("portNumber", "1")
        entities.append(
            ChargePointShedSwitch(
                coordinator=coordinator,
                port_key=port_key,
                station_id=station_id,
                port_number=port_number,
            )
        )

    async_add_entities(entities)


class ChargePointShedSwitch(ChargePointPortEntity, SwitchEntity):
    """Switch: ON = shed load (stop charging), OFF = restore normal charging."""

    _attr_name = "Load Shed"
    _attr_icon = "mdi:power-settings"

    def __init__(self, coordinator, port_key, station_id, port_number):
        super().__init__(coordinator, port_key, station_id, port_number)
        self._attr_unique_id = f"{station_id}_{port_number}_shed"

    @property
    def is_on(self) -> bool:
        return bool(self.port_data.get("shedState"))

    async def async_turn_on(self, **kwargs: Any) -> None:
        client: ChargePointClient = self.coordinator.client
        try:
            await self.hass.async_add_executor_job(
                client.shed_load, self._station_id, int(self._port_number), 0
            )
        except ChargePointAPIError as err:
            _LOGGER.error("shed_load failed on %s port %s: %s", self._station_id, self._port_number, err)
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        client: ChargePointClient = self.coordinator.client
        try:
            await self.hass.async_add_executor_job(
                client.clear_shed_state, self._station_id, int(self._port_number)
            )
        except ChargePointAPIError as err:
            _LOGGER.error("clear_shed_state failed on %s port %s: %s", self._station_id, self._port_number, err)
        await self.coordinator.async_request_refresh()
