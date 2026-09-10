from celery import Celery

from app.core.config import settings

celery_app = Celery(
    "appointment_booking",
    broker=settings.redis_url,
    backend=settings.celery_result_backend,
    include=[
        "app.tasks.notification_tasks",
        "app.tasks.test_tasks",
    ],
)

celery_app.conf.update(
    broker_connection_timeout=1,
    broker_connection_max_retries=0,
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
)
