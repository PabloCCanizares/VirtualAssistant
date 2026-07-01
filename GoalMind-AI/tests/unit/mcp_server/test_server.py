from __future__ import annotations

import asyncio

from mcp_server.server import build_server


def test_build_server_registers_initial_tools():
    async def _tool_names():
        server = build_server()
        return {tool.name for tool in await server.list_tools()}

    names = asyncio.run(_tool_names())

    assert {
        "get_active_user",
        "get_user_snapshot",
        "get_dashboard_briefing",
        "should_start_weekly_planning",
        "start_weekly_planning_session",
        "answer_weekly_planning_question",
        "build_weekly_plan",
        "get_current_week_plan",
        "list_projects",
        "get_project_context",
        "list_heuristics",
        "explain_heuristic",
        "find_atomic_findings",
        "find_bottlenecks",
        "find_emergent_insights",
        "analyze_operating_system",
        "get_operating_profile",
        "get_operating_map",
        "build_agent_context",
        "suggest_next_actions",
        "health_check",
        "create_project",
        "update_project",
        "create_goal",
        "update_goal",
        "create_task",
        "update_task",
        "add_project_note",
        "list_project_documents",
        "sync_now",
    }.issubset(names)
