from fastapi import FastAPI

from app.api.routes.admin import router as admin_router
from app.api.routes.admin_users import router as admin_users_router
from app.api.routes.appointments import router as appointments_router
from app.api.routes.auth import router as auth_router
from app.api.routes.availability import router as availability_router
from app.api.routes.customer import router as customer_router
from app.api.routes.providers import router as providers_router
from app.api.routes.services import router as services_router
from app.api.routes.terms import router as terms_router
from app.api.routes.password_reset import router as password_reset_router
from app.core.config import settings

app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    debug=settings.debug,
)

app.include_router(providers_router)


app.include_router(services_router)
app.include_router(availability_router)
app.include_router(appointments_router)
app.include_router(admin_router)
app.include_router(admin_users_router)
app.include_router(auth_router)
app.include_router(customer_router)
app.include_router(terms_router)
app.include_router(password_reset_router)


@app.get("/health")
def health_check():
    return {
        "status": "healthy",
        "environment": settings.environment,
    }
