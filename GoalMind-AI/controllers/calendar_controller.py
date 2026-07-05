# controllers/calendar_controller.py
from flask import Blueprint, render_template, request, jsonify
from bson import ObjectId
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
import unicodedata

from model.task_model import TaskModel
from model.goal_model import GoalModel
from model.daily_metric_model import DailyMetricModel

from database.mongo_conn import (
    flush_deletion_queue,
    get_app_user_id,
    get_collection,
    queue_deletion,
)
from services.weather_service import ensure_weather_for_range

calendar_bp = Blueprint("calendar_bp", __name__)
DEFAULT_USER_ID = get_app_user_id()

# -----------------------------
# 🗓️ Página del calendario
# -----------------------------
@calendar_bp.route("/calendar", methods=["GET"])
def calendar_page():
    """Renderiza la vista del calendario."""
    return render_template("partials/calendar_templates/calendar_menu.html", page="calendar")

# -----------------------------
# 🔌 API de eventos
# -----------------------------
def _events_col() -> Tuple[Any, Any]:
    """Devuelve (local_collection, remote_collection) para 'Events'."""
    return get_collection("Events")

def _parse_iso(dt_str: Optional[str]) -> Optional[datetime]:
    """
    Parsea ISO 8601 y normaliza a UTC (aware).
    - Si viene con 'Z' u offset -> se convierte a UTC.
    - Si viene sin tz (naive) -> se asume UTC.
    """
    if not dt_str:
        return None
    try:
        # Soporta "Z" (UTC)
        d = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        # Asegura tz-aware
        if d.tzinfo is None:
            d = d.replace(tzinfo=timezone.utc)
        # Normaliza a UTC
        return d.astimezone(timezone.utc)
    except Exception:
        return None

def _iso_utc(dt: Optional[datetime]) -> Optional[str]:
    """Serializa siempre en ISO con offset UTC (+00:00)."""
    if not isinstance(dt, datetime):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()

def _validate_required(payload: Dict[str, Any], fields: List[str]) -> Optional[str]:
    missing = [f for f in fields if payload.get(f) in (None, "", [])]
    return f"Faltan campos obligatorios: {', '.join(missing)}" if missing else None


TIME_LAYER_DEFAULTS: Dict[str, Dict[str, Any]] = {
    "productivo": {
        "bloquea_disponibilidad": True,
        "cuenta_productivo": True,
        "cuenta_recuperacion": False,
        "carga_mental": "media",
        "carga_fisica": "baja",
    },
    "salud": {
        "bloquea_disponibilidad": True,
        "cuenta_productivo": False,
        "cuenta_recuperacion": True,
        "carga_mental": "baja",
        "carga_fisica": "media",
    },
    "sueno": {
        "bloquea_disponibilidad": True,
        "cuenta_productivo": False,
        "cuenta_recuperacion": True,
        "carga_mental": "baja",
        "carga_fisica": "baja",
    },
    "mantenimiento": {
        "bloquea_disponibilidad": True,
        "cuenta_productivo": False,
        "cuenta_recuperacion": False,
        "carga_mental": "baja",
        "carga_fisica": "baja",
    },
    "ocio": {
        "bloquea_disponibilidad": True,
        "cuenta_productivo": False,
        "cuenta_recuperacion": True,
        "carga_mental": "baja",
        "carga_fisica": "baja",
    },
    "social": {
        "bloquea_disponibilidad": True,
        "cuenta_productivo": False,
        "cuenta_recuperacion": True,
        "carga_mental": "baja",
        "carga_fisica": "baja",
    },
    "logistica": {
        "bloquea_disponibilidad": True,
        "cuenta_productivo": False,
        "cuenta_recuperacion": False,
        "carga_mental": "baja",
        "carga_fisica": "baja",
    },
}

TIME_LAYER_HINTS = {
    "trabajo": "productivo",
    "estudio": "productivo",
    "tarea": "productivo",
    "reunion": "productivo",
    "entrega": "productivo",
    "formacion": "productivo",
    "foco": "productivo",
    "deporte": "salud",
    "entreno": "salud",
    "gym": "salud",
    "salud": "salud",
    "medico": "salud",
    "terapia": "salud",
    "paseo": "salud",
    "dormir": "sueno",
    "sueno": "sueno",
    "siesta": "sueno",
    "descanso": "sueno",
    "comida": "mantenimiento",
    "comer": "mantenimiento",
    "cocinar": "mantenimiento",
    "compra": "mantenimiento",
    "limpieza": "mantenimiento",
    "recado": "mantenimiento",
    "ocio": "ocio",
    "cine": "ocio",
    "serie": "ocio",
    "lectura": "ocio",
    "hobby": "ocio",
    "social": "social",
    "familia": "social",
    "amigos": "social",
    "celebracion": "social",
    "transporte": "logistica",
    "desplazamiento": "logistica",
    "viaje": "logistica",
    "logistica": "logistica",
}


def _normalize_text(value: Any) -> str:
    text = str(value or "").strip().lower()
    text = unicodedata.normalize("NFKD", text)
    return "".join(char for char in text if not unicodedata.combining(char))


def _coerce_bool(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    normalized = _normalize_text(value)
    if normalized in {"1", "true", "si", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return default


def _infer_time_layer(payload: Dict[str, Any]) -> str:
    explicit = _normalize_text(
        payload.get("capa_tiempo")
        or payload.get("time_layer")
        or payload.get("categoria_tiempo")
    )
    if explicit in TIME_LAYER_DEFAULTS:
        return explicit

    haystack = " ".join(
        _normalize_text(payload.get(key))
        for key in ("tipo_evento", "titulo", "descripcion")
    )
    for hint, layer in TIME_LAYER_HINTS.items():
        if hint in haystack:
            return layer
    return "productivo"


def _time_layer_fields(payload: Dict[str, Any]) -> Dict[str, Any]:
    layer = _infer_time_layer(payload)
    defaults = TIME_LAYER_DEFAULTS[layer]
    return {
        "capa_tiempo": layer,
        "bloquea_disponibilidad": _coerce_bool(
            payload.get("bloquea_disponibilidad"),
            defaults["bloquea_disponibilidad"],
        ),
        "cuenta_productivo": _coerce_bool(
            payload.get("cuenta_productivo"),
            defaults["cuenta_productivo"],
        ),
        "cuenta_recuperacion": _coerce_bool(
            payload.get("cuenta_recuperacion"),
            defaults["cuenta_recuperacion"],
        ),
        "carga_mental": (
            _normalize_text(payload.get("carga_mental"))
            if _normalize_text(payload.get("carga_mental")) in {"baja", "media", "alta"}
            else defaults["carga_mental"]
        ),
        "carga_fisica": (
            _normalize_text(payload.get("carga_fisica"))
            if _normalize_text(payload.get("carga_fisica")) in {"baja", "media", "alta"}
            else defaults["carga_fisica"]
        ),
    }


def _apply_time_layer_defaults(event: Dict[str, Any]) -> Dict[str, Any]:
    event.update(_time_layer_fields(event))
    return event


def _serialize_daily_metric(metric: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(metric or {})
    if out.get("_id") is not None:
        out["_id"] = str(out["_id"])
    for key in ("id_usuario", "usuario_id"):
        if isinstance(out.get(key), ObjectId):
            out[key] = str(out[key])
    for key in ("created_at", "updated_at"):
        out[key] = _iso_utc(out.get(key))
    return out

def _sync_event_association(event_id, old_ref_id, old_ref_tipo, new_ref_id, new_ref_tipo):
    """
    Gestiona la sincronización bidireccional del array event_ids
    en tareas y objetivos cuando se crea, actualiza o elimina un evento.
    
    - Elimina event_id del array event_ids del item anterior (si lo había).
    - Añade event_id al array event_ids del nuevo item (si lo hay).
    """
    eid = str(event_id)

    # Desasociar del item anterior
    if old_ref_id and old_ref_tipo:
        try:
            if old_ref_tipo == "tarea":
                TaskModel.remove_event_from_task(str(old_ref_id), eid, usuario_id=DEFAULT_USER_ID)
            elif old_ref_tipo == "objetivo":
                GoalModel.remove_event_from_goal(str(old_ref_id), eid, usuario_id=DEFAULT_USER_ID)
        except Exception as e:
            print(f"Error al desasociar evento {eid} del {old_ref_tipo} {old_ref_id}: {e}")

    # Asociar al nuevo item
    if new_ref_id and new_ref_tipo:
        try:
            if new_ref_tipo == "tarea":
                TaskModel.add_event_to_task(str(new_ref_id), eid, usuario_id=DEFAULT_USER_ID)
            elif new_ref_tipo == "objetivo":
                GoalModel.add_event_to_goal(str(new_ref_id), eid, usuario_id=DEFAULT_USER_ID)
        except Exception as e:
            print(f"Error al asociar evento {eid} al {new_ref_tipo} {new_ref_id}: {e}")


def _should_create_task_from_event(doc: Dict[str, Any], ref_id: Any, ref_tipo: Optional[str]) -> bool:
    return bool(ref_id and ref_tipo == "objetivo" and _normalize_text(doc.get("tipo_evento")) == "tarea")


def _create_task_from_event(doc: Dict[str, Any], event_id: ObjectId, goal_id: ObjectId) -> Optional[Dict[str, Any]]:
    task_doc = {
        "contenido": doc.get("titulo") or "Nueva tarea",
        "descripcion": doc.get("descripcion") or "",
        "estado": "pendiente",
        "prioridad": "Media",
        "fecha_limite": doc.get("fecha_fin") or doc.get("fecha_inicio"),
        "objetivo_id": goal_id,
        "event_ids": [event_id],
        "usuario_id": DEFAULT_USER_ID,
    }
    task = TaskModel.insert_task(task_doc, usuario_id=DEFAULT_USER_ID)
    try:
        TaskModel.recalculate_goal_progress(goal_id, usuario_id=DEFAULT_USER_ID)
    except Exception as e:
        print(f"Error al recalcular progreso del objetivo {goal_id}: {e}")
    return task


@calendar_bp.route("/api/events", methods=["GET"])
def api_list_events():
    """
    Devuelve una lista de eventos en bruto (con las claves esperadas por el front).
    Si se proporcionan start y end (ISO), filtra por intersección de rango.
    Todas las fechas se devuelven en ISO con offset UTC (+00:00).
    Filtra por el usuario actual.
    """
    start_iso = request.args.get("start")
    end_iso = request.args.get("end")
    start_dt = _parse_iso(start_iso)
    end_dt = _parse_iso(end_iso)

    col, _ = _events_col()

    query: Dict[str, Any] = {}

    # Añadir filtro de usuario
    from model.event_model import _uid_filter
    query.update(_uid_filter(DEFAULT_USER_ID))

    if start_dt and end_dt:
        # Intersección: (inicio <= end) y (fin >= start)
        query = {
            "$and": [
                _uid_filter(DEFAULT_USER_ID),
                {"$or": [
                    {"fecha_inicio": {"$lte": end_dt}, "fecha_fin": {"$gte": start_dt}},
                    {"start": {"$lte": end_dt}, "end": {"$gte": start_dt}},
                ]}
            ]
        }
    elif start_dt:
        query = {"$and": [_uid_filter(DEFAULT_USER_ID), {"$or": [{"fecha_inicio": {"$gte": start_dt}}, {"start": {"$gte": start_dt}}]}]}
    elif end_dt:
        query = {"$and": [_uid_filter(DEFAULT_USER_ID), {"$or": [{"fecha_inicio": {"$lte": end_dt}}, {"start": {"$lte": end_dt}}]}]}

    docs = list(col.find(query).sort("fecha_inicio", 1))

    # Normalizamos para JSON: stringificamos ObjectId y datetimes a ISO (UTC)
    events: List[Dict[str, Any]] = []
    for d in docs:
        out = dict(d)
        out["_id"] = str(out.get("_id"))
        # Fechas → ISO UTC
        for key in ("fecha_inicio", "fecha_fin", "created_at", "updated_at", "start", "end"):
            out[key] = _iso_utc(out.get(key))
        # IDs relacionados → str (nuevos campos unificados)
        for key in ("id_usuario", "usuario_id", "referencia_id", "objetivo_id", "generated_task_id"):
            if isinstance(out.get(key), ObjectId):
                out[key] = str(out[key])
        # Compatibilidad: si el evento todavía tiene id_tarea/id_objetivo (datos antiguos)
        for key in ("id_objetivo", "id_tarea"):
            if isinstance(out.get(key), ObjectId):
                out[key] = str(out[key])
        events.append(_apply_time_layer_defaults(out))

    return jsonify(events)


@calendar_bp.route("/api/events/timeline", methods=["GET"])
def api_events_timeline():
    timeline_type = (request.args.get("type") or "upcoming").strip().lower()
    now = datetime.now(timezone.utc)
    col, _ = _events_col()

    from model.event_model import _uid_filter

    if timeline_type == "past":
        date_query = {"$or": [{"fecha_fin": {"$lt": now}}, {"end": {"$lt": now}}]}
        sort_dir = -1
    else:
        date_query = {"$or": [{"fecha_fin": {"$gte": now}}, {"end": {"$gte": now}}]}
        sort_dir = 1

    docs = list(col.find({"$and": [_uid_filter(DEFAULT_USER_ID), date_query]}).sort("fecha_inicio", sort_dir))
    events = []
    for d in docs:
        out = dict(d)
        out["_id"] = str(out.get("_id"))
        for key in ("fecha_inicio", "fecha_fin", "created_at", "updated_at", "start", "end"):
            out[key] = _iso_utc(out.get(key))
        for key in (
            "id_usuario",
            "usuario_id",
            "referencia_id",
            "id_objetivo",
            "id_tarea",
            "objetivo_id",
            "generated_task_id",
        ):
            if isinstance(out.get(key), ObjectId):
                out[key] = str(out[key])
        events.append(_apply_time_layer_defaults(out))
    return jsonify(events)


@calendar_bp.route("/api/daily-metrics", methods=["GET"])
def api_daily_metrics():
    """Devuelve metricas diarias del usuario para un rango YYYY-MM-DD."""
    start = (request.args.get("start") or "").strip()
    end = (request.args.get("end") or start).strip()
    if not start:
        return jsonify({"error": "Falta start en formato YYYY-MM-DD."}), 400

    try:
        include_weather = (request.args.get("weather") or "").strip().lower() in {"1", "true", "yes", "on"}
        if include_weather:
            ensure_weather_for_range(start, end, usuario_id=DEFAULT_USER_ID)
        metrics = DailyMetricModel.get_range(start, end, usuario_id=DEFAULT_USER_ID)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    return jsonify([_serialize_daily_metric(metric) for metric in metrics])


@calendar_bp.route("/api/daily-metrics/<date_key>/sleep", methods=["POST", "PUT", "PATCH"])
def api_upsert_sleep_metric(date_key: str):
    """Guarda horas de sueno del dia. El origen manual deja sitio a wearables."""
    payload = request.get_json(silent=True) or {}
    has_value = "sleep_hours" in payload or "hours" in payload
    if not has_value:
        return jsonify({"error": "Falta sleep_hours."}), 400

    raw_hours = payload.get("sleep_hours", payload.get("hours"))
    source = (payload.get("source") or "manual").strip().lower() or "manual"

    try:
        metric = DailyMetricModel.upsert_sleep(
            date_key,
            raw_hours,
            source=source,
            usuario_id=DEFAULT_USER_ID,
        )
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    return jsonify(_serialize_daily_metric(metric))


@calendar_bp.route("/api/daily-metrics/<date_key>/mood", methods=["POST", "PUT", "PATCH"])
def api_upsert_mood_metric(date_key: str):
    """Guarda el animo diario en escala 1-5."""
    payload = request.get_json(silent=True) or {}
    has_value = "mood_score" in payload or "score" in payload
    if not has_value:
        return jsonify({"error": "Falta mood_score."}), 400

    raw_score = payload.get("mood_score", payload.get("score"))
    source = (payload.get("source") or "manual").strip().lower() or "manual"

    try:
        metric = DailyMetricModel.upsert_mood(
            date_key,
            raw_score,
            source=source,
            usuario_id=DEFAULT_USER_ID,
        )
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    return jsonify(_serialize_daily_metric(metric))


@calendar_bp.route("/api/events", methods=["POST"])
def api_create_event():
    """
    Crea un evento. Espera JSON con:
    - Requeridos:  titulo, fecha_inicio (ISO), fecha_fin (ISO)
    - Opcionales:  descripcion, tipo_evento, referencia_id, referencia_tipo ('tarea'|'objetivo')
    Guarda y devuelve todo normalizado a UTC.
    Sincroniza bidireccionalmente: añade el event_id al array event_ids
    de la tarea u objetivo asociado.
    """
    payload = request.get_json(silent=True) or {}
    error = _validate_required(payload, ["titulo", "fecha_inicio", "fecha_fin"])
    if error:
        return jsonify({"error": error}), 400

    start_dt = _parse_iso(payload.get("fecha_inicio"))
    end_dt = _parse_iso(payload.get("fecha_fin"))
    if not start_dt or not end_dt:
        return jsonify({"error": "Formato de fecha inválido (usa ISO 8601)."}), 400

    # Referencia unificada (reemplaza id_tarea / id_objetivo)
    ref_id_raw = payload.get("referencia_id")
    ref_tipo = (payload.get("referencia_tipo") or "").strip() or None
    ref_id = None
    if ref_id_raw and ref_tipo in ("tarea", "objetivo"):
        try:
            ref_id = ObjectId(ref_id_raw)
        except Exception:
            ref_id = None
            ref_tipo = None

    doc: Dict[str, Any] = {
        "titulo": (payload.get("titulo") or "").strip(),
        "descripcion": (payload.get("descripcion") or "").strip(),
        "fecha_inicio": start_dt,  # aware UTC
        "fecha_fin": end_dt,       # aware UTC
        "tipo_evento": (payload.get("tipo_evento") or "").strip() or None,
        "usuario_id": DEFAULT_USER_ID,
        # Referencia unificada
        "referencia_id": ref_id,
        "referencia_tipo": ref_tipo,
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }
    doc.update(_time_layer_fields(payload))

    col, _ = _events_col()
    res = col.insert_one(doc)
    event_id = res.inserted_id
    original_goal_id = ref_id if ref_tipo == "objetivo" else None

    if _should_create_task_from_event(doc, ref_id, ref_tipo):
        task = _create_task_from_event(doc, event_id, ref_id)
        task_id = task.get("_id") if task else None
        if task_id:
            ref_id = task_id
            ref_tipo = "tarea"
            doc["referencia_id"] = task_id
            doc["referencia_tipo"] = "tarea"
            doc["objetivo_id"] = original_goal_id
            doc["generated_task_id"] = task_id
            doc["updated_at"] = datetime.now(timezone.utc)
            col.update_one(
                {"_id": event_id},
                {
                    "$set": {
                        "referencia_id": task_id,
                        "referencia_tipo": "tarea",
                        "objetivo_id": original_goal_id,
                        "generated_task_id": task_id,
                        "updated_at": doc["updated_at"],
                    }
                },
            )

    # Sincronización bidireccional: añadir event_id a la tarea/objetivo
    if ref_id and ref_tipo:
        _sync_event_association(event_id, None, None, ref_id, ref_tipo)

    out = dict(doc)
    out["_id"] = str(event_id)
    # Serializa fechas a ISO UTC
    for key in ("fecha_inicio", "fecha_fin", "created_at", "updated_at"):
        out[key] = _iso_utc(out.get(key))
    # IDs relacionados → str
    for key in ("id_usuario", "usuario_id", "referencia_id", "objetivo_id", "generated_task_id"):
        if isinstance(out.get(key), ObjectId):
            out[key] = str(out[key])
    _apply_time_layer_defaults(out)

    return jsonify(out), 201

@calendar_bp.route("/api/events/<event_id>", methods=["PUT", "PATCH"])
def api_update_event(event_id: str):
    """
    Actualiza un evento por su ID. Manejo UTC consistente.
    Si cambia la asociación (referencia_id / referencia_tipo),
    sincroniza bidireccionalmente con las tareas/objetivos afectados.
    """
    payload = request.get_json(silent=True) or {}
    try:
        oid = ObjectId(event_id)
    except Exception:
        return jsonify({"error": "ID inválido."}), 400

    col, _ = _events_col()

    # Obtener el evento actual para conocer la asociación anterior
    existing = col.find_one({"_id": oid})
    if not existing:
        return jsonify({"error": "Evento no encontrado."}), 404

    updates: Dict[str, Any] = {}
    # Campos de texto directos
    for key in ("titulo", "descripcion", "tipo_evento"):
        if key in payload:
            updates[key] = (payload.get(key) or "").strip()

    # Fechas (normaliza a UTC)
    if "fecha_inicio" in payload:
        dt = _parse_iso(payload.get("fecha_inicio"))
        if not dt:
            return jsonify({"error": "fecha_inicio inválida (ISO 8601)."}), 400
        updates["fecha_inicio"] = dt
    if "fecha_fin" in payload:
        dt = _parse_iso(payload.get("fecha_fin"))
        if not dt:
            return jsonify({"error": "fecha_fin inválida (ISO 8601)."}), 400
        updates["fecha_fin"] = dt

    # Relaciones de usuario
    if "id_usuario" in payload:
        updates["id_usuario"] = ObjectId(payload["id_usuario"]) if payload.get("id_usuario") else None
    if "usuario_id" in payload:
        updates["usuario_id"] = ObjectId(payload["usuario_id"]) if payload.get("usuario_id") else None

    # Referencia unificada (reemplaza id_tarea / id_objetivo)
    ref_changed = False
    new_ref_id = None
    new_ref_tipo = None
    if "referencia_id" in payload or "referencia_tipo" in payload:
        ref_changed = True
        ref_id_raw = payload.get("referencia_id")
        new_ref_tipo = (payload.get("referencia_tipo") or "").strip() or None
        if ref_id_raw and new_ref_tipo in ("tarea", "objetivo"):
            try:
                new_ref_id = ObjectId(ref_id_raw)
            except Exception:
                new_ref_id = None
                new_ref_tipo = None
        else:
            new_ref_id = None
            new_ref_tipo = None

        updates["referencia_id"] = new_ref_id
        updates["referencia_tipo"] = new_ref_tipo

    time_layer_keys = {
        "capa_tiempo",
        "time_layer",
        "categoria_tiempo",
        "bloquea_disponibilidad",
        "cuenta_productivo",
        "cuenta_recuperacion",
        "carga_mental",
        "carga_fisica",
    }
    if any(key in payload for key in time_layer_keys | {"titulo", "descripcion", "tipo_evento"}):
        layer_source = dict(existing)
        layer_source.update(updates)
        for key in time_layer_keys:
            if key in payload:
                layer_source[key] = payload.get(key)
        updates.update(_time_layer_fields(layer_source))

    if not updates:
        return jsonify({"error": "No hay campos para actualizar."}), 400

    updates["updated_at"] = datetime.now(timezone.utc)

    col.update_one({"_id": oid}, {"$set": updates})

    # Sincronización bidireccional si cambió la referencia
    if ref_changed:
        old_ref_id = existing.get("referencia_id")
        old_ref_tipo = existing.get("referencia_tipo")
        # Compatibilidad: si el evento antiguo usaba id_tarea/id_objetivo
        if not old_ref_id and not old_ref_tipo:
            if existing.get("id_tarea"):
                old_ref_id = existing.get("id_tarea")
                old_ref_tipo = "tarea"
            elif existing.get("id_objetivo"):
                old_ref_id = existing.get("id_objetivo")
                old_ref_tipo = "objetivo"

        # Solo sincronizar si realmente cambió
        old_str = str(old_ref_id) if old_ref_id else None
        new_str = str(new_ref_id) if new_ref_id else None
        if old_str != new_str or old_ref_tipo != new_ref_tipo:
            _sync_event_association(oid, old_ref_id, old_ref_tipo, new_ref_id, new_ref_tipo)

    doc = col.find_one({"_id": oid})
    out = dict(doc)
    out["_id"] = str(out["_id"])
    # Fechas → ISO UTC
    for key in ("fecha_inicio", "fecha_fin", "created_at", "updated_at"):
        out[key] = _iso_utc(out.get(key))
    # IDs relacionados → str
    for key in ("id_usuario", "usuario_id", "referencia_id", "objetivo_id", "generated_task_id"):
        if isinstance(out.get(key), ObjectId):
            out[key] = str(out[key])
    # Compatibilidad con datos antiguos
    for key in ("id_objetivo", "id_tarea"):
        if isinstance(out.get(key), ObjectId):
            out[key] = str(out[key])
    _apply_time_layer_defaults(out)

    return jsonify(out)

@calendar_bp.route("/api/events/<event_id>", methods=["DELETE"])
def api_delete_event(event_id: str):
    """
    Elimina un evento por ID.
    Antes de eliminar, desasocia el event_id del array event_ids
    de la tarea u objetivo vinculado.
    """
    try:
        oid = ObjectId(event_id)
    except Exception:
        return jsonify({"error": "ID inválido."}), 400

    col, _ = _events_col()

    # Obtener evento antes de eliminar para conocer su asociación
    existing = col.find_one({"_id": oid})
    if not existing:
        return jsonify({"error": "Evento no encontrado."}), 404

    # Desasociar del item vinculado
    old_ref_id = existing.get("referencia_id")
    old_ref_tipo = existing.get("referencia_tipo")
    # Compatibilidad: si el evento usaba id_tarea/id_objetivo
    if not old_ref_id and not old_ref_tipo:
        if existing.get("id_tarea"):
            old_ref_id = existing.get("id_tarea")
            old_ref_tipo = "tarea"
        elif existing.get("id_objetivo"):
            old_ref_id = existing.get("id_objetivo")
            old_ref_tipo = "objetivo"

    if old_ref_id and old_ref_tipo:
        _sync_event_association(oid, old_ref_id, old_ref_tipo, None, None)

    if not queue_deletion("Events", oid):
        return jsonify({"error": "No se pudo registrar el borrado del evento."}), 500

    try:
        flush_deletion_queue()
    except Exception:
        pass

    return jsonify({"deleted": True, "_id": event_id})


# -----------------------------
# Busqueda mixta de tareas y objetivos
# -----------------------------
@calendar_bp.route("/api/search/associations", methods=["GET"])
def api_search_associations():
    """
    Busca tareas y objetivos por nombre para asociar a un evento.
    Parámetros:
    - q: texto a buscar (mínimo 2 caracteres)
    - limit: número máximo de resultados (por defecto 10, max 20)
    
    Devuelve una lista mixta de tareas y objetivos, cada uno con:
    - _id: ID del elemento
    - titulo: título/contenido del elemento
    - tipo: "tarea" o "objetivo"
    """
    query = request.args.get("q", "").strip()
    try:
        limit = min(int(request.args.get("limit", 10)), 20)
    except (ValueError, TypeError):
        limit = 10

    if len(query) < 2:
        return jsonify([])

    results: List[Dict[str, Any]] = []
    
    # Buscar tareas (usando el campo 'contenido' como título)
    tasks = TaskModel.search_tasks(nombre=query)
    for task in tasks[:limit]:
        results.append({
            "_id": str(task.get("_id")),
            "titulo": task.get("contenido", "Sin título"),
            "tipo": "tarea"
        })

    # Buscar objetivos
    goals = GoalModel.search_by_name(nombre=query, limit=limit)
    for goal in goals:
        results.append({
            "_id": str(goal.get("_id")),
            "titulo": goal.get("titulo", "Sin título"),
            "tipo": "objetivo"
        })

    # Mezclar y limitar resultados totales
    # Ordenar alternando tipos para mejor distribución visual
    tareas = [r for r in results if r["tipo"] == "tarea"]
    objetivos = [r for r in results if r["tipo"] == "objetivo"]
    
    mixed: List[Dict[str, Any]] = []
    i, j = 0, 0
    while len(mixed) < limit and (i < len(tareas) or j < len(objetivos)):
        if i < len(tareas):
            mixed.append(tareas[i])
            i += 1
        if len(mixed) < limit and j < len(objetivos):
            mixed.append(objetivos[j])
            j += 1

    return jsonify(mixed[:limit])
