from __future__ import annotations

from datetime import datetime

from bson import ObjectId
from pymongo import ReplaceOne

SYNC_COLLECTIONS = ("Tasks", "Goals", "Projects", "ProjectDocuments", "Events")
SYNC_TIMESTAMP_FIELDS = (
    "updated_at",
    "uploaded_at",
    "created_at",
    "fecha_creacion",
    "fecha_actualizacion",
    "fecha_modificacion",
    "fecha_inicio",
)


def sync_from_remote(collection_name, obj):
    """Download a remote document into local storage when it is missing."""
    from database.mongo_conn import get_collection, remote_uid_filter

    local_col, remote_col = get_collection(collection_name)

    if remote_col is None:
        return

    filtro = {"_id": obj["_id"]} if "_id" in obj else obj
    remote_filtro = {"$and": [filtro, remote_uid_filter()]}

    if not local_col.find_one(filtro):
        remoto = remote_col.find_one(remote_filtro)
        if remoto:
            local_col.insert_one(remoto)


def sync_to_remote(collection_name, obj):
    """Upload or update one document in remote storage."""
    from database.mongo_conn import get_collection

    _, remote_col = get_collection(collection_name)

    if remote_col is None:
        return False

    if "_id" not in obj:
        return False

    filtro = {"_id": obj["_id"]}

    remote_col.replace_one(filtro, obj, upsert=True)
    return True


def _parse_datetime(value):
    """Parse a value into datetime when possible."""
    if isinstance(value, datetime):
        return value
    if value is None:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "").strip())
    except Exception:
        return None


def _doc_timestamp(doc):
    """Return the best available timestamp for conflict resolution."""
    if not isinstance(doc, dict):
        return None
    for field in SYNC_TIMESTAMP_FIELDS:
        parsed = _parse_datetime(doc.get(field))
        if parsed is not None:
            return parsed
    return None


def _remote_should_replace_local(local_doc, remote_doc):
    """
    Reconciliation rule:
    - newer remote timestamp wins;
    - remote with timestamp wins over local without timestamp;
    - when neither side has timestamps, content differences make remote win.
    """
    if local_doc is None:
        return True

    local_ts = _doc_timestamp(local_doc)
    remote_ts = _doc_timestamp(remote_doc)
    if local_ts is not None and remote_ts is not None:
        return remote_ts > local_ts
    if remote_ts is not None and local_ts is None:
        return True
    if local_ts is not None and remote_ts is None:
        return False
    return local_doc != remote_doc


def _id_variants(raw_id):
    """Generate compatible _id variants for tolerant lookups."""
    variants = []
    seen = set()

    def _push(candidate):
        if candidate is None:
            return
        key = (type(candidate).__name__, str(candidate))
        if key in seen:
            return
        seen.add(key)
        variants.append(candidate)

    _push(raw_id)
    _push(str(raw_id) if raw_id is not None else None)
    try:
        if raw_id is not None and ObjectId.is_valid(str(raw_id)):
            normalized = ObjectId(str(raw_id))
            _push(normalized)
            _push(str(normalized))
    except Exception:
        pass
    return variants


def _find_by_id_variants(collection, raw_id):
    for candidate in _id_variants(raw_id):
        found = collection.find_one({"_id": candidate})
        if found:
            return found
    return None


def sync_all_collections():
    """Pull all configured collections from remote storage into local storage."""
    from flask import current_app

    from database.mongo_conn import ensure_remote_connection, get_collection, remote_uid_filter

    if not ensure_remote_connection(current_app):
        return 0

    pulled_docs = 0
    for col in SYNC_COLLECTIONS:
        pending_ids = get_pending_deletions(col)
        local_col, remote_col = get_collection(col)
        if remote_col is None:
            continue

        if pending_ids:
            object_ids = []
            string_ids = []
            for pid in pending_ids:
                try:
                    if ObjectId.is_valid(str(pid)):
                        object_ids.append(ObjectId(str(pid)))
                    else:
                        string_ids.append(str(pid))
                except Exception:
                    string_ids.append(str(pid))

            delete_query = {"$or": []}
            if object_ids:
                delete_query["$or"].append({"_id": {"$in": object_ids}})
            if string_ids:
                delete_query["$or"].append({"_id": {"$in": string_ids}})
            if delete_query["$or"]:
                local_col.delete_many(delete_query)

        for remote_doc in remote_col.find(remote_uid_filter()):
            remote_id = remote_doc.get("_id")
            if remote_id is None:
                continue
            if str(remote_id) in pending_ids:
                continue

            local_doc = _find_by_id_variants(local_col, remote_id)
            if local_doc is None:
                local_col.insert_one(remote_doc)
                pulled_docs += 1
                continue

            if _remote_should_replace_local(local_doc, remote_doc):
                if col == "ProjectDocuments" and local_doc.get("local_upload_id"):
                    remote_doc["local_upload_id"] = local_doc["local_upload_id"]

                local_id = local_doc.get("_id")
                if local_id == remote_id:
                    local_col.replace_one({"_id": remote_id}, remote_doc, upsert=True)
                else:
                    local_col.delete_one({"_id": local_id})
                    local_col.insert_one(remote_doc)
                pulled_docs += 1
    return pulled_docs


def sync_local_to_remote():
    """Push local documents into remote storage without overwriting newer remote docs."""
    from flask import current_app

    from database.mongo_conn import ensure_remote_connection, get_collection, remote_uid_filter

    if not ensure_remote_connection(current_app):
        return 0

    pushed_docs = 0
    for col in SYNC_COLLECTIONS:
        local_col, remote_col = get_collection(col)
        pending_ids = get_pending_deletions(col)

        if remote_col is None:
            continue
        remote_docs = {
            str(doc.get("_id")): doc
            for doc in remote_col.find(remote_uid_filter(), None)
            if doc.get("_id") is not None
        }
        docs = []
        for doc in local_col.find():
            local_id = doc.get("_id")
            local_id_key = str(local_id)
            if local_id_key in pending_ids:
                continue
            if col == "ProjectDocuments":
                if doc.get("remote_sync_pending"):
                    continue
                doc = dict(doc)
                doc.pop("local_upload_id", None)
            remote_doc = remote_docs.get(local_id_key)
            if remote_doc is not None and _remote_should_replace_local(doc, remote_doc):
                continue
            if remote_doc is not None and doc.get("_id") != remote_doc.get("_id"):
                doc = dict(doc)
                doc["_id"] = remote_doc.get("_id")
            docs.append(doc)
        ops = [
            ReplaceOne({"_id": doc["_id"]}, doc, upsert=True)
            for doc in docs
        ]
        if ops:
            remote_col.bulk_write(ops)
            pushed_docs += len(ops)
    return pushed_docs


def queue_deletion(collection_name, target_id):
    """Queue a deletion for remote sync and remove the document locally."""
    from database.mongo_conn import get_collection

    local_col, _ = get_collection("DeleteQueue")
    if not collection_name:
        return False
    if target_id is None:
        return False

    target_id_str = str(target_id)
    try:
        if ObjectId.is_valid(target_id_str):
            target_id_str = str(ObjectId(target_id_str))
    except Exception:
        pass

    queue_id = f"{collection_name}:{target_id_str}"

    payload = {
        "_id": queue_id,
        "collection": collection_name,
        "target_id": target_id_str,
        "deleted_at": datetime.utcnow(),
    }

    try:
        local_col.update_one({"_id": queue_id}, {"$setOnInsert": payload}, upsert=True)
        target_local, _ = get_collection(collection_name)
        queries = [{"_id": target_id_str}]
        try:
            if ObjectId.is_valid(target_id_str):
                queries.append({"_id": ObjectId(target_id_str)})
        except Exception:
            pass
        if queries:
            target_local.delete_many({"$or": queries})
        return True
    except Exception:
        return False


def get_pending_deletions(collection_name):
    """Return queued target ids for one collection."""
    from database.mongo_conn import get_collection

    local_col, _ = get_collection("DeleteQueue")
    pending = set()
    for doc in local_col.find({"collection": collection_name}):
        pending_id = doc.get("target_id", doc.get("_id"))
        if pending_id is not None:
            pending.add(str(pending_id))
    return pending


def flush_deletion_queue():
    """Propagate queued deletions to remote storage and clear completed items."""
    from database.mongo_conn import ensure_remote_connection, get_collection

    local_col, _ = get_collection("DeleteQueue")
    if not ensure_remote_connection():
        return 0

    removed = 0
    for item in local_col.find().sort("deleted_at", 1):
        collection = item.get("collection")
        target_id = item.get("target_id", item.get("_id"))
        if not collection or target_id is None:
            continue

        _, remote_col = get_collection(collection)
        if remote_col is None:
            continue

        candidates = []
        if isinstance(target_id, ObjectId):
            candidates.append(target_id)
            candidates.append(str(target_id))
        else:
            candidates.append(target_id)
            try:
                if ObjectId.is_valid(str(target_id)):
                    candidates.append(ObjectId(str(target_id)))
            except Exception:
                pass

        seen = set()
        unique_candidates = []
        for cid in candidates:
            key = (type(cid), str(cid))
            if key in seen:
                continue
            seen.add(key)
            unique_candidates.append(cid)

        delete_query = {"$or": [{"_id": cid} for cid in unique_candidates]}
        try:
            remote_col.delete_many(delete_query)
        except Exception:
            continue

        local_col.delete_one({"_id": item["_id"]})
        removed += 1

    return removed
