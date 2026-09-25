
## This repo has been archive now that there is a project that can read and input green button data into home assistant. You can find that project here: https://github.com/rocketraman/open-green-button-homeassistant

The repo does use a very different way to pull data from NT Hydro so it may have some uses still.


# NTPower — Home Assistant Integration

A custom Home Assistant integration that fetches energy usage data from NT Power and imports it into Home Assistant's long-term statistics. Supports incremental daily updates, full historical backfills, and baseline recalibration after manual corrections.

---

## Overview

NT Power does not provide a native Home Assistant integration. This component bridges that gap by authenticating with the NT Power API, downloading your hourly consumption data, and writing it into the Home Assistant statistics database using the [homeassistant-statistics](https://github.com/klausj1/homeassistant-statistics) TSV format.

Once set up, energy data appears under your chosen statistic entity and is visible in the Home Assistant Energy dashboard.

---

## Features

- Fetches hourly energy usage from the NT Power API
- Incremental daily updates — only fetches new data each run
- Full historical backfill for first-time setup or database rebuilds
- Persistent baseline state maintained between restarts and imports
- Meter reading recalibration to correct baseline drift after manual edits
- Configurable date ranges, statistic ID, timezone, and starting meter value
- Data stored as a standard TSV file compatible with homeassistant-statistics

---

## Requirements

- Home Assistant 2023.1 or later
- An NT Power online account with API access
- The [homeassistant-statistics](https://github.com/klausj1/homeassistant-statistics) integration installed (used to import the TSV data file)

---

## Installation

### Manual Installation (Custom Component)

1. Copy the `ntpower` folder into your Home Assistant configuration directory:
   ```
   /config/custom_components/ntpower/
   ```
2. Restart Home Assistant.
3. Navigate to **Settings → Devices & Services → Add Integration** and search for **NTPower**.

### Home Assistant Add-on

1. Place the repository folder into your add-ons directory:
   ```
   /addons/ntpower/
   ```
2. Make the startup script executable:
   ```bash
   chmod +x run.sh
   ```
3. In Home Assistant, go to **Supervisor → Add-ons**, locate the NTPower add-on, and start it.

---

## Configuration

On first run, the integration will prompt for the following information.

### Required

| Field | Description | Example |
|---|---|---|
| Account ID | Found on your NT Power bill or online account | `00469442-05` |
| Service ID | Found on your NT Power bill or online account | `00469442-E-05` |
| Username | Your NT Power online account email | `user@example.com` |
| Password | Your NT Power online account password | |

### Optional

| Field | Description | Default |
|---|---|---|
| Statistic ID | Home Assistant entity ID for the statistic | `sensor:ntpower_energy_export` |
| Unit | Energy unit | `kWh` |
| Timezone | Your local timezone | `America/Toronto` |
| Start Date | Earliest date to fetch data from (`YYYY-MM-DD`) | |
| Initial Sum | Your meter reading in kWh at the start date | |

### Initial Sum

The Initial Sum sets the cumulative kWh baseline from which all imported data is offset. It is only applied once — when the integration has no saved state. After that, the baseline is tracked automatically.

To find a suitable value, check your physical meter or a recent NT Power electricity bill for a total consumption figure corresponding to a known date.

**Example:** If your meter reads `83761.120` kWh on January 1st and you set your start date to `2025-01-01`, enter `83761.120` as the Initial Sum.

---

## Services

The integration exposes three services that can be called manually or via automations.

---

### `ntpower.refresh`

Performs an incremental update, fetching any new data since the last recorded timestamp. This is the service you should run on a daily schedule for ongoing tracking.

**Standard usage:**
```yaml
service: ntpower.refresh
```

No parameters are required. The integration picks up from where it last left off.

**Optional parameters:**
```yaml
service: ntpower.refresh
data:
  start_date: "2025-01-01"    # Override the fetch start date (YYYY-MM-DD)
  end_date: "2025-09-20"      # Limit the fetch to a specific end date (YYYY-MM-DD)
  initial_sum: 83761.120      # Set a baseline only if no saved state exists
```

---

### `ntpower.backfill`

Imports a large block of historical data. Use this for first-time setup, rebuilding the database, or importing a specific date range.

**Import full available history:**
```yaml
service: ntpower.backfill
data:
  full_history: true
  initial_sum: 83761.120    # Meter reading at the start of the history
```

**Import a specific date range:**
```yaml
service: ntpower.backfill
data:
  start_date: "2025-01-01"
  end_date: "2025-09-20"
  initial_sum: 83400.500    # Meter reading on start_date
```

**Import from a date through to today:**
```yaml
service: ntpower.backfill
data:
  start_date: "2025-07-01"
```

---

### `ntpower.reset_from_meter_reading`

Recalculates the stored baseline using a known physical meter reading. Use this after manually correcting data in Home Assistant that caused the cumulative total to drift.

This service calculates the correct baseline immediately, even if NT Power's API data is a few days behind. If the calculation is performed with missing recent data, the result is flagged as preliminary — re-running the same call once NT Power catches up will refine it.

**Reset using a known meter reading:**
```yaml
service: ntpower.reset_from_meter_reading
data:
  meter_reading_date: "2025-09-19 23:00"    # Date and time of the meter reading (YYYY-MM-DD HH:MM)
  meter_reading_kwh: 83761.120              # Meter reading in kWh at that time
```

**With an explicit date range:**
```yaml
service: ntpower.reset_from_meter_reading
data:
  meter_reading_date: "2025-09-15 12:00"
  meter_reading_kwh: 83625.120
  start_date: "2025-01-01"
  end_date: "2025-09-20"
```

---

## Getting Started

### First-Time Setup

1. Install the integration and complete the configuration wizard with your NT Power credentials.
2. Locate your current meter reading — check your physical meter or a recent electricity bill.
3. Run a full historical backfill:
   ```yaml
   service: ntpower.backfill
   data:
     full_history: true
     initial_sum: 83761.120    # Replace with your actual meter reading
   ```
4. Create a daily automation to keep data current (see the Automations section below).

### Ongoing Daily Tracking

Schedule `ntpower.refresh` to run each morning. The service automatically fetches only new data since the last run, so there is no need to manage date ranges manually.

### Fixing Energy Spikes After Manual Corrections

If you manually corrected an outlier spike in the Home Assistant statistics editor, the stored cumulative total no longer matches the actual meter. Subsequent imports will introduce new spikes because the baseline is wrong.

To fix this:
1. Take a physical meter reading, or find a reliable kWh figure from your NT Power account at a known date and time.
2. Call `ntpower.reset_from_meter_reading` with that value.

The integration recalculates the baseline immediately. If NT Power's API data is a few days behind, the result will be marked as preliminary — re-running the same call once the API catches up will refine the calculation.

---

## Automations

### Daily Incremental Refresh

```yaml
alias: "NTPower: Daily Refresh"
trigger:
  - platform: time
    at: "02:00:00"
action:
  - service: ntpower.refresh
mode: single
```

### Refresh on Home Assistant Restart

```yaml
alias: "NTPower: Refresh on Restart"
trigger:
  - platform: homeassistant
    event: start
action:
  - delay: "00:02:00"
  - service: ntpower.refresh
mode: single
```

### Weekly Refresh from a Fixed Start Date

```yaml
alias: "NTPower: Weekly Refresh"
trigger:
  - platform: time
    at: "03:00:00"
condition:
  - condition: time
    weekday:
      - sun
action:
  - service: ntpower.refresh
    data:
      start_date: "2025-01-01"
mode: single
```

---

## Data Storage

The integration stores all files under `/config/ntpower_data/`:

| File | Purpose |
|---|---|
| `counterdata.tsv` | Statistics import file in TSV format, consumed by homeassistant-statistics |
| `stat_import_state.json` | Persisted baseline and last-processed timestamp |
| `ntpower_raw_response.json` / `.csv` | Raw API response, retained for debugging |

### State File Format

`stat_import_state.json` contains the running total and the timestamp of the last imported record:

```json
{
  "sensor:ntpower_energy_export": {
    "last_sum": 83761.120,
    "last_ts": "2025-09-19T23:00:00-04:00"
  }
}
```

### TSV File Format

`counterdata.tsv` follows the homeassistant-statistics format:

```
statistic_id                    start              end                state  sum
sensor:ntpower_energy_export    20.09.2025 00:00   20.09.2025 01:00   2.45   83763.570
```

---

## Troubleshooting

**Energy spikes appear after the next import following a manual correction**  
The stored baseline no longer matches the actual meter. Use `ntpower.reset_from_meter_reading` with a known meter reading to recalibrate. See [METER_RESET_GUIDE.md](METER_RESET_GUIDE.md) for a step-by-step walkthrough.

**Data is not appearing in the Home Assistant Energy dashboard**  
Confirm that the TSV file exists at `/config/ntpower_data/counterdata.tsv`. Verify the Statistic ID in the integration configuration matches the entity expected by homeassistant-statistics. A Home Assistant restart may be required after the first import.

**The log shows "preliminary calculation"**  
The baseline was saved successfully, but NT Power's API data is a few days behind. Your next regular refresh will resolve this automatically, or you can re-run the same `reset_from_meter_reading` call once the API is up to date.

**A service call fails with an authentication error**  
Confirm that your NT Power username, password, Account ID, and Service ID are still correct. Credentials can be re-entered by removing and re-adding the integration.

### Full Reset

To clear all state and re-import from scratch:

1. Disable or stop any automations that call NTPower services.
2. Delete `/config/ntpower_data/stat_import_state.json`.
3. Delete `/config/ntpower_data/counterdata.tsv`.
4. Run a fresh backfill:
   ```yaml
   service: ntpower.backfill
   data:
     full_history: true
     initial_sum: 83761.120    # Your current meter reading
   ```

---

## Notes

- **Date format:** Use `YYYY-MM-DD` for dates and `YYYY-MM-DD HH:MM` for date/time values throughout all service calls.
- **Initial Sum** is applied only once, when no saved state file exists. After the first run, the baseline is tracked automatically and this value is ignored.
- **Automation timing:** Running the daily refresh between 2 AM and 6 AM is recommended, as NT Power's data pipeline is typically current by that time.
- **Meter reset guide:** See [METER_RESET_GUIDE.md](METER_RESET_GUIDE.md) for detailed instructions on correcting baseline drift.
