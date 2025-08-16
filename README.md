# NTPower Home Assistant Integration

A custom Home Assistant integration for downloading and importing **NT Power** energy usage data.  
Supports both incremental updates (daily/hourly) and one-time full history backfill with an optional initial meter reading.

---

## Features

- Fetch energy usage from NT Power’s official APIs (CSV or JSON).
- Incremental refresh for ongoing data collection.
- Full history backfill for first-time setup or re-imports.
- Configurable start date (default = Jan 1 of the current year).
- Optional initial meter reading (baseline sum).
  - If none provided → starts at 0.
  - If provided → used once at first import.
- Persistent baseline stored under `/config/ntpower_data/stat_import_state.json`.
- Data written in [Home Assistant statistics TSV format](https://github.com/klausj1/homeassistant-statistics) under `/config/ntpower_data/counterdata.tsv`.

---

## Installation

### As a Custom Component

1. Copy the folder into your Home Assistant config:
   ```
   /config/custom_components/ntpower/
   ```
2. Restart Home Assistant.
3. Add the integration through the UI:  
   **Settings → Devices & Services → Add Integration → NTPower**

### As an Add-on (optional)

1. Place the repo folder into:
   ```
   /addons/ntpower/
   ```
2. Ensure the included `run.sh` is executable:
   ```bash
   chmod +x run.sh
   ```
3. Add the add-on from **Supervisor → Add-ons** and start it.  
   (The add-on itself just installs the component; services are called via HA.)

---

## Configuration

During setup you will be asked for:

- Account ID  
- Service ID  
- Username / Password (portal login)  
- Statistic ID (default: `sensor:ntpower_energy_export`)  
- Unit (default: `kWh`)  
- Timezone (default: `America/Toronto`)  
- Base URL / Portal Origin (defaults provided)  

Optional at setup:

- Start Date (`YYYY-MM-DD`)  
- Initial Sum (your current meter reading, e.g. `61014`)  

---

## Services

### `ntpower.refresh`

Fetches new incremental data since the last run.  
Default behavior for daily automations.

Optional fields:

```yaml
start_date: "2025-01-01"   # override default (Jan 1 of current year)
end_date: "2025-08-01"     # optional cutoff, default = today
initial_sum: 61014         # baseline, only applied if no baseline exists
full_history: false        # ignored here unless explicitly passed
```

---

### `ntpower.backfill`

One-time full history import (or bounded range).  
Useful after first installation or to rebuild your DB.

Examples:

```yaml
# Go way back and start from a specific meter reading
service: ntpower.backfill
data:
  full_history: true
  initial_sum: 61014

# Backfill from 2023-01-01 until now
service: ntpower.backfill
data:
  start_date: "2023-01-01"

# Bounded backfill
service: ntpower.backfill
data:
  start_date: "2022-01-01"
  end_date: "2025-08-01"
```

---

## Example Automations

### Daily Incremental Refresh

```yaml
alias: "NTPower: Daily Refresh"
trigger:
  - platform: time
    at: "02:00:00"
action:
  - service: ntpower.refresh
    data: {}
mode: single
```

### One-time Full History Import

Run once from **Developer Tools → Services**:

```yaml
service: ntpower.backfill
data:
  full_history: true
  initial_sum: 61014
```

---

## Data Storage

- Raw responses: `/config/ntpower_data/ntpower_raw_response.json` (or `.csv`)  
- Import TSV: `/config/ntpower_data/counterdata.tsv`  
- Baseline state: `/config/ntpower_data/stat_import_state.json`

---

## Notes

- If `initial_sum` is provided, it is only applied once (when no baseline exists).  
- To reset and re-import, delete `stat_import_state.json` and rerun `ntpower.backfill`.  
- The TSV format is compatible with [homeassistant-statistics](https://github.com/klausj1/homeassistant-statistics).
