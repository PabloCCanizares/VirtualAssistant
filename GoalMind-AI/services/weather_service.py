from __future__ import annotations

import json
import os
from datetime import date, datetime, timedelta
from urllib.parse import urlencode
from urllib.request import urlopen

from model.daily_metric_model import DailyMetricModel


ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
DAILY_VARIABLES = (
    "weather_code",
    "temperature_2m_mean",
    "temperature_2m_max",
    "temperature_2m_min",
    "apparent_temperature_mean",
    "precipitation_sum",
    "precipitation_hours",
    "wind_speed_10m_max",
    "shortwave_radiation_sum",
    "sunshine_duration",
    "cloud_cover_mean",
)


def _date_key(value) -> str:
    return DailyMetricModel.normalize_date(value)


def _parse_date(value) -> date:
    return datetime.strptime(_date_key(value), "%Y-%m-%d").date()


def _daterange(start: date, end: date) -> list[date]:
    if end < start:
        start, end = end, start
    days = []
    current = start
    while current <= end:
        days.append(current)
        current += timedelta(days=1)
    return days


def _weather_config() -> dict:
    return {
        "enabled": (os.getenv("WEATHER_ENABLED") or "1").strip().lower()
        not in {"0", "false", "no", "off"},
        "latitude": float(os.getenv("WEATHER_LATITUDE") or "40.4168"),
        "longitude": float(os.getenv("WEATHER_LONGITUDE") or "-3.7038"),
        "location_name": os.getenv("WEATHER_LOCATION_NAME") or "Madrid",
        "timezone": os.getenv("WEATHER_TIMEZONE") or "Europe/Madrid",
        "timeout": float(os.getenv("WEATHER_TIMEOUT_SECONDS") or "4"),
    }


def _request_json(url: str, params: dict, timeout: float) -> dict:
    full_url = f"{url}?{urlencode(params)}"
    with urlopen(full_url, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _value_at(daily: dict, key: str, index: int):
    values = daily.get(key) or []
    if index >= len(values):
        return None
    return values[index]


def _records_from_response(payload: dict, *, kind: str, config: dict) -> list[dict]:
    daily = payload.get("daily") or {}
    dates = daily.get("time") or []
    records = []
    for index, day in enumerate(dates):
        record = {
            "date": day,
            "weather_kind": kind,
            "weather_model": "open-meteo",
            "weather_location_name": config["location_name"],
            "weather_latitude": config["latitude"],
            "weather_longitude": config["longitude"],
            "weather_timezone": config["timezone"],
        }
        for variable in DAILY_VARIABLES:
            record[variable] = _value_at(daily, variable, index)
        records.append(record)
    return records


def _fetch_segment(start: date, end: date, *, kind: str, config: dict) -> list[dict]:
    endpoint = ARCHIVE_URL if kind == "observed" else FORECAST_URL
    params = {
        "latitude": config["latitude"],
        "longitude": config["longitude"],
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "daily": ",".join(DAILY_VARIABLES),
        "timezone": config["timezone"],
        "temperature_unit": "celsius",
        "wind_speed_unit": "kmh",
        "precipitation_unit": "mm",
    }
    payload = _request_json(endpoint, params, config["timeout"])
    return _records_from_response(payload, kind=kind, config=config)


def fetch_weather_range(start_date, end_date) -> list[dict]:
    config = _weather_config()
    if not config["enabled"]:
        return []

    start = _parse_date(start_date)
    end = _parse_date(end_date)
    if end < start:
        start, end = end, start

    today = date.today()
    records: list[dict] = []
    if start < today:
        observed_end = min(end, today - timedelta(days=1))
        if observed_end >= start:
            records.extend(_fetch_segment(start, observed_end, kind="observed", config=config))
    if end >= today:
        forecast_start = max(start, today)
        records.extend(_fetch_segment(forecast_start, end, kind="forecast", config=config))
    return records


def _weather_stale(metric: dict | None, day: date, *, now: datetime) -> bool:
    if not metric or not metric.get("weather_fetched_at"):
        return True
    if metric.get("weather_temp_max_c") is None or metric.get("weather_temp_min_c") is None:
        return True
    if metric.get("weather_kind") == "forecast":
        if day < now.date():
            return True
        fetched = metric.get("weather_fetched_at")
        if isinstance(fetched, datetime):
            return now - fetched > timedelta(hours=6)
    return False


def _ranges_from_days(days: list[date]) -> list[tuple[date, date]]:
    if not days:
        return []
    ordered = sorted(set(days))
    ranges = []
    start = prev = ordered[0]
    for day in ordered[1:]:
        if day == prev + timedelta(days=1):
            prev = day
            continue
        ranges.append((start, prev))
        start = prev = day
    ranges.append((start, prev))
    return ranges


def ensure_weather_for_range(start_date, end_date, usuario_id=None) -> dict:
    config = _weather_config()
    if not config["enabled"]:
        return {"updated": 0, "errors": [], "enabled": False}

    start = _parse_date(start_date)
    end = _parse_date(end_date)
    if end < start:
        start, end = end, start

    existing = {
        metric.get("date"): metric
        for metric in DailyMetricModel.get_range(start.isoformat(), end.isoformat(), usuario_id=usuario_id)
    }
    now = datetime.utcnow()
    missing_or_stale = [
        day
        for day in _daterange(start, end)
        if _weather_stale(existing.get(day.isoformat()), day, now=now)
    ]

    updated = 0
    errors = []
    for range_start, range_end in _ranges_from_days(missing_or_stale):
        try:
            records = fetch_weather_range(range_start, range_end)
        except Exception as exc:
            errors.append(str(exc))
            continue
        for record in records:
            day = record.pop("date", None)
            if not day:
                continue
            DailyMetricModel.upsert_weather(day, record, usuario_id=usuario_id)
            updated += 1

    return {"updated": updated, "errors": errors, "enabled": True}
