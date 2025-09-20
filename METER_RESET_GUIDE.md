# Meter Reading Reset Guide

This guide explains how to use the meter reading reset functionality to fix energy spikes and synchronize your NT Power integration with Home Assistant energy statistics.

---

## When to Use Meter Reading Reset

### Common Scenarios

1. **Energy Spikes After Manual Corrections**
   - You manually corrected energy values in Home Assistant
   - Subsequent NT Power imports show unrealistic spikes (e.g., 61,014 kWh in one day)
   - Your energy dashboard shows impossible consumption values

2. **First-Time Setup with Historical Data**
   - You want to import historical data but have a known meter reading
   - You need to establish an accurate baseline for calculations

3. **Integration Baseline Out of Sync**
   - The integration's stored baseline no longer matches reality
   - Energy calculations are consistently off by a large margin

---

## How It Works

The meter reading reset functionality works by:

1. **Taking a Known Reference Point**: You provide a meter reading and date
2. **Working Backwards**: The system calculates what the baseline should be
3. **Immediate Calculation**: Uses available data (typically 2-3 days behind)
4. **Future Refinement**: Automatically improves accuracy as more data becomes available

### Smart Data Handling

- **Immediate Results**: Calculates with whatever data is available
- **Graceful Degradation**: Works even when NT Power data is delayed
- **Automatic Refinement**: Improves calculations as missing data arrives
- **Status Feedback**: Tells you exactly what data was used and what's missing

---

## Step-by-Step Instructions

### Method 1: Using Home Assistant Services (Recommended)

1. **Get Your Meter Reading**
   - Find a recent meter reading from your physical meter or NT Power bill
   - Note the exact date and kWh value

2. **Call the Reset Service**
   ```yaml
   service: ntpower.reset_from_meter_reading
   data:
     meter_reading_date: "2024-01-15"
     meter_reading_kwh: 45678.5
   ```

3. **Check the Results**
   - Look at the service response for status information
   - Check your energy dashboard for corrected values

### Method 2: Using Configuration UI

1. **Go to Integration Settings**
   - Settings → Devices & Services
   - Find your NT Power integration
   - Click "Configure"

2. **Fill in Meter Reading Fields**
   - **Meter Reading Date**: Format as YYYY-MM-DD (e.g., 2024-01-15)
   - **Meter Reading (kWh)**: Enter the exact reading (e.g., 45678.5)
   - **Recalculate from Meter Reading**: Check this box

3. **Save Configuration**
   - The reset will happen automatically
   - Check your energy dashboard for results

---

## Examples

### Example 1: Fixing Energy Spikes

**Problem**: After manually correcting some energy values in HA, you see a spike of 61,014 kWh on September 15th.

**Solution**:
```yaml
service: ntpower.reset_from_meter_reading
data:
  meter_reading_date: "2024-09-10"  # Date before the spike
  meter_reading_kwh: 23456.7        # Known good reading
```

**Result**: The integration recalculates the baseline, eliminating the spike.

### Example 2: First-Time Historical Import

**Problem**: You want to import 2 years of data but need accurate calculations.

**Solution**:
```yaml
service: ntpower.reset_from_meter_reading
data:
  meter_reading_date: "2024-01-01"  # Start of your data
  meter_reading_kwh: 20000.0        # Meter reading from that date
```

**Result**: All historical data is calculated from the correct baseline.

### Example 3: Automation for Regular Sync

**Use Case**: Automatically sync with monthly meter readings.

```yaml
automation:
  - alias: "Monthly Meter Reading Sync"
    trigger:
      - platform: time
        at: "02:00:00"
      - platform: template
        value_template: "{{ now().day == 1 }}"  # First day of month
    condition:
      - condition: template
        value_template: "{{ states('input_number.meter_reading') | float > 0 }}"
    action:
      - service: ntpower.reset_from_meter_reading
        data:
          meter_reading_date: "{{ now().replace(day=1).strftime('%Y-%m-%d') }}"
          meter_reading_kwh: "{{ states('input_number.meter_reading') | float }}"
```

---

## Understanding the Results

### Service Response Messages

The meter reset service provides detailed feedback:

#### Success Messages
- **"Baseline reset successfully"**: Complete success with full data
- **"Baseline reset with partial data"**: Success but some data missing
- **"Baseline reset with estimated data"**: Success using interpolation

#### Warning Messages
- **"Limited data available"**: Calculation done but accuracy may improve
- **"Using interpolated values"**: Some consumption data was estimated
- **"Data will be refined automatically"**: More accuracy coming as data arrives

#### Error Messages
- **"No consumption data available"**: Need to import basic data first
- **"Invalid meter reading"**: Date/value combination doesn't make sense
- **"Calculation failed"**: System error (check logs)

### Data Availability Status

The system tells you exactly what data was used:

```
Data Availability Report:
- Available days: 2024-01-10 to 2024-01-13 (4 days)
- Missing days: 2024-01-14 to 2024-01-15 (2 days)  
- Calculation method: Direct calculation with interpolation
- Accuracy: Good (will improve as missing data arrives)
```

---

## Troubleshooting

### Common Issues

#### "Meter reading seems unrealistic"
- **Cause**: Date/reading combination doesn't match expected consumption
- **Solution**: Double-check your meter reading date and value
- **Tip**: Use a reading from your NT Power bill for accuracy

#### "No consumption data found"
- **Cause**: No historical data has been imported yet
- **Solution**: Run a regular data import first, then use meter reset
- **Command**: Use the standard NT Power fetch service first

#### "Baseline calculation failed"
- **Cause**: System error or corrupted data
- **Solution**: Check Home Assistant logs for detailed error messages
- **Tip**: Try with a different date range or meter reading

### Validation Tips

1. **Use Recent Readings**: Readings within the last 30 days work best
2. **Check Your Bills**: NT Power bills have accurate meter readings
3. **Verify Dates**: Ensure date format is YYYY-MM-DD
4. **Round Appropriately**: Match the precision of your actual meter

### Data Delay Expectations

NT Power data typically has a 2-3 day delay:

- **Today**: No data available
- **Yesterday**: Usually no data
- **2-3 days ago**: Partial data may be available
- **4+ days ago**: Full data typically available

The reset function handles this gracefully and improves accuracy automatically.

---

## Best Practices

### When to Reset

1. **After Manual Corrections**: Always reset after manually editing HA energy data
2. **New Installation**: Reset with a known reading when setting up historical imports
3. **Periodic Verification**: Monthly resets with bill readings ensure long-term accuracy

### Choosing Reference Points

1. **Use Bill Readings**: Most accurate source
2. **Recent Dates**: Within 30 days for best data availability
3. **Avoid Holiday Periods**: NT Power may have data delays during holidays

### Automation Strategies

1. **Monthly Bill Sync**: Automate with input from monthly bills
2. **Spike Detection**: Trigger reset when consumption exceeds normal patterns
3. **Scheduled Verification**: Weekly checks during low-usage periods

---

## Technical Details

### Calculation Method

The meter reading reset uses the following approach:

1. **Gather Available Data**: Collect all consumption data around the reference date
2. **Calculate Working Values**: Sum consumption from meter reading date to present
3. **Determine Baseline**: `baseline = meter_reading - total_consumption`
4. **Validate Result**: Ensure calculated baseline is reasonable
5. **Apply Correction**: Update stored baseline for future calculations

### Data Interpolation

When consumption data is missing:

1. **Linear Interpolation**: Estimate missing daily values based on surrounding days
2. **Seasonal Adjustment**: Account for typical usage patterns
3. **Conservative Estimates**: Prefer slight underestimation to avoid spikes
4. **Automatic Refinement**: Replace estimates with real data when available

### Baseline Storage

The integration stores the calculated baseline persistently:

- **Location**: Home Assistant configuration directory
- **Format**: JSON with timestamp and validation data
- **Backup**: Previous baselines are preserved for rollback
- **Validation**: Checksums ensure data integrity

---

## Advanced Usage

### Integration with Energy Dashboard

The meter reset integrates seamlessly with Home Assistant's energy dashboard:

1. **Automatic Updates**: Energy statistics are recalculated immediately
2. **Historical Correction**: Past data is updated to reflect new baseline
3. **Future Accuracy**: All subsequent imports use the corrected baseline

### Scripting and Automation

You can integrate meter resets into complex automations:

```yaml
script:
  monthly_energy_sync:
    sequence:
      - service: ntpower.fetch_energy_data
        data:
          days_back: 3
      - wait_for_trigger:
          - platform: event
            event_type: ntpower_import_complete
        timeout: 300
      - service: ntpower.reset_from_meter_reading
        data:
          meter_reading_date: "{{ states('input_datetime.last_meter_reading') }}"
          meter_reading_kwh: "{{ states('input_number.last_meter_reading') }}"
```

### API Integration

For advanced users, the reset functionality can be called programmatically:

```python
# Example Python script for automated meter reading sync
import homeassistant.remote as remote

api = remote.API("localhost", 8123, "your_token")

result = remote.call_service(
    api, 
    "ntpower", 
    "reset_from_meter_reading",
    {
        "meter_reading_date": "2024-01-15",
        "meter_reading_kwh": 45678.5
    }
)
```

---

This guide should provide everything you need to successfully use the meter reading reset functionality to maintain accurate energy statistics in Home Assistant.
