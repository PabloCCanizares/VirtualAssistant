# Migración MCP a main

Estado preparado en la rama `codex/mcp-server-goalmind`.

## Objetivo del merge

Incluir la capa MCP y los servicios de inferencia/planificación que permiten a
un agente externo:

- leer el usuario activo real,
- consultar proyectos y contexto operativo,
- detectar hallazgos atómicos e insights emergentes,
- preparar briefing de dashboard,
- abrir una sesión de planificación semanal,
- crear/editar proyectos, objetivos, tareas y notas,
- listar documentos de proyecto,
- lanzar sincronización local/Atlas cuando haya remoto configurado.

## Archivos que pertenecen al paquete MCP/backend

Estos archivos deberían formar parte del merge MCP:

```text
GoalMind-AI/doc/mcp_server.md
GoalMind-AI/doc/mcp_main_migration.md
GoalMind-AI/mcp_server/__init__.py
GoalMind-AI/mcp_server/runtime.py
GoalMind-AI/mcp_server/server.py
GoalMind-AI/mcp_server/tools.py
GoalMind-AI/services/__init__.py
GoalMind-AI/services/dashboard_briefing_service.py
GoalMind-AI/services/emergent_insight_service.py
GoalMind-AI/services/heuristics/__init__.py
GoalMind-AI/services/heuristics/atomic.py
GoalMind-AI/services/heuristics/registry.py
GoalMind-AI/services/heuristics/types.py
GoalMind-AI/services/operating_map_service.py
GoalMind-AI/services/operating_profile_service.py
GoalMind-AI/services/pattern_detection_service.py
GoalMind-AI/services/portfolio_analysis_service.py
GoalMind-AI/services/user_context_service.py
GoalMind-AI/services/weekly_planning_service.py
GoalMind-AI/database/mongo_conn.py
GoalMind-AI/requirements.txt
GoalMind-AI/tests/unit/database/test_mongo_conn_advanced.py
GoalMind-AI/tests/unit/mcp_server/__init__.py
GoalMind-AI/tests/unit/mcp_server/test_server.py
GoalMind-AI/tests/unit/mcp_server/test_tools.py
```

## Archivos dashboard/UI

Estos archivos pertenecen a la integración visual del briefing en el dashboard.
Conviene revisarlos como segundo paquete si se quiere mantener el MCP puro:

```text
GoalMind-AI/controllers/dashboard_controller.py
GoalMind-AI/tests/unit/controllers/test_dashboard_controller.py
GoalMind-AI/static/js/dashboard_briefing.js
GoalMind-AI/static/css/dashboard.css
GoalMind-AI/templates/dashboard.html
GoalMind-AI/templates/partials/center_panel.html
```

## Cambios no relacionados que conviene revisar antes de mergear

```text
GoalMind-AI/app.py
GoalMind-AI/output/
docs/tfg/
```

`GoalMind-AI/app.py` registra `config_bp`; puede ser correcto, pero no es parte
directa del MCP. `GoalMind-AI/output/` contiene capturas/mockups generados.
`docs/tfg/` contiene documentación de escenarios externos al MCP.

## Staging recomendado para solo MCP/backend

Desde la raíz del repo:

```bash
git add \
  GoalMind-AI/doc/mcp_server.md \
  GoalMind-AI/doc/mcp_main_migration.md \
  GoalMind-AI/mcp_server \
  GoalMind-AI/services \
  GoalMind-AI/database/mongo_conn.py \
  GoalMind-AI/requirements.txt \
  GoalMind-AI/tests/unit/database/test_mongo_conn_advanced.py \
  GoalMind-AI/tests/unit/mcp_server
```

Después:

```bash
git diff --cached --check
git diff --cached --stat
/opt/anaconda3/bin/python -m pytest tests/unit/mcp_server tests/unit/database/test_mongo_conn_advanced.py -q
/opt/anaconda3/bin/python -m pytest -q
```

## Verificación realizada

Última verificación local:

```text
ruff check mcp_server services tests/unit/mcp_server database/mongo_conn.py
All checks passed.

/opt/anaconda3/bin/python -m pytest -q
1015 passed, 1 xfailed
```

También se validó conexión real MCP por `stdio`:

```text
list_tools -> 30 tools
health_check -> responde sin URI de Mongo ni secretos
get_active_user -> responde sin URI de Mongo ni secretos
```

## Nota de seguridad

No incluir `.env`, `database/mongo_user.json`, URIs completas de Atlas,
contraseñas ni claves API. Las tools MCP devuelven estado operativo y flags de
configuración, pero no secretos.
