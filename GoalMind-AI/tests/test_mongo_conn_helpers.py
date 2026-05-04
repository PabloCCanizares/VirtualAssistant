"""Tests para los helpers puros de database.mongo_conn (sin conectar a MongoDB)."""

from __future__ import annotations

from database import mongo_conn


class TestExtractUsernameFromUri:
    def test_extracts_user_from_srv_uri(self):
        uri = "mongodb+srv://dani:secret@cluster.mongodb.net/db"
        assert mongo_conn.extract_username_from_uri(uri) == "dani"

    def test_extracts_user_from_basic_uri(self):
        uri = "mongodb://alice:pwd@localhost:27017/db"
        assert mongo_conn.extract_username_from_uri(uri) == "alice"

    def test_returns_empty_when_no_user(self):
        assert mongo_conn.extract_username_from_uri("mongodb://localhost:27017/db") == ""

    def test_returns_empty_for_empty_uri(self):
        assert mongo_conn.extract_username_from_uri("") == ""

    def test_returns_empty_for_invalid_uri(self):
        # urlparse no lanza por strings raros, devuelve "" para username
        assert mongo_conn.extract_username_from_uri("not-a-uri") == ""


class TestGenerateUserIdFromNickname:
    def test_returns_24_hex_chars(self):
        out = mongo_conn.generate_user_id_from_nickname("dani")
        assert len(out) == 24
        # debe ser hex valido
        int(out, 16)

    def test_deterministic(self):
        a = mongo_conn.generate_user_id_from_nickname("dani")
        b = mongo_conn.generate_user_id_from_nickname("dani")
        assert a == b

    def test_case_and_whitespace_insensitive(self):
        a = mongo_conn.generate_user_id_from_nickname("Dani")
        b = mongo_conn.generate_user_id_from_nickname("  dani  ")
        assert a == b

    def test_different_nicknames_yield_different_ids(self):
        assert mongo_conn.generate_user_id_from_nickname("a") != mongo_conn.generate_user_id_from_nickname("b")


class TestGetAppUserId:
    def test_default_when_no_nickname(self, monkeypatch):
        monkeypatch.delenv("APP_USER_NICKNAME", raising=False)
        assert mongo_conn.get_app_user_id() == "66ffbbbbbbbbbbbbbbbb0100"

    def test_default_when_nickname_is_shared_user(self, monkeypatch):
        monkeypatch.setenv("APP_USER_NICKNAME", "shared_user")
        assert mongo_conn.get_app_user_id() == "66ffbbbbbbbbbbbbbbbb0100"

    def test_derived_id_for_real_nickname(self, monkeypatch):
        monkeypatch.setenv("APP_USER_NICKNAME", "dani")
        out = mongo_conn.get_app_user_id()
        assert len(out) == 24
        assert out != "66ffbbbbbbbbbbbbbbbb0100"


class TestRemoteUidFilter:
    def test_with_valid_objectid_returns_or_clause(self, monkeypatch):
        monkeypatch.setenv("APP_USER_NICKNAME", "dani")
        # get_app_user_id() devuelve 24 hex chars (formato ObjectId valido)
        result = mongo_conn.remote_uid_filter()
        assert "$or" in result
        # Una rama deberia ser string, otra ObjectId
        from bson import ObjectId

        kinds = {type(branch["usuario_id"]) for branch in result["$or"]}
        assert str in kinds
        assert ObjectId in kinds

    def test_with_explicit_uid(self):
        result = mongo_conn.remote_uid_filter(usuario_id="abc")
        # "abc" no es un ObjectId valido => devuelve solo {"usuario_id": "abc"}
        assert result == {"usuario_id": "abc"}
