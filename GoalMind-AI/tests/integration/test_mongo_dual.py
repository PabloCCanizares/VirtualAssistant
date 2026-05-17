"""Tests de integracion sobre la persistencia dual (local + remoto).

Sustituye los dos clientes Mongo por instancias de `mongomock`. El cliente
"remoto" representa Atlas y se puede desactivar para simular ausencia de red.

Cobertura:
- Conmutacion entre modos (local-only / dual) sin perdida de datos locales.
- Comportamiento de `ensure_remote_connection` cuando no hay internet o no
  hay URI configurada.
- Reconexion contra una URI valida una vez recuperada la conectividad.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration


def _insert_task(local_db, contenido="tarea local"):
    return local_db["Tasks"].insert_one({
        "contenido": contenido,
        "usuario_id": "66ffbbbbbbbbbbbbbbbb0100",
    })


class TestEnsureRemoteConnection:
    """`ensure_remote_connection` debe responder a la presencia de URI e internet."""

    def test_returns_true_when_remote_already_set(self):
        from database import mongo_conn

        assert mongo_conn.ensure_remote_connection() is True

    def test_returns_false_when_no_internet_and_no_remote(
        self, no_remote, offline, monkeypatch
    ):
        from database import mongo_conn

        # Aunque exista la URI configurada, sin internet no se intenta conectar.
        monkeypatch.setattr(mongo_conn, "_configured_remote_uri", "mongodb://stub")
        assert mongo_conn.ensure_remote_connection() is False

    def test_returns_false_when_no_uri_configured(self, no_remote, online, monkeypatch):
        from database import mongo_conn

        monkeypatch.setattr(mongo_conn, "_configured_remote_uri", "")
        # Sin URI, no se intenta crear cliente aunque haya internet.
        assert mongo_conn.ensure_remote_connection() is False

    def test_reconnects_when_internet_returns_and_uri_present(
        self, no_remote, online, monkeypatch, mongo_mock
    ):
        from database import mongo_conn

        # Sustituye el factory de clientes Mongo para devolver mongomock en
        # lugar de intentar abrir un socket real contra "stub".
        monkeypatch.setattr(
            mongo_conn,
            "_create_mongo_client",
            lambda uri: mongo_mock.remote_client,
        )
        monkeypatch.setattr(mongo_conn, "_configured_remote_uri", "mongodb://stub")

        assert mongo_conn.ensure_remote_connection() is True
        assert mongo_conn.mongo_remote is mongo_mock.remote_client


class TestLocalOnlyMode:
    """Sin remoto, las operaciones locales siguen siendo coherentes."""

    def test_get_collection_returns_none_for_remote_when_disabled(self, no_remote):
        from database.mongo_conn import get_collection

        local, remote = get_collection("Tasks")
        assert local is not None
        assert remote is None

    def test_local_writes_visible_immediately(self, mongo_mock):
        from database.mongo_conn import get_collection

        local, _ = get_collection("Tasks")
        local.insert_one({"contenido": "tarea X", "usuario_id": "u1"})
        assert local.find_one({"contenido": "tarea X"})["usuario_id"] == "u1"


class TestSwitchingModes:
    """Pasar de local-only a dual (y viceversa) no destruye datos locales."""

    def test_local_data_preserved_when_remote_reattached(self, mongo_mock, monkeypatch):
        from database import mongo_conn

        local, _ = mongo_conn.get_collection("Tasks")
        local.insert_one({"_id": "task-1", "contenido": "previa", "usuario_id": "u1"})

        # Pasamos a modo local-only (desconectamos remoto)
        monkeypatch.setattr(mongo_conn, "mongo_remote", None)
        assert mongo_conn.get_collection("Tasks")[1] is None
        # La tarea sigue ahi.
        assert local.find_one({"_id": "task-1"})["contenido"] == "previa"

        # Reactivamos remoto con un nuevo cliente
        monkeypatch.setattr(mongo_conn, "mongo_remote", mongo_mock.remote_client)
        new_local, new_remote = mongo_conn.get_collection("Tasks")
        assert new_remote is not None
        # La tarea local no se ha tocado.
        assert new_local.find_one({"_id": "task-1"})["contenido"] == "previa"

    def test_remote_offline_does_not_block_local_inserts(
        self, mongo_mock, no_remote
    ):
        # Aunque no haya remoto, los modelos siguen escribiendo localmente.
        from model.task_model import TaskModel

        result = TaskModel.insert_task({"contenido": "off-line", "usuario_id": "u1"})
        assert result["_id"] is not None
        assert mongo_mock.local_db["Tasks"].find_one({"_id": result["_id"]})
