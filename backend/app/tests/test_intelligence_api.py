import pytest
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)


def test_get_fleet_anomalies_endpoint():
    res = client.get("/api/v1/anomalies")
    assert res.status_code == 200
    data = res.json()
    assert isinstance(data, list)
    assert len(data) > 0

    # Verify schema of returned anomaly
    first = data[0]
    assert "equipment_id" in first
    assert "anomaly_type" in first
    assert "anomaly_score" in first
    assert "severity" in first
    assert "explanation" in first
    assert "supporting_signals" in first
    assert 0 <= first["anomaly_score"] <= 100


def test_get_anomalies_by_equipment_id_filter():
    res = client.get("/api/v1/anomalies?equipment_id=EQX1001")
    assert res.status_code == 200
    data = res.json()
    assert len(data) >= 1
    for a in data:
        assert a["equipment_id"] == "EQX1001"


def test_get_anomalies_by_severity_filter():
    res = client.get("/api/v1/anomalies?severity=CRITICAL")
    assert res.status_code == 200
    data = res.json()
    for a in data:
        assert a["severity"] == "CRITICAL"


def test_get_equipment_specific_anomalies_endpoint():
    res = client.get("/api/v1/equipment/EQX1001/anomalies")
    assert res.status_code == 200
    data = res.json()
    assert len(data) >= 1
    assert data[0]["equipment_id"] == "EQX1001"


def test_get_equipment_anomalies_unknown_equipment():
    res = client.get("/api/v1/equipment/EQX9999/anomalies")
    assert res.status_code == 404


def test_get_alerts_endpoint():
    res = client.get("/api/v1/alerts")
    assert res.status_code == 200
    data = res.json()
    assert isinstance(data, list)
    assert len(data) >= 1

    first = data[0]
    assert "id" in first
    assert "equipment_id" in first
    assert "alert_type" in first
    assert "severity" in first
    assert "message" in first
    assert "status" in first


def test_get_alerts_with_filters():
    res = client.get("/api/v1/alerts?status=OPEN&severity=CRITICAL")
    assert res.status_code == 200
    data = res.json()
    for alert in data:
        assert alert["status"] == "OPEN"
        assert alert["severity"] == "CRITICAL"


def test_get_forecasts_endpoint():
    res = client.get("/api/v1/forecasts?horizon_weeks=2")
    assert res.status_code == 200
    data = res.json()
    assert isinstance(data, list)
    assert len(data) > 0

    first = data[0]
    assert "site_id" in first
    assert "equipment_type" in first
    assert "predicted_units" in first
    assert "confidence" in first
    assert "explanation" in first
    assert "drivers" in first
    assert first["predicted_units"] >= 0
    assert any(row["predicted_units"] > 0 for row in data)
    assert 0.0 < first["confidence"] <= 1.0


def test_get_forecasts_summary_endpoint():
    res = client.get("/api/v1/forecasts/summary?horizon_weeks=4")
    assert res.status_code == 200
    data = res.json()
    assert "total_forecasted_units" in data
    assert "avg_confidence" in data
    assert "forecasts" in data
    assert data["total_forecasted_units"] > 0
    assert data["horizon_weeks"] == 4
