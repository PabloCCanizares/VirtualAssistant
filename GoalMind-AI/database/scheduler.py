# database/scheduler.py
# Módulo para gestionar la sincronización en background con APScheduler

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
import atexit

# Instancia global del scheduler
_scheduler = None


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

    _scheduler = BackgroundScheduler()

    def sync_job():
        """Job que ejecuta la sincronización dentro del contexto de Flask."""
        with app.app_context():
            from database.mongo_conn import sync_all_collections
            try:
                print("\n [Scheduler] Iniciando sincronización automática...")
                sync_all_collections()
                print(" [Scheduler] Sincronización completada.\n")
            except Exception as e:
                print(f"[Scheduler] Error en sincronización: {e}")

    # Añadir job de sincronización periódica
    _scheduler.add_job(
        func=sync_job,
        trigger=IntervalTrigger(minutes=sync_interval_minutes),
        id="sync_remote_job",
        name="Sincronización remota periódica",
        replace_existing=True
    )

    # Iniciar el scheduler
    _scheduler.start()
    print(f"✅ [Scheduler] Iniciado - Sincronización cada {sync_interval_minutes} minutos")

    # Ejecutar una sincronización inicial al arrancar (en background)
    _scheduler.add_job(
        func=sync_job,
        id="sync_initial",
        name="Sincronización inicial",
        replace_existing=True
    )

    # Asegurar que el scheduler se detenga al cerrar la aplicación
    atexit.register(lambda: shutdown_scheduler())

    return _scheduler


def shutdown_scheduler():
    """Detiene el scheduler de forma segura."""
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        print(" [Scheduler] Detenido")
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
        from database.mongo_conn import sync_all_collections
        sync_all_collections()
