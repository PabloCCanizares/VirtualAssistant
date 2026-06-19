from pathlib import Path
from typing import BinaryIO

from bson import ObjectId
from gridfs import GridFSBucket
from gridfs.errors import NoFile

from database.mongo_conn import get_local_database, get_remote_database, logger


def _get_gridfs_bucket(database):
    if database is None:
        return None
    return GridFSBucket(database, bucket_name="project_files")


def _delete_file_from_bucket(bucket, database, file_id):
    if not file_id or bucket is None or database is None:
        return False

    object_id = ObjectId(str(file_id))
    deleted = False

    try:
        bucket.delete(object_id)
        deleted = True
    except NoFile:
        pass
    except Exception as exc:
        logger.warning("No se pudo eliminar el archivo GridFS %s via bucket.delete: %s", file_id, exc)

    try:
        files_deleted = database["project_files.files"].delete_one({"_id": object_id}).deleted_count
        chunks_deleted = database["project_files.chunks"].delete_many({"files_id": object_id}).deleted_count
        return deleted or files_deleted > 0 or chunks_deleted > 0
    except Exception as exc:
        logger.warning("No se pudo completar la limpieza manual de GridFS %s: %s", file_id, exc)
        return deleted


def get_local_gridfs_bucket():
    """Devuelve el bucket local de GridFS."""
    return _get_gridfs_bucket(get_local_database())


def get_remote_gridfs_bucket(app=None):
    """Devuelve el bucket remoto de GridFS o None si no hay remoto disponible."""
    return _get_gridfs_bucket(get_remote_database(app))


def _upload_stream_to_bucket(
    bucket,
    stream: BinaryIO,
    upload_name: str,
    *,
    content_type=None,
    metadata=None,
):
    if bucket is None:
        return None

    extra_metadata = dict(metadata or {})
    if content_type:
        extra_metadata["content_type"] = content_type

    try:
        stream.seek(0)
    except Exception:
        pass

    try:
        return bucket.upload_from_stream(upload_name, stream, metadata=extra_metadata)
    except Exception as exc:
        logger.warning("No se pudo subir el archivo a GridFS: %s", exc)
        return None


def upload_stream_to_local_storage(
    stream,
    *,
    original_name,
    content_type=None,
    metadata=None,
):
    """Sube un stream a GridFS local y devuelve el ObjectId generado."""
    return _upload_stream_to_bucket(
        get_local_gridfs_bucket(),
        stream,
        original_name,
        content_type=content_type,
        metadata=metadata,
    )


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
    try:
        with path.open("rb") as handle:
            return _upload_stream_to_bucket(
                bucket,
                handle,
                upload_name,
                content_type=content_type,
                metadata=metadata,
            )
    except Exception as exc:
        logger.warning("No se pudo abrir el archivo local para subirlo a GridFS remoto: %s", exc)
        return None


def download_file_from_local_storage(file_id):
    """Descarga un archivo desde GridFS local y devuelve bytes o None."""
    if not file_id:
        return None

    bucket = get_local_gridfs_bucket()
    if bucket is None:
        return None

    try:
        return bucket.open_download_stream(ObjectId(str(file_id))).read()
    except (NoFile, Exception) as exc:
        logger.warning("No se pudo descargar el archivo local %s: %s", file_id, exc)
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


def delete_file_from_local_storage(file_id):
    """Elimina un archivo de GridFS local si existe."""
    if not file_id:
        return False

    database = get_local_database()
    bucket = get_local_gridfs_bucket()
    if bucket is None or database is None:
        return False

    return _delete_file_from_bucket(bucket, database, file_id)


def delete_file_from_remote_storage(file_id, app=None):
    """Elimina un archivo de GridFS remoto si existe."""
    if not file_id:
        return False

    database = get_remote_database(app)
    bucket = get_remote_gridfs_bucket(app)
    if bucket is None or database is None:
        return False

    return _delete_file_from_bucket(bucket, database, file_id)


def promote_local_file_to_remote(local_file_id, *, original_name, content_type=None, metadata=None, app=None):
    """Copia un archivo desde GridFS local al remoto y devuelve el ObjectId remoto."""
    local_bytes = download_file_from_local_storage(local_file_id)
    if local_bytes is None:
        return None

    bucket = get_remote_gridfs_bucket(app)
    if bucket is None:
        return None

    from io import BytesIO

    return _upload_stream_to_bucket(
        bucket,
        BytesIO(local_bytes),
        original_name,
        content_type=content_type,
        metadata=metadata,
    )
