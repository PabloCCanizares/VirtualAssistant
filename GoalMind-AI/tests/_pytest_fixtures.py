"""Fixtures compartidas por los niveles de integracion y aceptacion.

Este modulo NO es un `conftest.py`: se importa via `from tests._pytest_fixtures
import *` en cada `conftest.py` que las necesite (`tests/integration/conftest.py`
y `tests/functional/conftest.py`). De esta forma evitamos duplicar codigo y
mantenemos los tests unitarios libres de estos *autouse* mas pesados (Mongo
mock, GridFS, etc.).

Reemplazan las dependencias externas del sistema con dobles deterministas:
- MongoDB local y remoto -> dos clientes `mongomock` independientes inyectados
  en `database.mongo_conn.mongo_local.cx` y `database.mongo_conn.mongo_remote`.
- GridFS -> `InMemoryGridFSBucket` (uno local + uno remoto).
- Internet check -> los fixtures `online` / `offline` fuerzan
  `mongo_conn.internet_available()` a True o False.
- LLM -> `patch_llm` cablea una instancia (`ScriptedLLM` o cualquier doble) en
  `ai.config.build_llm` y `ai.graph.build_llm`.
- Variables de entorno minimas para que `chat_service.stream_chat` no aborte.
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import mongomock
import pytest

# Permitir `from tests._fakes import ...` desde cualquier nivel.
TESTS_DIR = Path(__file__).resolve().parent
if str(TESTS_DIR.parent) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR.parent))

from tests._fakes import InMemoryGridFSBucket, ScriptedLLM  # noqa: E402, F401


@pytest.fixture(autouse=True)
def mongomock_bulk_compat(monkeypatch):
    """Workaround de version: pymongo >= 4.15 envia `sort=` a `add_replace` /
    `add_update_*` via `ReplaceOne._add_to_bulk`, pero mongomock 4.3 (ultima
    version) no lo acepta. Envolvemos los metodos para ignorar kwargs
    desconocidos.
    """
    from mongomock.collection import BulkOperationBuilder

    def _wrap(name):
        original = getattr(BulkOperationBuilder, name)

        def wrapped(self, selector, *args, collation=None, hint=None, **_ignored):
            return original(self, selector, *args, collation=collation, hint=hint)

        monkeypatch.setattr(BulkOperationBuilder, name, wrapped)

    for method in ("add_replace", "add_update_one", "add_update_many"):
        if hasattr(BulkOperationBuilder, method):
            _wrap(method)


@pytest.fixture(autouse=True)
def llm_env(monkeypatch):
    """Variables de entorno minimas para que `chat_service.stream_chat` no aborte."""
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_MODEL", "test-model")
    monkeypatch.setenv("DEFAULT_USER_ID", "66ffbbbbbbbbbbbbbbbb0100")
    monkeypatch.setenv("APP_USER_NICKNAME", "")
    monkeypatch.delenv("MONGO_REMOTE_URI", raising=False)
    monkeypatch.delenv("MONGO_LOCAL_URI", raising=False)


@pytest.fixture(autouse=True)
def mongo_mock(monkeypatch):
    """Sustituye los clientes Mongo local y remoto por instancias de mongomock."""
    from database import mongo_conn

    local_client = mongomock.MongoClient()
    remote_client = mongomock.MongoClient()

    monkeypatch.setattr(mongo_conn, "_local_db_name", "test_local")
    monkeypatch.setattr(mongo_conn, "_remote_db_name", "test_remote")
    monkeypatch.setattr(mongo_conn, "_configured_remote_uri", "mongodb://stub")
    monkeypatch.setattr(mongo_conn.mongo_local, "cx", local_client, raising=False)
    monkeypatch.setattr(mongo_conn, "mongo_remote", remote_client)

    return SimpleNamespace(
        local_client=local_client,
        remote_client=remote_client,
        local_db=local_client["test_local"],
        remote_db=remote_client["test_remote"],
    )


@pytest.fixture(autouse=True)
def gridfs_patch(monkeypatch):
    """Sustituye los buckets GridFS por buckets en memoria."""
    from database import gridfs_storage

    local_bucket = InMemoryGridFSBucket()
    remote_bucket = InMemoryGridFSBucket()

    monkeypatch.setattr(gridfs_storage, "get_local_gridfs_bucket", lambda: local_bucket)

    def _remote_bucket(app=None):
        from database import mongo_conn

        if mongo_conn.mongo_remote is None:
            return None
        return remote_bucket

    monkeypatch.setattr(gridfs_storage, "get_remote_gridfs_bucket", _remote_bucket)

    return SimpleNamespace(local=local_bucket, remote=remote_bucket)


@pytest.fixture(autouse=True)
def clean_state():
    """Limpia los almacenes globales en memoria entre tests."""
    from ai.services.action_state import _pending_actions
    from ai.services.session_mutations_state import _session_mutations

    _pending_actions.clear()
    _session_mutations.clear()
    yield
    _pending_actions.clear()
    _session_mutations.clear()


@pytest.fixture
def reset_pending_actions():
    from ai.services.action_state import _pending_actions

    _pending_actions.clear()
    yield
    _pending_actions.clear()


@pytest.fixture
def reset_session_mutations():
    from ai.services.session_mutations_state import _session_mutations

    _session_mutations.clear()
    yield
    _session_mutations.clear()


@pytest.fixture
def offline(monkeypatch):
    """`internet_available()` devuelve False durante el test."""
    from database import mongo_conn

    monkeypatch.setattr(mongo_conn, "internet_available", lambda: False)


@pytest.fixture
def online(monkeypatch):
    """`internet_available()` devuelve True durante el test."""
    from database import mongo_conn

    monkeypatch.setattr(mongo_conn, "internet_available", lambda: True)


@pytest.fixture
def no_remote(monkeypatch):
    """Anula el cliente Mongo remoto para simular 'solo local'."""
    from database import mongo_conn

    monkeypatch.setattr(mongo_conn, "mongo_remote", None)


@pytest.fixture
def patch_llm(monkeypatch):
    """Inyecta una instancia de LLM en todos los puntos donde se invoca `build_llm`.

    Cubre el modulo `ai.config`, el grafo (`ai.graph`) y, si ya esta cargado,
    el servicio de resumen (`ai.services.doc_summarize_service`), que importa
    `build_llm` en su propio namespace.
    """

    def _patch(llm_instance):
        import sys

        from ai import config as ai_config
        import ai.graph as graph_module

        fake = lambda model=None: llm_instance  # noqa: E731

        monkeypatch.setattr(ai_config, "build_llm", fake)
        monkeypatch.setattr(graph_module, "build_llm", fake)
        # `doc_summarize_service` y `chat_service` hacen `from ai.config import build_llm`,
        # creando referencias locales. Si ya estan importados, parchear esa referencia.
        for mod_name in (
            "ai.services.doc_summarize_service",
            "ai.services.chat_service",
        ):
            mod = sys.modules.get(mod_name)
            if mod is not None and hasattr(mod, "build_llm"):
                monkeypatch.setattr(mod, "build_llm", fake)
        return llm_instance

    return _patch


@pytest.fixture
def flask_client():
    """Construye un cliente de pruebas Flask con `ai_chat_bp` registrado."""
    from flask import Flask

    from controllers.ai_chat_controller import ai_chat_bp

    app = Flask(__name__)
    app.config["TESTING"] = True
    app.secret_key = "test-secret"
    app.register_blueprint(ai_chat_bp)
    return app.test_client()


@pytest.fixture
def scripted_llm():
    """Factoria de `ScriptedLLM` para los tests de grafo."""

    def _factory(routes):
        return ScriptedLLM(routes=routes)

    return _factory
