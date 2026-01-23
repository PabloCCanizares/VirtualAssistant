# controllers/calendar_controller.py
from flask import Blueprint, render_template, request, jsonify
from bson import ObjectId
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from model.task_model import TaskModel
from model.goal_model import GoalModel

from database.mongo_conn import get_collection

# No ponemos url_prefix para que /api/... quede en la raíz,
# y la página del calendario sea /calendar
calendar_bp = Blueprint("calendar_bp", __name__)

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

@calendar_bp.route("/api/events", methods=["GET"])
def api_list_events():
    """
    Devuelve una lista de eventos en bruto (con las claves esperadas por el front).
    Si se proporcionan start y end (ISO), filtra por intersección de rango.
    Todas las fechas se devuelven en ISO con offset UTC (+00:00).
    """
    start_iso = request.args.get("start")
    end_iso = request.args.get("end")
    start_dt = _parse_iso(start_iso)
    end_dt = _parse_iso(end_iso)

    col, _ = _events_col()

    query: Dict[str, Any] = {}
    if start_dt and end_dt:
        # Intersección: (inicio <= end) y (fin >= start)
        query = {
            "$or": [
                {"fecha_inicio": {"$lte": end_dt}, "fecha_fin": {"$gte": start_dt}},
                {"start": {"$lte": end_dt}, "end": {"$gte": start_dt}},  # compatibilidad
            ]
        }
    elif start_dt:
        query = {"$or": [{"fecha_inicio": {"$gte": start_dt}}, {"start": {"$gte": start_dt}}]}
    elif end_dt:
        query = {"$or": [{"fecha_inicio": {"$lte": end_dt}}, {"start": {"$lte": end_dt}}]}

    docs = list(col.find(query).sort("fecha_inicio", 1))

    # Normalizamos para JSON: stringificamos ObjectId y datetimes a ISO (UTC)
    events: List[Dict[str, Any]] = []
    for d in docs:
        out = dict(d)
        out["_id"] = str(out.get("_id"))
        # Fechas → ISO UTC
        for key in ("fecha_inicio", "fecha_fin", "created_at", "updated_at", "start", "end"):
            out[key] = _iso_utc(out.get(key))
        # IDs relacionados → str
        for key in ("id_usuario", "usuario_id", "id_objetivo", "id_tarea"):
            if isinstance(out.get(key), ObjectId):
                out[key] = str(out[key])
        events.append(out)

    return jsonify(events)

@calendar_bp.route("/api/events", methods=["POST"])
def api_create_event():
    """
    Crea un evento. Espera JSON con:
    - Requeridos:  titulo, fecha_inicio (ISO), fecha_fin (ISO)
    - Opcionales:  descripcion, tipo_evento, id_usuario, usuario_id, id_objetivo
    Guarda y devuelve todo normalizado a UTC.
    """
    payload = request.get_json(silent=True) or {}
    error = _validate_required(payload, ["titulo", "fecha_inicio", "fecha_fin"])
    if error:
        return jsonify({"error": error}), 400

    start_dt = _parse_iso(payload.get("fecha_inicio"))
    end_dt = _parse_iso(payload.get("fecha_fin"))
    if not start_dt or not end_dt:
        return jsonify({"error": "Formato de fecha inválido (usa ISO 8601)."}), 400

    doc: Dict[str, Any] = {
        "titulo": (payload.get("titulo") or "").strip(),
        "descripcion": (payload.get("descripcion") or "").strip(),
        "fecha_inicio": start_dt,  # aware UTC
        "fecha_fin": end_dt,       # aware UTC
        "tipo_evento": (payload.get("tipo_evento") or "").strip() or None,
        # aceptamos ambas claves por compatibilidad
        "id_usuario": ObjectId(payload["id_usuario"]) if payload.get("id_usuario") else None,
        "usuario_id": ObjectId(payload["usuario_id"]) if payload.get("usuario_id") else None,
        "id_objetivo": ObjectId(payload["id_objetivo"]) if payload.get("id_objetivo") else None,
        "id_tarea": ObjectId(payload["id_tarea"]) if payload.get("id_tarea") else None,
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }

    col, _ = _events_col()
    res = col.insert_one(doc)

    out = dict(doc)
    out["_id"] = str(res.inserted_id)
    # Serializa fechas a ISO UTC
    for key in ("fecha_inicio", "fecha_fin", "created_at", "updated_at"):
        out[key] = _iso_utc(out.get(key))
    # IDs relacionados → str
    for key in ("id_usuario", "usuario_id", "id_objetivo", "id_tarea"):
        if isinstance(out.get(key), ObjectId):
            out[key] = str(out[key])

    return jsonify(out), 201

@calendar_bp.route("/api/events/<event_id>", methods=["PUT", "PATCH"])
def api_update_event(event_id: str):
    """Actualiza un evento por su ID. Manejo UTC consistente."""
    payload = request.get_json(silent=True) or {}
    try:
        oid = ObjectId(event_id)
    except Exception:
        return jsonify({"error": "ID inválido."}), 400

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

    # Relaciones
    if "id_usuario" in payload:
        updates["id_usuario"] = ObjectId(payload["id_usuario"]) if payload.get("id_usuario") else None
    if "usuario_id" in payload:
        updates["usuario_id"] = ObjectId(payload["usuario_id"]) if payload.get("usuario_id") else None
    if "id_objetivo" in payload:
        updates["id_objetivo"] = ObjectId(payload["id_objetivo"]) if payload.get("id_objetivo") else None
    if "id_tarea" in payload:
        updates["id_tarea"] = ObjectId(payload["id_tarea"]) if payload.get("id_tarea") else None

    if not updates:
        return jsonify({"error": "No hay campos para actualizar."}), 400

    updates["updated_at"] = datetime.now(timezone.utc)

    col, _ = _events_col()
    res = col.update_one({"_id": oid}, {"$set": updates})
    if res.matched_count == 0:
        return jsonify({"error": "Evento no encontrado."}), 404

    doc = col.find_one({"_id": oid})
    out = dict(doc)
    out["_id"] = str(out["_id"])
    # Fechas → ISO UTC
    for key in ("fecha_inicio", "fecha_fin", "created_at", "updated_at"):
        out[key] = _iso_utc(out.get(key))
    # IDs relacionados → str
    for key in ("id_usuario", "usuario_id", "id_objetivo", "id_tarea"):
        if isinstance(out.get(key), ObjectId):
            out[key] = str(out[key])

    return jsonify(out)

@calendar_bp.route("/api/events/<event_id>", methods=["DELETE"])
def api_delete_event(event_id: str):
    """Elimina un evento por ID."""
    try:
        oid = ObjectId(event_id)
    except Exception:
        return jsonify({"error": "ID inválido."}), 400

    col, _ = _events_col()
    res = col.delete_one({"_id": oid})
    if res.deleted_count == 0:
        return jsonify({"error": "Evento no encontrado."}), 404

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
