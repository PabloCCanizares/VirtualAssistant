import os

from flask import Flask


DEFAULT_UPLOAD_EXTENSIONS = {
    "pdf",
    "doc",
    "docx",
    "txt",
    "png",
    "jpg",
    "jpeg",
    "csv",
    "xlsx",
    "pptx",
    "zip",
}
def configure_storage(flask_app: Flask, env_int) -> None:
    allowed_ext_env = os.getenv("UPLOAD_ALLOWED_EXTENSIONS", "").strip()
    if allowed_ext_env:
        allowed_ext = {
            ext.strip().lower() for ext in allowed_ext_env.split(",") if ext.strip()
        }
    else:
        allowed_ext = set(DEFAULT_UPLOAD_EXTENSIONS)

    flask_app.config["UPLOAD_ALLOWED_EXTENSIONS"] = allowed_ext
    flask_app.config["MAX_CONTENT_LENGTH"] = env_int("MAX_CONTENT_LENGTH_MB", 25, minimum=1) * 1024 * 1024
