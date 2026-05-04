import logging
import time
from typing import Sequence

from langchain_core.messages import BaseMessage


logger = logging.getLogger(__name__)


class LLMInvokeError(RuntimeError):
    """Error al invocar el modelo tras agotar retries."""


def _extract_text(content) -> str:
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = [
            block.get("text", "") if isinstance(block, dict) else str(block)
            for block in content
            if not isinstance(block, dict) or block.get("type") == "text"
        ]
        return "".join(parts).strip()
    return str(content).strip()


def invoke_with_retry(
    llm,
    messages: Sequence[BaseMessage],
    *,
    retries: int = 1,
    backoff_seconds: float = 0.3,
) -> str:
    """
    Invoca un modelo LLM con retry simple y backoff exponencial.

    Args:
        llm: Instancia compatible con .invoke(messages).
        messages: Lista de mensajes de LangChain.
        retries: Número de reintentos tras el intento inicial.
        backoff_seconds: Espera base para backoff exponencial.

    Returns:
        Contenido de texto normalizado.

    Raises:
        LLMInvokeError: si todos los intentos fallan.
    """
    attempts = max(1, retries + 1)
    last_exc = None

    for attempt in range(attempts):
        try:
            response = llm.invoke(list(messages))
            return _extract_text(response.content or "")
        except Exception as exc:  # pragma: no cover - cobertura por tests de integración
            last_exc = exc
            if attempt >= attempts - 1:
                break
            delay = backoff_seconds * (2 ** attempt)
            logger.warning(
                "LLM invocation failed (attempt %s/%s): %s",
                attempt + 1,
                attempts,
                exc,
            )
            time.sleep(delay)

    raise LLMInvokeError("No se pudo completar la invocación del modelo.") from last_exc
