from datetime import datetime, timezone
from app.db.session import SessionLocal
import pytest
import app.seed.seed as seed_module
from app.seed.seed import seed_database, ANCHOR_TIME, demo_refresh_preview, refresh_demo_data, DEMO_REFRESH_CONFIRMATION
from app.models import Equipment, Site, Operator, Rental, Telemetry, Alert, AuditEvent, Action, ImpactRecord, Recommendation, Forecast
from app.services.status_service import derive_status, EquipmentStatus
from app.services.equipment_service import get_current_rental, get_latest_telemetry


def test_seed_counts_and_idempotency():
    db = SessionLocal()
    try:
        # Run seed
        seed_database(db, reset=True, anchor_time=ANCHOR_TIME)

        eq_count = db.query(Equipment).count()
        site_count = db.query(Site).count()
        op_count = db.query(Operator).count()
        rental_count = db.query(Rental).count()
        telemetry_count = db.query(Telemetry).count()
        alert_count = db.query(Alert).count()
        rec_count = db.query(Recommendation).count()
        action_count = db.query(Action).count()
        impact_count = db.query(ImpactRecord).count()
        forecast_count = db.query(Forecast).count()
        audit_count = db.query(AuditEvent).count()

        assert eq_count == 20
        assert site_count == 5
        assert op_count == 10
        assert rental_count == 22
        assert telemetry_count == 120
        assert alert_count == 15
        assert rec_count == 11
        assert action_count == 7
        assert impact_count == 4
        assert forecast_count == 240
        assert audit_count == 14

        # Run again with reset=False to verify idempotency
        seed_database(db, reset=False)
        assert db.query(Equipment).count() == 20
        assert db.query(Site).count() == 5
        assert db.query(Operator).count() == 10
        assert db.query(Rental).count() == 22
        assert db.query(Telemetry).count() == 120
        assert db.query(Alert).count() == 15
        assert db.query(Recommendation).count() == 11
        assert db.query(Action).count() == 7
        assert db.query(ImpactRecord).count() == 4
        assert db.query(Forecast).count() == 240
    finally:
        db.close()


def test_full_demo_distribution_coordinates_and_relationships():
    with SessionLocal() as db:
        seed_database(db, reset=True, anchor_time=ANCHOR_TIME)
        statuses = {status: 0 for status in EquipmentStatus}
        for equipment in db.query(Equipment).all():
            telemetry = get_latest_telemetry(equipment)
            statuses[derive_status(get_current_rental(equipment), telemetry, now=ANCHOR_TIME)] += 1
            assert telemetry is not None
            assert -90 <= telemetry.latitude <= 90
            assert -180 <= telemetry.longitude <= 180
            assert 0 <= telemetry.idle_hours <= telemetry.engine_hours
        assert statuses == {
            EquipmentStatus.ACTIVE: 9,
            EquipmentStatus.IDLE: 3,
            EquipmentStatus.DUE_SOON: 2,
            EquipmentStatus.OVERDUE: 2,
            EquipmentStatus.UNASSIGNED: 4,
        }
        assert all(rental.equipment and (not rental.site_id or rental.site) and (not rental.operator_id or rental.operator) for rental in db.query(Rental).all())
        assert all(item.equipment for item in db.query(Alert).all())
        assert all(item.equipment for item in db.query(Recommendation).all())
        assert all(item.equipment for item in db.query(Action).all())


def test_selective_demo_refresh_dry_run_preserves_unknown_records():
    with SessionLocal() as db:
        seed_database(db, reset=True, anchor_time=ANCHOR_TIME)
        db.add(Equipment(id="USER-ASSET", type="Forklift", dealer="User record", daily_rate=1))
        db.commit()
        preview = refresh_demo_data(db)
        assert preview["safe_to_execute"] is True
        assert preview["counts"]["equipment"] == 20
        assert db.query(Equipment).filter_by(id="USER-ASSET").one()
        result = refresh_demo_data(db, DEMO_REFRESH_CONFIRMATION, ANCHOR_TIME)
        assert result["counts"]["equipment"] == 20
        assert db.query(Equipment).filter_by(id="USER-ASSET").one()


def test_selective_refresh_requires_confirmation_and_rolls_back(monkeypatch):
    with SessionLocal() as db:
        seed_database(db, reset=True, anchor_time=ANCHOR_TIME)
        with pytest.raises(ValueError):
            refresh_demo_data(db, "yes", ANCHOR_TIME)
        before = demo_refresh_preview(db)["counts"]
        monkeypatch.setattr(seed_module, "seed_database", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("seed failed")))
        with pytest.raises(RuntimeError):
            refresh_demo_data(db, DEMO_REFRESH_CONFIRMATION, ANCHOR_TIME)
        assert demo_refresh_preview(db)["counts"] == before


def test_refresh_rolls_back_failure_after_forecasts(monkeypatch):
    with SessionLocal() as db:
        seed_database(db, reset=True, anchor_time=ANCHOR_TIME)
        original = seed_module.demo_fingerprint(db)
        sync = seed_module.sync_forecasts_to_db
        def fail_after_forecasts(*args, **kwargs):
            sync(*args, **kwargs)
            raise RuntimeError("failure after forecasts")
        monkeypatch.setattr(seed_module, "sync_forecasts_to_db", fail_after_forecasts)
        with pytest.raises(RuntimeError, match="after forecasts"):
            refresh_demo_data(db, DEMO_REFRESH_CONFIRMATION, ANCHOR_TIME)
        assert seed_module.demo_fingerprint(db) == original
        assert demo_refresh_preview(db)["safe_to_execute"]


@pytest.mark.parametrize("change", ["unmarked", "new_telemetry", "edited_operator", "external_rental"])
def test_refresh_refuses_ambiguous_or_changed_data(change):
    with SessionLocal() as db:
        seed_database(db, reset=True, anchor_time=ANCHOR_TIME)
        if change == "unmarked":
            owner = db.get(Equipment, "EQX1001")
            owner.metadata_json = {k: v for k, v in owner.metadata_json.items() if k != "demo_fingerprint"}
        elif change == "new_telemetry":
            db.add(Telemetry(equipment_id="EQX1001", timestamp=ANCHOR_TIME,
                latitude=18.7, longitude=81.2, engine_hours=30, idle_hours=4, fuel_pct=60))
        elif change == "edited_operator":
            db.get(Operator, "OP-001").name = "User edited this operator"
        else:
            db.add(Equipment(id="REAL-ASSET", type="Crane", dealer="User", daily_rate=50))
            db.flush()
            db.add(Rental(equipment_id="REAL-ASSET", site_id="SITE-001", daily_rate=50))
        db.commit()
        before = demo_refresh_preview(db)["counts"]
        assert not demo_refresh_preview(db)["safe_to_execute"]
        with pytest.raises(RuntimeError, match="ownership"):
            refresh_demo_data(db, DEMO_REFRESH_CONFIRMATION, ANCHOR_TIME)
        assert demo_refresh_preview(db)["counts"] == before


def test_seed_analytics_follow_existing_rules():
    from app.analytics.anomaly_engine import evaluate_equipment_anomalies
    from app.analytics.forecasting import get_historical_demand_matrix, generate_demand_forecasts
    from app.models import User
    with SessionLocal() as db:
        seed_database(db, reset=True, anchor_time=ANCHOR_TIME)
        for equipment in db.query(Equipment):
            anomalies = evaluate_equipment_anomalies(equipment, get_current_rental(equipment), get_latest_telemetry(equipment), now=ANCHOR_TIME)
            actual = {a.alert_type: a for a in db.query(Alert).filter_by(equipment_id=equipment.id, status="OPEN") if a.alert_type != "DUE_SOON"}
            assert set(actual) == {a.anomaly_type for a in anomalies}
            for anomaly in anomalies:
                assert actual[anomaly.anomaly_type].message == anomaly.explanation
        forecasts = generate_demand_forecasts(db, now=ANCHOR_TIME)
        assert len(forecasts) == db.query(Forecast).count()
        history = get_historical_demand_matrix(db, ANCHOR_TIME)
        assert history["SITE-004"]["Excavator"][0] == 1.0
        assert sum(row.realized_amount for row in db.query(ImpactRecord)) == 111500
        users = [(u.id, u.hashed_password, u.role) for u in db.query(User)]
        refresh_demo_data(db, DEMO_REFRESH_CONFIRMATION, ANCHOR_TIME)
        assert [(u.id, u.hashed_password, u.role) for u in db.query(User)] == users


def test_challenge_asset_scenarios():
    db = SessionLocal()
    try:
        seed_database(db, reset=True, anchor_time=ANCHOR_TIME)
        now = ANCHOR_TIME

        # 1. EQX1001: Under-utilized / Low utilization -> IDLE
        eq1001 = db.query(Equipment).filter(Equipment.id == "EQX1001").first()
        r1001 = get_current_rental(eq1001)
        t1001 = get_latest_telemetry(eq1001)
        status1001 = derive_status(r1001, t1001, now=now)
        assert status1001 == EquipmentStatus.IDLE
        assert t1001.idle_hours >= 8.0 or (t1001.engine_hours - t1001.idle_hours) / t1001.engine_hours < 0.20

        # 2. EQX1002: Missing assignment (operator is None) -> UNASSIGNED
        eq1002 = db.query(Equipment).filter(Equipment.id == "EQX1002").first()
        r1002 = get_current_rental(eq1002)
        t1002 = get_latest_telemetry(eq1002)
        assert r1002.operator_id is None
        status1002 = derive_status(r1002, t1002, now=now)
        assert status1002 == EquipmentStatus.UNASSIGNED

        # 3. EQX1003: Active Normal -> ACTIVE
        eq1003 = db.query(Equipment).filter(Equipment.id == "EQX1003").first()
        r1003 = get_current_rental(eq1003)
        t1003 = get_latest_telemetry(eq1003)
        status1003 = derive_status(r1003, t1003, now=now)
        assert status1003 == EquipmentStatus.ACTIVE

        # 4. EQX1004: Due Soon (<48h) -> DUE_SOON
        eq1004 = db.query(Equipment).filter(Equipment.id == "EQX1004").first()
        r1004 = get_current_rental(eq1004)
        t1004 = get_latest_telemetry(eq1004)
        status1004 = derive_status(r1004, t1004, now=now)
        assert status1004 == EquipmentStatus.DUE_SOON

        # 5. EQX1005: High-Use -> ACTIVE with heavy runtime
        eq1005 = db.query(Equipment).filter(Equipment.id == "EQX1005").first()
        r1005 = get_current_rental(eq1005)
        t1005 = get_latest_telemetry(eq1005)
        status1005 = derive_status(r1005, t1005, now=now)
        assert status1005 == EquipmentStatus.ACTIVE
        assert t1005.engine_hours >= 40.0

        # 6. EQX1006: Overdue -> OVERDUE
        eq1006 = db.query(Equipment).filter(Equipment.id == "EQX1006").first()
        r1006 = get_current_rental(eq1006)
        t1006 = get_latest_telemetry(eq1006)
        status1006 = derive_status(r1006, t1006, now=now)
        assert status1006 == EquipmentStatus.OVERDUE

        # 7. EQX1007: Unassigned (no active rental in yard) -> UNASSIGNED
        eq1007 = db.query(Equipment).filter(Equipment.id == "EQX1007").first()
        r1007 = get_current_rental(eq1007)
        t1007 = get_latest_telemetry(eq1007)
        assert r1007 is None
        status1007 = derive_status(r1007, t1007, now=now)
        assert status1007 == EquipmentStatus.UNASSIGNED
    finally:
        db.close()
