from __future__ import annotations

import io
import csv
import json
import re
from datetime import datetime, timedelta
from collections import defaultdict
from pathlib import Path
from typing import Dict, Any, List, Tuple
from urllib.parse import quote

import requests
from dateutil import tz

from .const import (
    CONF_ACCOUNT_ID, CONF_SERVICE_ID, CONF_USERNAME, CONF_PASSWORD,
    CONF_STATISTIC_ID, CONF_UNIT, CONF_TIMEZONE, CONF_BASE_URL,
    CONF_START_DATE, CONF_END_DATE, CONF_INITIAL_SUM, CONF_FULL_HISTORY,
    CONF_STATE_STORE, CONF_RESET_BASELINE, CONF_CONTINUE_FROM_TSV,
    CONF_METER_READING_DATE, CONF_METER_READING_KWH, CONF_RECALCULATE_FROM_METER,
)

BASELINE_DEFAULT_PATH = "/config/ntpower_data/stat_import_state.json"
NT_POWER_PORTAL_ORIGIN = "https://myaccount.ntpower.ca"

UUID_RE = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
JWT_RE = re.compile(r"^[A-Za-z0-9-_]+\.[A-Za-z0-9-_]+\.[A-Za-z0-9-_]+$")

def looks_like_bearer(val: str) -> bool:
    if not val:
        return False
    v = val.strip().strip('"').strip("'")
    return bool(UUID_RE.match(v) or JWT_RE.match(v))

def login_and_get_token(sess: requests.Session, username: str, password: str, portal_origin: str, login_url: str) -> str:
    data = {"username": username, "password": password, "client_id": "iam"}
    headers = {
        "origin": portal_origin,
        "referer": f"{portal_origin}/",
        "user-agent": "Mozilla/5.0",
        "x-requested-with": "XMLHttpRequest",
        "accept": "application/json, text/plain, */*",
        "content-type": "application/x-www-form-urlencoded; charset=UTF-8",
    }
    r = sess.post(login_url, data=data, headers=headers, timeout=60)
    r.raise_for_status()
    obj = r.json()
    token = (obj.get("access_token") or obj.get("token") or "").strip()
    if not looks_like_bearer(token):
        token = next((v for v in obj.values() if isinstance(v, str) and looks_like_bearer(v)), None)
    if not looks_like_bearer(token):
        raise RuntimeError("Token not found in login response")
    return token

def discover_account_info(sess: requests.Session, token: str, base_url: str, portal_origin: str) -> Tuple[str, str]:
    """
    Automatically discover account_id and service_id after login.
    
    Returns:
        Tuple of (account_id, service_id)
    """
    headers = {
        "accept": "application/json",
        "origin": portal_origin,
        "referer": f"{portal_origin}/",
        "x-requested-with": "XMLHttpRequest",
        "user-agent": "Mozilla/5.0",
        "authorization": f"Bearer {token}",
    }
    
    # Try to get account information from various endpoints
    account_endpoints = [
        f"{base_url}/accountapi/accounts",
        f"{base_url}/accountapi/account/info",
        f"{base_url}/accountapi/user/accounts",
        f"{base_url}/usageapi/accounts",
    ]
    
    for endpoint in account_endpoints:
        try:
            r = sess.get(endpoint, headers=headers, timeout=30)
            if r.status_code == 200:
                data = r.json()
                
                # Extract account and service info from response
                account_id, service_id = _extract_ids_from_response(data)
                if account_id and service_id:
                    return account_id, service_id
                    
        except Exception:
            continue
    
    raise RuntimeError("Could not automatically discover account_id and service_id. Please provide them manually.")

def _extract_ids_from_response(data: Any) -> Tuple[str | None, str | None]:
    """
    Extract account_id and service_id from API response data.
    """
    account_id = None
    service_id = None
    
    # Handle different response structures
    if isinstance(data, dict):
        # Direct fields
        account_id = (data.get("accountId") or data.get("account_id") or 
                     data.get("accountNumber") or data.get("account_number"))
        service_id = (data.get("serviceId") or data.get("service_id") or 
                     data.get("serviceNumber") or data.get("service_number"))
        
        # Check nested structures
        if not account_id or not service_id:
            for key in ["accounts", "services", "data", "result"]:
                if key in data and isinstance(data[key], list) and data[key]:
                    first_item = data[key][0]
                    if isinstance(first_item, dict):
                        if not account_id:
                            account_id = (first_item.get("accountId") or first_item.get("account_id") or 
                                        first_item.get("accountNumber") or first_item.get("account_number"))
                        if not service_id:
                            service_id = (first_item.get("serviceId") or first_item.get("service_id") or 
                                        first_item.get("serviceNumber") or first_item.get("service_number"))
    
    elif isinstance(data, list) and data:
        # Array response, take first item
        first_item = data[0]
        if isinstance(first_item, dict):
            account_id = (first_item.get("accountId") or first_item.get("account_id") or 
                         first_item.get("accountNumber") or first_item.get("account_number"))
            service_id = (first_item.get("serviceId") or first_item.get("service_id") or 
                         first_item.get("serviceNumber") or first_item.get("service_number"))
    
    return account_id, service_id

def usage_url(base_url: str, account_id: str, service_id: str, start_str: str, end_str: str, tz_encoded: str) -> str:
    return (
        f"{base_url}/usageapi/energy/account/{account_id}/service/{service_id}"
        f"/usageDownload?startDate={start_str}&endDate={end_str}&generation=false&tz={tz_encoded}"
    )

def parse_json_data(data: str, points: List[Tuple[datetime, float]], tz_local):
    def add_point(ts, val):
        if not ts or val is None:
            return
        try:
            dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
            dt_local = dt.astimezone(tz_local)
            points.append((dt_local, float(val)))
        except Exception:
            pass

    obj = json.loads(data)
    containers = []
    if isinstance(obj, list):
        containers = obj
    elif isinstance(obj, dict):
        maybe = obj.get("data") or obj.get("readings") or obj.get("blocks")
        containers = maybe if isinstance(maybe, list) else [obj]
    else:
        containers = []

    for item in containers:
        ts = (item.get("startTime") or item.get("time") or item.get("timestamp"))
        val = (item.get("kwh") or item.get("quantity") or item.get("value"))
        if ts and val is not None:
            add_point(ts, val)
            continue
        for key in ("intervalReadings", "readings", "intervals"):
            arr = item.get(key)
            if isinstance(arr, list):
                for r in arr:
                    r_ts = (r.get("startTime") or r.get("time") or r.get("timestamp"))
                    r_val = (r.get("kwh") or r.get("quantity") or r.get("value"))
                    add_point(r_ts, r_val)

def parse_csv_data(data: str, points: List[Tuple[datetime, float]], tz_local):
    reader = csv.reader(io.StringIO(data))
    for row in reader:
        if len(row) < 2 or not row[0] or not row[1]:
            continue
        try:
            dt = datetime.strptime(row[0].split(" to ")[0], "%Y/%m/%d %H:%M")
            points.append((dt.replace(tzinfo=tz_local), float(row[1])))
        except Exception:
            pass

def aggregate_points(points: List[Tuple[datetime, float]], fill_missing: bool, tz_local):
    by_hour = defaultdict(float)
    for dt, val in points:
        hour = dt.replace(minute=0, second=0, microsecond=0)
        by_hour[hour] += round(val, 3)
    if fill_missing and by_hour:
        cur = min(by_hour)
        last = max(by_hour)
        while cur <= last:
            by_hour.setdefault(cur, 0.0)
            cur += timedelta(hours=1)
    return by_hour

def _load_baseline(path: str, statistic_id: str) -> Tuple[float, datetime | None]:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        entry = data.get(statistic_id)
        if not entry:
            return 0.0, None
        last_sum = float(entry.get("last_sum", 0.0))
        last_ts = entry.get("last_ts")
        last_ts_dt = datetime.fromisoformat(last_ts) if last_ts else None
        return last_sum, last_ts_dt
    except Exception:
        return 0.0, None

def _save_baseline(path: str, statistic_id: str, last_sum: float, last_ts_dt: datetime):
    try:
        store = {}
        p = Path(path)
        if p.exists():
            try:
                store = json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                store = {}
        store[statistic_id] = {
            "last_sum": round(float(last_sum), 6),
            "last_ts": last_ts_dt.isoformat() if last_ts_dt else None,
        }
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(store, indent=2), encoding="utf-8")
    except Exception:
        pass

def validate_data_availability(by_hour: Dict[datetime, float], meter_date: datetime, tz_local) -> Tuple[str, str, bool]:
    """
    Validate data availability for baseline calculation.
    Always allows calculation but provides status and update recommendations.
    
    Args:
        by_hour: Dictionary of hourly energy consumption data
        meter_date: Date/time of the known meter reading
        tz_local: Local timezone
    
    Returns:
        Tuple of (status, message, needs_future_update)
        status: "complete", "preliminary", or "missing_data"
    """
    if not by_hour:
        return "missing_data", "No energy data available", False
    
    # Find the latest data point
    latest_data_hour = max(by_hour.keys())
    
    # Calculate how far the data extends relative to meter reading
    if latest_data_hour >= meter_date:
        # We have data past the meter reading date - perfect!
        return "complete", "✅ Complete data available for accurate baseline calculation", False
    
    # Calculate missing time period
    missing_time = meter_date - latest_data_hour
    missing_hours = missing_time.total_seconds() / 3600
    missing_days = missing_hours / 24
    
    if missing_hours <= 24:
        # Missing less than 1 day - very good
        return "complete", (
            f"✅ Nearly complete data (missing {missing_hours:.1f} hours). "
            f"Baseline calculation will be very accurate."
        ), False
    elif missing_hours <= 72:
        # Missing 1-3 days - acceptable, calculate now but suggest update
        return "preliminary", (
            f"⚠️ Preliminary calculation (missing {missing_days:.1f} days of recent data). "
            f"Latest data: {latest_data_hour.strftime('%Y-%m-%d %H:%M')}, "
            f"Meter reading: {meter_date.strftime('%Y-%m-%d %H:%M')}. "
            f"Baseline calculated with available data. Run again in {missing_days:.0f} days for final accuracy."
        ), True
    else:
        # Missing more than 3 days - still calculate but strongly recommend update
        return "preliminary", (
            f"⚠️ Preliminary calculation (missing {missing_days:.1f} days of recent data). "
            f"Latest data: {latest_data_hour.strftime('%Y-%m-%d %H:%M')}, "
            f"Meter reading: {meter_date.strftime('%Y-%m-%d %H:%M')}. "
            f"Baseline calculated but may be inaccurate. Strongly recommend re-running in {missing_days:.0f} days."
        ), True

def calculate_baseline_from_meter_reading(
    by_hour: Dict[datetime, float], 
    meter_date: datetime, 
    meter_kwh: float, 
    tz_local
) -> Tuple[float, str, str, bool]:
    """
    Calculate what the baseline sum should be at the first data point,
    given a known meter reading at a specific date/time.
    
    Args:
        by_hour: Dictionary of hourly energy consumption data
        meter_date: Date/time of the known meter reading
        meter_kwh: Known meter reading in kWh at that date/time
        tz_local: Local timezone
    
    Returns:
        Tuple of (calculated baseline sum, status, message, needs_future_update)
    """
    if not by_hour:
        return meter_kwh, "missing_data", "No consumption data available", False
    
    # Validate data availability first
    status, message, needs_update = validate_data_availability(by_hour, meter_date, tz_local)
    
    if status == "missing_data":
        return meter_kwh, status, message, needs_update
    
    # Sort the hours to find the data chronologically
    sorted_hours = sorted(by_hour.keys())
    first_hour = sorted_hours[0]
    
    # If meter reading is before our data, we can't calculate backwards
    if meter_date < first_hour:
        return meter_kwh, "complete", f"Meter reading date is before available data. Using meter reading as baseline.", False
    
    # Calculate total consumption from first data point to meter reading date
    # This will be accurate for available data, and incomplete for missing periods
    total_consumption = 0.0
    
    for hour in sorted_hours:
        if hour > meter_date:
            break
        total_consumption += by_hour[hour]
    
    # Work backwards: baseline = meter_reading - consumption_since_baseline
    baseline_sum = meter_kwh - total_consumption
    
    return max(0.0, baseline_sum), status, message, needs_update  # Ensure non-negative

def reset_baseline_from_meter_reading(config: Dict[str, Any], by_hour: Dict[datetime, float], tz_local) -> Tuple[float, datetime | None]:
    """
    Reset baseline using a known meter reading at a specific date/time.
    Always calculates with available data, even if incomplete.
    Provides guidance on when to re-run for better accuracy.
    
    Returns:
        Tuple of (baseline_sum, last_processed_timestamp)
    """
    meter_date_str = config.get(CONF_METER_READING_DATE)
    meter_kwh = config.get(CONF_METER_READING_KWH)
    
    if not meter_date_str or meter_kwh is None:
        print("Warning: Meter reading date and kWh must be provided for baseline calculation.")
        return 0.0, None
    
    try:
        # Parse the meter reading date
        meter_date = datetime.fromisoformat(meter_date_str).replace(tzinfo=tz_local)
        meter_kwh = float(meter_kwh)
        
        # Calculate baseline with data availability check
        baseline_sum, status, message, needs_update = calculate_baseline_from_meter_reading(by_hour, meter_date, meter_kwh, tz_local)
        
        # Print status messages based on data availability
        if status == "missing_data":
            print(f"❌ {message}")
            return 0.0, None
        elif status == "preliminary":
            print(f"⚠️ {message}")
            print(f"🔄 Baseline calculated: {baseline_sum:.3f} kWh (preliminary)")
            if needs_update:
                print(f"💡 Recommendation: Re-run this same service call in a few days for final accuracy")
        else:  # complete
            print(f"✅ {message}")
            print(f"✅ Baseline calculated: {baseline_sum:.3f} kWh (accurate)")
            
        print(f"📊 Meter reading: {meter_kwh} kWh at {meter_date.strftime('%Y-%m-%d %H:%M')}")
        
        # Find the last hour before or at the meter reading date
        last_processed = None
        for hour in sorted(by_hour.keys()):
            if hour <= meter_date:
                last_processed = hour
            else:
                break
        
        return baseline_sum, last_processed
        
    except Exception as e:
        print(f"❌ Error calculating baseline from meter reading: {e}")
        return 0.0, None

def _resolve_date_window(config: Dict[str, Any], tz_local):
    """Returns (start_date, end_date). end_date defaults to today local midnight."""
    now_local = datetime.now(tz_local)
    # end_date
    end_date = config.get(CONF_END_DATE)
    if isinstance(end_date, str) and end_date:
        end_date = datetime.fromisoformat(end_date).replace(tzinfo=tz_local)
    if not end_date:
        end_date = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
    # start_date
    start_date = config.get(CONF_START_DATE)
    if isinstance(start_date, str) and start_date:
        start_date = datetime.fromisoformat(start_date).replace(tzinfo=tz_local)
    elif config.get(CONF_FULL_HISTORY):
        start_date = datetime(2000, 1, 1, tzinfo=tz_local)
    else:
        start_date = datetime(now_local.year, 1, 1, tzinfo=tz_local)
    return start_date, end_date

def fetch_energy_data(config: Dict[str, Any]) -> List[Dict[str, Any]]:
    timezone_name = config.get(CONF_TIMEZONE, "America/Toronto")
    tz_local = tz.gettz(timezone_name)

    # Resolve time window
    start_date, end_date = _resolve_date_window(config, tz_local)
    start_str = start_date.strftime("%Y-%m-%d")
    end_str = end_date.strftime("%Y-%m-%d")
    tz_encoded = quote(timezone_name)

    sess = requests.Session()
    token = login_and_get_token(
        sess,
        config[CONF_USERNAME],
        config[CONF_PASSWORD],
        NT_POWER_PORTAL_ORIGIN,
        f"{config.get(CONF_BASE_URL, 'https://myaccountapi.ntpower.lhsharedservices.com')}/iamapi/iamapi/login",
    )
    url = usage_url(
        config.get(CONF_BASE_URL, "https://myaccountapi.ntpower.lhsharedservices.com"),
        config[CONF_ACCOUNT_ID],
        config[CONF_SERVICE_ID],
        start_str,
        end_str,
        tz_encoded,
    )
    headers = {
        "accept": "application/json,text/csv",
        "origin": NT_POWER_PORTAL_ORIGIN,
        "referer": f"{NT_POWER_PORTAL_ORIGIN}/",
        "x-requested-with": "XMLHttpRequest",
        "user-agent": "Mozilla/5.0",
        "authorization": f"Bearer {token}",
    }
    r = sess.get(url, headers=headers, timeout=120)
    r.raise_for_status()

    raw = r.text.strip()
    raw_path = (
        "/config/ntpower_data/ntpower_raw_response.json"
        if raw.startswith("{") or raw.startswith("[")
        else "/config/ntpower_data/ntpower_raw_response.csv"
    )
    Path(raw_path).parent.mkdir(parents=True, exist_ok=True)
    Path(raw_path).write_text(raw, encoding="utf-8")

    # Parse input
    points: List[Tuple[datetime, float]] = []
    if raw.startswith("{") or raw.startswith("["):
        parse_json_data(raw, points, tz_local)
    else:
        parse_csv_data(raw, points, tz_local)
    by_hour = aggregate_points(points, config.get("fill_missing", False), tz_local)

    # Baseline / persistence
    statistic_id = config.get(CONF_STATISTIC_ID, "sensor:ntpower_energy_export")
    state_store = config.get(CONF_STATE_STORE, BASELINE_DEFAULT_PATH)
    reset_baseline = bool(config.get(CONF_RESET_BASELINE, False))
    recalculate_from_meter = bool(config.get(CONF_RECALCULATE_FROM_METER, False))
    explicit_initial = config.get(CONF_INITIAL_SUM)

    if reset_baseline:
        baseline_sum, last_ts = 0.0, None
    elif recalculate_from_meter:
        # Use meter reading to calculate baseline
        baseline_sum, last_ts = reset_baseline_from_meter_reading(config, by_hour, tz_local)
        # Save this new baseline
        if last_ts is not None:
            _save_baseline(state_store, statistic_id, baseline_sum, last_ts)
    else:
        baseline_sum, last_ts = _load_baseline(state_store, statistic_id)

    if last_ts is None and explicit_initial is not None:
        try:
            baseline_sum = float(explicit_initial)
        except Exception:
            pass

    if last_ts is None and config.get(CONF_CONTINUE_FROM_TSV):
        try:
            p = Path(config[CONF_CONTINUE_FROM_TSV])
            if p.exists():
                lines = p.read_text(encoding="utf-8").splitlines()
                for line in reversed(lines[1:]):
                    parts = line.split("\t")
                    if len(parts) >= 5:
                        last_ts_str = parts[2]  # start
                        last_sum_str = parts[4]  # sum
                        last_ts = datetime.strptime(last_ts_str, "%d.%m.%Y %H:%M").replace(tzinfo=tz_local)
                        baseline_sum = float(last_sum_str)
                        break
        except Exception:
            pass

    # Build output rows
    output: List[Dict[str, Any]] = []
    running = float(baseline_sum)
    max_processed_ts = last_ts

    for hour in sorted(by_hour):
        # If recalculating from meter reading, include all data points
        # Otherwise, skip data points we've already processed
        if not recalculate_from_meter and last_ts is not None and hour <= last_ts:
            continue
            
        hourly = round(by_hour[hour], 3)
        
        # Add the hourly consumption to running total
        running += hourly
        
        output.append({
            "timestamp": hour.isoformat(),
            "state": hourly,
            "sum": round(running, 3),
        })
        max_processed_ts = hour

    if max_processed_ts is not None and (last_ts is None or max_processed_ts > last_ts):
        _save_baseline(state_store, statistic_id, running, max_processed_ts)

    return output

def write_tsv(points: List[Dict[str, Any]], statistic_id: str, unit: str, path: str):
    lines = ["statistic_id\tunit\tstart\tstate\tsum"]
    for row in points:
        t = datetime.fromisoformat(row["timestamp"]).strftime("%d.%m.%Y %H:00")
        state = f"{row['state']:.3f}"
        sumv  = f"{row.get('sum', 0.0):.3f}"
        lines.append(f"{statistic_id}\t{unit}\t{t}\t{state}\t{sumv}")
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text("\n".join(lines), encoding="utf-8")

def fetch_energy_and_write(config: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Fetch data and write TSV; returns the list of points written."""
    output = fetch_energy_data(config)
    tsv_path = "/config/ntpower_data/counterdata.tsv"
    write_tsv(
        output,
        config.get(CONF_STATISTIC_ID, "sensor:ntpower_energy_export"),
        config.get(CONF_UNIT, "kWh"),
        tsv_path,
    )
    return output
