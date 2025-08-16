import re
import io
import csv
import json
import requests
from datetime import datetime, timedelta
from collections import defaultdict
from dateutil import tz
from urllib.parse import quote
from pathlib import Path

# NEW: persistence of last processed timestamp & cumulative sum
BASELINE_DEFAULT_PATH = "/config/ntpower_data/stat_import_state.json"

UUID_RE = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
JWT_RE = re.compile(r"^[A-Za-z0-9-_]+\.[A-Za-z0-9-_]+\.[A-Za-z0-9-_]+$")

def looks_like_bearer(val: str) -> bool:
    if not val:
        return False
    v = val.strip().strip('"').strip("'")
    return bool(UUID_RE.match(v) or JWT_RE.match(v))

def login_and_get_token(sess, username, password, portal_origin, login_url):
    data = {
        "username": username,
        "password": password,
        "client_id": "iam",
    }
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
    token = (obj.get('access_token') or obj.get('token') or '').strip()
    if not looks_like_bearer(token):
        token = next((v for v in obj.values() if isinstance(v, str) and looks_like_bearer(v)), None)
    if not looks_like_bearer(token):
        raise RuntimeError("Token not found in login response")
    return token

def usage_url(base_url, account_id, service_id, start_str, end_str, tz_encoded):
    return (
        f"{base_url}/usageapi/energy/account/{account_id}/service/{service_id}"
        f"/usageDownload?startDate={start_str}&endDate={end_str}&generation=false&tz={tz_encoded}"
    )

def parse_json_data(data, points, tz_local):
    """
    Accepts multiple JSON shapes:
      - [ { "intervalReadings": [ { "startTime": "...", "value": ... }, ... ] }, ... ]
      - { "data": [ ...same as above... ] }
      - Flat lists/dicts with startTime + (kwh | quantity | value)
    """
    def add_point(ts, val):
        if not ts or val is None:
            return
        try:
            # supports "Z" and "-05:00" offsets
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

def parse_csv_data(data, points, tz_local):
    reader = csv.reader(io.StringIO(data))
    for row in reader:
        if len(row) < 2 or not row[0] or not row[1]:
            continue
        try:
            # Example: "2024/01/01 00:00 to 2024/01/01 01:00"
            dt = datetime.strptime(row[0].split(" to ")[0], "%Y/%m/%d %H:%M")
            points.append((dt.replace(tzinfo=tz_local), float(row[1])))
        except:
            pass

def aggregate_points(points, fill_missing, tz_local):
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

# ---------- NEW: Baseline persistence helpers ----------

def _load_baseline(path: str, statistic_id: str):
    """
    Returns (last_sum, last_ts or None).
    last_ts is timezone-aware ISO8601 string in file, converted back to datetime.
    """
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
        # Don't crash the run if state saving fails
        pass

# ---------- MAIN FETCH/BUILD ----------

def fetch_energy_data(config: dict) -> list[dict]:
    """
    Returns list of dicts:
      - timestamp: ISO8601 (hour start, tz-aware)
      - state: hourly kWh from source
      - sum: cumulative total BEFORE this hour (monotonic, used by HA)
    """
    timezone_name = config["timezone"]
    tz_local = tz.gettz(timezone_name)

    now_local = datetime.now(tz_local)
    start_date = datetime(now_local.year, 1, 1, tzinfo=tz_local)
    end_date = now_local.replace(hour=0, minute=0, second=0, microsecond=0)

    start_str = start_date.strftime("%Y-%m-%d")
    end_str = end_date.strftime("%Y-%m-%d")
    tz_encoded = quote(timezone_name)

    sess = requests.Session()
    token = login_and_get_token(
        sess,
        config["username"],
        config["password"],
        config["portal_origin"],
        f"{config['base_url']}/iamapi/iamapi/login"
    )
    url = usage_url(
        config["base_url"], config["account_id"], config["service_id"],
        start_str, end_str, tz_encoded
    )
    headers = {
        "accept": "application/json,text/csv",
        "origin": config["portal_origin"],
        "referer": f"{config['portal_origin']}/",
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

    # Parse ? aggregate hourly
    points = []
    if raw.startswith("{") or raw.startswith("["):
        parse_json_data(raw, points, tz_local)
    else:
        parse_csv_data(raw, points, tz_local)
    by_hour = aggregate_points(points, config.get("fill_missing", False), tz_local)

    # Determine baseline persistence
    statistic_id = config.get("statistic_id", "sensor:ntpower_energy_export")
    state_store = config.get("state_store", BASELINE_DEFAULT_PATH)
    reset_baseline = bool(config.get("reset_baseline", False))

    if reset_baseline:
        baseline_sum, last_ts = 0.0, None
    else:
        baseline_sum, last_ts = _load_baseline(state_store, statistic_id)

    # Optionally continue from an existing TSV (one-time migration)
    if last_ts is None and config.get("continue_from_tsv"):
        try:
            p = Path(config["continue_from_tsv"])
            if p.exists():
                # read last non-header line
                lines = p.read_text(encoding="utf-8").splitlines()
                for line in reversed(lines[1:]):
                    parts = line.split("\t")
                    if len(parts) >= 5:
                        # start is DD.MM.YYYY HH:MM, sum is 5th col
                        last_ts_str = parts[2]  # start
                        last_sum_str = parts[4]  # sum
                        last_ts = datetime.strptime(last_ts_str, "%d.%m.%Y %H:%M").replace(tzinfo=tz_local)
                        baseline_sum = float(last_sum_str)
                        break
        except Exception:
            pass

    # Build output: keep hourly in state; sum is total BEFORE this hour.
    output = []
    running = float(baseline_sum)
    max_processed_ts = last_ts

    for hour in sorted(by_hour):
        # Skip any hour we've already emitted (prevents dupes across runs)
        if last_ts is not None and hour <= last_ts:
            continue
        hourly = round(by_hour[hour], 3)

        output.append({
            "timestamp": hour.isoformat(),
            "state": hourly,
            "sum": round(running, 3),
        })
        running += hourly
        max_processed_ts = hour

    # Persist new baseline (only if we actually added new rows)
    if max_processed_ts is not None and (last_ts is None or max_processed_ts > last_ts):
        _save_baseline(state_store, statistic_id, running, max_processed_ts)

    return output

def write_tsv(points: list[dict], statistic_id: str, unit: str, path: str):
    """
    TSV header: statistic_id, unit, start, state, sum
      - state: hourly usage (kWh)
      - sum: cumulative total BEFORE the hour (monotonic)
    """
    lines = ["statistic_id\tunit\tstart\tstate\tsum"]
    for row in points:
        t = datetime.fromisoformat(row["timestamp"]).strftime("%d.%m.%Y %H:00")
        state = f"{row['state']:.3f}"
        sumv  = f"{row.get('sum', 0.0):.3f}"
        lines.append(f"{statistic_id}\t{unit}\t{t}\t{state}\t{sumv}")
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text("\n".join(lines), encoding="utf-8")

def fetch_energy_and_write(config: dict):
    """
    Typical config:
      {
        "username": "...",
        "password": "...",
        "base_url": "https://myaccountapi.ntpower.lhsharedservices.com",
        "portal_origin": "https://myaccount.ntpower.ca",
        "account_id": "...",
        "service_id": "...",
        "timezone": "America/Toronto",
        "statistic_id": "sensor:ntpower_energy_export",
        "unit": "kWh",
        "fill_missing": false,

        # Optional:
        "state_store": "/config/ntpower_data/stat_import_state.json",
        "reset_baseline": false,
        "continue_from_tsv": "/config/ntpower_data/previous_counterdata.tsv"
      }
    """
    output = fetch_energy_data(config)
    tsv_path = "/config/ntpower_data/counterdata.tsv"
    write_tsv(
        output,
        config.get("statistic_id", "sensor:ntpower_energy_export"),
        config.get("unit", "kWh"),
        tsv_path
    )
    return output
