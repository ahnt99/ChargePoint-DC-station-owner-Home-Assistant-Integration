"""Sensor platform for ChargePoint integration."""
from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfPower
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import ChargePointCoordinator
from .entity import ChargePointPortEntity
from .const import DOMAIN, COORDINATOR

_MONTH_NAMES = [
    "", "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December"
]


def _label_to_month_name(label: str) -> str:
    """Convert '2026-01' to 'January 2026'."""
    try:
        year, month = label.split("-")
        return f"{_MONTH_NAMES[int(month)]} {year}"
    except Exception:
        return label





@dataclass(frozen=True)
class ChargePointSensorDescription(SensorEntityDescription):
    """Describes a ChargePoint sensor."""
    port_data_key: str = ""
    extra_attrs: list[str] = field(default_factory=list)


# All fields confirmed from live API debug logs:
#
# getStationStatus port: portNumber, Status, TimeStamp, Connector, Power
# getLoad port:          portNumber, userID, credentialID, shedState,
#                        portLoad (kW), allowedLoad (kW), percentShed
# getLoad station:       stationID, stationName, Address, stationLoad

SENSOR_DESCRIPTIONS: tuple[ChargePointSensorDescription, ...] = (
    # --- Core status ---
    ChargePointSensorDescription(
        key="status",
        name="Status",
        icon="mdi:ev-station",
        port_data_key="status",
        extra_attrs=["stationID", "portNumber", "timestamp", "connector"],
    ),

    # --- Power / load ---
    ChargePointSensorDescription(
        key="port_load",
        name="Port Load",
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:lightning-bolt",
        port_data_key="portLoad",
    ),
    ChargePointSensorDescription(
        key="allowed_load",
        name="Allowed Load",
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:speedometer",
        port_data_key="allowedLoad",
    ),

    # --- Load shedding ---
    ChargePointSensorDescription(
        key="percent_shed",
        name="Percent Shed",
        native_unit_of_measurement="%",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:percent",
        port_data_key="percentShed",
    ),

    # --- Connector type (populated when in use) ---
    ChargePointSensorDescription(
        key="connector",
        name="Connector",
        icon="mdi:ev-plug-type2",
        port_data_key="connector",
        entity_registry_enabled_default=False,
    ),

    # --- Private / disabled by default ---
    ChargePointSensorDescription(
        key="user_id",
        name="User ID",
        icon="mdi:account",
        port_data_key="userID",
        entity_registry_enabled_default=False,
    ),
    ChargePointSensorDescription(
        key="credential_id",
        name="Credential ID",
        icon="mdi:card-account-details",
        port_data_key="credentialID",
        entity_registry_enabled_default=False,
    ),
)


@dataclass(frozen=True)
class ChargePointStationSensorDescription(SensorEntityDescription):
    """Describes a station-level (not per-port) sensor."""
    station_data_key: str = ""


STATION_SENSOR_DESCRIPTIONS: tuple[ChargePointStationSensorDescription, ...] = (
    ChargePointStationSensorDescription(
        key="station_load",
        name="Total Station Load",
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:transmission-tower",
        station_data_key="stationLoad",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up ChargePoint sensors."""
    coordinator: ChargePointCoordinator = hass.data[DOMAIN][entry.entry_id][COORDINATOR]

    entities: list[SensorEntity] = []

    # Per-port sensors
    for port_key, port_data in coordinator.data.get("ports", {}).items():
        station_id = port_data.get("stationID", coordinator.station_id)
        port_number = port_data.get("portNumber", "1")
        for description in SENSOR_DESCRIPTIONS:
            entities.append(
                ChargePointPortSensor(
                    coordinator=coordinator,
                    description=description,
                    port_key=port_key,
                    station_id=station_id,
                    port_number=port_number,
                )
            )

    # Station-level sensors (one per station, attached to port 1's device)
    first_port_key = next(iter(coordinator.data.get("ports", {})), None)
    if first_port_key:
        first_port = coordinator.data["ports"][first_port_key]
        station_id = first_port.get("stationID", coordinator.station_id)
        port_number = first_port.get("portNumber", "1")
        for description in STATION_SENSOR_DESCRIPTIONS:
            entities.append(
                ChargePointStationSensor(
                    coordinator=coordinator,
                    description=description,
                    port_key=first_port_key,
                    station_id=station_id,
                    port_number=port_number,
                )
            )
        for description in SESSION_SENSOR_DESCRIPTIONS:
            entities.append(
                ChargePointSessionSensor(
                    coordinator=coordinator,
                    description=description,
                    port_key=first_port_key,
                    station_id=station_id,
                    port_number=port_number,
                )
            )

    async_add_entities(entities)


class ChargePointPortSensor(ChargePointPortEntity, SensorEntity):
    """A sensor for a single ChargePoint port data field."""

    entity_description: ChargePointSensorDescription

    def __init__(self, coordinator, description, port_key, station_id, port_number):
        super().__init__(coordinator, port_key, station_id, port_number)
        self.entity_description = description
        self._attr_unique_id = f"{station_id}_{port_number}_{description.key}"

    @property
    def native_value(self) -> Any:
        val = self.port_data.get(self.entity_description.port_data_key)
        # Convert Decimal to float for HA
        if val is not None:
            try:
                return float(val)
            except (TypeError, ValueError):
                return val
        return val

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        attrs = {}
        for key in self.entity_description.extra_attrs:
            val = self.port_data.get(key)
            if val is not None:
                attrs[key] = str(val)
        return attrs


class ChargePointStationSensor(ChargePointPortEntity, SensorEntity):
    """A station-level sensor (e.g. total load across all ports)."""

    entity_description: ChargePointStationSensorDescription

    def __init__(self, coordinator, description, port_key, station_id, port_number):
        super().__init__(coordinator, port_key, station_id, port_number)
        self.entity_description = description
        self._attr_unique_id = f"{station_id}_{description.key}"

    @property
    def native_value(self) -> Any:
        val = self.coordinator.data.get(self.entity_description.station_data_key)
        if val is not None:
            try:
                return float(val)
            except (TypeError, ValueError):
                return val
        return val


# ---------------------------------------------------------------------------
# Session history sensors — attached to the station device (port 1)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ChargePointSessionSensorDescription(SensorEntityDescription):
    """Describes a session-history sensor."""
    data_key: str = ""


SESSION_SENSOR_DESCRIPTIONS: tuple[ChargePointSessionSensorDescription, ...] = (
    ChargePointSessionSensorDescription(
        key="session_count_7days",
        name="Last 7 Days Sessions",
        icon="mdi:counter",
        state_class=SensorStateClass.MEASUREMENT,
        data_key="session_count_7days",
    ),
    ChargePointSessionSensorDescription(
        key="monthly_energy",
        name="Monthly Energy Dispensed",
        native_unit_of_measurement="kWh",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:calendar-month",
        data_key="monthly_energy",
    ),
    ChargePointSessionSensorDescription(
        key="monthly_energy_0",
        name="Energy This Month",
        native_unit_of_measurement="kWh",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:calendar-today",
        data_key="monthly_0_kwh",
    ),
    ChargePointSessionSensorDescription(
        key="monthly_energy_1",
        name="Energy Last Month",
        native_unit_of_measurement="kWh",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:calendar-arrow-left",
        data_key="monthly_1_kwh",
    ),
    ChargePointSessionSensorDescription(
        key="monthly_energy_2",
        name="Energy 2 Months Ago",
        native_unit_of_measurement="kWh",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:calendar-arrow-left",
        data_key="monthly_2_kwh",
    ),
    ChargePointSessionSensorDescription(
        key="session_last_energy",
        name="Last Session Energy",
        native_unit_of_measurement="kWh",
        # No device_class=ENERGY — "last session" is not a running total
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:ev-plug-type2",
        data_key="session_last_energy_kwh",
    ),
    ChargePointSessionSensorDescription(
        key="session_last_end",
        name="Last Session End",
        device_class=SensorDeviceClass.TIMESTAMP,
        icon="mdi:clock-check-outline",
        data_key="session_last_end",
    ),
    ChargePointSessionSensorDescription(
        key="session_last_duration",
        name="Last Session Duration",
        native_unit_of_measurement="min",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:timer-outline",
        data_key="session_last_duration_min",
    ),
    ChargePointSessionSensorDescription(
        key="session_avg_energy",
        name="Average Session Energy",
        native_unit_of_measurement="kWh",
        # No device_class=ENERGY — average is not a running total
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:chart-bell-curve",
        data_key="session_avg_energy_kwh",
    ),
    ChargePointSessionSensorDescription(
        key="latest_alarm",
        name="Latest Alarm",
        icon="mdi:bell-alert",
        data_key="latest_alarm",
    ),
)


class ChargePointSessionSensor(ChargePointPortEntity, SensorEntity):
    """A station-level sensor sourced from session/alarm data in coordinator."""

    entity_description: ChargePointSessionSensorDescription

    def __init__(self, coordinator, description, port_key, station_id, port_number):
        super().__init__(coordinator, port_key, station_id, port_number)
        self.entity_description = description
        self._attr_unique_id = f"{station_id}_{description.key}"

    @property
    def native_value(self) -> Any:
        val = self.coordinator.data.get(self.entity_description.data_key)
        # Timestamp sensors — return datetime as-is
        if self.entity_description.device_class == SensorDeviceClass.TIMESTAMP:
            if val is None:
                return None
            try:
                return val if val.tzinfo else val.replace(tzinfo=timezone.utc)
            except Exception:
                return None
        # Monthly energy — state is current month kWh
        if self.entity_description.key == "monthly_energy":
            if isinstance(val, dict):
                return val.get("current_month_kwh")
            return None
        # Text sensors
        if self.entity_description.data_key in ("latest_alarm",):
            return val
        # Numeric sensors
        if val is not None:
            try:
                return float(val)
            except (TypeError, ValueError):
                return val
        return val

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        key = self.entity_description.key

        if key == "monthly_energy":
            val = self.coordinator.data.get("monthly_energy", {})
            if not isinstance(val, dict):
                return {}
            return {
                val.get("current_month", "current"): val.get("current_month_kwh", 0),
                val.get("month_1_label", ""): val.get("month_1_kwh", 0),
                val.get("month_2_label", ""): val.get("month_2_kwh", 0),
            }

        if key == "monthly_energy_0":
            label = self.coordinator.data.get("monthly_0_label", "")
            return {"period": label, "month_name": _label_to_month_name(label)}
        if key == "monthly_energy_1":
            label = self.coordinator.data.get("monthly_1_label", "")
            return {"period": label, "month_name": _label_to_month_name(label)}
        if key == "monthly_energy_2":
            label = self.coordinator.data.get("monthly_2_label", "")
            return {"period": label, "month_name": _label_to_month_name(label)}

        if key == "session_count_7days":
            sessions = self.coordinator.data.get("sessions_7days", [])
            total_7day_kwh = round(sum(s.get("Energy", 0) for s in sessions if (s.get("Energy") or 0) > 0), 2)

            # Convert a UTC datetime to HA's local timezone for display
            ha_tz = self.hass.config.time_zone
            try:
                import zoneinfo
                local_tz = zoneinfo.ZoneInfo(ha_tz)
            except Exception:
                local_tz = None

            def _to_local(dt):
                if dt is None:
                    return None
                try:
                    aware = dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
                    return aware.astimezone(local_tz) if local_tz else aware
                except Exception:
                    return None

            def _to_local_str(dt) -> str:
                local = _to_local(dt)
                return local.strftime("%Y-%m-%d %H:%M:%S") if local else str(dt)

            # Build full 7-day date range (oldest → newest) so days with 0 kWh appear
            today_local = datetime.now(local_tz if local_tz else timezone.utc).date()
            all_days = [(today_local - timedelta(days=6-i)) for i in range(7)]

            # Sum energy and count sessions per local calendar day
            daily_kwh: dict[date, float] = defaultdict(float)
            daily_count: dict[date, int] = defaultdict(int)
            for s in sessions:
                local_end = _to_local(s.get("endTime"))
                if local_end and (s.get("Energy") or 0) > 0:
                    daily_kwh[local_end.date()] += s.get("Energy", 0)
                    daily_count[local_end.date()] += 1

            daily_x = [d.strftime("%m/%d") for d in all_days]
            daily_y = [round(daily_kwh.get(d, 0), 2) for d in all_days]
            daily_sessions = [daily_count.get(d, 0) for d in all_days]

            attrs: dict[str, Any] = {
                "window": "last 7 days",
                "total_energy_kwh": total_7day_kwh,
                "chart_daily_x": daily_x,
                "chart_daily_y": daily_y,
                "chart_daily_sessions": daily_sessions,
            }
            for i, s in enumerate(sessions):
                attrs[f"session_{i+1}"] = {
                    "start": _to_local_str(s.get("startTime")),
                    "end": _to_local_str(s.get("endTime")),
                    "energy_kwh": round(s.get("Energy", 0), 2),
                    "session_id": s.get("sessionID"),
                    "port": s.get("portNumber"),
                }
            return attrs

        if key == "latest_alarm":
            alarms = self.coordinator.data.get("alarms", [])
            return {
                f"alarm_{i+1}": {
                    "type": a.get("alarmType", ""),
                    "time": str(a.get("alarmTime", "")),
                }
                for i, a in enumerate(alarms[:5])
            }

        if key == "session_last_energy":
            return {
                "start": str(self.coordinator.data.get("session_last_start", "")),
                "end": str(self.coordinator.data.get("session_last_end", "")),
            }

        if key == "session_last_end":
            return {
                "start": str(self.coordinator.data.get("session_last_start", "")),
                "duration_min": self.coordinator.data.get("session_last_duration_min"),
                "energy_kwh": self.coordinator.data.get("session_last_energy_kwh"),
            }

        return {}
