"""Weekly planning sessions for GoalMind AI."""

from __future__ import annotations

from datetime import datetime, time, timedelta
from typing import Any

from bson import ObjectId

from database.mongo_conn import get_app_user_id, get_collection, remote_uid_filter, sync_to_remote
from services.emergent_insight_service import analyze_operating_system
from services.user_context_service import (
    PROJECT_FIELDS,
    TASK_FIELDS,
    build_active_scope,
    doc_id,
    get_user_dataset,
    is_completed,
    parse_datetime,
    public_doc,
    ref_id,
    serialize_value,
)

COLLECTION = "PlanningSessions"
DEFAULT_TASK_MINUTES = 45

QUESTION_DEFINITIONS = [
    {
        "field": "weekly_available_hours",
        "label": "Horas utiles disponibles esta semana",
        "type": "number",
        "required": True,
        "why": "Permite saber si la semana cabe o hay que recortar.",
    },
    {
        "field": "current_energy",
        "label": "Energia actual",
        "type": "choice",
        "options": ["baja", "media", "alta"],
        "required": True,
        "why": "Ajusta la agresividad del plan.",
    },
    {
        "field": "weekly_top_priorities",
        "label": "Prioridades reales de la semana",
        "type": "list",
        "required": True,
        "why": "Evita que el sistema confunda actividad con importancia.",
    },
    {
        "field": "fixed_commitments",
        "label": "Compromisos fijos",
        "type": "list",
        "required": False,
        "why": "Ayuda a proteger tiempo que no se puede mover.",
    },
    {
        "field": "available_windows",
        "label": "Ventanas disponibles",
        "type": "list",
        "required": False,
        "why": "Convierte las horas totales en huecos reales de agenda.",
    },
    {
        "field": "avoid_this_week",
        "label": "Cosas que no quieres tocar esta semana",
        "type": "list",
        "required": False,
        "why": "Sirve para pausar frentes sin culpa ni ruido.",
    },
    {
        "field": "success_criteria",
        "label": "Criterio de exito del viernes",
        "type": "text",
        "required": True,
        "why": "Convierte la semana en una decision, no en una lista infinita.",
    },
    {
        "field": "notes",
        "label": "Contexto libre",
        "type": "text",
        "required": False,
        "why": "Recoge restricciones o preocupaciones que los datos no ven.",
    },
]

ALLOWED_FIELDS = {question["field"] for question in QUESTION_DEFINITIONS}
REQUIRED_FIELDS = {question["field"] for question in QUESTION_DEFINITIONS if question["required"]}
LIST_FIELDS = {"weekly_top_priorities", "fixed_commitments", "available_windows", "avoid_this_week"}


def week_window(now: datetime | None = None) -> tuple[datetime, datetime]:
    current = now or datetime.utcnow()
    start_date = current.date() - timedelta(days=current.weekday())
    start = datetime.combine(start_date, time.min)
    end = datetime.combine(start_date + timedelta(days=6), time.max.replace(microsecond=0))
    return start, end


def _collection():
    local_col, _ = get_collection(COLLECTION)
    return local_col


def _id_query(value: str | ObjectId) -> dict:
    queries = [{"_id": value}]
    raw = str(value)
    if ObjectId.is_valid(raw):
        queries.append({"_id": ObjectId(raw)})
        queries.append({"_id": raw})
    return {"$or": queries}


def _session_query(session_id: str | ObjectId, usuario_id: str) -> dict:
    return {"$and": [_id_query(session_id), remote_uid_filter(usuario_id)]}


def _public_session(session: dict | None) -> dict | None:
    if not session:
        return None
    return serialize_value(
        {
            "_id": session.get("_id"),
            "usuario_id": session.get("usuario_id"),
            "period_start": session.get("period_start"),
            "period_end": session.get("period_end"),
            "status": session.get("status"),
            "answers": session.get("answers") or {},
            "generated_plan": session.get("generated_plan"),
            "created_at": session.get("created_at"),
            "updated_at": session.get("updated_at"),
        }
    )


def _public_questions() -> list[dict[str, Any]]:
    return serialize_value(QUESTION_DEFINITIONS)


def _missing_questions(session: dict | None) -> list[dict[str, Any]]:
    answers = (session or {}).get("answers") or {}
    missing = []
    for question in QUESTION_DEFINITIONS:
        field = question["field"]
        value = answers.get(field)
        if not question["required"]:
            continue
        if value in (None, "", []):
            missing.append(question)
    return missing


def _next_questions(session: dict | None, *, limit: int = 3) -> list[dict[str, Any]]:
    answers = (session or {}).get("answers") or {}
    required = _missing_questions(session)
    optional = [
        question
        for question in QUESTION_DEFINITIONS
        if not question["required"] and question["field"] not in answers
    ]
    return serialize_value((required + optional)[:limit])


def _normalize_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        raw_items = value
    else:
        text = str(value)
        for separator in ("\n", ";"):
            text = text.replace(separator, ",")
        raw_items = text.split(",")
    seen = set()
    items = []
    for item in raw_items:
        cleaned = str(item or "").strip()
        if not cleaned:
            continue
        key = cleaned.lower()
        if key in seen:
            continue
        seen.add(key)
        items.append(cleaned)
    return items


def _normalize_energy(value: Any) -> str:
    raw = str(value or "").strip().lower()
    aliases = {
        "low": "baja",
        "bajo": "baja",
        "baja": "baja",
        "medium": "media",
        "medio": "media",
        "media": "media",
        "high": "alta",
        "alto": "alta",
        "alta": "alta",
    }
    if raw not in aliases:
        raise ValueError("current_energy debe ser baja, media o alta")
    return aliases[raw]


def _normalize_answer(field: str, value: Any) -> Any:
    if field not in ALLOWED_FIELDS:
        raise ValueError(f"Campo de planificacion no soportado: {field}")
    if field == "weekly_available_hours":
        try:
            parsed = float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError("weekly_available_hours debe ser numerico") from exc
        if parsed < 0 or parsed > 120:
            raise ValueError("weekly_available_hours debe estar entre 0 y 120")
        return round(parsed, 2)
    if field == "current_energy":
        return _normalize_energy(value)
    if field in LIST_FIELDS:
        return _normalize_list(value)
    return str(value or "").strip()


def get_current_week_planning_session(
    usuario_id: str | None = None,
    *,
    now: datetime | None = None,
) -> dict | None:
    user_id = str(usuario_id or get_app_user_id())
    start, end = week_window(now)
    return _collection().find_one(
        {
            "$and": [
                remote_uid_filter(user_id),
                {"period_start": start},
                {"period_end": end},
                {"status": {"$ne": "superseded"}},
            ]
        },
        sort=[("created_at", -1)],
    )


def should_start_weekly_planning(
    usuario_id: str | None = None,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    current = now or datetime.utcnow()
    user_id = str(usuario_id or get_app_user_id())
    session = get_current_week_planning_session(usuario_id=user_id, now=current)
    if session:
        missing = _missing_questions(session)
        return serialize_value(
            {
                "user_id": user_id,
                "period_start": session.get("period_start"),
                "period_end": session.get("period_end"),
                "should_start": False,
                "should_resume": session.get("status") == "active" and bool(missing),
                "reason": "Ya existe una sesion de planificacion para esta semana.",
                "session": _public_session(session),
                "next_questions": _next_questions(session),
                "questions": _public_questions(),
            }
        )

    analysis = analyze_operating_system(usuario_id=user_id, now=current, limit=20)
    findings = analysis["atomic_findings"]["findings"]
    insights = analysis["emergent_insights"]["insights"]
    overdue = sum(1 for finding in findings if finding.get("type") == "overdue_task")
    due_soon = sum(1 for finding in findings if finding.get("type") == "due_soon_task")
    high_insights = [insight for insight in insights if insight.get("impact") == "high"]
    early_week = current.weekday() in {0, 1}
    should_start = early_week or overdue > 0 or due_soon >= 3 or bool(high_insights)
    reasons = []
    if early_week:
        reasons.append("Inicio de semana sin sesion registrada.")
    if overdue:
        reasons.append(f"{overdue} tareas vencidas.")
    if due_soon >= 3:
        reasons.append(f"{due_soon} tareas vencen pronto.")
    if high_insights:
        reasons.append("Hay patrones emergentes de alto impacto.")
    if not reasons:
        reasons.append("No hay senales fuertes, pero la reunion puede mejorar foco y capacidad.")

    start, end = week_window(current)
    return serialize_value(
        {
            "user_id": user_id,
            "period_start": start,
            "period_end": end,
            "should_start": should_start,
            "should_resume": False,
            "reason": " ".join(reasons),
            "session": None,
            "next_questions": QUESTION_DEFINITIONS[:3],
            "questions": _public_questions(),
        }
    )


def start_weekly_planning_session(
    usuario_id: str | None = None,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    current = now or datetime.utcnow()
    user_id = str(usuario_id or get_app_user_id())
    existing = get_current_week_planning_session(usuario_id=user_id, now=current)
    if existing:
        return {
            "created": False,
            "session": _public_session(existing),
            "next_questions": _next_questions(existing),
            "questions": _public_questions(),
        }

    start, end = week_window(current)
    session = {
        "_id": ObjectId(),
        "usuario_id": user_id,
        "period_start": start,
        "period_end": end,
        "status": "active",
        "answers": {},
        "generated_plan": None,
        "created_at": current,
        "updated_at": current,
    }
    _collection().insert_one(session)
    sync_to_remote(COLLECTION, session)
    return {
        "created": True,
        "session": _public_session(session),
        "next_questions": _next_questions(session),
        "questions": _public_questions(),
    }


def answer_weekly_planning_question(
    session_id: str,
    field: str,
    value: Any,
    usuario_id: str | None = None,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    current = now or datetime.utcnow()
    user_id = str(usuario_id or get_app_user_id())
    normalized = _normalize_answer(field, value)
    col = _collection()
    session = col.find_one(_session_query(session_id, user_id))
    if not session:
        raise ValueError("Sesion de planificacion no encontrada para el usuario activo")

    answers = dict(session.get("answers") or {})
    answers[field] = normalized
    status = "active"
    if REQUIRED_FIELDS.issubset({key for key, val in answers.items() if val not in (None, "", [])}):
        status = "ready_for_plan"
    col.update_one(
        {"_id": session["_id"]},
        {
            "$set": {
                "answers": answers,
                "status": status,
                "updated_at": current,
            }
        },
    )
    updated = col.find_one({"_id": session["_id"]})
    sync_to_remote(COLLECTION, updated)
    return {
        "session": _public_session(updated),
        "next_questions": _next_questions(updated),
        "ready_for_plan": status == "ready_for_plan",
        "questions": _public_questions(),
    }


def _task_goal_id(task: dict) -> str:
    return ref_id(task.get("objetivo_id") or task.get("goal_id"))


def _task_project_id(task: dict, goals_by_id: dict[str, dict]) -> str:
    direct = ref_id(task.get("project_id"))
    if direct:
        return direct
    goal = goals_by_id.get(_task_goal_id(task))
    return ref_id((goal or {}).get("project_id"))


def _priority_rank(task: dict) -> int:
    priority = str(task.get("prioridad") or "").lower()
    if priority in {"alta", "high", "urgente", "critica", "crítica"}:
        return 0
    if priority in {"media", "medium"}:
        return 1
    if priority in {"baja", "low"}:
        return 3
    return 2


def _estimated_minutes(task: dict) -> tuple[int, bool]:
    for key in ("estimated_minutes", "duracion_estimada_min", "duration_minutes"):
        value = task.get(key)
        if value in (None, ""):
            continue
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            continue
        if parsed > 0:
            return parsed, False
    return DEFAULT_TASK_MINUTES, True


def _matches_focus(text: str, focus_terms: list[str]) -> bool:
    haystack = text.lower()
    return any(term.lower() in haystack for term in focus_terms if term)


def _task_sort_key(
    task: dict, now: datetime, focus_terms: list[str], projects_by_id: dict, goals_by_id: dict
) -> tuple:
    due_at = parse_datetime(task.get("fecha_limite"))
    project = projects_by_id.get(_task_project_id(task, goals_by_id), {})
    goal = goals_by_id.get(_task_goal_id(task), {})
    searchable = " ".join(
        [
            str(task.get("contenido") or ""),
            str(project.get("titulo") or ""),
            str(goal.get("titulo") or ""),
        ]
    )
    overdue_rank = 0 if due_at and due_at < now else 1
    due_rank = (due_at.date() - now.date()).days if due_at else 999
    focus_rank = 0 if _matches_focus(searchable, focus_terms) else 1
    return (
        overdue_rank,
        due_rank,
        focus_rank,
        _priority_rank(task),
        str(task.get("contenido") or ""),
    )


def _task_entry(task: dict, reason: str, *, estimated_minutes: int, assumed_estimate: bool) -> dict:
    return {
        "task": public_doc(task, TASK_FIELDS),
        "reason": reason,
        "estimated_minutes": estimated_minutes,
        "assumed_estimate": assumed_estimate,
    }


def _build_plan_from_session(session: dict, now: datetime) -> dict[str, Any]:
    answers = session.get("answers") or {}
    dataset = get_user_dataset(usuario_id=session["usuario_id"])
    active_scope = build_active_scope(dataset)
    analysis = analyze_operating_system(usuario_id=session["usuario_id"], now=now, limit=20)
    goals_by_id = {doc_id(goal): goal for goal in active_scope["goals"]}
    projects_by_id = {doc_id(project): project for project in active_scope["projects"]}
    pending_tasks = [task for task in active_scope["tasks"] if not is_completed(task)]
    focus_terms = _normalize_list(answers.get("weekly_top_priorities"))
    avoid_terms = _normalize_list(answers.get("avoid_this_week"))
    sorted_tasks = sorted(
        pending_tasks,
        key=lambda task: _task_sort_key(task, now, focus_terms, projects_by_id, goals_by_id),
    )

    available_hours = answers.get("weekly_available_hours")
    available_minutes = (
        int(float(available_hours) * 60) if available_hours not in (None, "") else None
    )
    energy = answers.get("current_energy")
    energy_factor = {"baja": 0.7, "media": 0.85, "alta": 1.0}.get(str(energy), 0.75)
    budget = int(available_minutes * energy_factor) if available_minutes is not None else None

    do_this_week = []
    defer = []
    review_or_drop = []
    used_minutes = 0
    for task in sorted_tasks:
        estimated, assumed = _estimated_minutes(task)
        due_at = parse_datetime(task.get("fecha_limite"))
        title = str(task.get("contenido") or "")
        avoid = _matches_focus(title, avoid_terms)
        if avoid:
            review_or_drop.append(
                _task_entry(
                    task,
                    "Coincide con un frente que has dicho que no quieres tocar esta semana.",
                    estimated_minutes=estimated,
                    assumed_estimate=assumed,
                )
            )
            continue
        should_include = (
            budget is None
            or used_minutes + estimated <= budget
            or (due_at is not None and due_at < now)
        )
        if should_include and len(do_this_week) < 12:
            used_minutes += estimated
            reason = "Alta prioridad temporal o alineada con foco semanal."
            if due_at and due_at < now:
                reason = "Tarea vencida: requiere decision esta semana."
            elif due_at and (due_at.date() - now.date()).days <= 7:
                reason = "Vence en los proximos 7 dias."
            elif _matches_focus(title, focus_terms):
                reason = "Coincide con las prioridades que has declarado."
            do_this_week.append(
                _task_entry(task, reason, estimated_minutes=estimated, assumed_estimate=assumed)
            )
        else:
            defer.append(
                _task_entry(
                    task,
                    "Queda fuera del presupuesto de capacidad o no compite por urgencia.",
                    estimated_minutes=estimated,
                    assumed_estimate=assumed,
                )
            )

    missing_questions = _missing_questions(session)
    assumptions = []
    if any(item["assumed_estimate"] for item in do_this_week + defer + review_or_drop):
        assumptions.append(
            f"Las tareas sin estimacion usan {DEFAULT_TASK_MINUTES} minutos por defecto."
        )
    if budget is None:
        assumptions.append(
            "No hay horas disponibles; el plan prioriza por urgencia y foco, no por capacidad real."
        )
    if energy:
        assumptions.append(f"La capacidad se ajusta por energia {energy}.")

    focus_projects = []
    for project in active_scope["projects"]:
        title = str(project.get("titulo") or "")
        if focus_terms and not _matches_focus(title, focus_terms):
            continue
        focus_projects.append(public_doc(project, PROJECT_FIELDS))

    severity = "ready" if not missing_questions else "limited_context"
    strategy = "Reducir frente activo y proteger capacidad."
    if analysis["risks"]:
        strategy = analysis["risks"][0]["summary"]
    if not do_this_week:
        strategy = (
            "Antes de ejecutar, completar datos de capacidad o escoger una prioridad principal."
        )

    return serialize_value(
        {
            "status": severity,
            "period_start": session.get("period_start"),
            "period_end": session.get("period_end"),
            "capacity": {
                "available_hours": available_hours,
                "available_minutes": available_minutes,
                "energy": energy,
                "effective_budget_minutes": budget,
                "planned_minutes": used_minutes,
            },
            "focus": {
                "priorities": focus_terms,
                "projects": focus_projects[:5],
                "success_criteria": answers.get("success_criteria"),
                "fixed_commitments": _normalize_list(answers.get("fixed_commitments")),
                "available_windows": _normalize_list(answers.get("available_windows")),
                "avoid_this_week": avoid_terms,
            },
            "recommended_strategy": strategy,
            "do_this_week": do_this_week[:12],
            "defer": defer[:12],
            "review_or_drop": review_or_drop[:12],
            "risks": analysis["risks"][:5],
            "missing_questions": missing_questions,
            "assumptions": assumptions,
            "source": {
                "pending_tasks": len(pending_tasks),
                "atomic_finding_count": analysis["atomic_findings"]["total"],
                "emergent_insight_count": analysis["emergent_insights"]["total"],
            },
        }
    )


def build_weekly_plan(
    session_id: str | None = None,
    usuario_id: str | None = None,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    current = now or datetime.utcnow()
    user_id = str(usuario_id or get_app_user_id())
    if session_id:
        session = _collection().find_one(_session_query(session_id, user_id))
    else:
        session = get_current_week_planning_session(usuario_id=user_id, now=current)
    if not session:
        raise ValueError("No hay sesion de planificacion semanal para el usuario activo")

    plan = _build_plan_from_session(session, current)
    status = "planned" if not plan["missing_questions"] else "active"
    _collection().update_one(
        {"_id": session["_id"]},
        {"$set": {"generated_plan": plan, "status": status, "updated_at": current}},
    )
    updated = _collection().find_one({"_id": session["_id"]})
    sync_to_remote(COLLECTION, updated)
    return {
        "session": _public_session(updated),
        "plan": plan,
        "ready": status == "planned",
        "next_questions": _next_questions(updated),
        "questions": _public_questions(),
    }


def get_current_week_plan(
    usuario_id: str | None = None,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    user_id = str(usuario_id or get_app_user_id())
    session = get_current_week_planning_session(usuario_id=user_id, now=now)
    return {
        "session": _public_session(session),
        "plan": serialize_value((session or {}).get("generated_plan")),
        "next_questions": _next_questions(session),
        "questions": _public_questions(),
    }
