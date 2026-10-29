# backend/live/rail_api.py
import os, requests
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

API_KEY  = os.getenv("RAIL_RADAR_API_KEY", "")
BASE_URL = os.getenv("RAIL_RADAR_BASE_URL", "https://api.railradar.in/api/v1")
HEADERS  = {"X-API-Key": API_KEY}

# Key stations to monitor for live cascade triggers
_stations_env = os.getenv("MONITOR_STATIONS", "NDLS,CNB,HWH,CSTM,MAS,ADI,SC")
MONITOR_STATIONS = [s.strip().upper() for s in _stations_env.split(",") if s.strip()]

def _parse_delay_hhmm(delay_str):
    """
    '01:36' → 96 minutes
    '00:33' → 33 minutes
    'On Time' or '' → 0
    """
    try:
        if not delay_str or delay_str.strip().lower() in ["on time", "", "-"]:
            return 0
        parts = delay_str.strip().split(":")
        if len(parts) == 2:
            return int(parts[0]) * 60 + int(parts[1])
        return 0
    except Exception:
        return 0

def get_station_live(station_code: str):
    """Live arrivals/departures at a station — this is our primary data source"""
    url = f"{BASE_URL}/stations/{station_code.upper()}/live"
    try:
        print(f"📡 [LIVE API] Requesting: {url}")
        r = requests.get(url, headers=HEADERS, timeout=10)
        print(f"🟢 [LIVE API] Response {r.status_code} for {station_code.upper()}")
        r.raise_for_status()
        return r.json()
    except requests.Timeout:
        print(f"🔴 [LIVE API] Timeout for {station_code.upper()}")
        return {"error": "timeout", "station": station_code}
    except Exception as e:
        print(f"🔴 [LIVE API] Error for {station_code.upper()}: {e}")
        return {"error": str(e), "station": station_code}

def get_delayed_trains_at_station(station_code: str):
    """
    Parse station board and extract all delayed trains with delay in minutes.
    Returns list of delay alerts ready to trigger cascade model.
    """
    data = get_station_live(station_code)
    if "error" in data:
        return []

    alerts = []
    trains = data.get("data", {}).get("trains", [])

    for entry in trains:
        # Skip cancelled or diverted
        status = entry.get("status", {})
        if status.get("isCancelled") or status.get("isDiverted"):
            continue

        live = entry.get("live", {})
        arr_delay = _parse_delay_hhmm(live.get("arrivalDelayDisplay", ""))
        dep_delay = _parse_delay_hhmm(live.get("departureDelayDisplay", ""))
        delay = max(arr_delay, dep_delay)

        if delay > 15:  # only meaningful delays
            train_info = entry.get("train", {})
            alerts.append({
                "train_number":    train_info.get("number"),
                "train_name":      train_info.get("name"),
                "train_type":      train_info.get("type"),
                "at_station":      station_code.upper(),
                "delay_minutes":   delay,
                "arrival_delay":   arr_delay,
                "departure_delay": dep_delay,
                "platform":        entry.get("platform"),
                "scheduled_arr":   entry.get("schedule", {}).get("arrival"),
                "scheduled_dep":   entry.get("schedule", {}).get("departure"),
                "severity": (
                    "CRITICAL" if delay > 120 else
                    "HIGH"     if delay > 60  else
                    "MEDIUM"
                ),
            })

    return sorted(alerts, key=lambda x: -x["delay_minutes"])

def get_all_live_delays(stations: list = None):
    """
    Fetch live delays across multiple key stations.
    Deduplicates trains appearing at multiple stations.
    """
    stations  = stations or MONITOR_STATIONS
    all_alerts = []
    seen_trains = set()

    for station in stations:
        alerts = get_delayed_trains_at_station(station)
        for alert in alerts:
            train_no = alert["train_number"]
            if train_no and train_no not in seen_trains:
                seen_trains.add(train_no)
                all_alerts.append(alert)

    return {
        "fetched_at":   datetime.now().strftime("%H:%M:%S"),
        "stations_checked": stations,
        "total_delayed": len(all_alerts),
        "alerts": sorted(all_alerts, key=lambda x: -x["delay_minutes"]),
    }

def get_station_board_summary(station_code: str):
    """
    Clean summary of station board — total trains, on-time %, delayed count.
    For dashboard Tab 1 station info panel.
    """
    data = get_station_live(station_code)
    if "error" in data:
        return data

    trains     = data.get("data", {}).get("trains", [])
    total      = len(trains)
    delayed    = 0
    cancelled  = 0
    on_time    = 0
    max_delay  = 0
    worst_train = None

    for entry in trains:
        status = entry.get("status", {})
        if status.get("isCancelled"):
            cancelled += 1
            continue
        live  = entry.get("live", {})
        delay = max(
            _parse_delay_hhmm(live.get("arrivalDelayDisplay", "")),
            _parse_delay_hhmm(live.get("departureDelayDisplay", ""))
        )
        if delay > 15:
            delayed += 1
            if delay > max_delay:
                max_delay   = delay
                worst_train = entry.get("train", {}).get("name")
        else:
            on_time += 1

    return {
        "station":       station_code.upper(),
        "total_trains":  total,
        "on_time":       on_time,
        "delayed":       delayed,
        "cancelled":     cancelled,
        "on_time_pct":   round(on_time / total * 100, 1) if total else 0,
        "max_delay_min": max_delay,
        "worst_train":   worst_train,
        "congestion_level": (
            "CRITICAL" if delayed > 10 else
            "HIGH"     if delayed > 5  else
            "MEDIUM"   if delayed > 2  else
            "LOW"
        ),
    }