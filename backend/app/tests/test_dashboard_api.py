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


def test_dashboard_kpis():
    response = client.get("/api/v1/dashboard")
    assert response.status_code == 200
    data = response.json()

    assert data["total_equipment"] == 20
    assert data["active"] >= 1
    assert data["idle"] >= 1
    assert data["due_soon"] >= 1
    assert data["overdue"] >= 1
    assert data["unassigned"] >= 1

    # Sum of status counts must equal total equipment
    total_status = (
        data["active"]
        + data["idle"]
        + data["due_soon"]
        + data["overdue"]
        + data["unassigned"]
    )
    assert total_status == 20

    assert "status_counts" in data
    assert data["open_alerts"] == 11
    assert data["fleet_utilization_pct"] > 0
