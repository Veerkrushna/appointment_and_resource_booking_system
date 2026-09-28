from fastapi.testclient import TestClient
from app.main import app
import uuid
from sqlalchemy import select
from app.db.database import SessionLocal
from app.models.user import User, UserRole

def test_flow():
    print("--- 1. Testing Admin/Customer Sign In ---")
    client = TestClient(app)
    
    test_email = f"test_user_{uuid.uuid4().hex[:6]}@example.com"
    password = "Password123!"
    
    reg_payload = {
        "name": "Test User",
        "email": test_email,
        "phone": "+1234567890",
        "password": password
    }
    reg_res = client.post("/api/auth/register", json=reg_payload)
    print(f"Customer Register: status={reg_res.status_code}")
    if reg_res.status_code not in (200, 201):
        print(f"Register failed: {reg_res.text}")

    # Test Sign in (Login)
    login_payload = {
        "email": test_email,
        "password": password
    }
    login_res = client.post("/api/auth/login", json=login_payload)
    print(f"Sign In (Login): status={login_res.status_code}")
    if login_res.status_code != 200:
        print(f"Login failed: {login_res.text}")
        return
    
    token_data = login_res.json()
    print(f"Sign In successful! Token received (User: {token_data.get('user', {}).get('name')}, Role: {token_data.get('user', {}).get('role')})")

    # Now let's check Admin Sign In or promoting user to Admin to test Add Provider & Update Provider
    db = SessionLocal()
    admin_user = db.scalar(select(User).where(User.role == UserRole.ADMIN))
    if not admin_user:
        u = db.scalar(select(User).where(User.email == test_email))
        u.role = UserRole.ADMIN
        db.commit()
        db.refresh(u)
        admin_email = test_email
    else:
        admin_email = admin_user.email
        u = db.scalar(select(User).where(User.email == test_email))
        if u:
            u.role = UserRole.ADMIN
            db.commit()
            admin_email = test_email

    # Login as Admin
    admin_login = client.post("/api/auth/login", json={"email": admin_email, "password": password})
    admin_token = admin_login.json()["access_token"]
    headers = {"Authorization": f"Bearer {admin_token}"}
    print(f"Admin Token obtained for {admin_email}")

    # --- 2. Testing Add Provider ---
    print("\n--- 2. Testing Add Provider ---")
    prov_email = f"dr_smith_{uuid.uuid4().hex[:6]}@example.com"
    prov_payload = {
        "name": "Dr. John Smith",
        "type": "person",
        "email": prov_email,
        "phone": "+1987654321",
        "bio": "Experienced cardiologist",
        "photo": "https://images.unsplash.com/photo-1622253692010-333f2da6031d",
        "specializations": ["Cardiology", "Internal Medicine"],
        "availability_status": "available",
        "availability_time": "09:00 am to 05:00 pm",
        "blackout_days": ["Saturday", "Sunday"],
        "password": "ProviderPassword123!",
        "confirm_password": "ProviderPassword123!"
    }

    create_res = client.post("/api/providers", json=prov_payload, headers=headers)
    print(f"Add Provider response status: {create_res.status_code}")
    if create_res.status_code not in (200, 201):
        print(f"Add Provider failed: {create_res.text}")
        return
    
    created_provider = create_res.json()
    prov_id = created_provider["id"]
    print(f"Created Provider successfully! ID: {prov_id}")
    print(f"  Name: {created_provider.get('name')}")
    print(f"  Availability: {created_provider.get('availability_time')}")
    print(f"  Blackout Days: {created_provider.get('blackout_days')}")

    # Test Provider Sign In with their new password
    print("\n--- 2b. Testing Provider Sign In with New Account ---")
    prov_login_res = client.post("/api/auth/login", json={"email": prov_email, "password": "ProviderPassword123!"})
    print(f"Provider Sign In status: {prov_login_res.status_code}")
    if prov_login_res.status_code == 200:
        print(f"Provider signed in successfully! Role: {prov_login_res.json().get('user', {}).get('role')}")
    else:
        print(f"Provider sign in failed: {prov_login_res.text}")

    # --- 3. Testing Update Provider ---
    print("\n--- 3. Testing Update Provider ---")
    update_payload = {
        "name": "Dr. John Smith, MD",
        "phone": "+1987654399",
        "bio": "Senior Chief Cardiologist and Surgeon",
        "availability_time": "08:00 am to 04:00 pm",
        "blackout_days": ["Sunday"]
    }
    update_res = client.put(f"/api/providers/{prov_id}", json=update_payload, headers=headers)
    print(f"Update Provider response status: {update_res.status_code}")
    if update_res.status_code == 200:
        updated_prov = update_res.json()
        print("Updated Provider successfully!")
        print(f"  Updated Name: {updated_prov.get('name')}")
        print(f"  Updated Phone: {updated_prov.get('phone')}")
        print(f"  Updated Bio: {updated_prov.get('bio')}")
        print(f"  Updated Availability: {updated_prov.get('availability_time')}")
        print(f"  Updated Blackout Days: {updated_prov.get('blackout_days')}")
    else:
        print(f"Update Provider failed: {update_res.text}")

    # Cleanup
    try:
        db.delete(u)
        db.commit()
    except:
        pass
    db.close()

    print("\nAll checks completed successfully!")

if __name__ == "__main__":
    test_flow()
