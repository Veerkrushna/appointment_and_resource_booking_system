from datetime import UTC, datetime, time
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
    from app.models.user import User, UserRole
    from app.core.security import hash_password
    from fastapi import HTTPException

    if payload.confirm_password and payload.confirm_password != payload.password:
        raise HTTPException(status_code=400, detail="Passwords do not match")

    data = payload.model_dump()
    password = data.pop("password")
    data.pop("confirm_password", None)

    existing_user = db.scalar(select(User).where(User.email == data["email"]))
    if existing_user:
        raise HTTPException(status_code=400, detail="User with this email already exists")

    user = User(
        name=data["name"],
        email=data["email"],
        phone=data["phone"],
        password_hash=hash_password(password),
        role=UserRole.PROVIDER,
    )
    db.add(user)
    db.flush()
    user_id = user.id

    provider = Provider(**data, user_id=user_id)
    db.add(provider)
    db.commit()
    db.refresh(provider)

    if provider.availability_time:
        import re
        from datetime import datetime as dt
        time_match = re.match(
            r"^\s*(\d{1,2}:\d{2}\s*(?:am|pm))\s+to\s+(\d{1,2}:\d{2}\s*(?:am|pm))\s*$",
            provider.availability_time.strip(),
            re.IGNORECASE,
        )
        if time_match:
            try:
                start_t = dt.strptime(time_match.group(1).strip().upper(), "%I:%M %p").time()
                end_t = dt.strptime(time_match.group(2).strip().upper(), "%I:%M %p").time()
                blackout_set = {d.strip().lower() for d in (provider.blackout_days or [])}
                day_map = {
                    "monday": 0,
                    "tuesday": 1,
                    "wednesday": 2,
                    "thursday": 3,
                    "friday": 4,
                    "saturday": 5,
                    "sunday": 6,
                }
                for day_name, day_num in day_map.items():
                    is_blackout = day_name in blackout_set
                    db.add(
                        ProviderAvailability(
                            provider_id=provider.id,
                            day_of_week=day_num,
                            start_time=None if is_blackout else start_t,
                            end_time=None if is_blackout else end_t,
                            is_working_day=not is_blackout,
                        )
                    )
                db.commit()
                db.refresh(provider)
            except Exception:
                pass

    return provider


def update_provider(
    db: Session, provider: Provider, payload: ProviderUpdate
) -> Provider:
    update_data = payload.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(provider, field, value)
    db.commit()
    db.refresh(provider)

    if "availability_time" in update_data or "blackout_days" in update_data:
        if provider.availability_time:
            import re
            from datetime import datetime as dt
            time_match = re.match(
                r"^\s*(\d{1,2}:\d{2}\s*(?:am|pm))\s+to\s+(\d{1,2}:\d{2}\s*(?:am|pm))\s*$",
                provider.availability_time.strip(),
                re.IGNORECASE,
            )
            if time_match:
                try:
                    start_t = dt.strptime(time_match.group(1).strip().upper(), "%I:%M %p").time()
                    end_t = dt.strptime(time_match.group(2).strip().upper(), "%I:%M %p").time()
                    blackout_set = {d.strip().lower() for d in (provider.blackout_days or [])}
                    day_map = {
                        "monday": 0,
                        "tuesday": 1,
                        "wednesday": 2,
                        "thursday": 3,
                        "friday": 4,
                        "saturday": 5,
                        "sunday": 6,
                    }
                    db.execute(
                        delete(ProviderAvailability).where(
                            ProviderAvailability.provider_id == provider.id
                        )
                    )
                    for day_name, day_num in day_map.items():
                        is_blackout = day_name in blackout_set
                        db.add(
                            ProviderAvailability(
                                provider_id=provider.id,
                                day_of_week=day_num,
                                start_time=None if is_blackout else start_t,
                                end_time=None if is_blackout else end_t,
                                is_working_day=not is_blackout,
                            )
                        )
                    db.commit()
                    db.refresh(provider)
                except Exception:
                    pass

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


def replace_weekly_schedule(
    db: Session, provider: Provider, days: list[dict]
) -> Provider:
    provider.availability.clear()
    provider.availability = [
        ProviderAvailability(provider_id=provider.id, **day) for day in days
    ]
    db.commit()
    db.refresh(provider)
    return provider


def update_weekly_schedule_day(
    db: Session, provider: Provider, day_of_week: int, day: dict
) -> Provider:
    existing = next(
        (
            availability
            for availability in provider.availability
            if availability.day_of_week == day_of_week
        ),
        None,
    )
    if existing is None:
        provider.availability.append(
            ProviderAvailability(provider_id=provider.id, **day)
        )
    else:
        for field, value in day.items():
            setattr(existing, field, value)
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
        blackout_start=datetime.combine(payload.start_date, time.min, tzinfo=UTC),
        blackout_end=datetime.combine(
            payload.end_date,
            time.max,
            tzinfo=UTC,
        ),
        reason=payload.reason,
        is_all_day=True,
    )
    db.add(blackout)
    db.commit()
    db.refresh(blackout)
    return blackout


def delete_provider_blackout(db: Session, provider_id: UUID, blackout_id: UUID) -> bool:
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
