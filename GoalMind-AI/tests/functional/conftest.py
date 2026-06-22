"""Fixtures para los tests funcionales (escenarios end-to-end).

Las fixtures se definen en `tests/_pytest_fixtures.py` y se comparten con la
suite de integracion. Aqui ademas se anade un helper para escribir los logs
legibles de cada escenario en `docs/tfg/escenarios/`.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from tests._pytest_fixtures import *  # noqa: F401, F403


@pytest.fixture
def full_flask_client():
    """Cliente Flask con TODOS los blueprints relevantes registrados.

    A diferencia de `flask_client` (que solo registra `ai_chat_bp` y se usa en
    los escenarios CU-03), esta fixture monta tambien `project_bp`, `goal_bp`
    y `config_bp` para los escenarios que ejercitan la UI directamente sin
    pasar por el agente: gestion completa de un proyecto (CU-02) y
    configuracion del sistema (CU-01).
    """
    from flask import Flask

    from controllers.ai_chat_controller import ai_chat_bp
    from controllers.config_controller import config_bp
    from controllers.goal_controller import goal_bp
    from controllers.project_controller import project_bp

    app = Flask(__name__)
    app.config["TESTING"] = True
    app.config["UPLOAD_ALLOWED_EXTENSIONS"] = {
        "pdf", "doc", "docx", "txt", "png", "jpg", "jpeg", "csv", "xlsx",
    }
    app.config["MAX_CONTENT_LENGTH"] = 25 * 1024 * 1024
    app.secret_key = "test-secret"

    app.register_blueprint(ai_chat_bp)
    app.register_blueprint(project_bp)
    app.register_blueprint(goal_bp)
    app.register_blueprint(config_bp)
    return app.test_client()


SCENARIO_LOG_DIR = (
    Path(__file__).resolve().parents[3] / "docs" / "tfg" / "escenarios"
)


def write_scenario_log(
    *,
    slug: str,
    title: str,
    user_prompts: list[str],
    events: list[tuple[str, dict]],
    db_summary: dict[str, Any],
    notas: str = "",
) -> Path:
    """Genera `docs/tfg/escenarios/<slug>.md` con prompt, eventos SSE y estado final.

    Se llama desde cada test al final del escenario para dejar un log legible
    que la memoria pueda referenciar literalmente.
    """
    SCENARIO_LOG_DIR.mkdir(parents=True, exist_ok=True)
    path = SCENARIO_LOG_DIR / f"{slug}.md"

    lines: list[str] = [f"# Escenario: {title}", ""]
    lines.append("## Prompt(s) del usuario")
    lines.append("")
    for i, prompt in enumerate(user_prompts, 1):
        lines.append(f"{i}. {prompt!r}")
    lines.append("")

    lines.append("## Eventos SSE emitidos por `/api/ai/chat`")
    lines.append("")
    lines.append("```")
    for e_type, data in events:
        if e_type == "status":
            name = data.get("name", "?")
            action = data.get("action", "")
            lines.append(f"status  | {name:25s} | {action}")
        elif e_type == "done":
            lines.append(f"done    | reply: {data.get('reply', '')[:120]}")
        elif e_type == "error":
            lines.append(f"error   | {data.get('message', '')}")
        else:
            lines.append(f"{e_type} | {json.dumps(data, ensure_ascii=False)}")
    lines.append("```")
    lines.append("")

    lines.append("## Estado final relevante de la BD")
    lines.append("")
    lines.append("```json")
    lines.append(json.dumps(db_summary, ensure_ascii=False, indent=2, default=str))
    lines.append("```")
    lines.append("")

    if notas:
        lines.append("## Notas")
        lines.append("")
        lines.append(notas.strip())
        lines.append("")

    path.write_text("\n".join(lines), encoding="utf-8")
    return path
