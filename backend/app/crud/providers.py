from datetime import datetime, time, timezone
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models.availability import (
    ProviderAvailability,
    ProviderBlackoutDate,
    ProviderBreak,
)
from app.models.providers import Provider
from app.schemas.providers import (
    AvailabilityRequest,
    ProviderCreate,
    ProviderUpdate,
    UnavailabilityRequest,
)


def get_provider(db: Session, provider_id: UUID) -> Provider | None:
    return db.get(Provider, provider_id)


def list_providers(
    db: Session,
    provider_type: str | None = None,
    availability_status: str | None = None,
) -> list[Provider]:
    query = select(Provider).order_by(Provider.name)
    if provider_type is not None:
        query = query.where(Provider.type == provider_type)
    if availability_status is not None:
        query = query.where(Provider.availability_status == availability_status)
    return list(db.scalars(query).all())


def create_provider(db: Session, payload: ProviderCreate) -> Provider:
    provider = Provider(**payload.model_dump())
    db.add(provider)
    db.commit()
    db.refresh(provider)
    return provider


def update_provider(
    db: Session, provider: Provider, payload: ProviderUpdate
) -> Provider:
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(provider, field, value)
    db.commit()
    db.refresh(provider)
    return provider


def replace_provider_availability(
    db: Session, provider: Provider, payload: AvailabilityRequest
) -> Provider:
    db.execute(
        delete(ProviderAvailability).where(
            ProviderAvailability.provider_id == provider.id
        )
    )
    db.execute(delete(ProviderBreak).where(ProviderBreak.provider_id == provider.id))
    db.execute(
        delete(ProviderBlackoutDate).where(
            ProviderBlackoutDate.provider_id == provider.id
        )
    )

    provider.availability = [
        ProviderAvailability(provider_id=provider.id, **item.model_dump())
        for item in payload.availability
    ]
    provider.breaks = [
        ProviderBreak(provider_id=provider.id, **item.model_dump())
        for item in payload.breaks
    ]
    provider.blackout_dates = [
        ProviderBlackoutDate(provider_id=provider.id, **item.model_dump())
        for item in payload.blackout_dates
    ]
    db.commit()
    db.refresh(provider)
    return provider


def list_provider_blackouts(
    db: Session, provider_id: UUID
) -> list[ProviderBlackoutDate]:
    query = (
        select(ProviderBlackoutDate)
        .where(ProviderBlackoutDate.provider_id == provider_id)
        .order_by(ProviderBlackoutDate.blackout_start)
    )
    return list(db.scalars(query).all())


def create_provider_blackout(
    db: Session, provider_id: UUID, payload: UnavailabilityRequest
) -> ProviderBlackoutDate:
    blackout = ProviderBlackoutDate(
        provider_id=provider_id,
        blackout_start=datetime.combine(
            payload.start_date, time.min, tzinfo=timezone.utc
        ),
        blackout_end=datetime.combine(
            payload.end_date,
            time.max,
            tzinfo=timezone.utc,
        ),
        reason=payload.reason,
        is_all_day=True,
    )
    db.add(blackout)
    db.commit()
    db.refresh(blackout)
    return blackout


def delete_provider_blackout(
    db: Session, provider_id: UUID, blackout_id: UUID
) -> bool:
    blackout = db.scalar(
        select(ProviderBlackoutDate).where(
            ProviderBlackoutDate.id == blackout_id,
            ProviderBlackoutDate.provider_id == provider_id,
        )
    )
    if blackout is None:
        return False
    db.delete(blackout)
    db.commit()
    return True