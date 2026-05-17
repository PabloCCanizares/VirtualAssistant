"""Tests de integracion sobre el borrado en cascada.

El borrado del agente IA (`_delete_project_cascade`, `_delete_goal_cascade`
en `ai/agents/action_executor.py`) propaga el borrado a entidades
descendentes y registra cada borrado en la `DeleteQueue`. Aqui se cubre la
cascada via la ruta del agente, sin pasar por HTTP.

Hallazgo documentado: `CategoryModel.delete_category` NO limpia las
referencias en `Projects.categorias`, `Goals.categorias` ni
`Tasks.categorias`. Los tests al final demuestran este comportamiento
para soportar la nota correspondiente en la memoria.
"""

from __future__ import annotations

import pytest
from bson import ObjectId

pytestmark = pytest.mark.integration

USER_ID_STR = "66ffbbbbbbbbbbbbbbbb0100"


def _seed_project_tree(local_db, *, with_doc=True):
    """Crea un proyecto con 2 objetivos, 3 tareas y opcionalmente 1 doc."""
    project_id = ObjectId()
    goal1, goal2 = ObjectId(), ObjectId()
    task1, task2, task3 = ObjectId(), ObjectId(), ObjectId()

    local_db["Projects"].insert_one({"_id": project_id, "titulo": "TFG", "usuario_id": USER_ID_STR})
    local_db["Goals"].insert_many([
        {"_id": goal1, "titulo": "redactar", "project_id": project_id, "usuario_id": USER_ID_STR},
        {"_id": goal2, "titulo": "implementar", "project_id": project_id, "usuario_id": USER_ID_STR},
    ])
    local_db["Tasks"].insert_many([
        {"_id": task1, "contenido": "intro", "objetivo_id": goal1, "usuario_id": USER_ID_STR},
        {"_id": task2, "contenido": "metodologia", "objetivo_id": goal1, "usuario_id": USER_ID_STR},
        {"_id": task3, "contenido": "tests", "objetivo_id": goal2, "usuario_id": USER_ID_STR},
    ])
    if with_doc:
        local_db["ProjectDocuments"].insert_one({
            "_id": ObjectId(),
            "project_id": project_id,
            "usuario_id": USER_ID_STR,
            "original_name": "borrador.pdf",
        })

    return {
        "project_id": project_id,
        "goal_ids": [goal1, goal2],
        "task_ids": [task1, task2, task3],
    }


class TestDeleteProjectCascade:
    def test_project_deletion_removes_goals_tasks_and_documents(self, mongo_mock):
        from ai.agents.action_executor import _delete_project_cascade

        ids = _seed_project_tree(mongo_mock.local_db)
        _delete_project_cascade(str(ids["project_id"]), USER_ID_STR)

        # Proyecto, objetivos y tareas eliminados
        assert mongo_mock.local_db["Projects"].count_documents({}) == 0
        assert mongo_mock.local_db["Goals"].count_documents({}) == 0
        assert mongo_mock.local_db["Tasks"].count_documents({}) == 0
        # Documentos del proyecto eliminados
        assert mongo_mock.local_db["ProjectDocuments"].count_documents({}) == 0

    def test_project_deletion_queues_all_descendants(self, mongo_mock):
        from ai.agents.action_executor import _delete_project_cascade

        ids = _seed_project_tree(mongo_mock.local_db)
        _delete_project_cascade(str(ids["project_id"]), USER_ID_STR)

        queue = list(mongo_mock.local_db["DeleteQueue"].find())
        cols = {q["collection"] for q in queue}
        assert {"Projects", "Goals", "Tasks", "ProjectDocuments"} <= cols


class TestDeleteGoalCascade:
    def test_goal_deletion_removes_its_tasks_but_not_siblings(self, mongo_mock):
        from ai.agents.action_executor import _delete_goal_cascade

        ids = _seed_project_tree(mongo_mock.local_db, with_doc=False)
        goal_to_keep = ids["goal_ids"][1]
        goal_to_delete = ids["goal_ids"][0]

        _delete_goal_cascade(str(goal_to_delete), USER_ID_STR)

        # El objetivo borrado y sus tareas estan fuera
        assert mongo_mock.local_db["Goals"].find_one({"_id": goal_to_delete}) is None
        remaining_tasks = list(mongo_mock.local_db["Tasks"].find())
        assert all(t["objetivo_id"] == goal_to_keep for t in remaining_tasks)
        # El otro objetivo sigue ahi
        assert mongo_mock.local_db["Goals"].find_one({"_id": goal_to_keep}) is not None


class TestCategoryDeleteDoesNotCleanReferences:
    """Hallazgo del bloque 2: el borrado de categoria deja referencias huerfanas."""

    def test_references_remain_after_delete(self, mongo_mock):
        from model.category_model import CategoryModel

        cat_id = ObjectId()
        # Inserta directamente la categoria saltando insert_category() (que requiere
        # busqueda case-insensitive con $regex sobre name; mongomock lo soporta,
        # pero aqui solo nos interesa la cascada del DELETE).
        mongo_mock.local_db["Categories"].insert_one({
            "_id": cat_id,
            "name": "investigacion",
            "usuario_id": USER_ID_STR,
        })
        # Tres entidades referencian la categoria.
        mongo_mock.local_db["Projects"].insert_one({
            "_id": ObjectId(), "titulo": "TFG",
            "categorias": [cat_id], "usuario_id": USER_ID_STR,
        })
        mongo_mock.local_db["Goals"].insert_one({
            "_id": ObjectId(), "titulo": "redactar",
            "categorias": [cat_id], "usuario_id": USER_ID_STR,
        })
        mongo_mock.local_db["Tasks"].insert_one({
            "_id": ObjectId(), "contenido": "intro",
            "categorias": [cat_id], "usuario_id": USER_ID_STR,
        })

        # Verificamos el uso pre-borrado
        usage = CategoryModel.get_category_usage(cat_id, usuario_id=USER_ID_STR)
        assert usage == {"goals": 1, "tasks": 1, "projects": 1, "total": 3}

        # Borrado
        assert CategoryModel.delete_category(cat_id, usuario_id=USER_ID_STR) is True

        # Las referencias siguen exactamente ahi (hallazgo).
        assert mongo_mock.local_db["Projects"].count_documents({"categorias": cat_id}) == 1
        assert mongo_mock.local_db["Goals"].count_documents({"categorias": cat_id}) == 1
        assert mongo_mock.local_db["Tasks"].count_documents({"categorias": cat_id}) == 1
