import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.repositories.service_repository import ServiceRepository
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
def create_service(
    service_data: ServiceCreate,
    db: Session = Depends(get_db),
):
    return ServiceRepository.create(
        db=db,
        service_data=service_data,
    )


@router.get(
    "",
    response_model=list[ServiceResponse],
)
def get_services(
    db: Session = Depends(get_db),
):
    return ServiceRepository.get_all(db=db)


@router.get(
    "/{service_id}",
    response_model=ServiceResponse,
)
def get_service(
    service_id: uuid.UUID,
    db: Session = Depends(get_db),
):
    service = ServiceRepository.get_by_id(
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
def update_service(
    service_id: uuid.UUID,
    service_data: ServiceUpdate,
    db: Session = Depends(get_db),
):
    service = ServiceRepository.get_by_id(
        db=db,
        service_id=service_id,
    )

    if service is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Service not found",
        )

    return ServiceRepository.update(
        db=db,
        service=service,
        service_data=service_data,
    )
