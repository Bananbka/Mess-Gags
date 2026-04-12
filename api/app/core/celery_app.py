from celery import Celery
from celery.schedules import crontab

from app.core.config import settings

celery_app = Celery(
    'worker',
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
)

celery_app.conf.update(
    task_track_started=True,
    broker_connection_retry_on_startup=True,
    timezone=settings.TIMEZONE,
    enable_utc=True,
)

celery_app.conf.beat_schedule = {
    'cleanup-minio-task': {
        'task': 'app.domains.files.tasks.cleanup_minio_orphans_task',
        'schedule': crontab(hour=3, minute=0),
    }
}

celery_app.autodiscover_tasks(['app.domains.users', 'app.domains.files'])
