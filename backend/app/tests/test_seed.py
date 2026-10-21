from datetime import datetime, timezone
from app.db.session import SessionLocal
from app.seed.seed import seed_database, ANCHOR_TIME
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

        assert eq_count == 7
        assert site_count == 3
        assert op_count == 4
        assert rental_count == 10
        assert telemetry_count == 42
        assert alert_count == 10
        assert rec_count == 8
        assert action_count == 7
        assert impact_count == 4
        assert forecast_count == 72
        assert audit_count == 14

        # Run again with reset=False to verify idempotency
        seed_database(db, reset=False)
        assert db.query(Equipment).count() == 7
        assert db.query(Site).count() == 3
        assert db.query(Operator).count() == 4
        assert db.query(Rental).count() == 10
        assert db.query(Telemetry).count() == 42
        assert db.query(Alert).count() == 10
        assert db.query(Recommendation).count() == 8
        assert db.query(Action).count() == 7
        assert db.query(ImpactRecord).count() == 4
        assert db.query(Forecast).count() == 72
    finally:
        db.close()


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
