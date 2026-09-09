import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.crud.services import (
    create_service,
    get_service,
    list_services,
    update_service,
)
from app.db.database import get_db
from app.schemas.service import (
    ServiceCreate,
    ServiceResponse,
    ServiceUpdate,
)

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


@router.put(
    "/{service_id}",
    response_model=ServiceResponse,
)
def update_service_endpoint(
    service_id: uuid.UUID,
    service_data: ServiceUpdate,
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

    return update_service(
        db=db,
        service=service,
        service_data=service_data,
    )
