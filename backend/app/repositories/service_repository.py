import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.service import Service
from app.schemas.service import ServiceCreate, ServiceUpdate


class ServiceRepository:
    @staticmethod
    def create(db: Session, service_data: ServiceCreate) -> Service:
        service = Service(**service_data.model_dump())

        db.add(service)
        db.commit()
        db.refresh(service)

        return service

    @staticmethod
    def get_all(db: Session) -> list[Service]:
        statement = select(Service).order_by(Service.created_at.desc())

        result = db.execute(statement)

        return list(result.scalars().all())

    @staticmethod
    def get_by_id(
        db: Session,
        service_id: uuid.UUID,
    ) -> Service | None:
        statement = select(Service).where(Service.id == service_id)

        result = db.execute(statement)

        return result.scalar_one_or_none()

    @staticmethod
    def update(
        db: Session,
        service: Service,
        service_data: ServiceUpdate,
    ) -> Service:

        update_data = service_data.model_dump(exclude_unset=True)

        for field, value in update_data.items():
            setattr(service, field, value)

        db.commit()
        db.refresh(service)

        return service
