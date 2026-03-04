"""Base entity for ChargePoint integration."""
from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .coordinator import ChargePointCoordinator
from .const import DOMAIN


class ChargePointPortEntity(CoordinatorEntity[ChargePointCoordinator]):
    """Base class for a ChargePoint port entity."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: ChargePointCoordinator,
        port_key: str,
        station_id: str,
        port_number: str,
    ) -> None:
        super().__init__(coordinator)
        self._port_key = port_key
        self._station_id = station_id
        self._port_number = port_number

    @property
    def port_data(self) -> dict:
        return self.coordinator.data.get("ports", {}).get(self._port_key, {})

    @property
    def device_info(self) -> DeviceInfo:
        """Group all entities under one device per station port, with real name/address."""
        data = self.coordinator.data
        station_name = data.get("stationName") or f"ChargePoint {self._station_id}"
        address = data.get("address")
        return DeviceInfo(
            identifiers={(DOMAIN, f"{self._station_id}:{self._port_number}")},
            name=f"{station_name} Port {self._port_number}",
            manufacturer="ChargePoint",
            model="EV Charging Station",
            serial_number=self._station_id,
            configuration_url="https://account.chargepoint.com",
            suggested_area=address,
        )

    @property
    def available(self) -> bool:
        return super().available and self._port_key in self.coordinator.data.get("ports", {})
