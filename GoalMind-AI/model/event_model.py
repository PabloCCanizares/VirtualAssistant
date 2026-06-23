from bson import ObjectId

from database.mongo_conn import get_app_user_id, get_collection, remote_uid_filter
from services.event_service import (
    normalize_event_payload,
    normalize_reference,
    reference_from_event,
    reference_query,
    sync_event_association,
)


def _uid_filter(_=None):
    """Local: sin filtro por usuario (BD de un solo usuario)."""
    return {}


class eventModel:
    COLLECTION = "Events"

    @staticmethod
    def get_all_events(usuario_id=None):
        local_col, _ = get_collection(eventModel.COLLECTION)
        return list(local_col.find(_uid_filter(usuario_id)).sort("fecha_inicio", 1))

    @staticmethod
    def get_events_by_task(task_id, usuario_id=None):
        """Obtiene todos los eventos asociados a una tarea específica."""
        local_col, _ = get_collection(eventModel.COLLECTION)
        oid, _ = normalize_reference(task_id, "tarea")
        if oid is None:
            return []
        uid_filter = _uid_filter(usuario_id)
        base_query = reference_query("tarea", oid)
        query = {"$and": [base_query, uid_filter]} if uid_filter else base_query
        return list(local_col.find(query).sort("fecha_inicio", 1))

    @staticmethod
    def get_events_by_goal(goal_id, usuario_id=None):
        """Obtiene todos los eventos asociados a un objetivo específico."""
        local_col, _ = get_collection(eventModel.COLLECTION)
        oid, _ = normalize_reference(goal_id, "objetivo")
        if oid is None:
            return []
        uid_filter = _uid_filter(usuario_id)
        base_query = reference_query("objetivo", oid)
        query = {"$and": [base_query, uid_filter]} if uid_filter else base_query
        return list(local_col.find(query).sort("fecha_inicio", 1))

    @staticmethod
    def get_event_by_id(event_id, usuario_id=None):
        local_col, _ = get_collection(eventModel.COLLECTION)
        try:
            oid = ObjectId(event_id) if not isinstance(event_id, ObjectId) else event_id
        except Exception:
            return None
        return local_col.find_one({"_id": oid, **_uid_filter(usuario_id)})

    @staticmethod
    def get_events_by_user(user_id):
        local_col, _ = get_collection(eventModel.COLLECTION)
        return list(local_col.find(_uid_filter(user_id)).sort("fecha_inicio", 1))

    @staticmethod
    def get_events_by_type(type_norm, usuario_id=None):
        """type_norm debe venir ya normalizado (sin tildes, minúsculas)"""
        local_col, _ = get_collection(eventModel.COLLECTION)
        query = {"tipo_evento": type_norm, **_uid_filter(usuario_id)}
        return list(local_col.find(query).sort("fecha_inicio", 1))

    @staticmethod
    def insert_event(data: dict, usuario_id=None):
        local_col, cloud_col = get_collection(eventModel.COLLECTION)
        
        uid = usuario_id or get_app_user_id()
        data = normalize_event_payload(data, usuario_id=uid)
        
        res = local_col.insert_one(data)
        event_id = res.inserted_id
        if cloud_col is not None:
            try:
                cloud_col.insert_one({**data, "_id": event_id})
            except Exception:
                pass

        ref_id, ref_tipo = reference_from_event(data)
        if ref_id and ref_tipo:
            sync_event_association(
                event_id,
                None,
                None,
                ref_id,
                ref_tipo,
                usuario_id=uid,
            )
        return event_id

    @staticmethod
    def update_event(event_id: str, updates: dict, usuario_id=None):
        local_col, cloud_col = get_collection(eventModel.COLLECTION)
        oid = ObjectId(event_id) if not isinstance(event_id, ObjectId) else event_id
        local_query = {"_id": oid}
        existing = local_col.find_one(local_query)
        old_ref_id, old_ref_tipo = reference_from_event(existing)

        norm_updates = dict(updates or {})
        ref_changed = any(
            key in norm_updates
            for key in ("referencia_id", "referencia_tipo", "id_tarea", "id_objetivo")
        )
        if ref_changed:
            new_ref_id, new_ref_tipo = normalize_reference(
                norm_updates.get("referencia_id"),
                norm_updates.get("referencia_tipo"),
                id_tarea=norm_updates.get("id_tarea"),
                id_objetivo=norm_updates.get("id_objetivo"),
            )
            norm_updates.pop("id_tarea", None)
            norm_updates.pop("id_objetivo", None)
            norm_updates["referencia_id"] = new_ref_id
            norm_updates["referencia_tipo"] = new_ref_tipo

        local_col.update_one(local_query, {"$set": norm_updates})
        if cloud_col is not None:
            remote_query = {"_id": oid, **remote_uid_filter(usuario_id)}
            try:
                cloud_col.update_one(remote_query, {"$set": norm_updates})
            except Exception:
                pass
        if ref_changed:
            sync_event_association(
                oid,
                old_ref_id,
                old_ref_tipo,
                norm_updates.get("referencia_id"),
                norm_updates.get("referencia_tipo"),
                usuario_id=usuario_id,
            )

    @staticmethod
    def delete_event(event_id: str, usuario_id=None):
        local_col, cloud_col = get_collection(eventModel.COLLECTION)
        oid = ObjectId(event_id) if not isinstance(event_id, ObjectId) else event_id
        local_query = {"_id": oid}
        existing = local_col.find_one(local_query)
        old_ref_id, old_ref_tipo = reference_from_event(existing)
        local_col.delete_one(local_query)
        if cloud_col is not None:
            remote_query = {"_id": oid, **remote_uid_filter(usuario_id)}
            try:
                cloud_col.delete_one(remote_query)
            except Exception:
                pass
        if old_ref_id and old_ref_tipo:
            sync_event_association(
                oid,
                old_ref_id,
                old_ref_tipo,
                None,
                None,
                usuario_id=usuario_id,
            )

    @staticmethod
    def delete_events_by_ids(ids: list[str], usuario_id=None):
        local_col, cloud_col = get_collection(eventModel.COLLECTION)
        oids = []
        for s in ids:
            try:
                oids.append(ObjectId(s))
            except Exception:
                continue
        if not oids:
            return 0
        local_query = {"_id": {"$in": oids}}
        res = local_col.delete_many(local_query)
        if cloud_col is not None:
            remote_query = {"_id": {"$in": oids}, **remote_uid_filter(usuario_id)}
            try:
                cloud_col.delete_many(remote_query)
            except Exception:
                pass
        return res.deleted_count
