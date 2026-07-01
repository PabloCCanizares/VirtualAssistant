"""Runtime bootstrap for the GoalMind AI MCP server."""

from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def initialize_runtime() -> dict:
    """Load local configuration and initialize Mongo clients without Flask views."""
    env_path = PROJECT_ROOT / ".env"
    if env_path.exists():
        load_dotenv(env_path, override=False)

    from database.mongo_conn import reconnect_databases

    result = reconnect_databases()
    return {
        "project_root": str(PROJECT_ROOT),
        "env_loaded": env_path.exists(),
        "mongo": result,
    }
