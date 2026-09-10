from app.celery_app import celery_app


@celery_app.task
def test_task(message: str):
    print(f"Celery received: {message}")
    return f"Processed: {message}"
