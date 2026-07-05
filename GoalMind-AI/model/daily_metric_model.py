from datetime import date, datetime

from bson import ObjectId

from database.mongo_conn import get_app_user_id, get_collection, sync_from_remote, sync_to_remote


def _uid_filter(usuario_id):
    uid = usuario_id or get_app_user_id()
    conditions = [{"usuario_id": uid}]
    try:
        if ObjectId.is_valid(str(uid)):
            conditions.append({"usuario_id": ObjectId(str(uid))})
    except Exception:
        pass
    return {"$or": conditions} if len(conditions) > 1 else conditions[0]


def _date_key(value):
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    raw = str(value or "").strip()
    if not raw:
        raise ValueError("Fecha vacia.")
    try:
        return datetime.strptime(raw[:10], "%Y-%m-%d").date().isoformat()
    except Exception as exc:
        raise ValueError("Fecha invalida. Usa YYYY-MM-DD.") from exc


def _normalize_sleep_hours(value):
    if value in (None, ""):
        return None
    try:
        hours = float(str(value).replace(",", "."))
    except Exception as exc:
        raise ValueError("Horas de sueno invalidas.") from exc
    if hours < 0 or hours > 24:
        raise ValueError("Las horas de sueno deben estar entre 0 y 24.")
    return round(hours, 2)


MOOD_LABELS = {
    1: "muy_bajo",
    2: "bajo",
    3: "neutro",
    4: "bueno",
    5: "muy_bueno",
}


def _normalize_mood_score(value):
    if value in (None, ""):
        return None
    try:
        score = int(value)
    except Exception as exc:
        raise ValueError("Animo invalido.") from exc
    if score not in MOOD_LABELS:
        raise ValueError("El animo debe estar entre 1 y 5.")
    return score


WEATHER_CODE_LABELS = {
    0: "despejado",
    1: "casi_despejado",
    2: "parcialmente_nublado",
    3: "cubierto",
    45: "niebla",
    48: "niebla_escarcha",
    51: "llovizna_suave",
    53: "llovizna",
    55: "llovizna_intensa",
    56: "llovizna_helada_suave",
    57: "llovizna_helada_intensa",
    61: "lluvia_suave",
    63: "lluvia",
    65: "lluvia_intensa",
    66: "lluvia_helada_suave",
    67: "lluvia_helada_intensa",
    71: "nieve_suave",
    73: "nieve",
    75: "nieve_intensa",
    77: "granizo_nieve",
    80: "chubascos_suaves",
    81: "chubascos",
    82: "chubascos_intensos",
    85: "chubascos_nieve_suaves",
    86: "chubascos_nieve_intensos",
    95: "tormenta",
    96: "tormenta_granizo_suave",
    99: "tormenta_granizo_intenso",
}


class DailyMetricModel:
    """Metricas diarias del usuario, separadas de eventos de agenda."""

    COLLECTION = "DailyMetrics"

    @staticmethod
    def normalize_date(value):
        return _date_key(value)

    @staticmethod
    def get_by_date(metric_date, usuario_id=None):
        local_col, _ = get_collection(DailyMetricModel.COLLECTION)
        day = _date_key(metric_date)
        query = {"$and": [{"date": day}, _uid_filter(usuario_id)]}
        metric = local_col.find_one(query)
        if not metric:
            sync_from_remote(DailyMetricModel.COLLECTION, {"date": day})
            metric = local_col.find_one(query)
        return metric

    @staticmethod
    def get_range(start_date, end_date, usuario_id=None):
        local_col, _ = get_collection(DailyMetricModel.COLLECTION)
        start = _date_key(start_date)
        end = _date_key(end_date)
        if end < start:
            start, end = end, start
        query = {
            "$and": [
                {"date": {"$gte": start, "$lte": end}},
                _uid_filter(usuario_id),
            ]
        }
        return list(local_col.find(query).sort("date", 1))

    @staticmethod
    def get_recent(limit=14, usuario_id=None):
        local_col, _ = get_collection(DailyMetricModel.COLLECTION)
        safe_limit = max(1, min(int(limit or 14), 90))
        return list(local_col.find(_uid_filter(usuario_id)).sort("date", -1).limit(safe_limit))

    @staticmethod
    def upsert_sleep(metric_date, sleep_hours, source="manual", usuario_id=None):
        local_col, _ = get_collection(DailyMetricModel.COLLECTION)
        uid = usuario_id or get_app_user_id()
        day = _date_key(metric_date)
        hours = _normalize_sleep_hours(sleep_hours)
        now = datetime.utcnow()
        existing = DailyMetricModel.get_by_date(day, usuario_id=uid)
        source_value = (source or "manual").strip().lower() or "manual"

        updates = {
            "date": day,
            "usuario_id": uid,
            "sleep_hours": hours,
            "sleep_source": source_value,
            "sleep_unit": "hours",
            "updated_at": now,
        }

        if existing:
            local_col.update_one({"_id": existing["_id"]}, {"$set": updates})
            metric = local_col.find_one({"_id": existing["_id"]})
        else:
            metric = {**updates, "created_at": now}
            result = local_col.insert_one(metric)
            metric["_id"] = result.inserted_id

        sync_to_remote(DailyMetricModel.COLLECTION, metric)
        return metric

    @staticmethod
    def upsert_mood(metric_date, mood_score, source="manual", usuario_id=None):
        local_col, _ = get_collection(DailyMetricModel.COLLECTION)
        uid = usuario_id or get_app_user_id()
        day = _date_key(metric_date)
        score = _normalize_mood_score(mood_score)
        now = datetime.utcnow()
        existing = DailyMetricModel.get_by_date(day, usuario_id=uid)
        source_value = (source or "manual").strip().lower() or "manual"

        updates = {
            "date": day,
            "usuario_id": uid,
            "mood_score": score,
            "mood_label": MOOD_LABELS.get(score) if score is not None else None,
            "mood_source": source_value,
            "updated_at": now,
        }

        if existing:
            local_col.update_one({"_id": existing["_id"]}, {"$set": updates})
            metric = local_col.find_one({"_id": existing["_id"]})
        else:
            metric = {**updates, "created_at": now}
            result = local_col.insert_one(metric)
            metric["_id"] = result.inserted_id

        sync_to_remote(DailyMetricModel.COLLECTION, metric)
        return metric

    @staticmethod
    def upsert_weather(metric_date, weather_data, source="open-meteo", usuario_id=None):
        local_col, _ = get_collection(DailyMetricModel.COLLECTION)
        uid = usuario_id or get_app_user_id()
        day = _date_key(metric_date)
        now = datetime.utcnow()
        existing = DailyMetricModel.get_by_date(day, usuario_id=uid)
        payload = dict(weather_data or {})

        code = payload.get("weather_code")
        try:
            code = int(code) if code is not None else None
        except Exception:
            code = None

        updates = {
            "date": day,
            "usuario_id": uid,
            "weather_source": (source or "open-meteo").strip().lower() or "open-meteo",
            "weather_fetched_at": now,
        }
        if code is not None:
            updates["weather_code"] = code
            updates["weather_label"] = WEATHER_CODE_LABELS.get(code, "desconocido")

        field_map = {
            "temperature_2m_mean": "weather_temp_mean_c",
            "temperature_2m_max": "weather_temp_max_c",
            "temperature_2m_min": "weather_temp_min_c",
            "apparent_temperature_mean": "weather_apparent_temp_mean_c",
            "precipitation_sum": "weather_precipitation_mm",
            "precipitation_hours": "weather_precipitation_hours",
            "wind_speed_10m_max": "weather_wind_speed_max_kmh",
            "shortwave_radiation_sum": "weather_shortwave_radiation_mj_m2",
            "sunshine_duration": "weather_sunshine_seconds",
            "cloud_cover_mean": "weather_cloud_cover_mean_pct",
        }
        for source_key, target_key in field_map.items():
            if source_key in payload:
                updates[target_key] = payload.get(source_key)

        for key in (
            "weather_kind",
            "weather_model",
            "weather_location_name",
            "weather_latitude",
            "weather_longitude",
            "weather_timezone",
        ):
            if key in payload:
                updates[key] = payload.get(key)

        if existing:
            local_col.update_one({"_id": existing["_id"]}, {"$set": updates})
            metric = local_col.find_one({"_id": existing["_id"]})
        else:
            metric = {**updates, "created_at": now}
            result = local_col.insert_one(metric)
            metric["_id"] = result.inserted_id

        sync_to_remote(DailyMetricModel.COLLECTION, metric)
        return metric
