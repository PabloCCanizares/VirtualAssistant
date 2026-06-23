from dataclasses import dataclass
from typing import Any, Callable


@dataclass
class FullSyncResult:
    success: bool
    error: str = ""
    flushed_deletions: int = 0
    promoted_uploads: int = 0
    pulled_docs: int = 0
    pushed_docs: int = 0


def run_full_sync(
    app: Any = None,
    *,
    ensure_remote_connection_fn: Callable[[Any], bool] | None = None,
    flush_deletion_queue_fn: Callable[[], int] | None = None,
    promote_pending_remote_uploads_fn: Callable[..., int] | None = None,
    sync_all_collections_fn: Callable[[], int] | None = None,
    sync_local_to_remote_fn: Callable[[], int] | None = None,
) -> FullSyncResult:
    if ensure_remote_connection_fn is None:
        from database.mongo_conn import ensure_remote_connection as ensure_remote_connection_fn
    if flush_deletion_queue_fn is None:
        from database.mongo_conn import flush_deletion_queue as flush_deletion_queue_fn
    if sync_all_collections_fn is None:
        from database.mongo_conn import sync_all_collections as sync_all_collections_fn
    if sync_local_to_remote_fn is None:
        from database.mongo_conn import sync_local_to_remote as sync_local_to_remote_fn
    if promote_pending_remote_uploads_fn is None:
        from model.project_document_model import ProjectDocumentModel

        promote_pending_remote_uploads_fn = ProjectDocumentModel.promote_pending_remote_uploads

    if not ensure_remote_connection_fn(app):
        return FullSyncResult(
            success=False,
            error="No hay conexión con la base de datos remota",
        )

    flushed = flush_deletion_queue_fn()
    promoted = promote_pending_remote_uploads_fn(app=app)
    pulled = sync_all_collections_fn()
    pushed = sync_local_to_remote_fn()

    return FullSyncResult(
        success=True,
        flushed_deletions=flushed,
        promoted_uploads=promoted,
        pulled_docs=pulled,
        pushed_docs=pushed,
    )
