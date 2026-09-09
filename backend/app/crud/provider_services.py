import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.provider_service import ProviderService
from app.models.service import Service


def get_provider_services(
    db: Session,
    provider_id: uuid.UUID,
) -> list[ProviderService]:
    statement = (
        select(ProviderService)
        .where(
            ProviderService.provider_id == provider_id,
            ProviderService.is_active.is_(True),
        )
        .order_by(ProviderService.created_at)
    )

    return list(db.scalars(statement).all())


def update_provider_services(
    db: Session,
    provider_id: uuid.UUID,
    service_ids: list[uuid.UUID],
) -> list[ProviderService]:
    # Remove duplicate IDs while preserving the intended set.
    requested_service_ids = set(service_ids)

    # Fetch all requested services and verify that every ID exists.
    statement = select(Service).where(Service.id.in_(requested_service_ids))

    existing_services = list(db.scalars(statement).all())

    existing_service_ids = {service.id for service in existing_services}

    missing_service_ids = requested_service_ids - existing_service_ids

    if missing_service_ids:
        raise ValueError(f"One or more services do not exist: {missing_service_ids}")

    # Get all existing provider-service relationships, including inactive
    # ones, so previously assigned services can be reactivated.
    statement = select(ProviderService).where(
        ProviderService.provider_id == provider_id
    )

    existing_links = list(db.scalars(statement).all())

    existing_links_by_service_id = {link.service_id: link for link in existing_links}

    # Activate requested services and create missing relationships.
    for service_id in requested_service_ids:
        existing_link = existing_links_by_service_id.get(service_id)

        if existing_link is not None:
            existing_link.is_active = True
        else:
            new_link = ProviderService(
                provider_id=provider_id,
                service_id=service_id,
                is_active=True,
            )
            db.add(new_link)

    # Mark services not included in the request as inactive.
    for link in existing_links:
        if link.service_id not in requested_service_ids:
            link.is_active = False

    db.commit()

    return get_provider_services(
        db=db,
        provider_id=provider_id,
    )
