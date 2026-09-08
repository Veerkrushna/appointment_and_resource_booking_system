import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.availability import ProviderBreak
from app.schemas.providers import (
    ProviderBreakCreate,
    ProviderBreakUpdate,
)


def create_provider_break(
    db: Session,
    provider_id: uuid.UUID,
    break_data: ProviderBreakCreate,
) -> ProviderBreak:
    provider_break = ProviderBreak(
        provider_id=provider_id,
        **break_data.model_dump(),
    )

    db.add(provider_break)
    db.commit()
    db.refresh(provider_break)

    return provider_break


def get_provider_breaks(
    db: Session,
    provider_id: uuid.UUID,
) -> list[ProviderBreak]:
    statement = (
        select(ProviderBreak)
        .where(ProviderBreak.provider_id == provider_id)
        .order_by(
            ProviderBreak.day_of_week,
            ProviderBreak.start_time,
        )
    )

    result = db.execute(statement)

    return list(result.scalars().all())


def get_provider_break(
    db: Session,
    provider_id: uuid.UUID,
    break_id: uuid.UUID,
) -> ProviderBreak | None:
    statement = select(ProviderBreak).where(
        ProviderBreak.id == break_id,
        ProviderBreak.provider_id == provider_id,
    )

    result = db.execute(statement)

    return result.scalar_one_or_none()


def update_provider_break(
    db: Session,
    provider_break: ProviderBreak,
    break_data: ProviderBreakUpdate,
) -> ProviderBreak:
    update_data = break_data.model_dump(exclude_unset=True)

    for field, value in update_data.items():
        setattr(provider_break, field, value)

    db.commit()
    db.refresh(provider_break)

    return provider_break


def delete_provider_break(
    db: Session,
    provider_break: ProviderBreak,
) -> None:
    db.delete(provider_break)
    db.commit()
