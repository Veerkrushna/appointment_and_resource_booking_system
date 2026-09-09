from datetime import time
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import delete

from app.api.routes.providers import (
    get_weekly_schedule,
    replace_weekly_schedule_endpoint,
    update_weekly_schedule_day_endpoint,
)
from app.db.database import SessionLocal
from app.models.availability import ProviderAvailability
from app.models.providers import AvailabilityStatus, Provider, ProviderType
from app.schemas.providers import (
    AvailabilityWindow,
    WeeklyScheduleRequest,
)


@pytest.fixture
def schedule_provider():
    db = SessionLocal()
    provider = Provider(
        name=f"Weekly Schedule Provider {uuid4()}",
        type=ProviderType.PERSON,
        email=f"weekly-{uuid4()}@example.com",
        timezone="UTC",
        availability_status=AvailabilityStatus.AVAILABLE,
    )
    db.add(provider)
    db.commit()
    provider_id = provider.id
    db.close()

    try:
        yield provider_id
    finally:
        cleanup = SessionLocal()
        cleanup.execute(
            delete(ProviderAvailability).where(
                ProviderAvailability.provider_id == provider_id
            )
        )
        cleanup.execute(delete(Provider).where(Provider.id == provider_id))
        cleanup.commit()
        cleanup.close()


def weekly_days(monday_start: str = "09:00:00") -> list[dict]:
    return [
        {
            "day_of_week": day_of_week,
            "start_time": monday_start if day_of_week == 0 else None,
            "end_time": "17:00:00" if day_of_week == 0 else None,
            "is_working_day": day_of_week == 0,
        }
        for day_of_week in range(7)
    ]


def test_weekly_schedule_replace_get_and_update(schedule_provider):
    db = SessionLocal()
    provider_id = schedule_provider
    payload = WeeklyScheduleRequest(days=weekly_days())

    replaced = replace_weekly_schedule_endpoint(provider_id, payload, db)
    assert replaced.provider_id == provider_id
    assert replaced.days[0].start_time == time(9, 0)
    assert replaced.days[1].is_working_day is False

    fetched = get_weekly_schedule(provider_id, db)
    assert fetched.days[0].end_time == time(17, 0)
    assert len(fetched.days) == 7

    updated = update_weekly_schedule_day_endpoint(
        provider_id,
        0,
        AvailabilityWindow(
            day_of_week=0,
            start_time=time(10, 0),
            end_time=time(18, 0),
            is_working_day=True,
        ),
        db,
    )
    assert updated.days[0].start_time == time(10, 0)
    assert updated.days[0].end_time == time(18, 0)
    db.close()


def test_weekly_schedule_update_rejects_day_mismatch(schedule_provider):
    db = SessionLocal()
    with pytest.raises(HTTPException) as error:
        update_weekly_schedule_day_endpoint(
            schedule_provider,
            1,
            AvailabilityWindow(
                day_of_week=0,
                start_time=time(10, 0),
                end_time=time(18, 0),
                is_working_day=True,
            ),
            db,
        )

    assert error.value.status_code == 422
    assert "must match" in str(error.value.detail)
    db.close()
