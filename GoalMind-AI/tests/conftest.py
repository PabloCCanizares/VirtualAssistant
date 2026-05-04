"""Configuracion comun para todos los tests unitarios.

- Inserta la raiz del proyecto en sys.path para permitir imports absolutos
  (ai.*, controllers.*, model.*, database.*, etc.) sin necesidad de instalar
  el paquete.
- Limpia variables de entorno sensibles para que las funciones que leen
  configuracion del .env se comporten de forma determinista.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


_ENV_VARS_TO_CLEAR = (
    "LLM_PROVIDER",
    "OPENAI_API_KEY",
    "OPENAI_MODEL",
    "GEMINI_API_KEY",
    "GEMINI_MODEL",
    "GROQ_API_KEY",
    "GROQ_MODEL",
    "DEFAULT_USER_ID",
    "DEEP_SEARCH_ENABLED",
    "DEEP_SEARCH_PROVIDER",
    "DEEP_SEARCH_API_KEY",
    "DEEP_SEARCH_MAX_RESULTS",
    "DEEP_SEARCH_TIMEOUT_SECONDS",
    "DEEP_SEARCH_MAX_SOURCES",
    "DEEP_SEARCH_MODE_DEFAULT",
    "DEEP_RESEARCH_MAX_ITERATIONS",
    "DEEP_RESEARCH_MAX_TASKS",
    "DEEP_RESEARCH_MAX_QUERIES_PER_TASK",
    "DEEP_RESEARCH_QUALITY_THRESHOLD",
    "DEEP_RESEARCH_STAGNATION_LIMIT",
    "DEEP_RESEARCH_LOOP_REPEAT_LIMIT",
    "DEEP_RESEARCH_MAX_REPORT_SOURCES",
    "DEEP_RESEARCH_INTERNAL_SOURCE_LIMIT",
    "DEEP_RESEARCH_PARALLEL_QUERIES",
    "FLASK_ENV",
    "FLASK_DEBUG",
    "FLASK_SECRET_KEY",
    "APP_USER_NICKNAME",
    "LOG_LEVEL",
)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Aisla cada test del entorno: borra variables relevantes antes de ejecutarlo."""
    for var in _ENV_VARS_TO_CLEAR:
        monkeypatch.delenv(var, raising=False)
    yield


@pytest.fixture
def reset_pending_actions():
    """Limpia el almacen en memoria de acciones pendientes antes y despues del test."""
    from ai.services.action_state import _pending_actions

    _pending_actions.clear()
    yield
    _pending_actions.clear()


@pytest.fixture
def reset_session_mutations():
    """Limpia el almacen en memoria de mutaciones de sesion."""
    from ai.services.session_mutations_state import _session_mutations

    _session_mutations.clear()
    yield
    _session_mutations.clear()
