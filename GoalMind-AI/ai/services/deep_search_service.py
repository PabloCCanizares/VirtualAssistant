import json
import logging
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from ai.config import DeepSearchConfig, get_deep_search_config

logger = logging.getLogger(__name__)


class DeepSearchError(RuntimeError):
    """Error de búsqueda profunda (configuración, red o proveedor)."""


ProviderHandler = Callable[[str, DeepSearchConfig], list[dict[str, Any]]]


def _http_post_json(
    url: str,
    payload: dict[str, Any],
    *,
    headers: dict[str, str],
    timeout_seconds: int,
) -> dict[str, Any]:
    data = json.dumps(payload).encode("utf-8")
    request = Request(url, data=data, headers=headers, method="POST")
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            body = response.read().decode("utf-8")
            return json.loads(body) if body else {}
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        raise DeepSearchError(f"HTTP {exc.code} en proveedor de búsqueda: {detail}") from exc
    except URLError as exc:
        raise DeepSearchError(f"Error de red en proveedor de búsqueda: {exc}") from exc
    except Exception as exc:
        raise DeepSearchError(f"No se pudo completar la petición de búsqueda: {exc}") from exc


def _http_get_json(
    url: str,
    *,
    headers: dict[str, str],
    timeout_seconds: int,
) -> dict[str, Any]:
    request = Request(url, headers=headers, method="GET")
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            body = response.read().decode("utf-8")
            return json.loads(body) if body else {}
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        raise DeepSearchError(f"HTTP {exc.code} en proveedor de búsqueda: {detail}") from exc
    except URLError as exc:
        raise DeepSearchError(f"Error de red en proveedor de búsqueda: {exc}") from exc
    except Exception as exc:
        raise DeepSearchError(f"No se pudo completar la petición de búsqueda: {exc}") from exc


def _normalize_result(
    *,
    title: str,
    url: str,
    snippet: str,
    score: float | int | None,
    provider: str,
    raw: dict[str, Any],
) -> dict[str, Any] | None:
    normalized_url = (url or "").strip()
    if not normalized_url:
        return None

    normalized_title = (title or "").strip() or normalized_url
    normalized_snippet = (snippet or "").strip()
    normalized_score = 0.0
    if isinstance(score, (int, float)):
        normalized_score = float(score)

    return {
        "title": normalized_title,
        "url": normalized_url,
        "snippet": normalized_snippet,
        "score": normalized_score,
        "provider": provider,
        "raw": raw,
    }


def _dedupe_by_url(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_url: dict[str, dict[str, Any]] = {}
    for result in results:
        key = (result.get("url") or "").strip()
        if not key:
            continue
        current = by_url.get(key)
        if current is None or float(result.get("score", 0.0)) > float(current.get("score", 0.0)):
            by_url[key] = result

    deduped = list(by_url.values())
    deduped.sort(key=lambda item: float(item.get("score", 0.0)), reverse=True)
    return deduped


def _search_tavily(query: str, config: DeepSearchConfig) -> list[dict[str, Any]]:
    payload = {
        "api_key": config.api_key,
        "query": query,
        "max_results": config.max_results,
        "search_depth": "advanced",
    }
    data = _http_post_json(
        "https://api.tavily.com/search",
        payload,
        headers={"Content-Type": "application/json"},
        timeout_seconds=config.timeout_seconds,
    )
    normalized: list[dict[str, Any]] = []
    for item in data.get("results", []) or []:
        result = _normalize_result(
            title=item.get("title", ""),
            url=item.get("url", ""),
            snippet=item.get("content", ""),
            score=item.get("score"),
            provider="tavily",
            raw=item,
        )
        if result:
            normalized.append(result)
    return normalized


def _search_serper(query: str, config: DeepSearchConfig) -> list[dict[str, Any]]:
    payload = {"q": query, "num": config.max_results}
    data = _http_post_json(
        "https://google.serper.dev/search",
        payload,
        headers={
            "Content-Type": "application/json",
            "X-API-KEY": config.api_key or "",
        },
        timeout_seconds=config.timeout_seconds,
    )
    normalized: list[dict[str, Any]] = []
    for item in data.get("organic", []) or []:
        result = _normalize_result(
            title=item.get("title", ""),
            url=item.get("link", ""),
            snippet=item.get("snippet", ""),
            score=item.get("position"),
            provider="serper",
            raw=item,
        )
        if result:
            normalized.append(result)
    return normalized


def _search_brave(query: str, config: DeepSearchConfig) -> list[dict[str, Any]]:
    params = urlencode({"q": query, "count": config.max_results})
    data = _http_get_json(
        f"https://api.search.brave.com/res/v1/web/search?{params}",
        headers={"X-Subscription-Token": config.api_key or ""},
        timeout_seconds=config.timeout_seconds,
    )
    normalized: list[dict[str, Any]] = []
    for item in ((data.get("web") or {}).get("results") or []):
        result = _normalize_result(
            title=item.get("title", ""),
            url=item.get("url", ""),
            snippet=item.get("description", ""),
            score=item.get("page_age"),  # Brave no expone score directo consistente
            provider="brave",
            raw=item,
        )
        if result:
            normalized.append(result)
    return normalized


PROVIDER_HANDLERS: dict[str, ProviderHandler] = {
    "tavily": _search_tavily,
    "serper": _search_serper,
    "brave": _search_brave,
}


def deep_search(query: str, *, config: DeepSearchConfig | None = None) -> list[dict[str, Any]]:
    cleaned_query = (query or "").strip()
    if not cleaned_query:
        return []

    current = config or get_deep_search_config()
    if not current.enabled:
        raise DeepSearchError("Deep search está deshabilitado por configuración.")
    if not (current.api_key or "").strip():
        raise DeepSearchError("Falta DEEP_SEARCH_API_KEY para búsqueda profunda.")

    handler = PROVIDER_HANDLERS.get(current.provider)
    if handler is None:
        raise DeepSearchError(f"Proveedor de deep search no soportado: {current.provider}")

    try:
        raw_results = handler(cleaned_query, current)
    except DeepSearchError:
        raise
    except Exception as exc:
        logger.exception("deep_search: fallo inesperado en proveedor %s", current.provider)
        raise DeepSearchError("No se pudo completar la búsqueda profunda.") from exc

    deduped = _dedupe_by_url(raw_results)
    return deduped[: current.max_results]
