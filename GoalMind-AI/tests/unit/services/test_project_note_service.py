from datetime import datetime

from services.project_service import add_project_note, delete_project_note

USER_ID = "66ffbbbbbbbbbbbbbbbb0100"


class _ProjectModel:
    project = None
    updated = None

    @classmethod
    def get_project_by_id(cls, project_id, usuario_id=None):
        return cls.project

    @classmethod
    def update_project(cls, project_id, updates, usuario_id=None):
        cls.updated = {
            "project_id": project_id,
            "updates": updates,
            "usuario_id": usuario_id,
        }


class TestAddProjectNote:
    def setup_method(self):
        _ProjectModel.project = {"_id": "p1", "notas": []}
        _ProjectModel.updated = None

    def test_rejects_empty_note(self):
        result = add_project_note(
            "p1",
            "   ",
            usuario_id=USER_ID,
            project_model=_ProjectModel,
        )

        assert result.ok is False
        assert result.level == "warning"
        assert _ProjectModel.updated is None

    def test_adds_note_with_deterministic_metadata(self):
        result = add_project_note(
            "p1",
            " revisar memoria ",
            usuario_id=USER_ID,
            project_model=_ProjectModel,
            note_id_factory=lambda: "note-1",
            now_fn=lambda: datetime(2026, 1, 1, 12, 0),
        )

        assert result.ok is True
        assert result.note == {
            "_id": "note-1",
            "text": "revisar memoria",
            "created_at": datetime(2026, 1, 1, 12, 0),
        }
        assert _ProjectModel.updated["updates"]["notas"] == [result.note]

    def test_missing_project_redirects_to_list(self):
        _ProjectModel.project = None

        result = add_project_note(
            "p1",
            "nota",
            usuario_id=USER_ID,
            project_model=_ProjectModel,
        )

        assert result.ok is False
        assert result.redirect_to_list is True


class TestDeleteProjectNote:
    def setup_method(self):
        _ProjectModel.project = {
            "_id": "p1",
            "notas": [{"_id": "n1", "text": "a"}, {"_id": "n2", "text": "b"}],
        }
        _ProjectModel.updated = None

    def test_removes_target_note(self):
        result = delete_project_note(
            "p1",
            "n1",
            usuario_id=USER_ID,
            project_model=_ProjectModel,
        )

        assert result.ok is True
        assert _ProjectModel.updated["updates"]["notas"] == [{"_id": "n2", "text": "b"}]

    def test_missing_project_redirects_to_list(self):
        _ProjectModel.project = None

        result = delete_project_note(
            "p1",
            "n1",
            usuario_id=USER_ID,
            project_model=_ProjectModel,
        )

        assert result.ok is False
        assert result.redirect_to_list is True
