import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.provider_service import ProviderService
from app.models.providers import Provider
from app.models.service import Service


def assign_providers_to_service(
    db: Session,
    service_id: uuid.UUID,
    provider_ids: list[uuid.UUID],
) -> list[ProviderService]:
    # 1. Verify that the service exists.
    service_statement = select(Service).where(Service.id == service_id)

    service = db.scalar(service_statement)

    if service is None:
        raise ValueError("Service not found")

    # 2. Remove duplicate provider IDs.
    requested_provider_ids = set(provider_ids)

    # 3. Verify that all requested providers exist.
    provider_statement = select(Provider).where(Provider.id.in_(requested_provider_ids))

    existing_providers = list(db.scalars(provider_statement).all())

    existing_provider_ids = {provider.id for provider in existing_providers}

    missing_provider_ids = requested_provider_ids - existing_provider_ids

    if missing_provider_ids:
        raise ValueError(f"One or more providers do not exist: {missing_provider_ids}")

    # 4. Fetch existing relationships, including inactive ones.
    relationship_statement = select(ProviderService).where(
        ProviderService.service_id == service_id
    )

    existing_links = list(db.scalars(relationship_statement).all())

    existing_links_by_provider_id = {link.provider_id: link for link in existing_links}

    # 5. Activate existing relationships or create new ones.
    for provider_id in requested_provider_ids:
        existing_link = existing_links_by_provider_id.get(provider_id)

        if existing_link is not None:
            existing_link.is_active = True
        else:
            new_link = ProviderService(
                provider_id=provider_id,
                service_id=service_id,
                is_active=True,
            )

            db.add(new_link)

    # 6. Save the changes.
    db.commit()

    # 7. Return all active providers assigned to this service.
    result_statement = (
        select(ProviderService)
        .where(
            ProviderService.service_id == service_id,
            ProviderService.is_active.is_(True),
        )
        .order_by(ProviderService.created_at)
    )

    return list(db.scalars(result_statement).all())
