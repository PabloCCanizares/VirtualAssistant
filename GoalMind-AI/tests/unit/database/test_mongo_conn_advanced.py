"""Tests para ramas de `database/mongo_conn.py` no cubiertas por integracion.

Los helpers puros (parse, filtros) ya estan cubiertos en
`tests/test_mongo_conn_helpers.py`; el flujo de sincronizacion en las
baterias de integracion. Aqui se atacan `reconnect_databases`,
`get_remote_database`, `get_local_database`, `_persist_user_nickname`,
`_doc_timestamp`, `_id_variants`, `_find_by_id_variants` y los caminos de
error.
"""

from __future__ import annotations

from datetime import datetime

import pytest
from bson import ObjectId

from database import mongo_conn


class TestDocTimestamp:
    def test_returns_none_for_non_dict(self):
        assert mongo_conn._doc_timestamp(None) is None
        assert mongo_conn._doc_timestamp("not-a-dict") is None

    def test_returns_first_available_field(self):
        ts = datetime(2026, 1, 1)
        doc = {"updated_at": ts}
        assert mongo_conn._doc_timestamp(doc) == ts

    def test_falls_back_to_other_timestamps(self):
        ts = datetime(2026, 1, 1)
        doc = {"fecha_creacion": ts}
        assert mongo_conn._doc_timestamp(doc) == ts

    def test_returns_none_when_no_timestamps(self):
        assert mongo_conn._doc_timestamp({"x": 1}) is None


class TestRemoteShouldReplaceLocal:
    def test_no_local_doc_yields_true(self):
        assert mongo_conn._remote_should_replace_local(None, {"x": 1}) is True

    def test_remote_newer_wins(self):
        local = {"updated_at": datetime(2026, 1, 1)}
        remote = {"updated_at": datetime(2026, 1, 2)}
        assert mongo_conn._remote_should_replace_local(local, remote) is True

    def test_local_newer_wins(self):
        local = {"updated_at": datetime(2026, 1, 2)}
        remote = {"updated_at": datetime(2026, 1, 1)}
        assert mongo_conn._remote_should_replace_local(local, remote) is False

    def test_remote_with_ts_local_without_wins(self):
        local = {"x": 1}
        remote = {"updated_at": datetime(2026, 1, 1)}
        assert mongo_conn._remote_should_replace_local(local, remote) is True

    def test_local_with_ts_remote_without_loses(self):
        local = {"updated_at": datetime(2026, 1, 1)}
        remote = {"x": 1}
        assert mongo_conn._remote_should_replace_local(local, remote) is False

    def test_no_timestamps_same_content_no_change(self):
        d = {"x": 1, "y": 2}
        assert mongo_conn._remote_should_replace_local(d, dict(d)) is False

    def test_no_timestamps_different_content_remote_wins(self):
        assert mongo_conn._remote_should_replace_local({"x": 1}, {"x": 2}) is True


class TestParseDatetime:
    def test_returns_existing_datetime(self):
        ts = datetime(2026, 1, 1)
        assert mongo_conn._parse_datetime(ts) == ts

    def test_returns_none_for_none(self):
        assert mongo_conn._parse_datetime(None) is None

    def test_parses_iso_string(self):
        out = mongo_conn._parse_datetime("2026-05-17T10:00:00")
        assert out.year == 2026

    def test_parses_iso_with_z(self):
        out = mongo_conn._parse_datetime("2026-05-17T10:00:00Z")
        assert out.year == 2026

    def test_returns_none_for_garbage(self):
        assert mongo_conn._parse_datetime("not-a-date") is None


class TestIdVariants:
    def test_objectid_input_generates_both_variants(self):
        oid = ObjectId()
        variants = mongo_conn._id_variants(oid)
        # Deberia incluir el ObjectId y su str
        types = {type(v).__name__ for v in variants}
        assert "ObjectId" in types
        assert "str" in types

    def test_string_input_generates_both(self):
        hex_id = str(ObjectId())
        variants = mongo_conn._id_variants(hex_id)
        types = {type(v).__name__ for v in variants}
        assert "str" in types
        assert "ObjectId" in types

    def test_invalid_string_only_gives_string(self):
        variants = mongo_conn._id_variants("not-a-valid-oid")
        assert all(isinstance(v, str) for v in variants)

    def test_none_input(self):
        variants = mongo_conn._id_variants(None)
        # None nunca se mete pero str(None) si — la implementacion deduplica.
        assert isinstance(variants, list)


class TestFindByIdVariants:
    def test_finds_with_objectid(self, mongo_mock):
        col = mongo_mock.local_db["test"]
        oid = ObjectId()
        col.insert_one({"_id": oid, "x": 1})
        found = mongo_conn._find_by_id_variants(col, oid)
        assert found is not None
        assert found["x"] == 1

    def test_finds_with_string(self, mongo_mock):
        col = mongo_mock.local_db["test"]
        oid = ObjectId()
        col.insert_one({"_id": oid, "x": 1})
        found = mongo_conn._find_by_id_variants(col, str(oid))
        assert found is not None

    def test_not_found_returns_none(self, mongo_mock):
        col = mongo_mock.local_db["test"]
        assert mongo_conn._find_by_id_variants(col, ObjectId()) is None


class TestIdDocMap:
    def test_finds_objectid_doc_from_string_lookup(self):
        oid = ObjectId()
        doc_map = mongo_conn._build_id_doc_map([{"_id": oid, "x": 1}])

        found = mongo_conn._find_in_id_doc_map(doc_map, str(oid))

        assert found is not None
        assert found["x"] == 1

    def test_finds_string_doc_from_objectid_lookup(self):
        oid = ObjectId()
        doc_map = mongo_conn._build_id_doc_map([{"_id": str(oid), "x": 1}])

        found = mongo_conn._find_in_id_doc_map(doc_map, oid)

        assert found is not None
        assert found["x"] == 1


class TestGetLocalAndRemoteDatabase:
    def test_get_local_database_returns_db(self, mongo_mock):
        db = mongo_conn.get_local_database()
        assert db is not None

    def test_get_remote_database_without_remote(self, mongo_mock, monkeypatch):
        monkeypatch.setattr(mongo_conn, "mongo_remote", None)
        monkeypatch.setattr(mongo_conn, "_configured_remote_uri", "")
        assert mongo_conn.get_remote_database() is None

    def test_get_remote_database_with_remote(self, mongo_mock):
        db = mongo_conn.get_remote_database()
        # Con mongo_remote activo (autouse) deberia devolver la BD
        assert db is not None


class TestQueueDeletionEdgeCases:
    def test_queue_deletion_no_collection(self, mongo_mock):
        assert mongo_conn.queue_deletion("", "x") is False

    def test_queue_deletion_no_target(self, mongo_mock):
        assert mongo_conn.queue_deletion("Tasks", None) is False

    def test_get_pending_deletions_empty(self, mongo_mock):
        assert mongo_conn.get_pending_deletions("Tasks") == set()


class TestReconnectDatabases:
    def test_reconnect_with_no_remote_uri_clears(self, mongo_mock, monkeypatch):
        from flask import Flask
        app = Flask(__name__)
        app.mongo_local = mongo_conn.mongo_local
        monkeypatch.setattr(mongo_conn, "_create_mongo_client", lambda uri: mongo_mock.local_client)
        monkeypatch.delenv("MONGO_REMOTE_URI", raising=False)
        monkeypatch.setenv("MONGO_LOCAL_URI", "mongodb://localhost:27017")
        monkeypatch.setenv("MONGO_LOCAL_DB", "test_local")

        out = mongo_conn.reconnect_databases(app)
        assert out["remote"] is True  # sin URI: se considera "ok" (vacio intencional)

    def test_reconnect_with_invalid_local_uri(self, mongo_mock, monkeypatch):
        from flask import Flask
        app = Flask(__name__)
        app.mongo_local = mongo_conn.mongo_local

        def _bad_client(*a, **k):
            raise RuntimeError("invalid")

        monkeypatch.setattr(mongo_conn, "MongoClient", _bad_client)
        out = mongo_conn.reconnect_databases(app)
        assert out["local"] is False
        assert out["errors"]


class TestPersistUserNickname:
    def test_no_op_when_no_uri(self, monkeypatch):
        monkeypatch.delenv("APP_USER_NICKNAME", raising=False)
        # No revienta con cadena vacia
        mongo_conn._persist_user_nickname("")

    def test_no_op_when_same_nickname(self, monkeypatch):
        monkeypatch.setenv("APP_USER_NICKNAME", "alice")
        mongo_conn._persist_user_nickname("mongodb+srv://alice:pwd@host")


class TestInternetAvailable:
    def test_returns_false_when_no_network(self, monkeypatch):
        import socket as _socket

        def _no_net(*a, **k):
            raise OSError("no net")

        monkeypatch.setattr(_socket, "create_connection", _no_net)
        assert mongo_conn.internet_available() is False
