"""DataUpdateCoordinator for ChargePoint."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import ChargePointClient, ChargePointAPIError
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


class ChargePointCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Manages polling the ChargePoint API for one station."""

    def __init__(
        self,
        hass: HomeAssistant,
        client: ChargePointClient,
        station_id: str,
        scan_interval: int,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{station_id}",
            update_interval=timedelta(seconds=scan_interval),
        )
        self.client = client
        self.station_id = station_id
        self._session_cache: list[dict] = []
        self._monthly_cache: list[dict] = []
        self._alarm_cache: list[dict] = []

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch latest data from the API."""
        try:
            status_data = await self.hass.async_add_executor_job(
                self.client.get_station_status, self.station_id
            )
            load_data = await self.hass.async_add_executor_job(
                self.client.get_load, self.station_id
            )
        except ChargePointAPIError as err:
            raise UpdateFailed(f"ChargePoint API error: {err}") from err

        # Resolve HA local timezone early — needed for session fetches
        try:
            import zoneinfo
            local_tz = zoneinfo.ZoneInfo(self.hass.config.time_zone)
        except Exception:
            local_tz = timezone.utc

        # Fetch session history every poll cycle
        try:
            self._session_cache = await self.hass.async_add_executor_job(
                self.client.get_charging_session_data, self.station_id, 10
            )
            self._monthly_cache = await self.hass.async_add_executor_job(
                self.client.get_monthly_session_data, self.station_id, local_tz
            )
        except ChargePointAPIError as err:
            _LOGGER.warning("Could not fetch session data: %s", err)

        # Fetch alarms every poll cycle
        try:
            self._alarm_cache = await self.hass.async_add_executor_job(
                self.client.get_alarms, self.station_id
            )
        except ChargePointAPIError as err:
            _LOGGER.warning("Could not fetch alarm data: %s", err)

        # Index load port data by port number
        port_loads: dict[str, dict] = {}
        for pd in load_data.get("ports", []):
            pn = str(pd.get("portNumber", ""))
            if pn:
                port_loads[pn] = pd

        # Compute cutoff = midnight 7 days ago in HA's local timezone
        now_local = datetime.now(local_tz)
        cutoff_local = now_local.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=7)
        cutoff_utc = cutoff_local.astimezone(timezone.utc)

        # Compute monthly energy buckets in local timezone
        monthly_stats = _compute_monthly_stats(self._monthly_cache, local_tz)

        # Compute session stats from cache
        session_stats = _compute_session_stats(self._session_cache, cutoff_utc)

        # Build per-port dict keyed by "stationID:portNumber"
        ports: dict[str, dict] = {}
        for ps in status_data:
            pn = str(ps.get("portNumber", ""))
            sid = ps.get("stationID", self.station_id)
            key = f"{sid}:{pn}"
            load = port_loads.get(pn, {})
            ports[key] = {
                "stationID": sid,
                "portNumber": pn,
                "status": ps.get("Status", "UNKNOWN"),
                "timestamp": ps.get("TimeStamp"),
                "connector": ps.get("Connector"),
                "power_level": ps.get("Power"),
                "portLoad": load.get("portLoad"),
                "allowedLoad": load.get("allowedLoad"),
                "percentShed": load.get("percentShed"),
                "shedState": load.get("shedState"),
                "userID": load.get("userID"),
                "credentialID": load.get("credentialID"),
            }

        # Most recent non-fault alarm (for sensor display)
        latest_alarm = None
        latest_alarm_time = None
        if self._alarm_cache:
            # First entry is most recent (API returns newest first)
            latest_alarm = self._alarm_cache[0].get("alarmType", "").strip()
            latest_alarm_time = self._alarm_cache[0].get("alarmTime")

        return {
            "stationID": self.station_id,
            "stationName": load_data.get("stationName"),
            "address": load_data.get("address"),
            "stationLoad": load_data.get("stationLoad"),
            "ports": ports,
            # Session history stats
            "session_count_7days": session_stats["count_7days"],
            "sessions_7days": session_stats["sessions_7days"],
            # Monthly energy — flattened for individual sensors
            "monthly_energy": monthly_stats,
            "monthly_0_kwh": monthly_stats.get("current_month_kwh", 0),
            "monthly_0_label": monthly_stats.get("current_month", ""),
            "monthly_1_kwh": monthly_stats.get("month_1_kwh", 0),
            "monthly_1_label": monthly_stats.get("month_1_label", ""),
            "monthly_2_kwh": monthly_stats.get("month_2_kwh", 0),
            "monthly_2_label": monthly_stats.get("month_2_label", ""),
            "session_last_energy_kwh": session_stats["last_energy"],
            "session_last_start": session_stats["last_start"],
            "session_last_end": session_stats["last_end"],
            "session_last_duration_min": session_stats["last_duration_min"],
            "session_avg_energy_kwh": session_stats["avg_energy"],
            # Raw session list for attributes (sorted newest-first by endTime)
            "sessions": self._session_cache[:20],
            # Alarm data
            "latest_alarm": latest_alarm,
            "latest_alarm_time": latest_alarm_time,
            "alarms": self._alarm_cache[:10],
        }


def _compute_session_stats(sessions: list[dict], cutoff: "datetime") -> dict[str, Any]:
    """Compute aggregate stats from session list. cutoff is UTC-aware midnight 7 days ago."""
    from datetime import datetime, timezone, timedelta

    def _to_utc(dt):
        """Normalize a datetime to UTC-aware, or return None."""
        if dt is None:
            return None
        if isinstance(dt, str):
            try:
                from datetime import datetime as dt_cls
                parsed = dt_cls.fromisoformat(dt.replace("Z", "+00:00"))
                return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
            except Exception:
                _LOGGER.warning("Could not parse datetime string: %r", dt)
                return None
        try:
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except Exception:
            _LOGGER.warning("Unexpected datetime type %s: %r", type(dt), dt)
            return None

    # Sort ALL sessions newest-first by endTime
    def _sort_key(s):
        t = _to_utc(s.get("endTime"))
        return t if t is not None else datetime.min.replace(tzinfo=timezone.utc)

    sessions_sorted = sorted(sessions, key=_sort_key, reverse=True)

    # Filter sessions with actual energy delivery (still newest-first)
    real = [s for s in sessions_sorted if (s.get("Energy") or 0) > 0]

    # Compute last-7-days window using the caller-supplied cutoff (local midnight, 7 days ago)
    sessions_7days = [
        s for s in sessions_sorted
        if _to_utc(s.get("endTime")) is not None and _to_utc(s.get("endTime")) >= cutoff
    ]

    if not real:
        return {
            "count_7days": len(sessions_7days),
            "sessions_7days": sessions_7days,
            "total_energy": None,
            "last_energy": None,
            "last_start": None,
            "last_end": None,
            "last_duration_min": None,
            "avg_energy": None,
        }

    total = sum(s.get("Energy", 0) for s in real)
    last = real[0]  # guaranteed most recent after sort
    last_start_utc = _to_utc(last.get("startTime"))
    last_end_utc = _to_utc(last.get("endTime"))
    duration = None
    if last_start_utc and last_end_utc:
        try:
            diff = last_end_utc - last_start_utc
            duration = round(diff.total_seconds() / 60, 1)
        except Exception:
            pass

    return {
        "count_7days": len(sessions_7days),
        "sessions_7days": sessions_7days,
        "total_energy": round(total, 2),
        "last_energy": round(last.get("Energy", 0), 2),
        "last_start": last_start_utc,
        "last_end": last_end_utc,
        "last_duration_min": duration,
        "avg_energy": round(total / len(real), 2) if real else None,
    }


def _compute_monthly_stats(sessions: list[dict], local_tz) -> dict[str, Any]:
    """Compute energy totals for current month and previous 2 months in local timezone."""
    from datetime import datetime, timezone, date
    from collections import defaultdict

    def _to_local(dt):
        if dt is None:
            return None
        try:
            aware = dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
            return aware.astimezone(local_tz) if local_tz else aware
        except Exception:
            return None

    # Build the 3 month windows: current month, then -1, -2
    today = datetime.now(local_tz if local_tz else timezone.utc)
    months = []
    for offset in range(3):
        # Go back 'offset' months from current
        month = today.month - offset
        year = today.year
        while month <= 0:
            month += 12
            year -= 1
        months.append((year, month))

    # Sum energy per (year, month)
    daily_sums: dict[tuple, float] = defaultdict(float)
    for s in sessions:
        local_end = _to_local(s.get("endTime"))
        energy = s.get("Energy") or 0
        if local_end and energy > 0:
            key = (local_end.year, local_end.month)
            daily_sums[key] += energy

    result = {}
    for i, (year, month) in enumerate(months):
        key = (year, month)
        label = f"{year}-{month:02d}"
        energy = round(daily_sums.get(key, 0), 2)
        if i == 0:
            result["current_month"] = label
            result["current_month_kwh"] = energy
        else:
            result[f"month_{i}_label"] = label
            result[f"month_{i}_kwh"] = energy

    return result
