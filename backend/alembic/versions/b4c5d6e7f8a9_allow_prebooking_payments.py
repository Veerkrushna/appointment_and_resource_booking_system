"""allow payments before a booking exists

Revision ID: b4c5d6e7f8a9
Revises: a4b5c6d7e8f9
"""

from collections.abc import Sequence

from alembic import op

revision: str = "b4c5d6e7f8a9"
down_revision: str | Sequence[str] | None = "a4b5c6d7e8f9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("ck_payments_appointment_or_series", "payments", type_="check")
    op.create_check_constraint(
        "ck_payments_not_both_appointment_and_series",
        "payments",
        "appointment_id IS NULL OR series_id IS NULL",
    )


def downgrade() -> None:
    op.execute(
        "DO $$ BEGIN "
        "IF EXISTS ("
        "SELECT 1 FROM payments "
        "WHERE appointment_id IS NULL AND series_id IS NULL"
        ") THEN "
        "RAISE EXCEPTION "
        "'Cannot restore strict payment booking constraint while unlinked payments exist'; "
        "END IF; "
        "END $$"
    )
    op.drop_constraint(
        "ck_payments_not_both_appointment_and_series",
        "payments",
        type_="check",
    )
    op.create_check_constraint(
        "ck_payments_appointment_or_series",
        "payments",
        "(appointment_id IS NOT NULL) <> (series_id IS NOT NULL)",
    )
