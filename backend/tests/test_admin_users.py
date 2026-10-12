from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.core.security import create_access_token
from app.db.database import SessionLocal
from app.main import app
from app.models.user import User, UserRole

client = TestClient(app)


@pytest.fixture
def admin_setup():
    db = SessionLocal()
    admin1 = User(
        name="Admin One",
        email=f"admin1-{uuid4()}@example.com",
        password_hash="hashedpass",
        role=UserRole.ADMIN,
    )
    admin2 = User(
        name="Admin Two",
        email=f"admin2-{uuid4()}@example.com",
        password_hash="hashedpass",
        role=UserRole.ADMIN,
    )
    db.add_all([admin1, admin2])
    db.commit()
    db.refresh(admin1)
    db.refresh(admin2)

    token1 = create_access_token(admin1.id, admin1.role)
    token2 = create_access_token(admin2.id, admin2.role)

    yield {
        "admin1": admin1,
        "admin2": admin2,
        "token1": token1,
        "token2": token2,
    }

    db.delete(admin1)
    db.delete(admin2)
    db.commit()
    db.close()


def test_list_admin_users_excludes_self(admin_setup):
    token1 = admin_setup["token1"]
    admin1 = admin_setup["admin1"]
    admin2 = admin_setup["admin2"]

    response = client.get(
        "/api/admin/users?role=ADMIN",
        headers={"Authorization": f"Bearer {token1}"},
    )
    assert response.status_code == 200
    data = response.json()
    user_ids = [item["id"] for item in data]
    # Admin 1 should see admin 2, but NOT themselves
    assert str(admin2.id) in user_ids
    assert str(admin1.id) not in user_ids


def test_create_admin_user(admin_setup):
    token1 = admin_setup["token1"]
    new_email = f"newadmin-{uuid4()}@example.com"

    response = client.post(
        "/api/admin/users",
        json={
            "name": "Super Admin",
            "email": new_email,
            "phone": "1234567890",
            "password": "Password123!",
            "role": "ADMIN",
        },
        headers={"Authorization": f"Bearer {token1}"},
    )
    assert response.status_code == 201
    created = response.json()
    assert created["name"] == "Super Admin"
    assert created["email"] == new_email
    assert created["role"] == "ADMIN"
    assert created["is_active"] is True

    # Clean up created user
    db = SessionLocal()
    db.query(User).filter(User.id == created["id"]).delete()
    db.commit()
    db.close()


def test_update_admin_status(admin_setup):
    token1 = admin_setup["token1"]
    admin2 = admin_setup["admin2"]

    # Deactivate admin2
    response = client.patch(
        f"/api/admin/users/{admin2.id}/status?is_active=false",
        headers={"Authorization": f"Bearer {token1}"},
    )
    assert response.status_code == 200
    assert response.json()["is_active"] is False

    # Admin 1 cannot change their own status
    self_response = client.patch(
        f"/api/admin/users/{admin_setup['admin1'].id}/status?is_active=false",
        headers={"Authorization": f"Bearer {token1}"},
    )
    assert self_response.status_code == 400
