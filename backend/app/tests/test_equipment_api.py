from fastapi.testclient import TestClient
from main import app
from app.db.session import SessionLocal
from app.seed.seed import seed_database

client = TestClient(app)


def setup_module():
    db = SessionLocal()
    try:
        seed_database(db, reset=True)
    finally:
        db.close()


def test_list_equipment_returns_demo_assets():
    response = client.get("/api/v1/equipment")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 20
    ids = {item["id"] for item in data}
    expected_ids = {f"EQX{number}" for number in range(1001, 1021)}
    assert ids == expected_ids


def test_list_equipment_fields_and_status():
    response = client.get("/api/v1/equipment")
    assert response.status_code == 200
    data = response.json()
    first = data[0]
    assert "id" in first
    assert "type" in first
    assert "dealer" in first
    assert "daily_rate" in first
    assert "status" in first
    assert "latest_telemetry" in first
    assert "current_rental" in first


def test_list_equipment_search_filter():
    response = client.get("/api/v1/equipment?search=Excavator")
    assert response.status_code == 200
    data = response.json()
    assert len(data) >= 1
    assert any(item["id"] == "EQX1001" for item in data)


def test_list_equipment_type_filter():
    response = client.get("/api/v1/equipment?type=Bulldozer")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 3
    assert {item["id"] for item in data} == {"EQX1002", "EQX1005", "EQX1015"}


def test_list_equipment_site_filter():
    response = client.get("/api/v1/equipment?site_id=SITE-001")
    assert response.status_code == 200
    data = response.json()
    assert len(data) >= 1
    for item in data:
        assert item["site"]["id"] == "SITE-001"


def test_get_equipment_detail_success():
    response = client.get("/api/v1/equipment/EQX1001")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == "EQX1001"
    assert data["type"] == "Excavator"
    assert data["dealer"] == "Tata Hitachi Construction Machinery"
    assert data["daily_rate"] == 18500.0
    assert "status" in data
    assert "recent_telemetry" in data
    assert len(data["recent_telemetry"]) > 0
    assert "rental_history" in data
    assert len(data["rental_history"]) > 0
    assert "active_alerts" in data
    assert "audit_timeline" in data


def test_get_equipment_detail_not_found():
    response = client.get("/api/v1/equipment/NONEXISTENT_999")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()
