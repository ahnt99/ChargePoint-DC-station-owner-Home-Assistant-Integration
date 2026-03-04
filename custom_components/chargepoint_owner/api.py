"""ChargePoint SOAP API client."""
from __future__ import annotations

import logging
from typing import Any

from lxml import etree
from zeep import Client, Transport
from zeep.helpers import serialize_object
from zeep.wsse import utils as wsse_utils
from zeep.exceptions import Fault

from .const import CHARGEPOINT_WSDL, CHARGEPOINT_ENDPOINT, WSSE_NS, PASSWORD_TYPE

_LOGGER = logging.getLogger(__name__)


class ChargePointAPIError(Exception):
    """Raised when an API call fails."""


class ChargePointAuthError(ChargePointAPIError):
    """Raised when authentication fails."""


class ChargePointWSSE:
    """Custom WS-Security plugin — builds PasswordText UsernameToken with lxml."""

    def __init__(self, username: str, password: str) -> None:
        self._username = username
        self._password = password

    def apply(self, envelope: etree._Element, headers: dict) -> tuple:
        security = wsse_utils.get_security_header(envelope)
        token = etree.SubElement(security, etree.QName(WSSE_NS, "UsernameToken"))
        username_el = etree.SubElement(token, etree.QName(WSSE_NS, "Username"))
        username_el.text = self._username
        password_el = etree.SubElement(token, etree.QName(WSSE_NS, "Password"))
        password_el.set("Type", PASSWORD_TYPE)
        password_el.text = self._password
        return envelope, headers

    def verify(self, envelope: etree._Element) -> etree._Element:
        return envelope


class ChargePointClient:
    """Client for the ChargePoint SOAP Web Services API."""

    def __init__(self, api_key: str, api_password: str) -> None:
        self._api_key = api_key
        self._api_password = api_password
        self._client: Client | None = None

    def _get_client(self) -> Client:
        if self._client is None:
            wsse = ChargePointWSSE(username=self._api_key, password=self._api_password)
            transport = Transport(operation_timeout=30, timeout=30)
            self._client = Client(
                wsdl=CHARGEPOINT_WSDL,
                wsse=wsse,
                transport=transport,
            )
            self._client.service._binding_options["address"] = CHARGEPOINT_ENDPOINT
        return self._client

    def _make_type(self, type_name: str, **fields: Any) -> Any:
        """Build a typed WSDL object by name."""
        client = self._get_client()
        t = client.get_type(f"ns0:{type_name}")
        return t(**fields)

    def _call(self, method: str, **kwargs: Any) -> Any:
        """Make a SOAP call, log the full serialized response for debugging, handle errors."""
        client = self._get_client()
        try:
            response = getattr(client.service, method)(**kwargs)
        except Fault as exc:
            _LOGGER.error("SOAP Fault calling %s: %s", method, exc)
            if "authentication" in str(exc).lower() or "security" in str(exc).lower():
                raise ChargePointAuthError(str(exc)) from exc
            raise ChargePointAPIError(str(exc)) from exc
        except Exception as exc:  # noqa: BLE001
            _LOGGER.error("Error calling %s: %s", method, exc)
            raise ChargePointAPIError(str(exc)) from exc

        # Log full response so we can see exactly what the API returns
        try:
            _LOGGER.debug("%s raw response: %s", method, serialize_object(response))
        except Exception:  # noqa: BLE001
            _LOGGER.debug("%s raw response (serialize failed): %s", method, response)

        rc = getattr(response, "responseCode", None)
        if rc is not None and str(rc).strip() not in ("100", "101", "102", "136"):
            rt = getattr(response, "responseText", "unknown error")
            # 136 = no data found — not an error, just an empty result
            if str(rc).strip() == "136":
                _LOGGER.debug("ChargePoint API: no data found (136) for %s", method)
                return response
            _LOGGER.error("ChargePoint API error %s: %s", rc, rt)
            if str(rc) in ("182", "183"):
                raise ChargePointAuthError(f"{rc}: {rt}")
            raise ChargePointAPIError(f"{rc}: {rt}")

        return response

    # -----------------------------------------------------------------------
    # Station management
    # -----------------------------------------------------------------------

    def get_stations(self, station_id: str | None = None) -> list[dict]:
        """Call getStations — uses stationSearchRequestExtended."""
        if station_id:
            q = self._make_type("stationSearchRequestExtended", stationID=station_id)
        else:
            q = self._make_type("stationSearchRequestExtended")

        response = self._call("getStations", searchQuery=q)
        stations = []
        station_data = getattr(response, "stationData", None)
        if station_data is None:
            _LOGGER.debug("getStations: no stationData in response")
            return stations
        if not isinstance(station_data, list):
            station_data = [station_data]

        for sd in station_data:
            # Log all top-level fields to discover actual attribute names
            _LOGGER.debug("getStations stationData fields: %s", serialize_object(sd))
            station: dict[str, Any] = {
                "stationID": getattr(sd, "stationID", None),
                "stationManufacturer": getattr(sd, "stationManufacturer", None),
                "stationModel": getattr(sd, "stationModel", None),
                "Address": getattr(sd, "Address", None),
                "City": getattr(sd, "City", None),
                "State": getattr(sd, "State", None),
                "numPorts": getattr(sd, "numPorts", None),
                "ports": [],
            }
            ports = getattr(sd, "Port", None)
            if ports is not None:
                if not isinstance(ports, list):
                    ports = [ports]
                for p in ports:
                    station["ports"].append({
                        "portNumber": getattr(p, "portNumber", None),
                        "stationName": getattr(p, "stationName", None),
                        "Level": getattr(p, "Level", None),
                        "Connector": getattr(p, "Connector", None),
                        "Power": getattr(p, "Power", None),
                    })
            stations.append(station)

        return stations

    def get_station_status(self, station_id: str | None = None) -> list[dict]:
        """
        Call getStationStatus — uses statusSearchdata.

        The WSDL type list includes 'portDataStatus' and 'oStatusdata' which
        suggests the response nests ports differently than getStations.
        Debug logging will reveal the actual structure.
        """
        if station_id:
            q = self._make_type("statusSearchdata", stationID=station_id)
        else:
            q = self._make_type("statusSearchdata")

        response = self._call("getStationStatus", searchQuery=q)
        result = []

        # Log top-level response attributes to find the correct field name
        _LOGGER.debug(
            "getStationStatus response fields: %s",
            {k: type(v).__name__ for k, v in serialize_object(response).items()
             if v is not None} if hasattr(response, "__iter__") else serialize_object(response)
        )

        # Try both 'stationData' and 'stationStatusData' — actual name revealed by debug log
        station_data = getattr(response, "stationData", None)
        if station_data is None:
            _LOGGER.warning(
                "getStationStatus: 'stationData' not found. Full response: %s",
                serialize_object(response),
            )
            return result

        if not isinstance(station_data, list):
            station_data = [station_data]

        for sd in station_data:
            _LOGGER.debug("getStationStatus stationData entry: %s", serialize_object(sd))
            sid = getattr(sd, "stationID", None)

            # Try both 'Port' and 'portData' — actual name revealed by debug log
            ports = getattr(sd, "Port", None)
            if ports is None:
                ports = getattr(sd, "portData", None)
            if ports is None:
                _LOGGER.warning(
                    "getStationStatus: no Port/portData found in stationData entry: %s",
                    serialize_object(sd),
                )
                continue

            if not isinstance(ports, list):
                ports = [ports]
            for p in ports:
                _LOGGER.debug("getStationStatus port entry: %s", serialize_object(p))
                result.append({
                    "stationID": sid,
                    "portNumber": str(getattr(p, "portNumber", "")),
                    "Status": str(getattr(p, "Status", "UNKNOWN")),
                    "TimeStamp": getattr(p, "TimeStamp", None),
                })

        return result

    def get_load(self, station_id: str) -> dict:
        """
        Call getLoad — uses stationloaddata.

        Response structure is logged so we can confirm field names.
        """
        q = self._make_type("stationloaddata", stationID=station_id)
        response = self._call("getLoad", searchQuery=q)

        station_data = getattr(response, "stationData", None)
        if station_data is None:
            _LOGGER.debug("getLoad: no stationData in response")
            return {}
        if isinstance(station_data, list):
            if not station_data:
                _LOGGER.debug("getLoad: stationData is empty list")
                return {}
            station_data = station_data[0]

        _LOGGER.debug("getLoad stationData: %s", serialize_object(station_data))

        result: dict[str, Any] = {
            "stationID": getattr(station_data, "stationID", None),
            "stationName": getattr(station_data, "stationName", None),
            "stationLoad": getattr(station_data, "stationLoad", None),
            "ports": [],
        }

        # Try 'Port' first, fall back to 'portData' (revealed by debug log)
        ports = getattr(station_data, "Port", None)
        if ports is None:
            ports = getattr(station_data, "portData", None)

        if ports is not None:
            if not isinstance(ports, list):
                ports = [ports]
            for p in ports:
                _LOGGER.debug("getLoad port entry: %s", serialize_object(p))
                result["ports"].append({
                    "portNumber": str(getattr(p, "portNumber", "")),
                    "userID": getattr(p, "userID", None),
                    "credentialID": getattr(p, "credentialID", None),
                    "shedState": getattr(p, "shedState", None),
                    "portLoad": getattr(p, "portLoad", None),
                    "allowedLoad": getattr(p, "allowedLoad", None),
                    "percentShed": getattr(p, "percentShed", None),
                })

        return result

    def get_charging_session_data(
        self,
        station_id: str,
        days_back: int = 30,
    ) -> list[dict]:
        """Call getChargingSessionData — fetches sessions from the last `days_back` days."""
        from datetime import datetime, timezone, timedelta

        # Always request a recent window so we get current data, not oldest historical batch
        start_dt = datetime.now(timezone.utc) - timedelta(days=days_back)
        kwargs: dict[str, Any] = {
            "stationID": station_id,
            "fromTimeStamp": start_dt,
        }
        q = self._make_type("sessionSearchdata", **kwargs)

        response = self._call("getChargingSessionData", searchQuery=q)
        sessions = []
        data = getattr(response, "ChargingSessionData", None)
        if data is None:
            return sessions
        if not isinstance(data, list):
            data = [data]

        for s in data:
            sessions.append({
                "sessionID": getattr(s, "sessionID", None),
                "stationID": getattr(s, "stationID", None),
                "portNumber": getattr(s, "portNumber", None),
                "userID": getattr(s, "userID", None),
                "startTime": getattr(s, "startTime", None),
                "endTime": getattr(s, "endTime", None),
                "Energy": getattr(s, "Energy", None),
            })

        return sessions

    def get_monthly_session_data(self, station_id: str, local_tz) -> list[dict]:
        """Fetch sessions for current month and previous 2 months separately.

        Makes 3 API calls scoped to each calendar month so we never hit the
        100-record cap that causes the API to return oldest sessions instead of newest.
        """
        from datetime import datetime, timezone, timedelta
        import calendar

        now_local = datetime.now(local_tz if local_tz else timezone.utc)
        all_sessions: list[dict] = []

        for offset in range(3):
            # Compute (year, month) going back `offset` months
            month = now_local.month - offset
            year = now_local.year
            while month <= 0:
                month += 12
                year -= 1

            # Start = midnight on the 1st of that month (local), converted to UTC
            month_start_local = now_local.replace(
                year=year, month=month, day=1,
                hour=0, minute=0, second=0, microsecond=0
            )
            month_start_utc = month_start_local.astimezone(timezone.utc)

            # End = midnight on 1st of NEXT month (exclusive), or now for current month
            if offset == 0:
                month_end_utc = datetime.now(timezone.utc)
            else:
                last_day = calendar.monthrange(year, month)[1]
                month_end_local = now_local.replace(
                    year=year, month=month, day=last_day,
                    hour=23, minute=59, second=59, microsecond=0
                )
                month_end_utc = month_end_local.astimezone(timezone.utc)

            kwargs: dict[str, Any] = {
                "stationID": station_id,
                "fromTimeStamp": month_start_utc,
                "toTimeStamp": month_end_utc,
            }
            q = self._make_type("sessionSearchdata", **kwargs)
            try:
                response = self._call("getChargingSessionData", searchQuery=q)
                data = getattr(response, "ChargingSessionData", None)
                if data is None:
                    continue
                if not isinstance(data, list):
                    data = [data]
                for s in data:
                    all_sessions.append({
                        "sessionID": getattr(s, "sessionID", None),
                        "portNumber": getattr(s, "portNumber", None),
                        "startTime": getattr(s, "startTime", None),
                        "endTime": getattr(s, "endTime", None),
                        "Energy": getattr(s, "Energy", None),
                    })
            except ChargePointAPIError as exc:
                # 136 = no session data for this period — perfectly normal for quiet months
                if "136" in str(exc):
                    _LOGGER.debug("No sessions for month offset=%d (error 136)", offset)
                else:
                    _LOGGER.warning("Monthly session fetch offset=%d failed: %s", offset, exc)
            except Exception as exc:
                _LOGGER.warning("Monthly session fetch offset=%d unexpected error: %s", offset, exc)

        return all_sessions


        """Call shedLoad — uses shedLoadQueryInputData."""
        q = self._make_type(
            "shedLoadQueryInputData",
            stationID=station_id,
            portNumber=port_number,
            allowedLoadPerStation=allowed_load,
        )
        self._call("shedLoad", shedQuery=q)

    def clear_shed_state(self, station_id: str, port_number: int) -> None:
        """Call clearShedState — uses stationIdList."""
        q = self._make_type(
            "stationIdList",
            stationID=station_id,
            portNumber=port_number,
        )
        self._call("clearShedState", clearQuery=q)

    def validate_credentials(self) -> bool:
        """Try a minimal API call to verify credentials are valid."""
        try:
            q = self._make_type("stationSearchRequestExtended")
            self._call("getStations", searchQuery=q)
            return True
        except ChargePointAuthError:
            return False
        except ChargePointAPIError:
            return True

    def get_alarms(self, station_id: str) -> list[dict]:
        """Call getAlarms — returns list of alarms newest first."""
        q = self._make_type("getAlarmsSearchQuery", stationID=station_id)
        response = self._call("getAlarms", searchQuery=q)
        alarms = []
        data = getattr(response, "Alarms", None)
        if data is None:
            return alarms
        if not isinstance(data, list):
            data = [data]
        for a in data:
            alarms.append({
                "alarmType": str(getattr(a, "alarmType", "") or "").strip(),
                "alarmTime": getattr(a, "alarmTime", None),
                "portNumber": getattr(a, "portNumber", None),
            })
        return alarms

    # -----------------------------------------------------------------------
    # Raw probe methods — return the full unserialized zeep response object
    # so diagnostics.py can serialize and log everything the API returns.
    # -----------------------------------------------------------------------

    def _get_raw_stations(self, station_id: str | None = None) -> Any:
        """Return raw getStations response."""
        q = self._make_type("stationSearchRequestExtended",
                            **{"stationID": station_id} if station_id else {})
        return self._call("getStations", searchQuery=q)

    def _get_raw_station_status(self, station_id: str | None = None) -> Any:
        """Return raw getStationStatus response."""
        q = self._make_type("statusSearchdata",
                            **{"stationID": station_id} if station_id else {})
        return self._call("getStationStatus", searchQuery=q)

    def _get_raw_load(self, station_id: str) -> Any:
        """Return raw getLoad response."""
        q = self._make_type("stationloaddata", stationID=station_id)
        return self._call("getLoad", searchQuery=q)

    def _get_raw_session_data(self, station_id: str) -> Any:
        """Return raw getChargingSessionData response (most recent sessions)."""
        q = self._make_type("sessionSearchdata", stationID=station_id)
        return self._call("getChargingSessionData", searchQuery=q)

    def _get_raw_alarms(self, station_id: str) -> Any:
        """Return raw getAlarms response."""
        q = self._make_type("getAlarmsSearchQuery", stationID=station_id)
        return self._call("getAlarms", searchQuery=q)

    def _get_raw_orgs(self) -> Any:
        """Return raw getOrgsAndStationGroups response."""
        q = self._make_type("getOrgsAndStationGroupsSearchQuery")
        return self._call("getOrgsAndStationGroups", searchQuery=q)

    def list_available_methods(self) -> list[str]:
        """Return all operation names exposed by the WSDL service."""
        client = self._get_client()
        return [op for op in client.service._operations]
