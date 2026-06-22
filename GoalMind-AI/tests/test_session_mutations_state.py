"""Tests para session_mutations_state: log de mutaciones por usuario en memoria."""

from __future__ import annotations

import json

import pytest

from ai.services import session_mutations_state as sms

pytestmark = pytest.mark.usefixtures("reset_session_mutations")


class TestGetSessionMutations:
    def test_empty_when_user_unset(self):
        assert sms.get_session_mutations("u1") == []

    def test_returns_copy_of_list(self):
        sms.append_session_mutation("u1", {"action": "listed", "type": "document", "id": "1"})
        first = sms.get_session_mutations("u1")
        first.clear()  # mutar la copia no debe afectar al estado interno
        assert len(sms.get_session_mutations("u1")) == 1

    def test_returns_empty_for_falsy_user(self):
        assert sms.get_session_mutations(None) == []
        assert sms.get_session_mutations("") == []


class TestAppendSessionMutation:
    def test_records_relevant_fields(self):
        sms.append_session_mutation(
            "u1",
            {
                "action": "read",
                "type": "document",
                "id": "doc-1",
                "name": "doc.pdf",
                "description": "proyecto: P1",
            },
        )
        records = sms.get_session_mutations("u1")
        assert len(records) == 1
        rec = records[0]
        assert rec["action"] == "read"
        assert rec["type"] == "document"
        assert rec["id"] == "doc-1"
        assert rec["name"] == "doc.pdf"
        assert rec["description"] == "proyecto: P1"
        assert "timestamp" in rec  # ISO 8601 UTC

    def test_omits_description_when_absent(self):
        sms.append_session_mutation("u1", {"action": "listed", "type": "document", "id": "x"})
        records = sms.get_session_mutations("u1")
        assert "description" not in records[0]

    def test_appends_in_order(self):
        for i in range(3):
            sms.append_session_mutation("u1", {"action": "listed", "type": "document", "id": str(i)})
        ids = [r["id"] for r in sms.get_session_mutations("u1")]
        assert ids == ["0", "1", "2"]

    def test_falsy_user_is_noop(self):
        sms.append_session_mutation(None, {"action": "x", "type": "document", "id": "1"})
        sms.append_session_mutation("", {"action": "x", "type": "document", "id": "1"})
        assert sms._session_mutations == {}


class TestGetSessionMutationsJson:
    def test_serializes_records_as_json_array(self):
        sms.append_session_mutation("u1", {"action": "listed", "type": "document", "id": "1"})
        as_json = sms.get_session_mutations_json("u1")
        parsed = json.loads(as_json)
        assert isinstance(parsed, list)
        assert parsed[0]["id"] == "1"

    def test_empty_user_yields_empty_array(self):
        assert json.loads(sms.get_session_mutations_json("nope")) == []


class TestClearSessionMutations:
    def test_removes_user_records(self):
        sms.append_session_mutation("u1", {"action": "x", "type": "document", "id": "1"})
        sms.clear_session_mutations("u1")
        assert sms.get_session_mutations("u1") == []

    def test_idempotent_for_unknown_user(self):
        sms.clear_session_mutations("nope")
