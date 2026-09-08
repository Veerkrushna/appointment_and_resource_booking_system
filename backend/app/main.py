from fastapi import FastAPI

from app.api.routes.availability import router as availability_router
from app.api.routes.providers import router as providers_router
from app.api.routes.services import router as services_router
from app.core.config import settings

app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    debug=settings.debug,
)

app.include_router(providers_router)


app.include_router(services_router)
app.include_router(availability_router)


@app.get("/health")
def health_check():
    return {
        "status": "healthy",
        "environment": settings.environment,
    }
