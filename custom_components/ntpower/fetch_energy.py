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
    CONF_STATISTIC_ID, CONF_UNIT, CONF_TIMEZONE, CONF_BASE_URL, CONF_PORTAL_ORIGIN,
    CONF_START_DATE, CONF_END_DATE, CONF_INITIAL_SUM, CONF_FULL_HISTORY,
    CONF_STATE_STORE, CONF_RESET_BASELINE, CONF_CONTINUE_FROM_TSV,
)

BASELINE_DEFAULT_PATH = "/config/ntpower_data/stat_import_state.json"

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
        config.get(CONF_PORTAL_ORIGIN, "https://myaccount.ntpower.ca"),
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
        "origin": config.get(CONF_PORTAL_ORIGIN, "https://myaccount.ntpower.ca"),
        "referer": f"{config.get(CONF_PORTAL_ORIGIN, 'https://myaccount.ntpower.ca')}/",
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
    explicit_initial = config.get(CONF_INITIAL_SUM)

    if reset_baseline:
        baseline_sum, last_ts = 0.0, None
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
