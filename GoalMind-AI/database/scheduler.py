# Módulo para gestionar la sincronización en background con APScheduler

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.executors.pool import ThreadPoolExecutor
from apscheduler.triggers.interval import IntervalTrigger
import atexit
import logging
import time

# Instancia global del scheduler
_scheduler = None
logger = logging.getLogger(__name__)


def _run_sync_cycle(app, *, manual=False):
    """Ejecuta un ciclo completo de sync (pull y push) dentro del contexto Flask."""
    started_at = time.monotonic()
    with app.app_context():
        from database.mongo_conn import (
            ensure_remote_connection,
            flush_deletion_queue,
            sync_all_collections,
            sync_local_to_remote,
        )
        from model.project_document_model import ProjectDocumentModel

        if not ensure_remote_connection(app):
            logger.info("[Scheduler] Remoto no disponible, sync omitida.")
            return 0, 0, 0, 0

        deleted = flush_deletion_queue()
        promoted = ProjectDocumentModel.promote_pending_remote_uploads(app=app)
        # Pull primero para que local tenga el estado remoto más reciente
        # antes de trabajar offline y antes del siguiente ciclo de uso.
        pulled = sync_all_collections()
        pushed = sync_local_to_remote()
        elapsed = time.monotonic() - started_at
        prefix = "manual" if manual else "completada"
        logger.info(
            "[Scheduler] Sync %s en %.2fs | deletions=%s promoted=%s pulled=%s pushed=%s",
            prefix,
            elapsed,
            deleted if isinstance(deleted, int) else 0,
            promoted if isinstance(promoted, int) else 0,
            pulled if isinstance(pulled, int) else 0,
            pushed if isinstance(pushed, int) else 0,
        )
        return (
            deleted if isinstance(deleted, int) else 0,
            promoted if isinstance(promoted, int) else 0,
            pulled if isinstance(pulled, int) else 0,
            pushed if isinstance(pushed, int) else 0,
        )


def init_scheduler(app, sync_interval_minutes=1):
    """
    Inicializa el scheduler de sincronización en background.

    Args:
        app: Instancia de Flask
        sync_interval_minutes: Intervalo en minutos entre sincronizaciones (default: 1)
    """
    global _scheduler

    # Evitar crear múltiples schedulers (ej. en modo debug con reloader)
    if _scheduler is not None:
        return _scheduler

    executors = {"default": ThreadPoolExecutor(2)}
    _scheduler = BackgroundScheduler(executors=executors)

    def sync_job():
        """Job que ejecuta la sincronización dentro del contexto de Flask."""
        try:
            _run_sync_cycle(app, manual=False)
        except Exception as e:
            logger.warning("[Scheduler] Error en sincronización: %s", e, exc_info=True)

    # Añadir job de sincronización periódica
    _scheduler.add_job(
        func=sync_job,
        trigger=IntervalTrigger(minutes=sync_interval_minutes),
        id="sync_remote_job",
        name="Sincronización remota periódica",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        misfire_grace_time=30,
    )

    # Iniciar el scheduler
    _scheduler.start()
    logger.info("[Scheduler] Iniciado - Sincronización cada %s minutos", sync_interval_minutes)

    # Ejecutar una sincronización inicial al arrancar (en background)
    _scheduler.add_job(
        func=sync_job,
        id="sync_initial",
        name="Sincronización inicial",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )

    # Asegurar que el scheduler se detenga al cerrar la aplicación
    atexit.register(lambda: shutdown_scheduler())

    return _scheduler


def shutdown_scheduler():
    """Detiene el scheduler de forma segura."""
    global _scheduler
    if _scheduler is not None:
        try:
            _scheduler.shutdown(wait=True)
        except Exception:
            pass
        logger.info("[Scheduler] Detenido")
        _scheduler = None


def get_scheduler():
    """Devuelve la instancia del scheduler."""
    return _scheduler


def trigger_sync_now(app):
    """
    Fuerza una sincronización inmediata (útil para llamar manualmente).

    Args:
        app: Instancia de Flask
    """
    _run_sync_cycle(app, manual=True)
