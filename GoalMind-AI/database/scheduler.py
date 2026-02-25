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
        started_at = time.monotonic()
        with app.app_context():
            from database.mongo_conn import (
                ensure_remote_connection,
                flush_deletion_queue,
                sync_all_collections,
                sync_local_to_remote,
            )
            try:
                ensure_remote_connection(app)
                deleted = flush_deletion_queue()
                pushed = sync_local_to_remote()
                pulled = sync_all_collections()
                elapsed = time.monotonic() - started_at
                logger.info(
                    "[Scheduler] Sync completada en %.2fs | deletions=%s pushed=%s pulled=%s",
                    elapsed,
                    deleted if isinstance(deleted, int) else 0,
                    pushed if isinstance(pushed, int) else 0,
                    pulled if isinstance(pulled, int) else 0,
                )
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
    logger.info("✅ [Scheduler] Iniciado - Sincronización cada %s minutos", sync_interval_minutes)

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
    with app.app_context():
        from database.mongo_conn import (
            ensure_remote_connection,
            flush_deletion_queue,
            sync_all_collections,
            sync_local_to_remote,
        )
        ensure_remote_connection(app)
        deleted = flush_deletion_queue()
        pushed = sync_local_to_remote()
        pulled = sync_all_collections()
        logger.info(
            "[Scheduler] Sync manual completada | deletions=%s pushed=%s pulled=%s",
            deleted if isinstance(deleted, int) else 0,
            pushed if isinstance(pushed, int) else 0,
            pulled if isinstance(pulled, int) else 0,
        )
