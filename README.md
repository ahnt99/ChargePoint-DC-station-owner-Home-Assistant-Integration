# ChargePoint Station Owner — Home Assistant Integration

[![HACS Custom](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://hacs.xyz)
[![HA Version](https://img.shields.io/badge/Home%20Assistant-2024.1%2B-blue)](https://www.home-assistant.io/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

A Home Assistant custom integration for **ChargePoint commercial station owners** who manage their own chargers via the ChargePoint SOAP Web Services API (v5.0). This is distinct from the built-in ChargePoint integration which is for EV drivers — this integration targets station operators who have API credentials from the ChargePoint portal.

![ChargePoint Station Owner](custom_components/chargepoint_owner/brand/logo.png)

---

## Features

- **Real-time port status** — Available, In Use, Offline per port
- **Live power monitoring** — Current load (kW), allowed load, and percent shed per port
- **Session history** — Last session energy, duration, and end time
- **7-day energy tracking** — Daily kWh and session counts with chart-ready attributes
- **Monthly energy comparison** — Current month + previous 2 months, each as individual sensors
- **Alarm monitoring** — Latest alarm type from the station
- **Load shedding control** — Switch to enable/disable load shed per port
- **HACS installable** — Easy install and updates via HACS

---

## Requirements

- Home Assistant 2024.1 or newer
- A ChargePoint **station owner** API account (not a driver account)
- API credentials from the ChargePoint portal: **Organizations → API Info**

---

## Installation

### Via HACS (Recommended)

1. Open HACS in your Home Assistant instance
2. Go to **Integrations**
3. Click the three-dot menu (⋮) in the top right → **Custom repositories**
4. Add the repository URL: `https://github.com/ahnt99/ChargePoint-DC-station-owner-Home-Assistant-Integration`
5. Select category: **Integration**
6. Click **Add**
7. Find **ChargePoint Station Owner** in the list and click **Download**
8. Restart Home Assistant

### Manual Installation

1. Download the latest zip from the [link](https://github.com/ahnt99/ChargePoint-DC-station-owner-Home-Assistant-Integration/archive/refs/heads/main.zip)
2. Extract and copy the `chargepoint_owner` folder into your `config/custom_components/` directory
3. Restart Home Assistant

---

## Configuration

### Getting API Credentials

1. Log in to the [ChargePoint portal](https://na.chargepoint.com)
2. Go to **Organizations → API Info**
3. Copy your **API License Key** and generate an **API Password**

> **Note:** These are organization-level credentials, different from your ChargePoint driver login.

### Adding the Integration

1. In Home Assistant, go to **Settings → Devices & Services**
2. Click **+ Add Integration**
3. Search for **ChargePoint Station Owner**
4. Enter your **API License Key** and **API Password**
5. Select your station from the dropdown
6. Set your preferred polling interval (default: 60 seconds)

---

## Entities

### Per Port (repeated for each physical port)

| Entity | Type | Description |
|---|---|---|
| Status | Sensor | `AVAILABLE`, `INUSE`, `OFFLINE`, etc. |
| Port Load | Sensor | Current draw in kW |
| Allowed Load | Sensor | Maximum allowed kW |
| Percent Shed | Sensor | Load reduction % currently applied |
| Connector | Sensor | Connector type when in use |
| Charging | Binary Sensor | ON when a vehicle is actively charging |
| Load Shed Active | Binary Sensor | ON when load shedding is active |
| Load Shed | Switch | Enable/disable load shedding |

### Station Level

| Entity | Type | Description |
|---|---|---|
| Total Station Load | Sensor | Combined kW across all ports |
| Last Session End | Sensor | Timestamp of most recent session end |
| Last Session Energy | Sensor | kWh delivered in the most recent session |
| Last Session Duration | Sensor | Duration of most recent session in minutes |
| Average Session Energy | Sensor | Average kWh across recent sessions |
| Last 7 Days Sessions | Sensor | Count of sessions in the rolling 7-day window |
| Monthly Energy Dispensed | Sensor | Current month kWh (with 3-month history in attributes) |
| Energy This Month | Sensor | kWh from 1st of current month to now |
| Energy Last Month | Sensor | kWh for previous calendar month |
| Energy 2 Months Ago | Sensor | kWh for 2 months prior |
| Latest Alarm | Sensor | Most recent alarm type from the station |

---

## Dashboard Examples

### 7-Day Energy & Session Chart (apexcharts-card)

Requires [apexcharts-card](https://github.com/RomRider/apexcharts-card) from HACS.
<img width="521" height="369" alt="Screenshot1" src="https://github.com/user-attachments/assets/505faa4f-1572-4c55-9d58-b2e9e5715c64" />

```yaml
type: custom:apexcharts-card
header:
  show: true
  title: ChargePoint Last 7 Days
graph_span: 6d
span:
  start: day
  offset: "-6d"
series:
  - entity: sensor.your_station_last_7_days_sessions
    name: Energy (kWh)
    type: column
    yaxis_id: energy
    data_generator: |
      const x = entity.attributes.chart_daily_x;
      const y = entity.attributes.chart_daily_y;
      const year = new Date().getFullYear();
      return x.map((label, i) => {
        const [month, day] = label.split('/');
        return [new Date(year, parseInt(month)-1, parseInt(day), 0, 0, 0).getTime(), y[i]];
      });
    show:
      datalabels: true
yaxis:
  - min: 0
    decimals: 0
    apex_config:
      tickAmount: 4
      title:
        text: kWh
      axisBorder:
        show: true
apex_config:
  chart:
    height: 300
  xaxis:
    type: datetime
    labels:
      format: MM/dd
  plotOptions:
    bar:
      columnWidth: 70%
      colors:
        ranges:
          - from: 0
            to: 39.99
            color: "#025c50"
          - from: 40
            to: 79.99
            color: "#02ab94"
          - from: 80
            to: 99999
            color: "#02f5d4"
  dataLabels:
    style:
      colors:
        - "#00000"
    offsetY: -11
```

### Monthly Energy Comparison (apexcharts-card)

```yaml
type: custom:apexcharts-card
graph_span: 3month
span:
  start: month
  offset: "-70days"
header:
  show: true
  title: Monthly Energy Comparison
  show_states: true
  colorize_states: true
series:
  - entity: sensor.your_station_energy_2_months_ago
    color: "#025c50"
    type: column
    name: 2 months ago
    data_generator: |
      return [[entity.attributes.month_name, entity.state]];
  - entity: sensor.your_station_energy_last_month
    color: "#02ab94"
    type: column
    name: Last month
    data_generator: |
      return [[entity.attributes.month_name, entity.state]];
  - entity: sensor.your_station_energy_this_month
    color: "#02f5d4"
    type: column
    name: This month
    data_generator: |
      return [[entity.attributes.month_name, entity.state]];
apex_config:
  chart:
    height: 280
  plotOptions:
    bar:
      columnWidth: 70%
  yaxis:
    decimalsInFloat: 0
    title:
      text: kWh
    axisBorder:
      show: true
  xaxis:
    labels:
      format: MMMM yyyy
  legend:
    show: false
```

---

## Sensor Attributes

### Last 7 Days Sessions
| Attribute | Description |
|---|---|
| `total_energy_kwh` | Sum of all energy in the 7-day window |
| `chart_daily_x` | Array of date labels (`MM/DD`) for charting |
| `chart_daily_y` | Array of daily kWh values |
| `chart_daily_sessions` | Array of daily session counts |
| `session_1` … `session_N` | Per-session detail: start, end, energy_kwh, port |

### Energy This / Last / 2 Months Ago
| Attribute | Description |
|---|---|
| `period` | Month in `YYYY-MM` format |
| `month_name` | Human-readable name, e.g. `January 2026` |

---

## Developer Service

A diagnostic service `chargepoint_owner.probe_api` is available under **Developer Tools → Services**. It calls every API method and logs the full raw response at INFO level — useful for discovering what data your specific station exposes.

---

## Troubleshooting

**Integration shows "Authentication Failed"**
Verify your API License Key and Password in the ChargePoint portal under Organizations → API Info. Passwords must be regenerated if forgotten.

**Last Session shows old date**
The API returns sessions unsorted. The integration sorts by `endTime` descending after fetching. If the date is still stale, try restarting the integration via Settings → Devices & Services → ChargePoint Station Owner → Reload.

**Error 136 in logs**
This is normal — it means no sessions were found for a given month (e.g. a month with no charging activity). The sensor will show `0.0 kWh`.

**Entities not updating**
Default polling is 60 seconds. You can lower it during setup or via the integration's **Configure** option.

---

## API Reference

This integration uses the [ChargePoint Web Services API v5.0](https://na.chargepoint.com/UI/s3docs/docs/help/SetupWebServicesAPI.pdf).

SOAP methods used:
- `getStations` — station metadata
- `getStationStatus` — port status and connector info
- `getLoad` — real-time power data and shed state
- `getChargingSessionData` — session history
- `getAlarms` — station fault and event history
- `shedLoad` / `clearShedState` — load control


