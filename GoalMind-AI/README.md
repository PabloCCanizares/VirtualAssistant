# GoalMind-AI

**GoalMind-AI** es un asistente personal inteligente desarrollado como Trabajo de Fin de Grado.
Combina una aplicación web construida con **Flask** y una capa de agentes basada en
**LangChain** y **LangGraph** para ayudar al usuario a planificar objetivos, gestionar tareas,
mantener su agenda y realizar investigaciones documentales asistidas por LLM.

## Descripción general

La aplicación ofrece un dashboard único con los siguientes módulos:

- **Objetivos y proyectos**: creación, seguimiento y categorización de metas a largo plazo
  con sus tareas asociadas.
- **Tareas y calendario semanal**: planificación de actividades con visualización tipo agenda.
- **Estadísticas**: indicadores de progreso sobre objetivos completados, tareas y dedicación.
- **Documentos de proyecto**: subida, parseo (PDF, DOCX, XLSX) y almacenamiento en GridFS.
- **Chat con IA**: conversación con un sistema multi-agente capaz de interpretar la intención
  del usuario, ejecutar acciones sobre la base de datos (crear/editar tareas, objetivos…),
  redactar y organizar documentos, y realizar *deep research* sobre la documentación cargada.

El backend persiste los datos en **MongoDB** (una instancia local y, opcionalmente, una remota)
y los archivos binarios en **GridFS**. La capa de IA soporta varios proveedores
(**OpenAI**, **Google Gemini**, **Groq**) gestionados de forma uniforme mediante LangChain.

## Estructura de directorios

```
GoalMind-AI/
├── app.py                      # Punto de entrada Flask (registro de blueprints)
├── bootstrap.py                # Carga del .env y utilidades de configuración
├── Dockerfile                  # Imagen de producción con gunicorn
├── docker-compose.yml          # Servicio app + MongoDB
├── requirements.txt            # Dependencias Python
├── pyproject.toml              # Configuración de pytest, coverage y ruff
│
├── config/                     # Configuración de storage (GridFS, uploads)
├── database/                   # Conexión a MongoDB y wrapper de GridFS
├── model/                      # Modelos de dominio (Goal, Task, Project, Event, …)
├── controllers/                # Blueprints Flask (dashboard, tareas, objetivos, chat IA…)
│
├── ai/                         # Capa de inteligencia artificial
│   ├── chat.py                 # Orquestador de conversación
│   ├── graph.py                # Grafo LangGraph del sistema multi-agente
│   ├── state.py                # Estado compartido entre agentes
│   ├── config.py               # Selección de modelos LLM
│   ├── agents/                 # Agentes especializados (supervisor, planner, critic,
│   │                           #  doc_reader, doc_writer, research, recommendations…)
│   ├── prompts/                # Prompts de cada agente
│   ├── services/               # Servicios (chat, parsing, deep search, LLM utils)
│   ├── repositories/           # Acceso a contexto persistente
│   └── deep_research/          # Subsistema de investigación profunda
│
├── templates/                  # Plantillas Jinja2 (base, dashboard, partials/)
├── static/                     # CSS y JS del frontend
│
├── tests/                      # Suite de tests con pytest
└── doc/                        # Documentación adicional del TFG
```

## Requisitos previos

- **Python 3.11+** (recomendado 3.13)
- **MongoDB** local en `mongodb://localhost:27017` (o vía Docker Compose)
- Un archivo **`.env`** en la raíz del proyecto con, al menos:

```env
FLASK_SECRET_KEY=...
MONGO_LOCAL_URI=mongodb://localhost:27017
MONGO_DB_NAME=goalmind
# Claves de los proveedores LLM que se vayan a usar
OPENAI_API_KEY=...
GOOGLE_API_KEY=...
GROQ_API_KEY=...
```

## Instalación y ejecución

### Opción 1 — Entorno virtual local

```powershell
python -m venv venv
venv\Scripts\activate         # Windows
# source venv/bin/activate    # Linux / macOS
pip install -r requirements.txt
python app.py                 # o: flask --app app run --debug
```

Aplicación disponible en <http://127.0.0.1:5000/>.

### Opción 2 — Docker Compose

```bash
docker compose up --build
```

Levanta la app en el puerto `5000` junto con un contenedor MongoDB 7 con
volumen persistente y volumen para `uploads/`.

## Tests

```bash
pytest                        # ejecución completa
pytest --cov                  # con cobertura (configurada en pyproject.toml)
```

## Licencia

Proyecto académico desarrollado como Trabajo de Fin de Grado.
