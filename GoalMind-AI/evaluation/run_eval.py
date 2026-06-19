#!/usr/bin/env python3
"""Runner de evaluacion del asistente GoalMind-AI (bloque 5.4 de la memoria).

Ejecuta cada prompt del dataset `evaluation/dataset/prompts.jsonl` contra el
grafo de agentes con el LLM real (configurado por env: `LLM_PROVIDER` +
`OPENAI_API_KEY` / `GEMINI_API_KEY` / `GROQ_API_KEY`). La base de datos se
puebla en memoria a partir de `evaluation/dataset/db_fixture.json`.

Metricas emitidas:
- Clasificacion de intencion: precision global + por categoria, mas matriz
  de confusion.
- Exito de planes CRUD: para prompts de tipo `action`, comparacion entre la
  cola de acciones esperada y la generada por `action_planner`. Se compara
  por tupla `(op, entity)` y, cuando el referente es no nulo, por
  substring sobre los parametros de la accion.
- Aclaraciones: numero de veces que el sistema pide clarificacion (i.e. el
  flujo termina con `?` o sin ejecutar acciones cuando se esperaba una);
  se reportan cuantas eran realmente ambiguas (aclaracion pertinente) y
  cuantas no (friccion innecesaria).
- Errores por ambiguedad: prompts con `ambiguity != "low"` en los que el
  sistema NO pidio clarificacion y aun asi ejecuto algo.
- Latencia: tiempo total por prompt (segundos). Se reporta p50/p95/p99.

Uso:
    python evaluation/run_eval.py [--limit N] [--provider openai|gemini|groq]

Sin --provider, se respeta `LLM_PROVIDER` del entorno.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import statistics
import sys
import time
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("eval")

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DATASET_PATH = ROOT / "evaluation" / "dataset" / "prompts.jsonl"
FIXTURE_PATH = ROOT / "evaluation" / "dataset" / "db_fixture.json"
RESULTS_DIR = ROOT / "evaluation" / "results"


# ---------------------------------------------------------------------------
# Tipos
# ---------------------------------------------------------------------------


@dataclass
class PromptResult:
    prompt_id: str
    prompt: str
    expected_intent: str
    expected_clarification: bool
    ambiguity: str
    actual_intent: str | None = None
    intent_match: bool = False
    asked_clarification: bool = False
    clarification_pertinent: bool | None = None
    expected_actions: list[dict] | None = None
    actual_actions: list[dict] | None = None
    actions_match: bool | None = None
    duration_seconds: float | None = None
    final_reply: str = ""
    error: str | None = None


@dataclass
class Aggregates:
    n_prompts: int = 0
    n_errors: int = 0
    intent_accuracy: float = 0.0
    intent_accuracy_per_category: dict[str, float] = field(default_factory=dict)
    confusion_matrix: dict[str, dict[str, int]] = field(default_factory=dict)
    action_match_rate: float | None = None
    n_action_prompts: int = 0
    asked_clarifications: int = 0
    pertinent_clarifications: int = 0
    unnecessary_clarifications: int = 0
    silent_on_ambiguous: int = 0
    latency_p50: float | None = None
    latency_p95: float | None = None
    latency_p99: float | None = None
    latency_mean: float | None = None


# ---------------------------------------------------------------------------
# Carga de dataset / fixture y configuracion de la BD
# ---------------------------------------------------------------------------


def load_dataset() -> list[dict]:
    with DATASET_PATH.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def load_fixture() -> dict:
    with FIXTURE_PATH.open(encoding="utf-8") as f:
        return json.load(f)


def setup_mongo(fixture: dict):
    """Crea dos `mongomock.MongoClient` y los inyecta en `database.mongo_conn`.

    Devuelve una tupla `(local_client, remote_client)` para que el caller
    los pueda interrogar si lo necesita.
    """
    import mongomock
    from bson import ObjectId

    from database import gridfs_storage, mongo_conn

    # Workaround pymongo 4.15+ vs mongomock 4.3 (kwarg `sort` en bulk_write).
    from mongomock.collection import BulkOperationBuilder

    for method in ("add_replace", "add_update_one", "add_update_many"):
        if hasattr(BulkOperationBuilder, method):
            original = getattr(BulkOperationBuilder, method)

            def _wrap(orig):
                def wrapped(self, selector, *args, collation=None, hint=None, **_):
                    return orig(self, selector, *args, collation=collation, hint=hint)
                return wrapped
            setattr(BulkOperationBuilder, method, _wrap(original))

    local_client = mongomock.MongoClient()
    remote_client = mongomock.MongoClient()

    mongo_conn._local_db_name = "test_local"
    mongo_conn._remote_db_name = "test_remote"
    mongo_conn._configured_remote_uri = "mongodb://stub"
    mongo_conn.mongo_local.cx = local_client
    mongo_conn.mongo_remote = remote_client

    # GridFS in-memory para evitar tocar el sistema de ficheros real.
    class _Bucket:
        def __init__(self):
            self.files = {}

        def upload_from_stream(self, name, stream, metadata=None):
            from bson import ObjectId
            fid = ObjectId()
            stream.seek(0)
            self.files[fid] = (stream.read(), name, metadata or {})
            return fid

        def open_download_stream(self, fid):
            from gridfs.errors import NoFile
            from io import BytesIO
            fid = ObjectId(str(fid))
            if fid not in self.files:
                raise NoFile(str(fid))
            return BytesIO(self.files[fid][0])

        def delete(self, fid):
            from gridfs.errors import NoFile
            fid = ObjectId(str(fid))
            if fid not in self.files:
                raise NoFile(str(fid))
            del self.files[fid]

    local_bucket = _Bucket()
    remote_bucket = _Bucket()
    gridfs_storage.get_local_gridfs_bucket = lambda: local_bucket
    gridfs_storage.get_remote_gridfs_bucket = lambda app=None: (
        remote_bucket if mongo_conn.mongo_remote is not None else None
    )

    # Poblado de colecciones desde el fixture.
    local_db = local_client["test_local"]
    user_id = fixture.get("usuario_id", "66ffbbbbbbbbbbbbbbbb0100")
    for col in ("Projects", "Goals", "Tasks", "Events", "ProjectDocuments", "Categories"):
        docs = []
        for raw in fixture.get(col, []):
            doc = dict(raw)
            # Convertir _id y referencias hex a ObjectId
            for key in ("_id", "project_id", "objetivo_id"):
                val = doc.get(key)
                if isinstance(val, str) and len(val) == 24:
                    try:
                        doc[key] = ObjectId(val)
                    except Exception:
                        pass
            doc.setdefault("usuario_id", user_id)
            docs.append(doc)
        if docs:
            local_db[col].insert_many(docs)

    return local_client, remote_client


# ---------------------------------------------------------------------------
# Instrumentacion del grafo para capturar intent + action queue
# ---------------------------------------------------------------------------


class GraphProbe:
    """Captura la salida del `supervisor` y del `action_planner` durante un run."""

    def __init__(self):
        self.supervisor_route: str | None = None
        self.actions_emitted: list[dict] | None = None
        self.asked_clarification: bool = False
        self.draft_response_seen: str = ""

    def install(self):
        from ai.agents import supervisor as supervisor_mod
        from ai.agents import action_planner as planner_mod

        original_supervisor = supervisor_mod.supervisor_node
        original_planner = planner_mod.action_planner_node

        def wrapped_supervisor(state, llm):
            result = original_supervisor(state, llm)
            self.supervisor_route = (
                result.get("query_type")
                or result.get("route")
                or self.supervisor_route
            )
            if (result.get("final_response") or "").strip().endswith("?"):
                self.asked_clarification = True
            return result

        def wrapped_planner(state, llm):
            result = original_planner(state, llm)
            # Si planner pidio aclaracion: hay draft_response sin queue.
            if result.get("draft_response") and not result.get("action_queue"):
                self.asked_clarification = True
                self.draft_response_seen = result["draft_response"]
            # Si planner produjo la cola, la capturamos.
            if isinstance(result.get("action_queue"), list):
                self.actions_emitted = result["action_queue"]
            # Si planner exigio confirmacion, captura la cola que dejo pendiente.
            pending = result.get("pending_action_intent")
            if pending and pending.get("action_name") == "__queue__":
                self.actions_emitted = pending.get("parameters", {}).get("queue", [])
            return result

        supervisor_mod.supervisor_node = wrapped_supervisor
        planner_mod.action_planner_node = wrapped_planner

        # Tambien re-inyectar en ai.agents.__init__ y ai.graph si ya importaron.
        from ai import agents
        agents.supervisor_node = wrapped_supervisor
        agents.action_planner_node = wrapped_planner
        import ai.graph as graph_mod
        graph_mod.supervisor_node = wrapped_supervisor
        graph_mod.action_planner_node = wrapped_planner


# ---------------------------------------------------------------------------
# Evaluacion de un prompt
# ---------------------------------------------------------------------------


_INTENT_NORMALIZER = {
    "weekly_summary": "weekly_summary",
    "weekly_plan": "weekly_plan",
    "deep_research": "deep_research",
    "research": "research",
    "action": "action",
    "recommendations": "recommendations",
    "progress": "progress",
    "document": "document",
    None: "unknown",
}


def normalize_intent(route: str | None) -> str:
    if route is None:
        return "unknown"
    return _INTENT_NORMALIZER.get(route, route)


def compare_action_lists(expected: list[dict] | None, actual: list[dict] | None) -> bool | None:
    """Compara dos listas de acciones por tupla (op, entity).

    El campo `ref` del esperado se cruza con `action_parameters` por substring
    (`titulo`, `contenido` o cualquier valor textual).
    """
    if not expected:
        return None
    if not actual:
        return False
    # Mapa esperado: lista de (op, entity, ref)
    op_to_action = {
        "create_project": ("create", "project"),
        "create_goal": ("create", "goal"),
        "create_task": ("create", "task"),
        "create_event": ("create", "event"),
        "delete_project": ("delete", "project"),
        "delete_goal": ("delete", "goal"),
        "delete_task": ("delete", "task"),
        "delete_event": ("delete", "event"),
        "update_project": ("update", "project"),
        "update_goal": ("update", "goal"),
        "update_task": ("update", "task"),
        "mark_task_complete": ("mark_complete", "task"),
    }
    actual_tuples = []
    for a in actual:
        key = a.get("action_name")
        if key not in op_to_action:
            continue
        op, entity = op_to_action[key]
        params = a.get("action_parameters") or {}
        ref_value = " ".join(str(v) for v in params.values() if isinstance(v, str))
        actual_tuples.append((op, entity, ref_value.lower()))

    for exp in expected:
        op = exp.get("op")
        entity = exp.get("entity")
        ref = (exp.get("ref") or "").lower()
        found = False
        for op_a, entity_a, ref_a in actual_tuples:
            if op_a == op and entity_a == entity:
                if not ref or ref in ref_a:
                    found = True
                    break
        if not found:
            return False
    return True


def evaluate_prompt(record: dict, llm, fixture: dict) -> PromptResult:
    """Ejecuta un prompt contra el grafo y mide los indicadores."""
    from langchain_core.messages import HumanMessage

    from ai.graph import build_chat_graph

    probe = GraphProbe()
    probe.install()
    app_graph = build_chat_graph(llm)

    state = {
        "messages": [HumanMessage(content=record["prompt"])],
        "context_json": "{}",
        "user_id": fixture.get("usuario_id", "66ffbbbbbbbbbbbbbbbb0100"),
        "session_mutations_json": "[]",
        "deep_search_mode": "auto",
        "deep_search_requested": False,
        "deep_search_error": "",
    }

    result = PromptResult(
        prompt_id=record["id"],
        prompt=record["prompt"],
        expected_intent=record["expected_intent"],
        expected_clarification=record.get("expected_clarification", False),
        ambiguity=record.get("ambiguity", "low"),
        expected_actions=record.get("expected_actions"),
    )

    t0 = time.perf_counter()
    try:
        final_state = app_graph.invoke(state, config={"recursion_limit": 50})
        result.final_reply = (final_state.get("final_response") or "").strip()
    except Exception as exc:
        result.error = f"{type(exc).__name__}: {exc}"
    finally:
        result.duration_seconds = time.perf_counter() - t0

    result.actual_intent = normalize_intent(probe.supervisor_route)
    result.intent_match = result.actual_intent == result.expected_intent
    result.asked_clarification = (
        probe.asked_clarification
        or result.final_reply.strip().endswith("?")
        or "no he podido identificar" in result.final_reply.lower()
    )
    result.actual_actions = probe.actions_emitted
    result.actions_match = compare_action_lists(result.expected_actions, probe.actions_emitted)

    if result.ambiguity == "low":
        result.clarification_pertinent = False if result.asked_clarification else None
    else:
        result.clarification_pertinent = result.asked_clarification

    return result


# ---------------------------------------------------------------------------
# Agregaciones e informes
# ---------------------------------------------------------------------------


def aggregate(results: list[PromptResult]) -> Aggregates:
    agg = Aggregates(n_prompts=len(results))
    agg.n_errors = sum(1 for r in results if r.error)

    # Intent
    intents_correct = [r for r in results if r.intent_match and not r.error]
    agg.intent_accuracy = len(intents_correct) / len(results) if results else 0.0

    # Por categoria
    bucket = defaultdict(lambda: [0, 0])  # [correct, total]
    for r in results:
        bucket[r.expected_intent][1] += 1
        if r.intent_match:
            bucket[r.expected_intent][0] += 1
    agg.intent_accuracy_per_category = {
        cat: (c / t if t else 0.0) for cat, (c, t) in bucket.items()
    }

    # Matriz de confusion
    cm: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for r in results:
        actual = r.actual_intent or "unknown"
        cm[r.expected_intent][actual] += 1
    agg.confusion_matrix = {k: dict(v) for k, v in cm.items()}

    # Action match rate
    action_results = [r for r in results if r.expected_actions]
    agg.n_action_prompts = len(action_results)
    if action_results:
        agg.action_match_rate = sum(1 for r in action_results if r.actions_match) / len(action_results)

    # Aclaraciones
    asked = [r for r in results if r.asked_clarification]
    agg.asked_clarifications = len(asked)
    agg.pertinent_clarifications = sum(1 for r in asked if r.ambiguity != "low")
    agg.unnecessary_clarifications = sum(1 for r in asked if r.ambiguity == "low")
    agg.silent_on_ambiguous = sum(
        1 for r in results if r.ambiguity != "low" and not r.asked_clarification
    )

    # Latencias
    durations = [r.duration_seconds for r in results if r.duration_seconds is not None]
    if durations:
        durations.sort()
        agg.latency_mean = statistics.mean(durations)

        def _pct(p):
            k = max(0, min(len(durations) - 1, int(round(p / 100 * (len(durations) - 1)))))
            return durations[k]

        agg.latency_p50 = _pct(50)
        agg.latency_p95 = _pct(95)
        agg.latency_p99 = _pct(99)

    return agg


def emit_reports(timestamp: str, results: list[PromptResult], agg: Aggregates):
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    json_path = RESULTS_DIR / f"run_{timestamp}.json"
    md_path = RESULTS_DIR / f"run_{timestamp}.md"

    json_path.write_text(json.dumps({
        "timestamp": timestamp,
        "n_prompts": len(results),
        "results": [asdict(r) for r in results],
        "aggregates": asdict(agg),
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    md = []
    md.append(f"# Evaluacion {timestamp}")
    md.append("")
    md.append(f"- **Prompts evaluados**: {agg.n_prompts}")
    md.append(f"- **Errores de ejecucion**: {agg.n_errors}")
    md.append(f"- **Precision global de intencion**: {agg.intent_accuracy*100:.2f}%")
    if agg.action_match_rate is not None:
        md.append(
            f"- **Tasa de exito de planes CRUD**: "
            f"{agg.action_match_rate*100:.2f}% sobre {agg.n_action_prompts} prompts de tipo action"
        )
    md.append(f"- **Aclaraciones solicitadas**: {agg.asked_clarifications}")
    md.append(f"  - Pertinentes (`ambiguity != low`): {agg.pertinent_clarifications}")
    md.append(f"  - Friccion innecesaria (`ambiguity = low`): {agg.unnecessary_clarifications}")
    md.append(f"- **Errores por ambiguedad** (no aclaro y ejecuto algo): {agg.silent_on_ambiguous}")
    if agg.latency_p50 is not None:
        md.append(f"- **Latencia** (s): mean={agg.latency_mean:.2f}, p50={agg.latency_p50:.2f}, "
                  f"p95={agg.latency_p95:.2f}, p99={agg.latency_p99:.2f}")
    md.append("")

    md.append("## Precision por categoria")
    md.append("")
    md.append("| Categoria | Aciertos | Total | Precision |")
    md.append("| --- | ---: | ---: | ---: |")
    for cat, acc in sorted(agg.intent_accuracy_per_category.items()):
        c = sum(1 for r in results if r.expected_intent == cat and r.intent_match)
        t = sum(1 for r in results if r.expected_intent == cat)
        md.append(f"| `{cat}` | {c} | {t} | {acc*100:.2f}% |")
    md.append("")

    md.append("## Matriz de confusion (esperada x predicha)")
    md.append("")
    categories = sorted(set(list(agg.intent_accuracy_per_category.keys()) +
                            [k for v in agg.confusion_matrix.values() for k in v.keys()]))
    md.append("| Esperada \\ Predicha | " + " | ".join(f"`{c}`" for c in categories) + " |")
    md.append("| --- |" + "|".join([" ---: "] * len(categories)) + " |")
    for exp in sorted(agg.intent_accuracy_per_category.keys()):
        row = [f"`{exp}`"]
        for pred in categories:
            row.append(str(agg.confusion_matrix.get(exp, {}).get(pred, 0)))
        md.append("| " + " | ".join(row) + " |")
    md.append("")

    md.append("## Detalle por prompt")
    md.append("")
    md.append("| ID | Prompt | Esperada | Predicha | Match | Clar. | Pert. | Acciones | Lat (s) | Error |")
    md.append("| --- | --- | --- | --- | :-: | :-: | :-: | :-: | ---: | --- |")
    for r in results:
        am = "✓" if r.intent_match else "✗"
        cl = "✓" if r.asked_clarification else " "
        pe = "" if r.clarification_pertinent is None else ("✓" if r.clarification_pertinent else "✗")
        ac = ""
        if r.actions_match is True:
            ac = "✓"
        elif r.actions_match is False:
            ac = "✗"
        prompt_short = r.prompt[:60].replace("|", "\\|")
        err = (r.error or "").replace("|", "\\|")[:40]
        lat = f"{r.duration_seconds:.2f}" if r.duration_seconds else "-"
        md.append(
            f"| {r.prompt_id} | {prompt_short} | `{r.expected_intent}` | "
            f"`{r.actual_intent}` | {am} | {cl} | {pe} | {ac} | {lat} | {err} |"
        )

    md_path.write_text("\n".join(md), encoding="utf-8")
    return json_path, md_path


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def build_llm_from_env(provider: str | None):
    if provider:
        os.environ["LLM_PROVIDER"] = provider
    from ai.config import build_llm, get_settings

    settings = get_settings()
    if settings.llm_provider == "openai" and not settings.openai_api_key:
        raise RuntimeError("Falta OPENAI_API_KEY")
    if settings.llm_provider == "gemini" and not settings.gemini_api_key:
        raise RuntimeError("Falta GEMINI_API_KEY")
    if settings.llm_provider == "groq" and not settings.groq_api_key:
        raise RuntimeError("Falta GROQ_API_KEY")
    return build_llm()


def main():
    parser = argparse.ArgumentParser(description="Runner de evaluacion (bloque 5.4).")
    parser.add_argument("--limit", type=int, default=None, help="Evaluar solo los primeros N prompts.")
    parser.add_argument("--provider", choices=["openai", "gemini", "groq"], default=None,
                        help="LLM provider a usar (sobrescribe LLM_PROVIDER del entorno).")
    parser.add_argument("--dry-run", action="store_true",
                        help="No invoca al LLM real; valida que el dataset y fixture cargan.")
    args = parser.parse_args()

    dataset = load_dataset()
    fixture = load_fixture()
    if args.limit:
        dataset = dataset[: args.limit]
    print(f"Cargados {len(dataset)} prompts.")

    if args.dry_run:
        # Solo carga y valida, no ejecuta.
        intents = defaultdict(int)
        for d in dataset:
            intents[d["expected_intent"]] += 1
        print("Distribucion de intents esperados:")
        for k, v in sorted(intents.items()):
            print(f"  {k:20s} {v}")
        return 0

    try:
        llm = build_llm_from_env(args.provider)
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        print("\nDefine al menos una de OPENAI_API_KEY, GEMINI_API_KEY o GROQ_API_KEY", file=sys.stderr)
        print("(y opcionalmente LLM_PROVIDER) antes de ejecutar el runner.", file=sys.stderr)
        return 2

    setup_mongo(fixture)

    results: list[PromptResult] = []
    for i, record in enumerate(dataset, 1):
        print(f"[{i:3d}/{len(dataset)}] {record['id']}: {record['prompt'][:60]}")
        result = evaluate_prompt(record, llm, fixture)
        results.append(result)

    agg = aggregate(results)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    json_path, md_path = emit_reports(timestamp, results, agg)
    print(f"\nResultados: {json_path}")
    print(f"Informe:    {md_path}")

    print("\n=== Resumen ===")
    print(f"Precision intent: {agg.intent_accuracy*100:.2f}%")
    if agg.action_match_rate is not None:
        print(f"Tasa CRUD:        {agg.action_match_rate*100:.2f}%")
    print(f"Aclaraciones:     {agg.asked_clarifications} "
          f"(pertinentes={agg.pertinent_clarifications}, friccion={agg.unnecessary_clarifications})")
    if agg.latency_p50:
        print(f"Latencia:         p50={agg.latency_p50:.2f}s, p95={agg.latency_p95:.2f}s, p99={agg.latency_p99:.2f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
