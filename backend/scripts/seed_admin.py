"""Create the first admin account from environment variables, if none exists."""

import os
import sys
from pathlib import Path

backend_dir = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(backend_dir))
os.chdir(backend_dir)

from sqlalchemy import select  # noqa: E402

from app.core.security import hash_password  # noqa: E402
from app.db.database import SessionLocal  # noqa: E402
from app.models.user import User, UserRole  # noqa: E402


def main() -> None:
    email = os.environ.get("INITIAL_ADMIN_EMAIL", "admin@test.com").strip().lower()
    password = os.environ.get("INITIAL_ADMIN_PASSWORD", "admin@1234")
    if not email or not password:
        raise SystemExit("INITIAL_ADMIN_EMAIL and INITIAL_ADMIN_PASSWORD are required")

    with SessionLocal() as db:
        if db.scalar(select(User.id).where(User.role == UserRole.ADMIN)) is not None:
            print("Admin account already exists; skipping bootstrap.")
            return
        admin = User(
            name="admin",
            email=email,
            password_hash=hash_password(password),
            role=UserRole.ADMIN,
        )
        db.add(admin)
        db.commit()
        print(f"Created initial admin account for {email}.")


if __name__ == "__main__":
    main()
