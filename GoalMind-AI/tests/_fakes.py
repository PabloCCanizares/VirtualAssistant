"""Dobles de prueba reutilizables (LLM, GridFS) para tests de integracion y funcionales.

Convivencia con tests unitarios: el `_FakeLLM` original de `tests/test_llm_utils.py`
sigue funcionando para verificar la politica de reintentos. Aqui se anaden dos
variantes mas potentes:

- `ScriptedLLM`: dispatcher por *marker* en el system prompt; util para
  ejercitar el grafo completo (supervisor + action_planner + ...).
- `InMemoryGridFSBucket`: bucket GridFS de memoria, sustituto del bucket real
  para los tests que tocan documentos binarios sin requerir Mongo.
"""

from __future__ import annotations

import json
from io import BytesIO
from types import SimpleNamespace
from typing import Any, Callable, Iterable, Mapping

from bson import ObjectId
from langchain_core.messages import BaseMessage, SystemMessage


# ---------------------------------------------------------------------------
# LLM guionizado por marcador en el system prompt
# ---------------------------------------------------------------------------

class ScriptedLLM:
    """LLM falso cuya respuesta depende del *system prompt* recibido.

    Uso tipico:
        llm = ScriptedLLM(routes={
            "SUPERVISOR_PROMPT_MARKER": '{"category": "action"}',
            "ACTION_PLANNER_PROMPT_MARKER": json.dumps({"actions": [...]}),
        })

    Las claves del dict son *substrings* a buscar en cualquier `SystemMessage`
    del input. La primera coincidencia gana. Los valores pueden ser:
      - `str`: se devuelve tal cual (envuelto en SimpleNamespace(content=...)).
      - `callable`: se invoca con la lista de mensajes y debe devolver str.
      - `Exception`: se lanza.

    Si no hay match, se busca la clave `"_default"`; si tampoco hay, se
    lanza `AssertionError` con el primer system prompt encontrado (para que
    el test falle visiblemente y se anada la ruta que faltaba).
    """

    def __init__(
        self,
        routes: Mapping[str, str | Callable[[list], str] | Exception],
        *,
        capture_calls: bool = True,
    ) -> None:
        self.routes = dict(routes)
        self.capture_calls = capture_calls
        self.calls: list[dict[str, Any]] = []

    def invoke(self, messages: Iterable[BaseMessage]):
        msgs = list(messages)
        system_text = "\n".join(
            m.content for m in msgs if isinstance(m, SystemMessage)
        )
        if self.capture_calls:
            self.calls.append({
                "system_text": system_text,
                "num_messages": len(msgs),
            })

        for marker, response in self.routes.items():
            if marker == "_default":
                continue
            if marker in system_text:
                return self._materialize(response, msgs)

        if "_default" in self.routes:
            return self._materialize(self.routes["_default"], msgs)

        snippet = system_text[:300].replace("\n", " ")
        raise AssertionError(
            f"ScriptedLLM: ninguna ruta coincide. system_prompt[:300]={snippet!r}"
        )

    @staticmethod
    def _materialize(response, msgs):
        if isinstance(response, Exception):
            raise response
        if callable(response):
            return SimpleNamespace(content=response(msgs))
        return SimpleNamespace(content=response)


def supervisor_response(category: str, *, use_critic: bool = False, **extras) -> str:
    """Construye un JSON minimo valido como respuesta del supervisor."""
    payload = {"category": category, "use_critic": use_critic, **extras}
    return json.dumps(payload, ensure_ascii=False)


def action_planner_response(actions: list[dict], *, clarification: str | None = None) -> str:
    """Construye un JSON valido como respuesta del action_planner."""
    if clarification:
        return json.dumps({"clarification_question": clarification})
    return json.dumps({"actions": actions}, ensure_ascii=False)


# ---------------------------------------------------------------------------
# GridFS in-memory (sustituto de GridFSBucket sin tocar Mongo)
# ---------------------------------------------------------------------------

class InMemoryGridFSBucket:
    """Mini-bucket GridFS sobre dict. Compatible en interfaz con GridFSBucket.

    Solo implementa los metodos que usa el codigo del proyecto:
    `upload_from_stream`, `open_download_stream` y `delete`.
    """

    def __init__(self) -> None:
        self.files: dict[ObjectId, tuple[bytes, str, dict]] = {}

    def upload_from_stream(self, filename: str, stream, metadata=None) -> ObjectId:
        try:
            stream.seek(0)
        except Exception:
            pass
        data = stream.read()
        file_id = ObjectId()
        self.files[file_id] = (data, filename, dict(metadata or {}))
        return file_id

    def open_download_stream(self, file_id):
        oid = ObjectId(str(file_id))
        if oid not in self.files:
            from gridfs.errors import NoFile
            raise NoFile(f"no such file: {file_id}")
        data, _, _ = self.files[oid]
        return BytesIO(data)

    def delete(self, file_id):
        oid = ObjectId(str(file_id))
        if oid not in self.files:
            from gridfs.errors import NoFile
            raise NoFile(f"no such file: {file_id}")
        del self.files[oid]
