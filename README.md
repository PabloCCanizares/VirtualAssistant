# Asistente Personal LLM — Flask demo

Estructura dividida en **panel izquierdo (sidebar)**, **header**, **panel central**, **panel derecho**, y **footer**.

## Cómo ejecutar
```bash
python3 -m venv .venv
source .venv/bin/activate  # En Windows: .venv\Scripts\activate
pip install -r requirements.txt
python app.py  # o: flask --app app run --debug
```
Abrir: http://127.0.0.1:5000/

## Estructura
- `templates/base.html` — Layout general (incluye `partials/` y bloque `content`)
- `templates/dashboard.html` — Contenido del dashboard (incluye panel central y derecho)
- `templates/partials/left_panel.html` — Sidebar
- `templates/partials/header.html` — Barra superior
- `templates/partials/center_panel.html` — Calendario semanal
- `templates/partials/right_panel.html` — Objetivos, tareas, alarmas, estadísticas y forms
- `templates/partials/footer.html` — Pie
- `static/css/styles.css` — Estilos extraídos del HTML original
- `static/js/app.js` — Script base

> Nota: las rutas `/agenda`, `/objetivos`, `/tareas`, `/estadisticas`, `/config` reutilizan el layout. Puedes crear
> plantillas específicas para cada sección si lo deseas.
