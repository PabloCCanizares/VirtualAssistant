"""Tests para helpers puros de ai.agents.supervisor (sin invocar al LLM)."""

from __future__ import annotations

import json

from ai.agents import supervisor


class TestParseSupervisorJson:
    def test_empty_text_returns_empty_dict(self):
        assert supervisor._parse_supervisor_json("") == {}

    def test_strict_json_parsed(self):
        assert supervisor._parse_supervisor_json('{"category": "research"}') == {"category": "research"}

    def test_recovery_from_surrounding_text(self):
        raw = 'pensamiento... {"category": "action", "use_critic": false} ...fin'
        assert supervisor._parse_supervisor_json(raw) == {"category": "action", "use_critic": False}

    def test_returns_empty_when_unparseable(self):
        assert supervisor._parse_supervisor_json("nada parseable") == {}

    def test_returns_empty_for_malformed_json_substring(self):
        assert supervisor._parse_supervisor_json('start { malformed } end') == {}


class TestExtractDocsFromMutations:
    def test_invalid_json_returns_empty(self):
        assert supervisor._extract_docs_from_mutations("no json") == []

    def test_non_list_returns_empty(self):
        assert supervisor._extract_docs_from_mutations(json.dumps({"x": 1})) == []

    def test_filters_non_document_mutations(self):
        mutations = [
            {"type": "task", "action": "listed", "id": "t1"},
            {"type": "document", "action": "listed", "id": "d1", "name": "a.pdf"},
        ]
        out = supervisor._extract_docs_from_mutations(json.dumps(mutations))
        assert len(out) == 1
        assert out[0]["_id"] == "d1"

    def test_filters_irrelevant_actions(self):
        mutations = [
            {"type": "document", "action": "deleted", "id": "d1"},
            {"type": "document", "action": "read", "id": "d2"},
        ]
        out = supervisor._extract_docs_from_mutations(json.dumps(mutations))
        assert [d["_id"] for d in out] == ["d2"]

    def test_dedupes_by_id(self):
        mutations = [
            {"type": "document", "action": "listed", "id": "d1", "name": "a.pdf"},
            {"type": "document", "action": "read", "id": "d1", "name": "a.pdf"},
        ]
        out = supervisor._extract_docs_from_mutations(json.dumps(mutations))
        assert len(out) == 1

    def test_extracts_project_name_from_description(self):
        mutations = [
            {
                "type": "document",
                "action": "listed",
                "id": "d1",
                "name": "doc.pdf",
                "description": "proyecto: Proyecto Alfa",
            }
        ]
        out = supervisor._extract_docs_from_mutations(json.dumps(mutations))
        assert out[0]["_project_name"] == "Proyecto Alfa"

    def test_default_name_when_missing(self):
        mutations = [{"type": "document", "action": "listed", "id": "d1"}]
        out = supervisor._extract_docs_from_mutations(json.dumps(mutations))
        assert out[0]["original_name"] == "sin nombre"


class TestBuildDocListForResolver:
    def test_renders_lines_per_document(self):
        docs = [
            {"_id": "d1", "original_name": "a.pdf", "project_id": "p1"},
            {"_id": "d2", "original_name": "b.pdf", "project_id": "p1"},
        ]
        context = {
            "projects": [{"_id": "p1", "titulo": "Mi Proyecto", "categorias": ["c1"]}],
            "categories": [{"_id": "c1", "nombre": "Investigacion"}],
        }
        out = supervisor._build_doc_list_for_resolver(docs, context)
        assert "ID: d1" in out
        assert "Nombre: a.pdf" in out
        assert "Mi Proyecto" in out
        assert "Investigacion" in out

    def test_uses_fallback_when_project_not_in_context(self):
        docs = [{"_id": "d1", "original_name": "x.pdf", "_project_name": "Externo"}]
        out = supervisor._build_doc_list_for_resolver(docs, context={"projects": [], "categories": []})
        assert "Externo" in out

    def test_handles_doc_without_categories(self):
        docs = [{"_id": "d1", "original_name": "x.pdf", "project_id": "p1"}]
        context = {"projects": [{"_id": "p1", "titulo": "P", "categorias": []}], "categories": []}
        out = supervisor._build_doc_list_for_resolver(docs, context)
        assert "sin categoría" in out


class TestBuildProjectListForResolver:
    def test_renders_empty_string_when_no_projects(self):
        assert supervisor._build_project_list_for_resolver([]) == ""

    def test_renders_project_lines(self):
        projects = [{"_id": "p1", "titulo": "Tesis"}, {"_id": "p2"}]
        out = supervisor._build_project_list_for_resolver(projects)
        assert "ID: p1" in out
        assert "Titulo: Tesis" in out
        assert "sin titulo" in out  # fallback


class TestRouteAfterSupervisor:
    def test_default_when_no_route_set(self):
        from ai.state import AppState  # noqa: F401  (importado por compatibilidad)

        state = {"messages": []}
        assert supervisor.route_after_supervisor(state) == "research"

    def test_returns_route_in_state(self):
        assert supervisor.route_after_supervisor({"route": "weekly_summary"}) == "weekly_summary"
