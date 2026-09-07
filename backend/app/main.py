from fastapi import FastAPI

from app.api.routes.services import router as services_router
from app.core.config import settings


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    debug=settings.debug,
)


app.include_router(services_router)


@app.get("/health")
def health_check():
    return {
        "status": "healthy",
        "environment": settings.environment,
    }
