# GoalMind AI MCP Server

Servidor MCP local para conectar agentes externos con GoalMind AI sin pasar por
las vistas HTML de Flask.

## Arranque

Desde la raíz de `GoalMind-AI`:

```bash
python -m mcp_server.server
```

Por defecto usa transporte `stdio`, recomendado para clientes MCP locales.

También se puede preparar un transporte HTTP durante desarrollo:

```bash
python -m mcp_server.server --transport streamable-http --host 127.0.0.1 --port 8000
```

## Conexión desde un cliente MCP

Para un cliente MCP local, configura el servidor con el directorio de trabajo
apuntando a la carpeta `GoalMind-AI`:

```json
{
  "mcpServers": {
    "goalmind-ai": {
      "command": "python",
      "args": ["-m", "mcp_server.server"],
      "cwd": "/ruta/a/VirtualAssistant/GoalMind-AI"
    }
  }
}
```

Si el cliente no hereda el entorno del shell, usa la ruta absoluta del Python
del proyecto o del entorno que tenga instalado `mcp` y el resto de dependencias.

Smoke local recomendado:

```bash
python -m mcp_server.server
```

El proceso queda escuchando por `stdio`; para una prueba automatizada se puede
usar `mcp.client.stdio` y comprobar que `list_tools` devuelve `health_check`,
`get_active_user` y `sync_now`.

## Configuración

El servidor carga `.env` si existe y reutiliza las mismas variables que la app:

- `DEFAULT_USER_ID`
- `APP_USER_NICKNAME`
- `MONGO_LOCAL_URI`
- `MONGO_LOCAL_DB`
- `MONGO_REMOTE_URI`
- `MONGO_REMOTE_DB`

No imprime ni devuelve secretos. En particular, no expone `MONGO_REMOTE_URI`,
contraseñas ni API keys.

El usuario activo se resuelve con `database.mongo_conn.get_app_user_id()`.

## Enfoque

El MCP se organiza como una capa de contexto y agencia:

- Tools sensoriales: leen y componen estado operativo.
- Tools cognitivas: detectan patrones y sugieren acciones sin escribir.
- Tools motoras: ejecutan cambios controlados.

La primera vertical implementada cubre lectura, contexto y análisis. Las tools
motoras destructivas quedan fuera de esta fase.

## Heurísticas

La capa cognitiva usa heurísticas deterministas y explicables antes de cualquier
LLM. Hay dos niveles:

- `atomic_findings`: señales individuales como tarea vencida, proyecto sin
  objetivos o tarea sin fecha.
- `emergent_insights`: conclusiones compuestas que combinan múltiples señales,
  por ejemplo deuda de planificación o foco fragmentado.
- `operating_profile`: síntesis con score, dimensiones operativas, patrones
  dominantes y próximos movimientos.
- `operating_map`: grafo ligero de relaciones entre proyectos, objetivos,
  tareas, documentos y eventos.
- `dashboard_briefing`: tarjetas y tareas sugeridas para mostrar en el
  dashboard inicial sin escribir en la base de datos.

Cada hallazgo atómico devuelve:

```json
{
  "type": "goal_without_tasks",
  "category": "structure",
  "severity": "medium",
  "entity": {},
  "evidence": {},
  "confidence": 0.98,
  "explanation": "El objetivo no tiene tareas asociadas.",
  "recommendation": "Crear una siguiente acción pequeña y concreta.",
  "suggested_tool": "create_task",
  "suggested_payload": {},
  "requires_confirmation": false
}
```

Categorías actuales:

- `structure`
- `time`
- `load`
- `data_quality`
- `progress`

Parámetros configurables:

- `stale_days`
- `due_soon_days`
- `overloaded_task_threshold`
- `max_active_projects`
- `max_pending_tasks`
- `low_progress_threshold`

## Tools disponibles

### `get_active_user`

Devuelve el usuario activo de GoalMind AI y si hay base local/remota configurada.

Payload:

```json
{}
```

### `list_projects`

Lista proyectos del usuario activo.

Payload:

```json
{
  "limit": 50,
  "search": "TFG"
}
```

### `get_user_snapshot`

Devuelve una vista compacta del usuario activo:

- contadores de proyectos, objetivos, tareas, documentos y eventos,
- tareas pendientes y completadas,
- proyectos activos,
- proyectos sin objetivos,
- objetivos sin tareas,
- próximas fechas límite,
- actividad reciente.

Payload:

```json
{}
```

### `get_dashboard_briefing`

Genera trabajo visible para el dashboard inicial:

- diagnostico operativo,
- tarjetas de aviso,
- tareas sugeridas por el asistente,
- datos que faltan para mejorar la lectura,
- KPIs de soporte.

Estas tareas son propuestas del MCP, no documentos insertados en la coleccion
`Tasks`.

```json
{
  "limit": 8
}
```

### `should_start_weekly_planning`

Indica si el sistema deberia proponer una reunion semanal. Tiene en cuenta:

- si ya existe una sesion para la semana actual,
- inicio de semana,
- tareas vencidas,
- tareas proximas,
- insights emergentes de alto impacto.

```json
{}
```

### `start_weekly_planning_session`

Crea o reanuda la sesion semanal actual en la coleccion `PlanningSessions`.
No crea tareas reales.

```json
{}
```

### `answer_weekly_planning_question`

Guarda una respuesta de la reunion semanal.

Campos soportados:

- `weekly_available_hours`
- `current_energy`
- `weekly_top_priorities`
- `fixed_commitments`
- `avoid_this_week`
- `success_criteria`
- `notes`

Para campos tipo lista se puede enviar texto separado por comas, punto y coma
o saltos de linea.

```json
{
  "session_id": "000000000000000000000000",
  "field": "weekly_top_priorities",
  "value": "TFG, salud, Atlas"
}
```

### `build_weekly_plan`

Construye y guarda un plan semanal determinista desde la sesion:

- capacidad efectiva segun horas y energia,
- prioridades de foco,
- tareas sugeridas para esta semana,
- tareas a diferir,
- tareas a revisar o pausar,
- riesgos y supuestos.

```json
{
  "session_id": "000000000000000000000000"
}
```

### `get_current_week_plan`

Devuelve la sesion semanal actual y el plan generado, si existe.

```json
{}
```

### `get_project_context`

Devuelve contexto completo de un proyecto:

- proyecto,
- objetivos,
- tareas agrupadas por objetivo,
- documentos,
- notas,
- progreso calculado,
- huecos o inconsistencias.

Payload:

```json
{
  "project_id": "000000000000000000000000"
}
```

### `find_bottlenecks`

Alias compatible sobre `find_atomic_findings`. Detecta bloqueos sin modificar
datos:

- proyectos sin objetivos,
- objetivos sin tareas,
- tareas vencidas,
- tareas huérfanas,
- proyectos sin actividad reciente,
- objetivos con demasiadas tareas pendientes.

Payload:

```json
{
  "categories": ["structure", "time"],
  "limit": 100,
  "stale_days": 30,
  "due_soon_days": 7,
  "overloaded_task_threshold": 8
}
```

### `list_heuristics`

Lista heurísticas registradas. Acepta filtro opcional por categoría.

```json
{
  "categories": ["structure"]
}
```

### `explain_heuristic`

Explica una heurística concreta.

```json
{
  "name": "project_without_goals"
}
```

### `find_atomic_findings`

Ejecuta el registry de heurísticas atómicas y devuelve hallazgos homogéneos.

```json
{
  "categories": ["time", "load"],
  "limit": 50,
  "stale_days": 30,
  "due_soon_days": 7,
  "max_active_projects": 6,
  "max_pending_tasks": 30
}
```

### `find_emergent_insights`

Combina hallazgos atómicos y agregados del dataset para generar conclusiones
emergentes explicables.

Insights actuales:

- `operational_drift`
- `planning_debt`
- `focus_fragmentation`
- `execution_without_structure`
- `research_without_execution`
- `priority_attention_mismatch`

```json
{
  "limit": 20,
  "stale_days": 30,
  "max_active_projects": 6,
  "max_pending_tasks": 30
}
```

### `analyze_operating_system`

Devuelve una lectura global del sistema personal:

- snapshot,
- hallazgos atómicos,
- insights emergentes,
- riesgos,
- oportunidades,
- recomendaciones,
- acciones sugeridas.

```json
{
  "limit": 20
}
```

### `get_operating_profile`

Devuelve una lectura compacta para decidir qué debe atender primero un agente:

- score operativo global,
- estado por dimensiones,
- patrones dominantes,
- riesgos principales,
- próximos movimientos sugeridos,
- explicación breve de por qué aparece ese perfil.

```json
{
  "limit": 10,
  "stale_days": 30,
  "max_active_projects": 6,
  "max_pending_tasks": 30
}
```

### `get_operating_map`

Construye un mapa read-only de relaciones del usuario activo:

- nodos de proyectos, objetivos, tareas, documentos y eventos,
- aristas como `has_goal`, `has_task`, `has_document` o `scheduled_event`,
- resúmenes por proyecto,
- nodos más conectados,
- entidades desconectadas o con enlaces rotos.

```json
{
  "limit": 50,
  "include_events": true
}
```

### `build_agent_context`

Prepara un paquete compacto para agentes externos:

- identidad activa,
- resumen ejecutivo,
- perfil operativo,
- mapa operativo,
- proyectos clave,
- objetivos bloqueados,
- tareas urgentes,
- patrones detectados,
- acciones posibles,
- restricciones de seguridad.

```json
{
  "limit": 10
}
```

### `suggest_next_actions`

Convierte insights emergentes y hallazgos atómicos en recomendaciones
accionables. Devuelve tool sugerida y payload, pero no ejecuta nada.

Payload:

```json
{
  "limit": 10,
  "stale_days": 30,
  "overloaded_task_threshold": 8
}
```

### `create_task`

Crea una tarea para el usuario activo. Puede ligarse a objetivo y proyecto.
Si se pasa `goal_id`, la tool verifica que el objetivo pertenezca al usuario
activo. Si el objetivo tiene `project_id`, lo hereda automáticamente.

Payload:

```json
{
  "contenido": "Redactar introducción",
  "goal_id": "000000000000000000000000",
  "descripcion": "Primer borrador",
  "estado": "pendiente",
  "prioridad": "alta"
}
```

### `health_check`

Comprueba salud basica del MCP y bases configuradas sin exponer secretos.

```json
{}
```

### `create_project`

Crea un proyecto del usuario activo.

```json
{
  "titulo": "TFG",
  "descripcion": "Memoria del trabajo final",
  "estado": "Activo",
  "prioridad": "Alta"
}
```

### `update_project`

Actualiza campos seguros de un proyecto del usuario activo.

```json
{
  "project_id": "000000000000000000000000",
  "descripcion": "Nuevo alcance",
  "progreso": 40
}
```

### `create_goal`

Crea un objetivo, opcionalmente ligado a proyecto.

```json
{
  "titulo": "Redactar marco teorico",
  "project_id": "000000000000000000000000",
  "prioridad": "Alta"
}
```

### `update_goal`

Actualiza campos seguros de un objetivo del usuario activo.

```json
{
  "goal_id": "000000000000000000000000",
  "progreso": 25,
  "descripcion": "Primer bloque definido"
}
```

### `update_task`

Actualiza campos seguros de una tarea del usuario activo.

```json
{
  "task_id": "000000000000000000000000",
  "estado": "completada",
  "descripcion": "Cerrada desde MCP"
}
```

### `add_project_note`

Agrega una anotacion a un proyecto. Usa el mismo campo `notas` que la vista de
proyecto.

```json
{
  "project_id": "000000000000000000000000",
  "text": "Idea de estructura para la memoria"
}
```

### `list_project_documents`

Lista documentos de un proyecto del usuario activo.

```json
{
  "project_id": "000000000000000000000000",
  "limit": 50
}
```

### `sync_now`

Ejecuta sincronizacion local/Atlas si hay base remota disponible:

- cola de borrados,
- promocion de documentos pendientes,
- pull remoto,
- push local.

No devuelve URIs ni secretos.

```json
{}
```

## Notas de arquitectura

- `mcp_server/server.py` solo registra tools en FastMCP.
- `mcp_server/tools.py` contiene handlers puros y testeables.
- `services/user_context_service.py` compone snapshots y contexto de proyecto.
- `services/heuristics/types.py` define el contrato común de hallazgos.
- `services/heuristics/atomic.py` contiene evaluadores atómicos.
- `services/heuristics/registry.py` ejecuta y filtra heurísticas.
- `services/pattern_detection_service.py` conserva wrappers de detección.
- `services/emergent_insight_service.py` combina señales en conclusiones emergentes.
- `services/dashboard_briefing_service.py` prepara tarjetas y tareas sugeridas para el dashboard.
- `services/weekly_planning_service.py` gestiona sesiones y planes semanales.
- `services/operating_map_service.py` genera el mapa read-only de relaciones.
- `services/operating_profile_service.py` sintetiza score, dimensiones y próximos movimientos.
- `services/portfolio_analysis_service.py` genera acciones sugeridas desde findings e insights.
- Las tools llaman a modelos/casos de dominio, no a controladores Flask.
- Las operaciones se filtran por usuario activo salvo que una futura tool
  explicite otra política.
- Las llamadas mutantes capturan stdout de modelos existentes para no romper el
  protocolo MCP sobre `stdio`.
