import logging
from datetime import datetime, timezone
from typing import Any

from bson import ObjectId

logger = logging.getLogger(__name__)

VALID_REFERENCE_TYPES = {"tarea", "objetivo"}


def parse_object_id(value: Any) -> ObjectId | None:
    if value is None:
        return None
    if isinstance(value, ObjectId):
        return value
    try:
        raw = str(value)
        if ObjectId.is_valid(raw):
            return ObjectId(raw)
    except Exception:
        return None
    return None


def normalize_reference(
    referencia_id: Any = None,
    referencia_tipo: str | None = None,
    *,
    id_tarea: Any = None,
    id_objetivo: Any = None,
) -> tuple[ObjectId | None, str | None]:
    """Return the canonical event reference, accepting legacy fields for reads."""
    ref_id = referencia_id
    ref_tipo = (referencia_tipo or "").strip() or None

    if not ref_id and id_tarea:
        ref_id = id_tarea
        ref_tipo = "tarea"
    elif not ref_id and id_objetivo:
        ref_id = id_objetivo
        ref_tipo = "objetivo"

    if ref_tipo not in VALID_REFERENCE_TYPES:
        return None, None

    parsed_id = parse_object_id(ref_id)
    if parsed_id is None:
        return None, None

    return parsed_id, ref_tipo


def reference_from_event(event_doc: dict | None) -> tuple[ObjectId | None, str | None]:
    if not event_doc:
        return None, None
    return normalize_reference(
        event_doc.get("referencia_id"),
        event_doc.get("referencia_tipo"),
        id_tarea=event_doc.get("id_tarea"),
        id_objetivo=event_doc.get("id_objetivo"),
    )


def reference_query(kind: str, raw_id: Any) -> dict:
    parsed_id = parse_object_id(raw_id)
    if parsed_id is None or kind not in VALID_REFERENCE_TYPES:
        return {"_id": {"$exists": False}}

    legacy_field = "id_tarea" if kind == "tarea" else "id_objetivo"
    return {
        "$or": [
            {"referencia_tipo": kind, "referencia_id": parsed_id},
            {legacy_field: parsed_id},
        ]
    }


def normalize_event_payload(data: dict, *, usuario_id: Any) -> dict:
    doc = dict(data or {})
    ref_id, ref_tipo = normalize_reference(
        doc.get("referencia_id"),
        doc.get("referencia_tipo"),
        id_tarea=doc.get("id_tarea"),
        id_objetivo=doc.get("id_objetivo"),
    )

    doc.pop("id_tarea", None)
    doc.pop("id_objetivo", None)
    doc["referencia_id"] = ref_id
    doc["referencia_tipo"] = ref_tipo
    doc["usuario_id"] = doc.get("usuario_id") or usuario_id

    now = datetime.now(timezone.utc)
    doc.setdefault("created_at", now)
    doc["updated_at"] = doc.get("updated_at") or now
    return doc


def sync_event_association(
    event_id: Any,
    old_ref_id: Any,
    old_ref_tipo: str | None,
    new_ref_id: Any,
    new_ref_tipo: str | None,
    *,
    usuario_id: Any = None,
    task_model=None,
    goal_model=None,
) -> None:
    """Keep task/goal event_ids aligned with an event reference change."""
    if task_model is None:
        from model.task_model import TaskModel as task_model
    if goal_model is None:
        from model.goal_model import GoalModel as goal_model

    eid = str(event_id)

    if old_ref_id and old_ref_tipo:
        try:
            if old_ref_tipo == "tarea":
                task_model.remove_event_from_task(str(old_ref_id), eid, usuario_id=usuario_id)
            elif old_ref_tipo == "objetivo":
                goal_model.remove_event_from_goal(str(old_ref_id), eid, usuario_id=usuario_id)
        except Exception:
            logger.warning(
                "No se pudo desasociar evento %s de %s %s",
                eid,
                old_ref_tipo,
                old_ref_id,
                exc_info=True,
            )

    if new_ref_id and new_ref_tipo:
        try:
            if new_ref_tipo == "tarea":
                task_model.add_event_to_task(str(new_ref_id), eid, usuario_id=usuario_id)
            elif new_ref_tipo == "objetivo":
                goal_model.add_event_to_goal(str(new_ref_id), eid, usuario_id=usuario_id)
        except Exception:
            logger.warning(
                "No se pudo asociar evento %s a %s %s",
                eid,
                new_ref_tipo,
                new_ref_id,
                exc_info=True,
            )
