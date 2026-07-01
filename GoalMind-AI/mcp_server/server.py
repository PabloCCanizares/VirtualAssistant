"""FastMCP entrypoint for GoalMind AI."""

from __future__ import annotations

import argparse
from typing import Literal

from mcp.server.fastmcp import FastMCP

from mcp_server import tools as tool_handlers
from mcp_server.runtime import initialize_runtime

Transport = Literal["stdio", "sse", "streamable-http"]


def build_server(*, host: str = "127.0.0.1", port: int = 8000) -> FastMCP:
    mcp = FastMCP(
        "GoalMind AI",
        instructions=(
            "Servidor MCP local para operar GoalMind AI. Todas las herramientas "
            "filtran por el usuario activo de la app y no exponen secretos."
        ),
        host=host,
        port=port,
    )

    @mcp.tool()
    def get_active_user() -> dict:
        """Devuelve el usuario activo real que usa GoalMind AI."""
        return tool_handlers.get_active_user()

    @mcp.tool()
    def list_projects(limit: int = 50, search: str | None = None) -> dict:
        """Lista proyectos del usuario activo, con búsqueda opcional."""
        return tool_handlers.list_projects(limit=limit, search=search)

    @mcp.tool()
    def get_user_snapshot() -> dict:
        """Devuelve un snapshot operativo del usuario activo."""
        return tool_handlers.get_user_snapshot()

    @mcp.tool()
    def get_dashboard_briefing(limit: int = 8) -> dict:
        """Devuelve tarjetas y tareas sugeridas para el dashboard inicial."""
        return tool_handlers.get_dashboard_briefing(limit=limit)

    @mcp.tool()
    def should_start_weekly_planning() -> dict:
        """Indica si conviene proponer una reunion de planificacion semanal."""
        return tool_handlers.should_start_weekly_planning()

    @mcp.tool()
    def start_weekly_planning_session() -> dict:
        """Crea o reanuda la sesion de planificacion semanal actual."""
        return tool_handlers.start_weekly_planning_session()

    @mcp.tool()
    def answer_weekly_planning_question(session_id: str, field: str, value: str) -> dict:
        """Guarda una respuesta de la sesion semanal."""
        return tool_handlers.answer_weekly_planning_question(
            session_id=session_id,
            field=field,
            value=value,
        )

    @mcp.tool()
    def build_weekly_plan(session_id: str | None = None) -> dict:
        """Construye y guarda un plan semanal determinista desde la sesion."""
        return tool_handlers.build_weekly_plan(session_id=session_id)

    @mcp.tool()
    def get_current_week_plan() -> dict:
        """Devuelve la sesion y plan semanal actuales, si existen."""
        return tool_handlers.get_current_week_plan()

    @mcp.tool()
    def get_project_context(project_id: str) -> dict:
        """Devuelve contexto completo de un proyecto del usuario activo."""
        return tool_handlers.get_project_context(project_id=project_id)

    @mcp.tool()
    def list_heuristics(categories: list[str] | str | None = None) -> dict:
        """Lista heurísticas deterministas registradas."""
        return tool_handlers.list_heuristics(categories=categories)

    @mcp.tool()
    def explain_heuristic(name: str) -> dict:
        """Explica una heurística determinista registrada."""
        return tool_handlers.explain_heuristic(name=name)

    @mcp.tool()
    def find_atomic_findings(
        categories: list[str] | str | None = None,
        limit: int = 100,
        stale_days: int = 30,
        due_soon_days: int = 7,
        overloaded_task_threshold: int = 8,
        max_active_projects: int = 6,
        max_pending_tasks: int = 30,
        low_progress_threshold: int = 25,
    ) -> dict:
        """Ejecuta heurísticas atómicas deterministas sin escribir en BD."""
        return tool_handlers.find_atomic_findings(
            categories=categories,
            limit=limit,
            stale_days=stale_days,
            due_soon_days=due_soon_days,
            overloaded_task_threshold=overloaded_task_threshold,
            max_active_projects=max_active_projects,
            max_pending_tasks=max_pending_tasks,
            low_progress_threshold=low_progress_threshold,
        )

    @mcp.tool()
    def find_bottlenecks(
        categories: list[str] | str | None = None,
        limit: int = 100,
        stale_days: int = 30,
        due_soon_days: int = 7,
        overloaded_task_threshold: int = 8,
        max_active_projects: int = 6,
        max_pending_tasks: int = 30,
        low_progress_threshold: int = 25,
    ) -> dict:
        """Detecta bloqueos y huecos estructurales sin escribir en BD."""
        return tool_handlers.find_bottlenecks(
            categories=categories,
            limit=limit,
            stale_days=stale_days,
            due_soon_days=due_soon_days,
            overloaded_task_threshold=overloaded_task_threshold,
            max_active_projects=max_active_projects,
            max_pending_tasks=max_pending_tasks,
            low_progress_threshold=low_progress_threshold,
        )

    @mcp.tool()
    def suggest_next_actions(
        limit: int = 10,
        categories: list[str] | str | None = None,
        stale_days: int = 30,
        due_soon_days: int = 7,
        overloaded_task_threshold: int = 8,
        max_active_projects: int = 6,
        max_pending_tasks: int = 30,
        low_progress_threshold: int = 25,
    ) -> dict:
        """Sugiere acciones MCP con payloads sin ejecutarlas."""
        return tool_handlers.suggest_next_actions(
            limit=limit,
            categories=categories,
            stale_days=stale_days,
            due_soon_days=due_soon_days,
            overloaded_task_threshold=overloaded_task_threshold,
            max_active_projects=max_active_projects,
            max_pending_tasks=max_pending_tasks,
            low_progress_threshold=low_progress_threshold,
        )

    @mcp.tool()
    def find_emergent_insights(
        limit: int = 20,
        stale_days: int = 30,
        due_soon_days: int = 7,
        overloaded_task_threshold: int = 8,
        max_active_projects: int = 6,
        max_pending_tasks: int = 30,
        low_progress_threshold: int = 25,
    ) -> dict:
        """Construye conclusiones emergentes explicables a partir de señales pequeñas."""
        return tool_handlers.find_emergent_insights(
            limit=limit,
            stale_days=stale_days,
            due_soon_days=due_soon_days,
            overloaded_task_threshold=overloaded_task_threshold,
            max_active_projects=max_active_projects,
            max_pending_tasks=max_pending_tasks,
            low_progress_threshold=low_progress_threshold,
        )

    @mcp.tool()
    def analyze_operating_system(
        limit: int = 20,
        stale_days: int = 30,
        due_soon_days: int = 7,
        overloaded_task_threshold: int = 8,
        max_active_projects: int = 6,
        max_pending_tasks: int = 30,
        low_progress_threshold: int = 25,
    ) -> dict:
        """Devuelve snapshot, findings, insights emergentes, riesgos y acciones sugeridas."""
        return tool_handlers.analyze_operating_system(
            limit=limit,
            stale_days=stale_days,
            due_soon_days=due_soon_days,
            overloaded_task_threshold=overloaded_task_threshold,
            max_active_projects=max_active_projects,
            max_pending_tasks=max_pending_tasks,
            low_progress_threshold=low_progress_threshold,
        )

    @mcp.tool()
    def get_operating_profile(
        limit: int = 10,
        stale_days: int = 30,
        due_soon_days: int = 7,
        overloaded_task_threshold: int = 8,
        max_active_projects: int = 6,
        max_pending_tasks: int = 30,
        low_progress_threshold: int = 25,
    ) -> dict:
        """Devuelve score, dimensiones, patrones dominantes y próximos movimientos."""
        return tool_handlers.get_operating_profile(
            limit=limit,
            stale_days=stale_days,
            due_soon_days=due_soon_days,
            overloaded_task_threshold=overloaded_task_threshold,
            max_active_projects=max_active_projects,
            max_pending_tasks=max_pending_tasks,
            low_progress_threshold=low_progress_threshold,
        )

    @mcp.tool()
    def get_operating_map(limit: int = 50, include_events: bool = True) -> dict:
        """Devuelve un mapa de relaciones entre proyectos, objetivos, tareas y documentos."""
        return tool_handlers.get_operating_map(limit=limit, include_events=include_events)

    @mcp.tool()
    def build_agent_context(
        limit: int = 10,
        stale_days: int = 30,
        due_soon_days: int = 7,
        overloaded_task_threshold: int = 8,
        max_active_projects: int = 6,
        max_pending_tasks: int = 30,
        low_progress_threshold: int = 25,
    ) -> dict:
        """Prepara un paquete de contexto para agentes externos."""
        return tool_handlers.build_agent_context(
            limit=limit,
            stale_days=stale_days,
            due_soon_days=due_soon_days,
            overloaded_task_threshold=overloaded_task_threshold,
            max_active_projects=max_active_projects,
            max_pending_tasks=max_pending_tasks,
            low_progress_threshold=low_progress_threshold,
        )

    @mcp.tool()
    def health_check() -> dict:
        """Comprueba salud básica del MCP y acceso a bases sin exponer secretos."""
        return tool_handlers.health_check()

    @mcp.tool()
    def create_project(
        titulo: str,
        descripcion: str | None = None,
        estado: str | None = "Activo",
        prioridad: str | None = "Media",
        fecha_inicio: str | None = None,
        fecha_fin: str | None = None,
    ) -> dict:
        """Crea un proyecto para el usuario activo."""
        return tool_handlers.create_project(
            titulo=titulo,
            descripcion=descripcion,
            estado=estado,
            prioridad=prioridad,
            fecha_inicio=fecha_inicio,
            fecha_fin=fecha_fin,
        )

    @mcp.tool()
    def update_project(
        project_id: str,
        titulo: str | None = None,
        descripcion: str | None = None,
        estado: str | None = None,
        prioridad: str | None = None,
        progreso: int | str | None = None,
        fecha_inicio: str | None = None,
        fecha_fin: str | None = None,
    ) -> dict:
        """Actualiza campos seguros de un proyecto del usuario activo."""
        return tool_handlers.update_project(
            project_id=project_id,
            titulo=titulo,
            descripcion=descripcion,
            estado=estado,
            prioridad=prioridad,
            progreso=progreso,
            fecha_inicio=fecha_inicio,
            fecha_fin=fecha_fin,
        )

    @mcp.tool()
    def create_goal(
        titulo: str,
        project_id: str | None = None,
        descripcion: str | None = None,
        estado: str | None = "Activo",
        prioridad: str | None = "Media",
        progreso: int | str | None = 0,
        fecha_inicio: str | None = None,
        fecha_fin: str | None = None,
    ) -> dict:
        """Crea un objetivo para el usuario activo."""
        return tool_handlers.create_goal(
            titulo=titulo,
            project_id=project_id,
            descripcion=descripcion,
            estado=estado,
            prioridad=prioridad,
            progreso=progreso,
            fecha_inicio=fecha_inicio,
            fecha_fin=fecha_fin,
        )

    @mcp.tool()
    def update_goal(
        goal_id: str,
        titulo: str | None = None,
        project_id: str | None = None,
        descripcion: str | None = None,
        estado: str | None = None,
        prioridad: str | None = None,
        progreso: int | str | None = None,
        fecha_inicio: str | None = None,
        fecha_fin: str | None = None,
    ) -> dict:
        """Actualiza campos seguros de un objetivo del usuario activo."""
        return tool_handlers.update_goal(
            goal_id=goal_id,
            titulo=titulo,
            project_id=project_id,
            descripcion=descripcion,
            estado=estado,
            prioridad=prioridad,
            progreso=progreso,
            fecha_inicio=fecha_inicio,
            fecha_fin=fecha_fin,
        )

    @mcp.tool()
    def create_task(
        contenido: str,
        goal_id: str | None = None,
        project_id: str | None = None,
        descripcion: str | None = None,
        fecha_limite: str | None = None,
        estado: str | None = "pendiente",
        prioridad: str | None = "media",
    ) -> dict:
        """Crea una tarea para el usuario activo, opcionalmente ligada a objetivo/proyecto."""
        return tool_handlers.create_task(
            contenido=contenido,
            goal_id=goal_id,
            project_id=project_id,
            descripcion=descripcion,
            fecha_limite=fecha_limite,
            estado=estado,
            prioridad=prioridad,
        )

    @mcp.tool()
    def update_task(
        task_id: str,
        contenido: str | None = None,
        goal_id: str | None = None,
        project_id: str | None = None,
        descripcion: str | None = None,
        fecha_limite: str | None = None,
        estado: str | None = None,
        prioridad: str | None = None,
    ) -> dict:
        """Actualiza campos seguros de una tarea del usuario activo."""
        return tool_handlers.update_task(
            task_id=task_id,
            contenido=contenido,
            goal_id=goal_id,
            project_id=project_id,
            descripcion=descripcion,
            fecha_limite=fecha_limite,
            estado=estado,
            prioridad=prioridad,
        )

    @mcp.tool()
    def add_project_note(project_id: str, text: str) -> dict:
        """Agrega una anotación a un proyecto del usuario activo."""
        return tool_handlers.add_project_note(project_id=project_id, text=text)

    @mcp.tool()
    def list_project_documents(project_id: str, limit: int = 50) -> dict:
        """Lista documentos de un proyecto del usuario activo."""
        return tool_handlers.list_project_documents(project_id=project_id, limit=limit)

    @mcp.tool()
    def sync_now() -> dict:
        """Ejecuta sincronización manual local/Atlas si hay remoto disponible."""
        return tool_handlers.sync_now()

    return mcp


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="GoalMind AI MCP server")
    parser.add_argument(
        "--transport",
        choices=("stdio", "sse", "streamable-http"),
        default="stdio",
        help="MCP transport. Default: stdio.",
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    initialize_runtime()
    mcp = build_server(host=args.host, port=args.port)
    mcp.run(transport=args.transport)


if __name__ == "__main__":
    main()
