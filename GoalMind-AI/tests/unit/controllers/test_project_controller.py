"""Bateria completa del controlador REST de proyectos (`controllers/project_controller.py`).

Cubre las 11 rutas HTTP (listado con filtros, alta, detalle, alta/baja de
anotaciones, actualizacion, borrado en cascada, subida/visualizacion/descarga/
baja de documentos). Los *helpers* puros (`_format_size`, `_parse_importance`,
`_resolve_document_source`, etc.) ya estan cubiertos por
`tests/test_project_helpers.py`; este fichero se centra en los *endpoints*.
"""

from __future__ import annotations

from io import BytesIO

import pytest
from bson import ObjectId
from flask import Flask

from controllers import project_controller
from controllers.project_controller import project_bp


@pytest.fixture
def client(monkeypatch):
    app = Flask(__name__)
    app.secret_key = "test-secret"
    app.config["TESTING"] = True

    def _fake_render(template_name, **ctx):
        keys = ",".join(sorted(ctx.keys()))
        return f"RENDER::{template_name}::{keys}"

    monkeypatch.setattr(project_controller, "render_template", _fake_render)
    # Aislar GridFS y la cola de borrados.
    monkeypatch.setattr(project_controller, "queue_deletion", lambda *a, **k: True)
    monkeypatch.setattr(project_controller, "flush_deletion_queue", lambda: 0)
    monkeypatch.setattr(
        project_controller, "upload_stream_to_local_storage",
        lambda stream, original_name=None, content_type=None, metadata=None: ObjectId(),
    )
    monkeypatch.setattr(
        project_controller, "promote_local_file_to_remote",
        lambda local_id, original_name=None, content_type=None, metadata=None, app=None: ObjectId(),
    )
    monkeypatch.setattr(
        project_controller, "download_file_from_local_storage",
        lambda fid: b"file-bytes",
    )
    monkeypatch.setattr(
        project_controller, "download_file_from_remote_storage",
        lambda fid, app=None: None,
    )
    app.register_blueprint(project_bp)
    return app.test_client()


def _project_doc(titulo="TFG", estado="Activo", prioridad="Alta", categorias=None):
    return {
        "_id": ObjectId(),
        "titulo": titulo,
        "estado": estado,
        "prioridad": prioridad,
        "importancia": 7,
        "categorias": categorias or [],
    }


def _stub_loaders(monkeypatch, projects=None, goals=None, docs=None, categories=None):
    monkeypatch.setattr(
        project_controller.ProjectModel, "get_all_projects",
        staticmethod(lambda usuario_id=None: projects or []),
    )
    monkeypatch.setattr(
        project_controller.GoalModel, "get_all_goals",
        staticmethod(lambda usuario_id=None: goals or []),
    )
    monkeypatch.setattr(
        project_controller.ProjectDocumentModel, "get_all_documents",
        staticmethod(lambda usuario_id=None: docs or []),
    )
    monkeypatch.setattr(
        project_controller.CategoryModel, "get_all_categories",
        staticmethod(lambda usuario_id=None: categories or []),
    )


# ---------------------------------------------------------------------------
# GET /projects/
# ---------------------------------------------------------------------------


class TestListProjects:
    def test_returns_render_with_projects(self, client, monkeypatch):
        _stub_loaders(monkeypatch, projects=[_project_doc()])
        resp = client.get("/projects/")
        assert resp.status_code == 200
        assert b"projects" in resp.data
        assert b"goal_counts" in resp.data
        assert b"doc_counts" in resp.data

    def test_filter_by_query_q(self, client, monkeypatch):
        _stub_loaders(monkeypatch, projects=[_project_doc("TFG"), _project_doc("otra")])
        resp = client.get("/projects/?q=tfg")
        assert resp.status_code == 200

    def test_filter_by_status_priority_category(self, client, monkeypatch):
        cat_id = ObjectId()
        _stub_loaders(
            monkeypatch,
            projects=[
                _project_doc("A", estado="Activo", prioridad="Alta", categorias=[cat_id]),
                _project_doc("B", estado="Pausado", prioridad="Baja"),
            ],
        )
        resp = client.get(f"/projects/?status=activo&priority=alta&category={cat_id}")
        assert resp.status_code == 200

    def test_sort_cookie_is_set(self, client, monkeypatch):
        _stub_loaders(monkeypatch, projects=[_project_doc()])
        resp = client.get("/projects/?order=importance-asc")
        assert resp.status_code == 200
        # La cookie `projects_sort` debe estar en la respuesta
        cookies = resp.headers.get_all("Set-Cookie")
        assert any("projects_sort" in c for c in cookies)

    def test_invalid_sort_falls_back(self, client, monkeypatch):
        _stub_loaders(monkeypatch, projects=[_project_doc()])
        resp = client.get("/projects/?order=invalid")
        assert resp.status_code == 200

    def test_handles_loader_exception(self, client, monkeypatch):
        def _boom(usuario_id=None):
            raise RuntimeError("db")

        monkeypatch.setattr(
            project_controller.ProjectModel, "get_all_projects", staticmethod(_boom)
        )
        # Los otros loaders siguen al default
        _stub_loaders(monkeypatch)
        resp = client.get("/projects/")
        assert resp.status_code == 200

    def test_goals_compute_progress_average(self, client, monkeypatch):
        proj = _project_doc()
        _stub_loaders(
            monkeypatch,
            projects=[proj],
            goals=[
                {"_id": ObjectId(), "project_id": proj["_id"], "progreso": 80},
                {"_id": ObjectId(), "project_id": proj["_id"], "progreso": 40},
            ],
        )
        resp = client.get("/projects/")
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# POST /projects/add
# ---------------------------------------------------------------------------


class TestAddProject:
    def test_redirects_when_no_title(self, client):
        resp = client.post("/projects/add", data={})
        assert resp.status_code == 302

    def test_inserts_project_with_full_payload(self, client, monkeypatch):
        captured = {}
        cat = ObjectId()
        monkeypatch.setattr(
            project_controller.ProjectModel, "insert_project",
            staticmethod(lambda d: captured.setdefault("d", d) or d),
        )
        resp = client.post(
            "/projects/add",
            data={
                "titulo": "Mi proyecto",
                "descripcion": "d",
                "estado": "Activo",
                "prioridad": "Alta",
                "fecha_inicio": "2026-01-01",
                "fecha_fin": "2026-12-31",
                "categorias": str(cat),
            },
        )
        assert resp.status_code == 302
        assert captured["d"]["titulo"] == "Mi proyecto"
        assert captured["d"]["categorias"] == [cat]

    def test_exception_redirects_gracefully(self, client, monkeypatch):
        def _boom(d):
            raise RuntimeError("fail")

        monkeypatch.setattr(project_controller.ProjectModel, "insert_project", staticmethod(_boom))
        resp = client.post("/projects/add", data={"titulo": "x"})
        assert resp.status_code == 302


# ---------------------------------------------------------------------------
# GET /projects/<project_id>
# ---------------------------------------------------------------------------


class TestViewProject:
    def test_redirects_when_not_found(self, client, monkeypatch):
        monkeypatch.setattr(
            project_controller.ProjectModel, "get_project_by_id",
            staticmethod(lambda pid, usuario_id=None: None),
        )
        resp = client.get(f"/projects/{ObjectId()}")
        assert resp.status_code == 302

    def test_renders_project_with_goals_docs_tasks(self, client, monkeypatch):
        proj = _project_doc()
        goal = {"_id": ObjectId(), "titulo": "g1", "project_id": proj["_id"]}
        monkeypatch.setattr(
            project_controller.ProjectModel, "get_project_by_id",
            staticmethod(lambda pid, usuario_id=None: proj),
        )
        monkeypatch.setattr(
            project_controller.GoalModel, "get_by_project",
            staticmethod(lambda pid, usuario_id=None: [goal]),
        )
        monkeypatch.setattr(
            project_controller.ProjectDocumentModel, "get_by_project",
            staticmethod(lambda pid, usuario_id=None: [
                {"_id": ObjectId(), "original_name": "d.pdf", "goal_id": goal["_id"]}
            ]),
        )
        monkeypatch.setattr(
            project_controller.TaskModel, "get_tasks_by_goal",
            staticmethod(lambda gid, usuario_id=None: [
                {"_id": ObjectId(), "contenido": "t", "estado": "pendiente", "prioridad": "media"}
            ]),
        )
        monkeypatch.setattr(
            project_controller.CategoryModel, "get_all_categories",
            staticmethod(lambda usuario_id=None: []),
        )
        resp = client.get(f"/projects/{proj['_id']}")
        assert resp.status_code == 200
        assert b"goals" in resp.data
        assert b"documents" in resp.data
        assert b"goal_tasks" in resp.data


# ---------------------------------------------------------------------------
# POST /projects/<project_id>/notes/add
# ---------------------------------------------------------------------------


class TestAddProjectNote:
    def test_empty_note_redirects(self, client):
        resp = client.post(f"/projects/{ObjectId()}/notes/add", data={"note_text": "   "})
        assert resp.status_code == 302

    def test_project_not_found(self, client, monkeypatch):
        monkeypatch.setattr(
            project_controller.ProjectModel, "get_project_by_id",
            staticmethod(lambda pid, usuario_id=None: None),
        )
        resp = client.post(f"/projects/{ObjectId()}/notes/add", data={"note_text": "x"})
        assert resp.status_code == 302

    def test_appends_note(self, client, monkeypatch):
        pid = ObjectId()
        proj = {"_id": pid, "titulo": "P", "notas": []}
        captured = {}
        monkeypatch.setattr(
            project_controller.ProjectModel, "get_project_by_id",
            staticmethod(lambda p, usuario_id=None: proj),
        )
        monkeypatch.setattr(
            project_controller.ProjectModel, "update_project",
            staticmethod(lambda p, upd, usuario_id=None: captured.update({"upd": upd})),
        )
        resp = client.post(f"/projects/{pid}/notes/add", data={"note_text": "hola"})
        assert resp.status_code == 302
        assert len(captured["upd"]["notas"]) == 1
        assert captured["upd"]["notas"][0]["text"] == "hola"


# ---------------------------------------------------------------------------
# POST /projects/<project_id>/notes/<note_id>/delete
# ---------------------------------------------------------------------------


class TestDeleteProjectNote:
    def test_project_not_found_redirects(self, client, monkeypatch):
        monkeypatch.setattr(
            project_controller.ProjectModel, "get_project_by_id",
            staticmethod(lambda p, usuario_id=None: None),
        )
        resp = client.post(f"/projects/{ObjectId()}/notes/n1/delete")
        assert resp.status_code == 302

    def test_filters_out_target_note(self, client, monkeypatch):
        captured = {}
        proj = {"_id": ObjectId(), "notas": [{"_id": "n1", "text": "a"}, {"_id": "n2", "text": "b"}]}
        monkeypatch.setattr(
            project_controller.ProjectModel, "get_project_by_id",
            staticmethod(lambda p, usuario_id=None: proj),
        )
        monkeypatch.setattr(
            project_controller.ProjectModel, "update_project",
            staticmethod(lambda p, upd, usuario_id=None: captured.update({"upd": upd})),
        )
        resp = client.post(f"/projects/{proj['_id']}/notes/n1/delete")
        assert resp.status_code == 302
        assert [n["_id"] for n in captured["upd"]["notas"]] == ["n2"]


# ---------------------------------------------------------------------------
# POST /projects/update/<project_id>
# ---------------------------------------------------------------------------


class TestUpdateProject:
    def test_updates_passes_fields(self, client, monkeypatch):
        captured = {}
        monkeypatch.setattr(
            project_controller.ProjectModel, "update_project",
            staticmethod(lambda p, upd, usuario_id=None: captured.update({"upd": upd})),
        )
        resp = client.post(
            f"/projects/update/{ObjectId()}",
            data={"titulo": "nuevo", "estado": "Pausado"},
        )
        assert resp.status_code == 302
        assert captured["upd"]["titulo"] == "nuevo"
        assert captured["upd"]["estado"] == "Pausado"

    def test_categorias_valid_single_value(self, client, monkeypatch):
        captured = {}
        cat = ObjectId()
        monkeypatch.setattr(
            project_controller.ProjectModel, "update_project",
            staticmethod(lambda p, upd, usuario_id=None: captured.update({"upd": upd})),
        )
        resp = client.post(
            f"/projects/update/{ObjectId()}",
            data={"titulo": "x", "categorias": str(cat)},
        )
        assert resp.status_code == 302
        assert captured["upd"]["categorias"] == [cat]

    def test_categorias_invalid_silently_filtered(self, client, monkeypatch):
        captured = {}
        monkeypatch.setattr(
            project_controller.ProjectModel, "update_project",
            staticmethod(lambda p, upd, usuario_id=None: captured.update({"upd": upd})),
        )
        resp = client.post(
            f"/projects/update/{ObjectId()}",
            data={"titulo": "x", "categorias": "no-es-objectid"},
        )
        assert resp.status_code == 302
        # La lista de categorias queda vacia tras el filtrado.
        assert captured["upd"].get("categorias", []) == []

    def test_exception_redirects(self, client, monkeypatch):
        def _boom(p, upd, usuario_id=None):
            raise RuntimeError("fail")

        monkeypatch.setattr(project_controller.ProjectModel, "update_project", staticmethod(_boom))
        resp = client.post(f"/projects/update/{ObjectId()}", data={"titulo": "x"})
        assert resp.status_code == 302


# ---------------------------------------------------------------------------
# POST /projects/delete/<project_id>  (con cascada)
# ---------------------------------------------------------------------------


class TestDeleteProject:
    def test_cascade_removes_goals_tasks_and_documents(self, client, monkeypatch):
        pid = ObjectId()
        goal_id = ObjectId()
        task_id = ObjectId()
        doc_id = ObjectId()
        queue_calls = []

        monkeypatch.setattr(
            project_controller.GoalModel, "get_by_project",
            staticmethod(lambda p, usuario_id=None: [{"_id": goal_id}]),
        )
        monkeypatch.setattr(
            project_controller.TaskModel, "get_tasks_by_goal",
            staticmethod(lambda g, usuario_id=None: [{"_id": task_id}]),
        )
        monkeypatch.setattr(
            project_controller.TaskModel, "delete_tasks_by_ids",
            staticmethod(lambda ids, usuario_id=None: len(ids)),
        )
        monkeypatch.setattr(
            project_controller.GoalModel, "delete_goals_by_ids",
            staticmethod(lambda ids, usuario_id=None: len(ids)),
        )
        monkeypatch.setattr(
            project_controller.ProjectDocumentModel, "get_by_project",
            staticmethod(lambda p, usuario_id=None: [{"_id": doc_id, "project_id": pid}]),
        )
        monkeypatch.setattr(
            project_controller.ProjectDocumentModel, "delete_document",
            staticmethod(lambda d, usuario_id=None: True),
        )
        monkeypatch.setattr(
            project_controller.ProjectModel, "delete_project",
            staticmethod(lambda p, usuario_id=None: True),
        )
        monkeypatch.setattr(
            project_controller, "queue_deletion",
            lambda col, tid: queue_calls.append((col, tid)),
        )

        resp = client.post(f"/projects/delete/{pid}")
        assert resp.status_code == 302
        cols = [c for c, _ in queue_calls]
        assert cols.count("Tasks") == 1
        assert cols.count("Goals") == 1
        assert cols.count("ProjectDocuments") == 1
        assert cols.count("Projects") == 1

    def test_delete_with_collection_errors_still_redirects(self, client, monkeypatch):
        def _boom(*a, **k):
            raise RuntimeError("fail")

        monkeypatch.setattr(project_controller.GoalModel, "get_by_project", staticmethod(_boom))
        monkeypatch.setattr(
            project_controller.ProjectDocumentModel, "get_by_project",
            staticmethod(_boom),
        )
        monkeypatch.setattr(
            project_controller.ProjectModel, "delete_project",
            staticmethod(_boom),
        )
        resp = client.post(f"/projects/delete/{ObjectId()}")
        assert resp.status_code == 302


# ---------------------------------------------------------------------------
# POST /projects/<project_id>/documents  (subida)
# ---------------------------------------------------------------------------


class TestUploadDocument:
    def test_project_not_found(self, client, monkeypatch):
        monkeypatch.setattr(
            project_controller.ProjectModel, "get_project_by_id",
            staticmethod(lambda p, usuario_id=None: None),
        )
        resp = client.post(
            f"/projects/{ObjectId()}/documents",
            data={},
        )
        assert resp.status_code == 302

    def test_no_file_redirects(self, client, monkeypatch):
        monkeypatch.setattr(
            project_controller.ProjectModel, "get_project_by_id",
            staticmethod(lambda p, usuario_id=None: _project_doc()),
        )
        resp = client.post(f"/projects/{ObjectId()}/documents", data={})
        assert resp.status_code == 302

    def test_upload_with_remote_promotion(self, client, monkeypatch):
        proj_id = ObjectId()
        captured = {}
        monkeypatch.setattr(
            project_controller.ProjectModel, "get_project_by_id",
            staticmethod(lambda p, usuario_id=None: {"_id": proj_id, "titulo": "P"}),
        )
        monkeypatch.setattr(
            project_controller.ProjectDocumentModel, "insert_document",
            staticmethod(lambda d, usuario_id=None: captured.setdefault("d", d) or d),
        )
        resp = client.post(
            f"/projects/{proj_id}/documents",
            data={"document": (BytesIO(b"contenido"), "x.txt")},
            content_type="multipart/form-data",
        )
        assert resp.status_code == 302
        # Se ha guardado con `upload_id` remoto y la bandera de sync apagada.
        assert captured["d"]["remote_sync_pending"] is False
        assert "upload_id" in captured["d"]

    def test_upload_falls_back_to_local_when_remote_fails(self, client, monkeypatch):
        proj_id = ObjectId()
        captured = {}
        monkeypatch.setattr(
            project_controller.ProjectModel, "get_project_by_id",
            staticmethod(lambda p, usuario_id=None: {"_id": proj_id, "titulo": "P"}),
        )
        monkeypatch.setattr(
            project_controller, "promote_local_file_to_remote",
            lambda *a, **k: None,
        )
        monkeypatch.setattr(
            project_controller.ProjectDocumentModel, "insert_document",
            staticmethod(lambda d, usuario_id=None: captured.setdefault("d", d) or d),
        )
        resp = client.post(
            f"/projects/{proj_id}/documents",
            data={"document": (BytesIO(b"x"), "y.txt")},
            content_type="multipart/form-data",
        )
        assert resp.status_code == 302
        # Sin remoto: queda con la bandera de sync pendiente.
        assert captured["d"]["remote_sync_pending"] is True
        assert "local_upload_id" in captured["d"]

    def test_upload_local_storage_failure_redirects(self, client, monkeypatch):
        monkeypatch.setattr(
            project_controller.ProjectModel, "get_project_by_id",
            staticmethod(lambda p, usuario_id=None: {"_id": ObjectId(), "titulo": "P"}),
        )
        monkeypatch.setattr(
            project_controller, "upload_stream_to_local_storage",
            lambda *a, **k: None,
        )
        resp = client.post(
            f"/projects/{ObjectId()}/documents",
            data={"document": (BytesIO(b"x"), "z.txt")},
            content_type="multipart/form-data",
        )
        assert resp.status_code == 302


# ---------------------------------------------------------------------------
# GET /projects/documents/<doc_id>/view  +  /download
# ---------------------------------------------------------------------------


class TestViewAndDownloadDocument:
    def test_view_returns_404_redirect_when_not_found(self, client, monkeypatch):
        monkeypatch.setattr(
            project_controller.ProjectDocumentModel, "get_document_by_id",
            staticmethod(lambda d, usuario_id=None: None),
        )
        resp = client.get(f"/projects/documents/{ObjectId()}/view")
        assert resp.status_code == 302

    def test_view_streams_file_when_present(self, client, monkeypatch):
        doc = {
            "_id": ObjectId(),
            "original_name": "a.txt",
            "content_type": "text/plain",
            "local_upload_id": ObjectId(),
            "project_id": ObjectId(),
        }
        monkeypatch.setattr(
            project_controller.ProjectDocumentModel, "get_document_by_id",
            staticmethod(lambda d, usuario_id=None: doc),
        )
        resp = client.get(f"/projects/documents/{doc['_id']}/view")
        assert resp.status_code == 200
        assert resp.data == b"file-bytes"

    def test_view_handles_missing_bytes(self, client, monkeypatch):
        doc = {"_id": ObjectId(), "original_name": "x", "project_id": ObjectId()}
        monkeypatch.setattr(
            project_controller.ProjectDocumentModel, "get_document_by_id",
            staticmethod(lambda d, usuario_id=None: doc),
        )
        monkeypatch.setattr(
            project_controller, "download_file_from_local_storage", lambda fid: None,
        )
        monkeypatch.setattr(
            project_controller, "download_file_from_remote_storage", lambda fid, app=None: None,
        )
        resp = client.get(f"/projects/documents/{doc['_id']}/view")
        assert resp.status_code == 302

    def test_download_attaches_filename(self, client, monkeypatch):
        doc = {
            "_id": ObjectId(),
            "original_name": "x.pdf",
            "content_type": "application/pdf",
            "local_upload_id": ObjectId(),
            "project_id": ObjectId(),
        }
        monkeypatch.setattr(
            project_controller.ProjectDocumentModel, "get_document_by_id",
            staticmethod(lambda d, usuario_id=None: doc),
        )
        resp = client.get(f"/projects/documents/{doc['_id']}/download")
        assert resp.status_code == 200
        assert "attachment" in resp.headers.get("Content-Disposition", "")

    def test_download_not_found_redirects(self, client, monkeypatch):
        monkeypatch.setattr(
            project_controller.ProjectDocumentModel, "get_document_by_id",
            staticmethod(lambda d, usuario_id=None: None),
        )
        resp = client.get(f"/projects/documents/{ObjectId()}/download")
        assert resp.status_code == 302


# ---------------------------------------------------------------------------
# POST /projects/documents/<doc_id>/delete
# ---------------------------------------------------------------------------


class TestDeleteDocument:
    def test_delete_not_found_redirects(self, client, monkeypatch):
        monkeypatch.setattr(
            project_controller.ProjectDocumentModel, "get_document_by_id",
            staticmethod(lambda d, usuario_id=None: None),
        )
        resp = client.post(f"/projects/documents/{ObjectId()}/delete")
        assert resp.status_code == 302

    def test_delete_invokes_model_and_queue(self, client, monkeypatch):
        doc_id = ObjectId()
        queue_calls = []
        monkeypatch.setattr(
            project_controller.ProjectDocumentModel, "get_document_by_id",
            staticmethod(lambda d, usuario_id=None: {"_id": doc_id, "project_id": ObjectId()}),
        )
        monkeypatch.setattr(
            project_controller.ProjectDocumentModel, "delete_document",
            staticmethod(lambda d, usuario_id=None: True),
        )
        monkeypatch.setattr(
            project_controller, "queue_deletion",
            lambda col, did: queue_calls.append((col, did)),
        )
        resp = client.post(f"/projects/documents/{doc_id}/delete")
        assert resp.status_code == 302
        assert queue_calls == [("ProjectDocuments", str(doc_id))]

    def test_delete_with_model_exception_still_queues(self, client, monkeypatch):
        doc_id = ObjectId()
        monkeypatch.setattr(
            project_controller.ProjectDocumentModel, "get_document_by_id",
            staticmethod(lambda d, usuario_id=None: {"_id": doc_id, "project_id": ObjectId()}),
        )

        def _boom(*a, **k):
            raise RuntimeError("fail")

        monkeypatch.setattr(
            project_controller.ProjectDocumentModel, "delete_document", staticmethod(_boom)
        )
        resp = client.post(f"/projects/documents/{doc_id}/delete")
        assert resp.status_code == 302
