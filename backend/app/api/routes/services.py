import uuid
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.security import require_role
from app.crud.service_providers import (
    assign_providers_to_service,
    get_service_providers,
)
from app.crud.services import (
    create_service,
    get_service,
    list_services,
    list_services_with_providers,
    update_service,
)
from app.db.database import get_db
from app.models.user import User, UserRole
from app.schemas.provider_service import ProviderServiceResponse
from app.schemas.service import (
    AdminServiceResponse,
    ServiceCreate,
    ServiceProviderSummary,
    ServiceResponse,
    ServiceUpdate,
)
from app.schemas.service_provider import ServiceProvidersAssign

router = APIRouter(
    prefix="/api/services",
    tags=["Services"],
)


@router.post(
    "",
    response_model=ServiceResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_service_endpoint(
    service_data: ServiceCreate,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(require_role(UserRole.ADMIN))],
):
    return create_service(
        db=db,
        service_data=service_data,
    )


@router.get(
    "",
    response_model=list[ServiceResponse],
)
def get_services(
    db: Annotated[Session, Depends(get_db)],
):
    return list_services(db=db)


@router.get(
    "/admin-with-providers",
    response_model=list[AdminServiceResponse],
    dependencies=[Depends(require_role(UserRole.ADMIN))],
)
def get_admin_services_with_providers(
    db: Annotated[Session, Depends(get_db)],
):
    return [
        AdminServiceResponse(
            **ServiceResponse.model_validate(service).model_dump(),
            providers=[
                ServiceProviderSummary(
                    provider_id=link.provider_id,
                    provider_name=link.provider.name,
                )
                for link in service.provider_links
                if link.is_active
            ],
        )
        for service in list_services_with_providers(db=db)
    ]


@router.get(
    "/{service_id}",
    response_model=ServiceResponse,
)
def get_service_by_id(
    service_id: uuid.UUID,
    db: Annotated[Session, Depends(get_db)],
):
    service = get_service(
        db=db,
        service_id=service_id,
    )

    if service is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Service not found",
        )

    return service


@router.get(
    "/{service_id}/providers",
    response_model=list[ServiceProviderSummary],
    dependencies=[Depends(require_role(UserRole.ADMIN))],
)
def get_service_provider_names(
    service_id: UUID,
    db: Annotated[Session, Depends(get_db)],
):
    try:
        provider_links = get_service_providers(db=db, service_id=service_id)
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(error),
        ) from error

    return [
        ServiceProviderSummary(
            provider_id=link.provider_id,
            provider_name=link.provider.name,
        )
        for link in provider_links
    ]


@router.put(
    "/{service_id}",
    response_model=ServiceResponse,
)
def update_service_endpoint(
    service_id: uuid.UUID,
    service_data: ServiceUpdate,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(require_role(UserRole.ADMIN))],
):
    service = get_service(
        db=db,
        service_id=service_id,
    )

    if service is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Service not found",
        )

    return update_service(
        db=db,
        service=service,
        service_data=service_data,
    )


@router.post(
    "/{service_id}/providers",
    response_model=list[ProviderServiceResponse],
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(require_role(UserRole.ADMIN))],
)
def assign_providers(
    service_id: UUID,
    payload: ServiceProvidersAssign,
    db: Annotated[Session, Depends(get_db)],
):
    try:
        return assign_providers_to_service(
            db=db,
            service_id=service_id,
            provider_ids=payload.provider_ids,
        )
    except ValueError as error:
        error_message = str(error)

        if error_message == "Service not found":
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=error_message,
            ) from error

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_message,
        ) from error
