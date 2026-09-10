from celery import Celery

from app.core.config import settings

celery_app = Celery(
    "appointment_booking",
    broker=settings.redis_url,
    include=["app.tasks"],
)
celery_app.conf.update(
    broker_connection_timeout=1,
    broker_connection_max_retries=0,
)