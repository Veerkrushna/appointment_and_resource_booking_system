import enum
from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.models.booking_hold import BookingHoldStatus
from app.models.payment import PaymentStatus, PaymentWebhookEventStatus


class PaymentReconciliationReason(enum.StrEnum):
    CAPTURED_UNLINKED = "captured_unlinked"
    CAPTURE_VALIDATION_FAILED = "capture_validation_failed"
    LOCAL_PAYMENT_STATE_CONFLICT = "local_payment_state_conflict"
    RETRYABLE_WEBHOOK_EVENT = "retryable_webhook_event"
    FAILED_WEBHOOK_EVENT = "failed_webhook_event"
    EXPIRED_HOLD = "expired_hold"
    RELEASED_HOLD = "released_hold"
    STALE_CREATED_NO_CAPTURE_EVIDENCE = "stale_created_no_confirmed_capture_evidence"
    MISSING_LOCAL_PROVIDER_ORDER_ID = "missing_local_provider_order_id"
    MISSING_LOCAL_PROVIDER_PAYMENT_ID = "missing_local_provider_payment_id"
    MISMATCHED_PROVIDER_ORDER_ID = "mismatched_provider_order_id"
    MISMATCHED_PROVIDER_PAYMENT_ID = "mismatched_provider_payment_id"
    INCONSISTENT_APPOINTMENT_LINK = "inconsistent_appointment_link"


class PaymentReconciliationHold(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    status: BookingHoldStatus
    expires_at: datetime
    appointment_start: datetime
    appointment_end: datetime
    provider_id: UUID
    service_id: UUID


class PaymentReconciliationEvent(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    provider_event_id: str
    event_type: str
    provider_order_id: str | None
    provider_payment_id: str | None
    capture_validation_failure: str | None
    capture_validation_details: dict[str, object] | None
    local_payment_state_conflict: bool = False
    status: PaymentWebhookEventStatus
    error_message: str | None
    created_at: datetime
    updated_at: datetime
    processed_at: datetime | None


class PaymentReconciliationCandidate(BaseModel):
    payment_id: UUID
    status: PaymentStatus
    amount: int
    currency: str
    provider_order_id: str | None
    provider_payment_id: str | None
    appointment_id: UUID | None
    series_id: UUID | None
    created_at: datetime
    updated_at: datetime
    reasons: list[PaymentReconciliationReason]
    provider_verification_required: Literal[True] = True
    booking_holds: list[PaymentReconciliationHold]
    webhook_events: list[PaymentReconciliationEvent]
