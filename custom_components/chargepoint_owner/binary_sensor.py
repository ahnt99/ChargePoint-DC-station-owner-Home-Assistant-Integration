"""Binary sensor platform for ChargePoint integration."""
from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import ChargePointCoordinator
from .entity import ChargePointPortEntity
from .const import DOMAIN, COORDINATOR, STATUS_INUSE


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: ChargePointCoordinator = hass.data[DOMAIN][entry.entry_id][COORDINATOR]

    entities = []
    for port_key, port_data in coordinator.data.get("ports", {}).items():
        station_id = port_data.get("stationID", coordinator.station_id)
        port_number = port_data.get("portNumber", "1")
        for cls in (
            ChargePointChargingBinarySensor,
            ChargePointShedActiveBinarySensor,
        ):
            entities.append(cls(coordinator, port_key, station_id, port_number))

    async_add_entities(entities)


class ChargePointChargingBinarySensor(ChargePointPortEntity, BinarySensorEntity):
    """ON when a vehicle is actively charging."""
    _attr_name = "Charging"
    _attr_device_class = BinarySensorDeviceClass.BATTERY_CHARGING
    _attr_icon = "mdi:ev-plug-type2"

    def __init__(self, coordinator, port_key, station_id, port_number):
        super().__init__(coordinator, port_key, station_id, port_number)
        self._attr_unique_id = f"{station_id}_{port_number}_charging"

    @property
    def is_on(self) -> bool:
        return self.port_data.get("status", "").upper() == STATUS_INUSE


class ChargePointShedActiveBinarySensor(ChargePointPortEntity, BinarySensorEntity):
    """ON when load shedding is active on this port (shedState == 1)."""
    _attr_name = "Load Shed Active"
    _attr_icon = "mdi:transmission-tower-off"

    def __init__(self, coordinator, port_key, station_id, port_number):
        super().__init__(coordinator, port_key, station_id, port_number)
        self._attr_unique_id = f"{station_id}_{port_number}_shed_active"

    @property
    def is_on(self) -> bool:
        # shedState is 0 or 1 integer per confirmed API response
        return int(self.port_data.get("shedState", 0)) == 1
