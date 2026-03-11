from pathlib import Path

from bson import ObjectId
from gridfs import GridFSBucket
from gridfs.errors import NoFile

from database.mongo_conn import get_remote_database, logger


def get_remote_gridfs_bucket(app=None):
    """Devuelve el bucket remoto de GridFS o None si no hay remoto disponible."""
    db_remote = get_remote_database(app)
    if db_remote is None:
        return None
    return GridFSBucket(db_remote, bucket_name="project_files")


def upload_file_to_remote_storage(
    file_path,
    *,
    original_name=None,
    content_type=None,
    metadata=None,
    app=None,
):
    """Sube un archivo local a GridFS remoto y devuelve el ObjectId generado."""
    bucket = get_remote_gridfs_bucket(app)
    if bucket is None:
        return None

    path = Path(file_path)
    if not path.exists():
        return None

    upload_name = original_name or path.name
    extra_metadata = dict(metadata or {})
    if content_type:
        extra_metadata["content_type"] = content_type

    try:
        with path.open("rb") as handle:
            return bucket.upload_from_stream(upload_name, handle, metadata=extra_metadata)
    except Exception as exc:
        logger.warning("No se pudo subir el archivo a GridFS remoto: %s", exc)
        return None


def download_file_from_remote_storage(file_id, app=None):
    """Descarga un archivo desde GridFS remoto y devuelve bytes o None."""
    if not file_id:
        return None

    bucket = get_remote_gridfs_bucket(app)
    if bucket is None:
        return None

    try:
        return bucket.open_download_stream(ObjectId(str(file_id))).read()
    except (NoFile, Exception) as exc:
        logger.warning("No se pudo descargar el archivo remoto %s: %s", file_id, exc)
        return None


def delete_file_from_remote_storage(file_id, app=None):
    """Elimina un archivo de GridFS remoto si existe."""
    if not file_id:
        return False

    bucket = get_remote_gridfs_bucket(app)
    if bucket is None:
        return False

    try:
        bucket.delete(ObjectId(str(file_id)))
        return True
    except NoFile:
        return False
    except Exception as exc:
        logger.warning("No se pudo eliminar el archivo remoto %s: %s", file_id, exc)
        return False
