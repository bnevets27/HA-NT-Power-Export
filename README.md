# NTPower Home Assistant Integration

A custom Home Assistant integration for downloading and importing **NT Power** energy usage data.  
Supports both incremental updates (daily/hourly) and one-time full history backfill with smart meter reading synchronization.

---

## Features

- **Automatic Data Import**: Fetch energy usage from NT Power's official APIs (CSV or JSON)
- **Incremental Updates**: Daily refresh for ongoing data collection
- **Full History Backfill**: One-time import for first-time setup or re-imports
- **Smart Baseline Management**: Automatic calculation with meter reading synchronization
- **Outlier Correction**: Fix energy spikes caused by manual corrections in Home Assistant
- **Configurable Date Ranges**: Custom start/end dates for any time period
- **Persistent Storage**: Maintains baseline state between imports
- **HA Statistics Compatible**: Data written in [Home Assistant statistics TSV format](https://github.com/klausj1/homeassistant-statistics)

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

During initial setup, you'll need to provide your NT Power account information:

### Required Fields
To get your Account and Service ID, go to "my energy usage" the URL will be formatted as follows:
myaccount.ntpower.ca/myaccount/myaccount#!/energyuse/***ACCOUNT ID***/***SERVICE ID***

- **Account ID**: Find this on your NT Power bill or online account (format: `00469442-05`)
- **Service ID**: Also on your bill or account (format: `00469442-E-05`) 
- **Username**: Your NT Power online account email
- **Password**: Your NT Power online account password

### Optional Fields

- **Statistic ID**: Home Assistant entity ID (default: `sensor:ntpower_energy_export`)
- **Unit**: Energy measurement unit (default: `kWh`)
- **Timezone**: Your local timezone (default: `America/Toronto`)
- **Start Date**: When to begin data collection (format: `YYYY-MM-DD`, example: `2025-01-01`)
- **Initial Sum**: Your current meter reading in kWh (example: `83761.120`)

### Understanding Key Configuration Options

#### **Initial Sum (Starting Meter Reading)**
- **What it does**: Sets the baseline for your energy calculations
- **When to use**: When you know your exact meter reading at a specific point
- **Example**: If your meter reads `83761.120` kWh on January 1st, use that as your initial sum
- **Important**: Only applied once when no baseline exists - future updates calculate automatically

#### **Meter Reading Reset** 
- **What it does**: Fixes sync issues when manual corrections in HA cause baseline mismatches
- **When to use**: After manually correcting outlier spikes in Home Assistant
- **How it works**: Uses a known meter reading to recalibrate the baseline calculation
- **Example**: If you corrected a 61014 kWh spike manually, use this to resync future imports

---

## Services

The integration provides three main services for different use cases:

### `ntpower.refresh`

**Purpose**: Daily incremental data updates  
**Use case**: Regular automation to fetch new energy data since the last import

**Basic usage** (most common):
```yaml
service: ntpower.refresh
# No parameters needed - uses intelligent defaults
```

**Advanced usage** with custom parameters:
```yaml
service: ntpower.refresh
data:
  start_date: "2025-01-01"      # Override default start (format: YYYY-MM-DD)
  end_date: "2025-09-20"        # Optional end date (format: YYYY-MM-DD)  
  initial_sum: 83761.120        # Baseline reading (only if no baseline exists)
```

---

### `ntpower.backfill`

**Purpose**: Large historical data import  
**Use case**: First-time setup, rebuilding database, or importing specific date ranges

**Full history import** (recommended for first setup):
```yaml
service: ntpower.backfill
data:
  full_history: true
  initial_sum: 83761.120        # Your meter reading at start date
```

**Specific date range**:
```yaml
service: ntpower.backfill
data:
  start_date: "2025-01-01"      # Start of import range
  end_date: "2025-09-20"        # End of import range
  initial_sum: 83400.500        # Meter reading on start_date
```

**Recent months only**:
```yaml
service: ntpower.backfill  
data:
  start_date: "2025-07-01"      # Last 3 months
  # end_date omitted = imports until today
```

---

### `ntpower.reset_from_meter_reading`

**Purpose**: Fix sync issues after manual corrections in Home Assistant  
**Use case**: When outlier spikes cause baseline mismatches in future imports

⭐ **NEW**: Smart calculation that works immediately, even with incomplete NT Power data

**Basic meter reset**:
```yaml
service: ntpower.reset_from_meter_reading
data:
  meter_reading_date: "2025-09-19 23:00"    # When you read your meter (YYYY-MM-DD HH:MM)
  meter_reading_kwh: 83761.120              # Actual meter reading in kWh
```

**With custom date range**:
```yaml
service: ntpower.reset_from_meter_reading
data:
  meter_reading_date: "2025-09-15 12:00"    # Known meter reading time
  meter_reading_kwh: 83625.120              # Actual reading at that time
  start_date: "2025-01-01"                  # Override data fetch range
  end_date: "2025-09-20"                    # Override data fetch range
```

**Smart Features:**
- ✅ **Immediate fix**: Resolves sync issues right away, even if NT Power data is 2-3 days behind
- ⚠️ **Status feedback**: Shows "complete" (accurate) or "preliminary" (missing recent data)
- 🔄 **Auto-refinement**: Re-run the same service call later for improved accuracy
- 💡 **No waiting**: Don't wait days to fix outlier problems!

---

## Usage Scenarios

### Scenario 1: First-Time Setup

**Goal**: Import all your historical energy data from NT Power

1. **Install** the integration through Home Assistant UI
2. **Configure** with your NT Power credentials  
3. **Take a meter reading** or check your latest bill for current kWh total
4. **Run full backfill**:
   ```yaml
   service: ntpower.backfill
   data:
     full_history: true
     initial_sum: 83761.120    # Your current meter reading
   ```
5. **Set up daily automation** (see examples below)

### Scenario 2: Daily Energy Tracking

**Goal**: Automatically import new energy data every day

**Set up automation**:
```yaml
alias: "NTPower: Daily Energy Import"
trigger:
  - platform: time
    at: "06:00:00"              # Run every morning at 6 AM
action:
  - service: ntpower.refresh
    data: {}                    # No parameters needed
mode: single
```

### Scenario 3: Fixing Energy Spikes

**Goal**: Correct sync issues after manually fixing outliers in Home Assistant

**Problem**: You had a 61014 kWh spike on Sept 15, manually corrected it, but next import creates new spikes

**Solution**:
1. **Take a meter reading** after the corrected date (e.g., Sept 19 at 11 PM = 83761.120 kWh)
2. **Reset baseline**:
   ```yaml
   service: ntpower.reset_from_meter_reading
   data:
     meter_reading_date: "2025-09-19 23:00"
     meter_reading_kwh: 83761.120
   ```
3. **Future imports** will now be properly synchronized

### Scenario 4: Import Specific Date Range

**Goal**: Backfill data for a specific time period (e.g., summer months)

```yaml
service: ntpower.backfill
data:
  start_date: "2025-06-01"      # Start of summer
  end_date: "2025-08-31"        # End of summer  
  initial_sum: 82500.0          # Meter reading on June 1st
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

### Weekly Full Refresh (Alternative)

```yaml
alias: "NTPower: Weekly Refresh"  
trigger:
  - platform: time
    at: "03:00:00"
  - condition: time
    weekday:
      - sun                     # Run on Sundays only
action:
  - service: ntpower.refresh
    data:
      start_date: "2025-01-01"  # Always refresh from year start
mode: single
```

### Conditional Refresh on HA Restart

```yaml
alias: "NTPower: Refresh on Restart"
trigger:
  - platform: homeassistant
    event: start
action:
  - delay: "00:02:00"           # Wait for HA to fully start
  - service: ntpower.refresh
    data: {}
mode: single
```

---

## Data Storage

All data is stored in the `/config/ntpower_data/` directory:

- **`counterdata.tsv`**: Home Assistant statistics import file (TSV format)
- **`stat_import_state.json`**: Baseline state and last processed timestamp  
- **`ntpower_raw_response.json`** (or `.csv`): Raw NT Power API response for debugging

### Understanding the Files

**`stat_import_state.json`**: Contains your baseline calculation and sync state
```json
{
  "sensor:ntpower_energy_export": {
    "last_sum": 83761.120,                    // Current baseline total
    "last_ts": "2025-09-19T23:00:00-04:00"    // Last processed timestamp
  }
}
```

**`counterdata.tsv`**: Tab-separated file ready for HA statistics import
```
statistic_id    start   end     state   sum
sensor:ntpower_energy_export    20.09.2025 00:00   20.09.2025 01:00   2.45    83763.570
```

---

## Troubleshooting

### Common Issues

**Energy spikes after manual corrections in HA**
- **Solution**: Use `ntpower.reset_from_meter_reading` to resync the baseline
- **Example**: Take a meter reading and reset with the service call

**Data not importing into Home Assistant**  
- Check that the TSV file exists: `/config/ntpower_data/counterdata.tsv`
- Verify the statistic ID matches your configured entity
- Restart Home Assistant to reload statistics

**"Preliminary calculation" message**
- Your baseline was calculated but NT Power data is 2-3 days behind
- **Action**: Your sync issues are fixed immediately! For best accuracy, re-run the same service call in a few days

**Service call fails**
- Check Home Assistant logs for error details
- Verify NT Power credentials are still valid
- Ensure account ID and service ID are correct format

### Reset and Start Over

To completely reset and re-import all data:

1. **Stop** any running automations
2. **Delete** the state file: `/config/ntpower_data/stat_import_state.json`
3. **Delete** existing data: `/config/ntpower_data/counterdata.tsv`
4. **Run** full backfill with your current meter reading:
   ```yaml
   service: ntpower.backfill
   data:
     full_history: true
     initial_sum: 83761.120    # Your current meter reading
   ```

---

## Notes

- **Initial Sum**: Only applied once when no baseline exists - automatic calculation thereafter
- **Meter Reset**: Use after manual corrections in HA to prevent future sync issues  
- **Date Formats**: Always use `YYYY-MM-DD` for dates, `YYYY-MM-DD HH:MM` for date/time
- **Compatibility**: TSV format works with [homeassistant-statistics](https://github.com/klausj1/homeassistant-statistics)
- **Automation Timing**: Run daily refresh early morning (2-6 AM) when NT Power data is most current

📖 **For detailed meter reset instructions, see [METER_RESET_GUIDE.md](METER_RESET_GUIDE.md)**



