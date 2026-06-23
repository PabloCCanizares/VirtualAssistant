from database.mongo_settings import (
    DEFAULT_MONGO_DB,
    DEFAULT_MONGO_LOCAL_URI,
    build_database_uri,
    load_mongo_settings,
    redact_mongo_uri,
)


class TestLoadMongoSettings:
    def test_defaults_to_local_only(self):
        settings = load_mongo_settings({})

        assert settings.local_uri == DEFAULT_MONGO_LOCAL_URI
        assert settings.local_db == DEFAULT_MONGO_DB
        assert settings.remote_uri == ""
        assert settings.remote_db == DEFAULT_MONGO_DB
        assert settings.remote_configured is False

    def test_trims_values_and_detects_remote(self):
        settings = load_mongo_settings({
            "MONGO_LOCAL_URI": " mongodb://localhost:27017 ",
            "MONGO_LOCAL_DB": " local_db ",
            "MONGO_REMOTE_URI": " mongodb+srv://user:pwd@cluster.example.net ",
            "MONGO_REMOTE_DB": " remote_db ",
        })

        assert settings.local_uri == "mongodb://localhost:27017"
        assert settings.local_db == "local_db"
        assert settings.remote_uri == "mongodb+srv://user:pwd@cluster.example.net"
        assert settings.remote_db == "remote_db"
        assert settings.remote_configured is True


class TestBuildDatabaseUri:
    def test_appends_database_to_plain_local_uri(self):
        out = build_database_uri("mongodb://127.0.0.1:27017", "GoalMind")

        assert out == "mongodb://127.0.0.1:27017/GoalMind"

    def test_preserves_query_params(self):
        out = build_database_uri(
            "mongodb://localhost:27017/?directConnection=true",
            "GoalMind",
        )

        assert out == "mongodb://localhost:27017/GoalMind?directConnection=true"

    def test_replaces_existing_path_with_configured_database(self):
        out = build_database_uri(
            "mongodb://localhost:27017/admin?authSource=admin",
            "GoalMind",
        )

        assert out == "mongodb://localhost:27017/GoalMind?authSource=admin"

    def test_supports_srv_uri(self):
        out = build_database_uri(
            "mongodb+srv://user:pwd@cluster.example.net/?retryWrites=true",
            "GoalMind",
        )

        assert out == "mongodb+srv://user:pwd@cluster.example.net/GoalMind?retryWrites=true"


class TestRedactMongoUri:
    def test_masks_password(self):
        out = redact_mongo_uri("mongodb://alice:secret@localhost:27017/db")

        assert out == "mongodb://alice:***@localhost:27017/db"
        assert "secret" not in out

    def test_preserves_uri_without_credentials(self):
        uri = "mongodb://localhost:27017/db"

        assert redact_mongo_uri(uri) == uri
