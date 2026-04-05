from celery import Celery

from app.core.config import settings

celery_app = Celery(
    'worker',
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
)

celery_app.conf.update(
    task_track_started=True,
    broker_connection_retry_on_startup=True
)

celery_app.autodiscover_tasks(['app.domains.users'])
