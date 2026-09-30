import urllib.request
import urllib.parse
import json

def test_api():
    # Login as admin
    login_data = json.dumps({
        "email": "admin@example.com",
        "password": "adminpassword"
    }).encode("utf-8")
    
    req = urllib.request.Request(
        "http://localhost:8000/api/auth/login",
        data=login_data,
        headers={"Content-Type": "application/json"}
    )
    
    try:
        resp = urllib.request.urlopen(req)
        auth_data = json.loads(resp.read())
        token = auth_data["access_token"]
        print("Logged in")
    except Exception as e:
        print("Login failed:", e)
        return

    # Check /api/admin/appointments
    req_appt = urllib.request.Request(
        "http://localhost:8000/api/admin/appointments?page=1",
        headers={"Authorization": f"Bearer {token}"}
    )
    try:
        resp_appt = urllib.request.urlopen(req_appt)
        print("Appointments OK:", len(resp_appt.read()))
    except urllib.error.HTTPError as e:
        print("Appointments Error:", e.code)
        print(e.read().decode("utf-8"))

    # Check /api/services
    req_srv = urllib.request.Request("http://localhost:8000/api/services")
    try:
        resp_srv = urllib.request.urlopen(req_srv)
        print("Services OK:", len(resp_srv.read()))
    except urllib.error.HTTPError as e:
        print("Services Error:", e.code)
        print(e.read().decode("utf-8"))

    # Check /api/providers
    req_prov = urllib.request.Request("http://localhost:8000/api/providers")
    try:
        resp_prov = urllib.request.urlopen(req_prov)
        print("Providers OK:", len(resp_prov.read()))
    except urllib.error.HTTPError as e:
        print("Providers Error:", e.code)
        print(e.read().decode("utf-8"))

test_api()
