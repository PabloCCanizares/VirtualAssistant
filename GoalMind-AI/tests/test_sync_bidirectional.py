from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta

from bson import ObjectId
from flask import Flask

from database import mongo_conn
from database.scheduler import trigger_sync_now


class _FakeCollection:
    def __init__(self, docs=None):
        self._docs = {}
        for doc in docs or []:
            copied = deepcopy(doc)
            self._docs[copied["_id"]] = copied
        self.bulk_write_calls = 0

    def find(self, _query=None, _projection=None):
        return [deepcopy(doc) for doc in self._docs.values()]

    def find_one(self, query):
        doc_id = query.get("_id")
        if doc_id in self._docs:
            return deepcopy(self._docs[doc_id])
        return None

    def insert_one(self, doc):
        copied = deepcopy(doc)
        self._docs[copied["_id"]] = copied
        return type("InsertResult", (), {"inserted_id": copied["_id"]})()

    def insert_many(self, docs):
        for doc in docs:
            copied = deepcopy(doc)
            self._docs[copied["_id"]] = copied
        return type("InsertManyResult", (), {"inserted_ids": [doc["_id"] for doc in docs]})()

    def replace_one(self, query, doc, upsert=False):
        doc_id = query.get("_id")
        if doc_id in self._docs or upsert:
            copied = deepcopy(doc)
            self._docs[copied["_id"]] = copied
            return type("ReplaceResult", (), {"modified_count": 1})()
        return type("ReplaceResult", (), {"modified_count": 0})()

    def bulk_write(self, ops):
        self.bulk_write_calls += 1
        for op in ops:
            doc_id = op._filter.get("_id")
            copied = deepcopy(op._doc)
            self._docs[doc_id] = copied
        return type("BulkResult", (), {"modified_count": len(ops)})()

    def delete_many(self, query):
        deleted = 0
        or_rules = query.get("$or", []) if isinstance(query, dict) else []
        if or_rules:
            to_delete = set()
            for rule in or_rules:
                id_rule = rule.get("_id", {})
                if isinstance(id_rule, dict) and "$in" in id_rule:
                    for item in id_rule["$in"]:
                        if item in self._docs:
                            to_delete.add(item)
            for doc_id in to_delete:
                self._docs.pop(doc_id, None)
            deleted = len(to_delete)
        return type("DeleteResult", (), {"deleted_count": deleted})()

    def delete_one(self, query):
        doc_id = query.get("_id")
        if doc_id in self._docs:
            self._docs.pop(doc_id, None)
            return type("DeleteOneResult", (), {"deleted_count": 1})()
        return type("DeleteOneResult", (), {"deleted_count": 0})()


def _dt(base_days: int) -> datetime:
    return datetime(2026, 1, 1) + timedelta(days=base_days)


def test_sync_all_collections_updates_existing_docs_from_remote(monkeypatch):
    local = _FakeCollection([{"_id": "p1", "name": "local-old", "updated_at": _dt(0)}])
    remote = _FakeCollection([{"_id": "p1", "name": "remote-new", "updated_at": _dt(1)}])

    monkeypatch.setattr(mongo_conn, "collections", ["Projects"])
    monkeypatch.setattr(mongo_conn, "ensure_remote_connection", lambda _app=None: True)
    monkeypatch.setattr(mongo_conn, "get_pending_deletions", lambda _collection: set())
    monkeypatch.setattr(mongo_conn, "get_collection", lambda _name: (local, remote))

    pulled = mongo_conn.sync_all_collections()

    assert pulled == 1
    assert local.find_one({"_id": "p1"})["name"] == "remote-new"


def test_sync_all_collections_replaces_when_no_timestamps_and_payload_differs(monkeypatch):
    local = _FakeCollection([{"_id": "t1", "content": "local"}])
    remote = _FakeCollection([{"_id": "t1", "content": "remote"}])

    monkeypatch.setattr(mongo_conn, "collections", ["Tasks"])
    monkeypatch.setattr(mongo_conn, "ensure_remote_connection", lambda _app=None: True)
    monkeypatch.setattr(mongo_conn, "get_pending_deletions", lambda _collection: set())
    monkeypatch.setattr(mongo_conn, "get_collection", lambda _name: (local, remote))

    pulled = mongo_conn.sync_all_collections()

    assert pulled == 1
    assert local.find_one({"_id": "t1"})["content"] == "remote"


def test_sync_local_to_remote_does_not_overwrite_newer_remote(monkeypatch):
    local = _FakeCollection([{"_id": "g1", "status": "local-stale", "updated_at": _dt(0)}])
    remote = _FakeCollection([{"_id": "g1", "status": "remote-new", "updated_at": _dt(2)}])

    monkeypatch.setattr(mongo_conn, "collections", ["Goals"])
    monkeypatch.setattr(mongo_conn, "ensure_remote_connection", lambda _app=None: True)
    monkeypatch.setattr(mongo_conn, "get_pending_deletions", lambda _collection: set())
    monkeypatch.setattr(mongo_conn, "get_collection", lambda _name: (local, remote))

    pushed = mongo_conn.sync_local_to_remote()

    assert pushed == 0
    assert remote.find_one({"_id": "g1"})["status"] == "remote-new"


def test_sync_local_to_remote_pushes_when_local_is_newer(monkeypatch):
    local = _FakeCollection([{"_id": "g2", "status": "local-new", "updated_at": _dt(4)}])
    remote = _FakeCollection([{"_id": "g2", "status": "remote-old", "updated_at": _dt(1)}])

    monkeypatch.setattr(mongo_conn, "collections", ["Goals"])
    monkeypatch.setattr(mongo_conn, "ensure_remote_connection", lambda _app=None: True)
    monkeypatch.setattr(mongo_conn, "get_pending_deletions", lambda _collection: set())
    monkeypatch.setattr(mongo_conn, "get_collection", lambda _name: (local, remote))

    pushed = mongo_conn.sync_local_to_remote()

    assert pushed == 1
    assert remote.find_one({"_id": "g2"})["status"] == "local-new"


def test_sync_all_collections_normalizes_string_objectid_mismatch(monkeypatch):
    oid = ObjectId("67efbbbbbbbbbbbbbbbb0001")
    local = _FakeCollection([{"_id": str(oid), "name": "local"}])
    remote = _FakeCollection([{"_id": oid, "name": "remote", "updated_at": _dt(2)}])

    monkeypatch.setattr(mongo_conn, "collections", ["Projects"])
    monkeypatch.setattr(mongo_conn, "ensure_remote_connection", lambda _app=None: True)
    monkeypatch.setattr(mongo_conn, "get_pending_deletions", lambda _collection: set())
    monkeypatch.setattr(mongo_conn, "get_collection", lambda _name: (local, remote))

    pulled = mongo_conn.sync_all_collections()

    assert pulled == 1
    assert local.find_one({"_id": oid})["name"] == "remote"
    assert local.find_one({"_id": str(oid)}) is None


def test_trigger_sync_now_runs_pull_before_push(monkeypatch):
    calls = []

    monkeypatch.setattr(
        "database.mongo_conn.ensure_remote_connection",
        lambda app=None: calls.append("ensure_remote_connection") or True,
    )
    monkeypatch.setattr(
        "database.mongo_conn.flush_deletion_queue",
        lambda: calls.append("flush_deletion_queue") or 0,
    )
    monkeypatch.setattr(
        "model.project_document_model.ProjectDocumentModel.promote_pending_remote_uploads",
        lambda app=None: calls.append("promote_pending_remote_uploads") or 0,
    )
    monkeypatch.setattr(
        "database.mongo_conn.sync_all_collections",
        lambda: calls.append("sync_all_collections") or 0,
    )
    monkeypatch.setattr(
        "database.mongo_conn.sync_local_to_remote",
        lambda: calls.append("sync_local_to_remote") or 0,
    )

    app = Flask(__name__)
    trigger_sync_now(app)

    assert calls == [
        "ensure_remote_connection",
        "flush_deletion_queue",
        "promote_pending_remote_uploads",
        "sync_all_collections",
        "sync_local_to_remote",
    ]
