from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Mapping
from urllib.parse import quote, urlsplit, urlunsplit

DEFAULT_MONGO_LOCAL_URI = "mongodb://127.0.0.1:27017"
DEFAULT_MONGO_DB = "VirtualAssistantDB"


@dataclass(frozen=True)
class MongoSettings:
    local_uri: str
    local_db: str
    remote_uri: str
    remote_db: str

    @property
    def local_connection_uri(self) -> str:
        return build_database_uri(self.local_uri, self.local_db)

    @property
    def remote_configured(self) -> bool:
        return bool(self.remote_uri.strip())


def load_mongo_settings(environ: Mapping[str, str] | None = None) -> MongoSettings:
    env = os.environ if environ is None else environ
    return MongoSettings(
        local_uri=(env.get("MONGO_LOCAL_URI") or DEFAULT_MONGO_LOCAL_URI).strip(),
        local_db=_normalize_database_name(env.get("MONGO_LOCAL_DB")),
        remote_uri=(env.get("MONGO_REMOTE_URI") or "").strip(),
        remote_db=_normalize_database_name(env.get("MONGO_REMOTE_DB")),
    )


def build_database_uri(base_uri: str, db_name: str) -> str:
    """Return a Mongo URI with db_name as path while preserving query params."""
    base = (base_uri or DEFAULT_MONGO_LOCAL_URI).strip()
    database = quote(_normalize_database_name(db_name), safe="")

    parsed = urlsplit(base)
    if parsed.scheme in {"mongodb", "mongodb+srv"} and parsed.netloc:
        return urlunsplit((
            parsed.scheme,
            parsed.netloc,
            f"/{database}",
            parsed.query,
            parsed.fragment,
        ))

    return f"{base.rstrip('/')}/{database}"


def redact_mongo_uri(uri: str) -> str:
    """Mask credentials in Mongo URIs before writing them to logs."""
    if not uri:
        return ""

    parsed = urlsplit(uri)
    userinfo, separator, hosts = parsed.netloc.rpartition("@")
    if not separator or not userinfo:
        return uri

    username = userinfo.split(":", 1)[0]
    netloc = f"{username}:***@{hosts}"
    return urlunsplit((
        parsed.scheme,
        netloc,
        parsed.path,
        parsed.query,
        parsed.fragment,
    ))


def _normalize_database_name(db_name: str | None) -> str:
    return (db_name or DEFAULT_MONGO_DB).strip() or DEFAULT_MONGO_DB
