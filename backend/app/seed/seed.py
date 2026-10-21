import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from sqlalchemy.orm import Session
from sqlalchemy import text
from app.db.session import SessionLocal
from app.models import (
    Base,
    Equipment,
    Site,
    Operator,
    Rental,
    Telemetry,
    Alert,
    Forecast,
    Recommendation,
    AuditEvent,
    Action,
    ImpactRecord,
    User,
)
from app.analytics.forecasting import generate_demand_forecasts, sync_forecasts_to_db
from app.core.security import hash_password

# Deterministic anchor timestamp
ANCHOR_TIME = datetime(2026, 9, 1, 12, 0, 0, tzinfo=timezone.utc)


def reset_database(db: Session):
    """
    Reset demo database tables across all models in reverse foreign key order.
    """
    Base.metadata.create_all(bind=db.get_bind())
    for model in [ImpactRecord, Action, AuditEvent, Recommendation, Forecast, Alert, Telemetry, Rental, Operator, Site, Equipment]:
        try:
            db.query(model).delete()
        except Exception:
            pass
    db.commit()


def seed_database(db: Session, reset: bool = False, anchor_time: datetime | None = None):
    """
    Deterministic & Idempotent Database Seeder localized for Indian infrastructure operations.
    Seeds the 7 challenge equipment assets, 3 sites, 4 operators, active & historical rentals,
    telemetry streams, alerts, recommendations, actions, forecasts, and financial impact records.
    """
    Base.metadata.create_all(bind=db.get_bind())
    if reset:
        reset_database(db)
    elif any(db.query(model).first() is not None for model in
             (Equipment, Rental, Telemetry, Site, Operator, Alert, Recommendation, Action, ImpactRecord, Forecast, AuditEvent)):
        # Existing data is never moved or partially reseeded on a restart.
        return

    base_time = anchor_time or datetime.now(timezone.utc).replace(microsecond=0)

    # 1. Seed Sites (3 realistic Indian construction/mining operations)
    sites_data = [
        {
            "id": "SITE-001",
            "name": "Bailadila Iron Ore Complex",
            "location": "Deposit 14 Mining Sector, Kirandul, Chhattisgarh",
            "latitude": 18.7180,
            "longitude": 81.2580,
            "created_at": base_time - timedelta(days=60),
        },
        {
            "id": "SITE-002",
            "name": "Navi Mumbai International Airport",
            "location": "Terminal 1 Earthworks & Staging, Maharashtra",
            "latitude": 18.9894,
            "longitude": 73.0648,
            "created_at": base_time - timedelta(days=45),
        },
        {
            "id": "SITE-003",
            "name": "Kallambella Wind Energy Corridor",
            "location": "NH-48 Industrial Package 3, Karnataka",
            "latitude": 13.6067,
            "longitude": 76.9033,
            "created_at": base_time - timedelta(days=30),
        },
    ]

    for s_data in sites_data:
        existing = db.query(Site).filter(Site.id == s_data["id"]).first()
        if existing:
            for k, v in s_data.items():
                setattr(existing, k, v)
        else:
            db.add(Site(**s_data))

    db.flush()

    # 2. Seed Operators (4 authentic certified heavy machinery operators)
    operators_data = [
        {
            "id": "OP-001",
            "name": "Rajesh Sharma",
            "contact": "r.sharma@infraco.in | +91 98201 23456",
            "created_at": base_time - timedelta(days=90),
        },
        {
            "id": "OP-002",
            "name": "Priya Patel",
            "contact": "p.patel@heavyworks.in | +91 98202 34567",
            "created_at": base_time - timedelta(days=90),
        },
        {
            "id": "OP-003",
            "name": "Amit Verma",
            "contact": "a.verma@metrobuild.in | +91 98203 45678",
            "created_at": base_time - timedelta(days=75),
        },
        {
            "id": "OP-004",
            "name": "Sunita Rao",
            "contact": "s.rao@apexops.in | +91 98204 56789",
            "created_at": base_time - timedelta(days=60),
        },
    ]

    for o_data in operators_data:
        existing = db.query(Operator).filter(Operator.id == o_data["id"]).first()
        if existing:
            for k, v in o_data.items():
                setattr(existing, k, v)
        else:
            db.add(Operator(**o_data))

    db.flush()

    # 3. Seed Challenge Equipment (EQX1001 - EQX1007) with realistic Indian rates and dealers
    equipment_data = [
        {
            "id": "EQX1001",
            "type": "Excavator",
            "dealer": "Tata Hitachi Construction Machinery",
            "daily_rate": 18500.0,
            "metadata_json": {"model": "Tata Hitachi EX200 Super+", "serial": "TH-EX200-9941", "qr_code": "EQX1001"},
            "created_at": base_time - timedelta(days=20),
        },
        {
            "id": "EQX1002",
            "type": "Bulldozer",
            "dealer": "BEML Heavy Earthmovers",
            "daily_rate": 26000.0,
            "metadata_json": {"model": "BEML BD65 Crawler", "serial": "BEML-BD65-3821", "qr_code": "EQX1002"},
            "created_at": base_time - timedelta(days=15),
        },
        {
            "id": "EQX1003",
            "type": "Wheel Loader",
            "dealer": "L&T Equipment Solutions",
            "daily_rate": 15000.0,
            "metadata_json": {"model": "L&T 9020 Heavy Loader", "serial": "LT-9020-7712", "qr_code": "EQX1003"},
            "created_at": base_time - timedelta(days=18),
        },
        {
            "id": "EQX1004",
            "type": "Generator",
            "dealer": "Kirloskar Oil Engines (KOEL)",
            "daily_rate": 5500.0,
            "metadata_json": {"model": "Kirloskar Green 160kVA Silent DG", "serial": "KOEL-160-1094", "qr_code": "EQX1004"},
            "created_at": base_time - timedelta(days=12),
        },
        {
            "id": "EQX1005",
            "type": "Bulldozer",
            "dealer": "Action Construction Equipment (ACE)",
            "daily_rate": 24000.0,
            "metadata_json": {"model": "ACE BD-80 Heavy Spec", "serial": "ACE-BD80-8823", "qr_code": "EQX1005"},
            "created_at": base_time - timedelta(days=25),
        },
        {
            "id": "EQX1006",
            "type": "Scissor Lift",
            "dealer": "JCB India Commercial",
            "daily_rate": 7500.0,
            "metadata_json": {"model": "JCB S3246E Electric", "serial": "JCB-S32-4419", "qr_code": "EQX1006"},
            "created_at": base_time - timedelta(days=30),
        },
        {
            "id": "EQX1007",
            "type": "Boom Lift",
            "dealer": "Sany Heavy Industry India",
            "daily_rate": 9500.0,
            "metadata_json": {"model": "Sany SPA200 Articulated Boom", "serial": "SANY-SPA-5520", "qr_code": "EQX1007"},
            "created_at": base_time - timedelta(days=10),
        },
    ]

    for eq_data in equipment_data:
        existing = db.query(Equipment).filter(Equipment.id == eq_data["id"]).first()
        if existing:
            for k, v in eq_data.items():
                setattr(existing, k, v)
        else:
            db.add(Equipment(**eq_data))

    db.flush()

    # 4. Seed Rentals (Active + Consistent Historical Completed Contracts)
    rentals_data = [
        # EQX1001: Under-utilized (Active rental at SITE-001, OP-001, high idle hours)
        {
            "equipment_id": "EQX1001",
            "site_id": "SITE-001",
            "operator_id": "OP-001",
            "checked_out_at": base_time - timedelta(days=5),
            "due_at": base_time + timedelta(days=10),
            "checked_in_at": None,
            "daily_rate": 18500.0,
            "condition_notes": "Delivered in good working order. Open-cast excavation and benching phase.",
            "created_at": base_time - timedelta(days=5),
        },
        # EQX1002: Missing Assignment (Checked out to SITE-002 with operator_id=None)
        {
            "equipment_id": "EQX1002",
            "site_id": "SITE-002",
            "operator_id": None,
            "checked_out_at": base_time - timedelta(days=2),
            "due_at": base_time + timedelta(days=8),
            "checked_in_at": None,
            "daily_rate": 26000.0,
            "condition_notes": "Delivered to NMIA staging area. Operator assignment pending.",
            "created_at": base_time - timedelta(days=2),
        },
        # EQX1003: Active Normal (Healthy active rental at SITE-001, OP-002)
        {
            "equipment_id": "EQX1003",
            "site_id": "SITE-001",
            "operator_id": "OP-002",
            "checked_out_at": base_time - timedelta(days=4),
            "due_at": base_time + timedelta(days=7),
            "checked_in_at": None,
            "daily_rate": 15000.0,
            "condition_notes": "Active in aggregate handling and haul road grading.",
            "created_at": base_time - timedelta(days=4),
        },
        # EQX1003 (Historical): Past rental completed at SITE-002 before reallocating to SITE-001
        {
            "equipment_id": "EQX1003",
            "site_id": "SITE-002",
            "operator_id": "OP-002",
            "checked_out_at": base_time - timedelta(days=25),
            "due_at": base_time - timedelta(days=18),
            "checked_in_at": base_time - timedelta(days=18),
            "daily_rate": 15000.0,
            "condition_notes": "Completed initial logistics staging at NMIA. Reassigned to Bailadila.",
            "created_at": base_time - timedelta(days=25),
        },
        # EQX1004: Due Soon (Due within 20 hours < 48h threshold at SITE-002, OP-003)
        {
            "equipment_id": "EQX1004",
            "site_id": "SITE-002",
            "operator_id": "OP-003",
            "checked_out_at": base_time - timedelta(days=6),
            "due_at": base_time + timedelta(hours=20),
            "checked_in_at": None,
            "daily_rate": 5500.0,
            "condition_notes": "Temporary 3-phase power for site trailers and night floodlighting.",
            "created_at": base_time - timedelta(days=6),
        },
        # EQX1004 (Historical): Past rental completed at SITE-002
        {
            "equipment_id": "EQX1004",
            "site_id": "SITE-002",
            "operator_id": "OP-003",
            "checked_out_at": base_time - timedelta(days=28),
            "due_at": base_time - timedelta(days=10),
            "checked_in_at": base_time - timedelta(days=10),
            "daily_rate": 5500.0,
            "condition_notes": "Phase 1 temporary power generation contract completed.",
            "created_at": base_time - timedelta(days=28),
        },
        # EQX1005: High-Use (Active heavy bulldozer with 48h engine runtime at SITE-002, OP-004)
        {
            "equipment_id": "EQX1005",
            "site_id": "SITE-002",
            "operator_id": "OP-004",
            "checked_out_at": base_time - timedelta(days=8),
            "due_at": base_time + timedelta(days=12),
            "checked_in_at": None,
            "daily_rate": 24000.0,
            "condition_notes": "High-intensity airside earthworks and runway compaction.",
            "created_at": base_time - timedelta(days=8),
        },
        # EQX1005 (Historical): Past rental extended for runway compaction
        {
            "equipment_id": "EQX1005",
            "site_id": "SITE-002",
            "operator_id": "OP-004",
            "checked_out_at": base_time - timedelta(days=35),
            "due_at": base_time - timedelta(days=15),
            "checked_in_at": base_time - timedelta(days=15),
            "daily_rate": 24000.0,
            "condition_notes": "Primary sub-base grading completed successfully.",
            "created_at": base_time - timedelta(days=35),
        },
        # EQX1006: Overdue (Due 2 days ago at SITE-003, OP-001)
        {
            "equipment_id": "EQX1006",
            "site_id": "SITE-003",
            "operator_id": "OP-001",
            "checked_out_at": base_time - timedelta(days=10),
            "due_at": base_time - timedelta(days=2),
            "checked_in_at": None,
            "daily_rate": 7500.0,
            "condition_notes": "Wind turbine tower electrical and transmission cabling installation.",
            "created_at": base_time - timedelta(days=10),
        },
        # EQX1007: Unassigned (Previous rental completed and checked in 3 days ago, now in yard)
        {
            "equipment_id": "EQX1007",
            "site_id": "SITE-003",
            "operator_id": "OP-003",
            "checked_out_at": base_time - timedelta(days=9),
            "due_at": base_time - timedelta(days=4),
            "checked_in_at": base_time - timedelta(days=3),
            "daily_rate": 9500.0,
            "condition_notes": "Returned clean, full tank, parked in central depot staging yard.",
            "created_at": base_time - timedelta(days=9),
        },
    ]

    for r_data in rentals_data:
        existing = (
            db.query(Rental)
            .filter(
                Rental.equipment_id == r_data["equipment_id"],
                Rental.checked_out_at == r_data["checked_out_at"],
            )
            .first()
        )
        if not existing:
            db.add(Rental(**r_data))

    db.flush()

    # 5. Seed Historical Telemetry Streams (Positioned around real Indian site centroids)
    telemetry_profiles = {
        # EQX1001: Low Utilization / High Idle (14.2h idle out of 16.0h total -> 11.2% utilization < 20%)
        "EQX1001": {
            "lat": 18.7180, "lng": 81.2580,
            "engine_base": 16.0, "idle_base": 14.2, "fuel": 82.0
        },
        # EQX1002: Missing assignment (Stationary at staging yard, 2.0h engine, 1.8h idle)
        "EQX1002": {
            "lat": 18.9894, "lng": 73.0648,
            "engine_base": 2.0, "idle_base": 1.8, "fuel": 95.0
        },
        # EQX1003: Active Normal (28.5h engine, 4.2h idle -> 85.3% utilization)
        "EQX1003": {
            "lat": 18.7185, "lng": 81.2590,
            "engine_base": 28.5, "idle_base": 4.2, "fuel": 68.0
        },
        # EQX1004: Due Soon Generator (34.0h engine, 2.1h idle -> 93.8% utilization)
        "EQX1004": {
            "lat": 18.9900, "lng": 73.0655,
            "engine_base": 34.0, "idle_base": 2.1, "fuel": 45.0
        },
        # EQX1005: High-Use (48.0h engine, 2.4h idle -> 95.0% utilization, heavy fuel consumption)
        "EQX1005": {
            "lat": 18.9890, "lng": 73.0640,
            "engine_base": 48.0, "idle_base": 2.4, "fuel": 32.0
        },
        # EQX1006: Overdue Scissor Lift (22.0h engine, 3.5h idle)
        "EQX1006": {
            "lat": 13.6067, "lng": 76.9033,
            "engine_base": 22.0, "idle_base": 3.5, "fuel": 74.0
        },
        # EQX1007: Unassigned Yard Asset (0.0 active hours in yard, 100% fuel)
        "EQX1007": {
            "lat": 13.6075, "lng": 76.9045,
            "engine_base": 0.0, "idle_base": 0.0, "fuel": 100.0
        },
    }

    for eq_id, profile in telemetry_profiles.items():
        for i in range(6):
            t_offset = timedelta(hours=(5 - i) * 4)
            t_timestamp = base_time - t_offset
            step_factor = (i + 1) / 6.0

            t_record = {
                "equipment_id": eq_id,
                "timestamp": t_timestamp,
                "latitude": round(profile["lat"] + (i * 0.0001), 6),
                "longitude": round(profile["lng"] + (i * 0.0001), 6),
                "engine_hours": round(profile["engine_base"] * step_factor, 1),
                "idle_hours": round(profile["idle_base"] * step_factor, 1),
                "fuel_pct": max(5.0, round(profile["fuel"] - (i * 2.5), 1)),
                "created_at": t_timestamp,
            }

            existing = (
                db.query(Telemetry)
                .filter(
                    Telemetry.equipment_id == eq_id,
                    Telemetry.timestamp == t_timestamp,
                )
                .first()
            )
            if not existing:
                db.add(Telemetry(**t_record))

    db.flush()

    # 6. Seed Alerts (Active Open Alerts + Historical Resolved Alerts)
    alerts_data = [
        # Open Alert 1: EQX1001 EXCESSIVE_IDLE
        {
            "equipment_id": "EQX1001",
            "alert_type": "EXCESSIVE_IDLE",
            "severity": "CRITICAL",
            "message": "Asset EQX1001 has accumulated 14.2h of idle engine time, exceeding the acceptable operational threshold of 8.0h (Total engine runtime: 16.0h).",
            "status": "OPEN",
            "metadata_json": {"idle_hours": 14.2, "threshold_hours": 8.0, "engine_hours": 16.0, "anomaly_score": 85, "recommended_action": "REASSIGN_EQUIPMENT"},
            "created_at": base_time - timedelta(hours=8),
            "resolved_at": None,
        },
        # Open Alert 2: EQX1001 LOW_UTILIZATION
        {
            "equipment_id": "EQX1001",
            "alert_type": "LOW_UTILIZATION",
            "severity": "CRITICAL",
            "message": "Asset EQX1001 has an active utilization rate of 11.2% (1.8h active out of 16.0h engine runtime), falling below the 20% operational threshold.",
            "status": "OPEN",
            "metadata_json": {"utilization_rate": 0.1125, "threshold": 0.20, "active_hours": 1.8, "engine_hours": 16.0, "idle_hours": 14.2, "anomaly_score": 75, "recommended_action": "REASSIGN_EQUIPMENT"},
            "created_at": base_time - timedelta(hours=8),
            "resolved_at": None,
        },
        # Open Alert 3: EQX1002 MISSING_ASSIGNMENT
        {
            "equipment_id": "EQX1002",
            "alert_type": "MISSING_ASSIGNMENT",
            "severity": "CRITICAL",
            "message": "Asset EQX1002 has an active rental (Contract) but lacks a certified operator assignment.",
            "status": "OPEN",
            "metadata_json": {"missing_fields": ["operator"], "site_id": "SITE-002", "operator_id": None, "anomaly_score": 75, "recommended_action": "ASSIGN_OPERATOR"},
            "created_at": base_time - timedelta(hours=12),
            "resolved_at": None,
        },
        # Open Alert 4: EQX1002 LOW_UTILIZATION
        {
            "equipment_id": "EQX1002",
            "alert_type": "LOW_UTILIZATION",
            "severity": "CRITICAL",
            "message": "Asset EQX1002 has an active utilization rate of 10.0% (0.2h active out of 2.0h engine runtime), falling below the 20% operational threshold.",
            "status": "OPEN",
            "metadata_json": {"utilization_rate": 0.10, "threshold": 0.20, "active_hours": 0.2, "engine_hours": 2.0, "idle_hours": 1.8, "anomaly_score": 75, "recommended_action": "REASSIGN_EQUIPMENT"},
            "created_at": base_time - timedelta(hours=12),
            "resolved_at": None,
        },
        # Open Alert 5: EQX1004 DUE_SOON
        {
            "equipment_id": "EQX1004",
            "alert_type": "DUE_SOON",
            "severity": "MEDIUM",
            "message": "Rental for Generator EQX1004 expires within 24 hours. Prepare return handoff or extension.",
            "status": "OPEN",
            "metadata_json": {"hours_remaining": 20, "site_id": "SITE-002"},
            "created_at": base_time - timedelta(hours=4),
            "resolved_at": None,
        },
        # Open Alert 6: EQX1006 OVERDUE
        {
            "equipment_id": "EQX1006",
            "alert_type": "OVERDUE",
            "severity": "CRITICAL",
            "message": f"Rental contract for EQX1006 is 48.0h overdue (scheduled return was {(base_time - timedelta(days=2)):%Y-%m-%d %H:%M UTC}). Rate surcharge is active at ₹7,500.00/day.",
            "status": "OPEN",
            "metadata_json": {"overdue_hours": 48.0, "daily_rate": 7500.0, "anomaly_score": 84, "recommended_action": "INITIATE_RETURN"},
            "created_at": base_time - timedelta(days=2),
            "resolved_at": None,
        },
        # Historical Resolved Alert 7: EQX1003 EXCESSIVE_IDLE (Resolved by completed action)
        {
            "equipment_id": "EQX1003",
            "alert_type": "EXCESSIVE_IDLE",
            "severity": "HIGH",
            "message": "Asset EQX1003 accumulated 9.5h idle runtime during initial staging.",
            "status": "RESOLVED",
            "metadata_json": {"idle_hours": 9.5, "threshold_hours": 8.0, "resolution": "Reassigned to Bailadila Deposit 14"},
            "created_at": base_time - timedelta(days=20),
            "resolved_at": base_time - timedelta(days=18),
        },
        # Historical Resolved Alert 8: EQX1004 ZERO_RUNTIME (Resolved by completed investigation)
        {
            "equipment_id": "EQX1004",
            "alert_type": "ZERO_RUNTIME",
            "severity": "WARNING",
            "message": "Asset EQX1004 recorded 0.0h runtime during initial staging.",
            "status": "RESOLVED",
            "metadata_json": {"engine_hours": 0.0, "resolution": "Sensor calibrated and verified"},
            "created_at": base_time - timedelta(days=12),
            "resolved_at": base_time - timedelta(days=10),
        },
        # Historical Resolved Alert 9: EQX1005 DUE_SOON (Resolved by completed extension)
        {
            "equipment_id": "EQX1005",
            "alert_type": "DUE_SOON",
            "severity": "MEDIUM",
            "message": "Rental for Bulldozer EQX1005 expiring within 48 hours for runway compaction.",
            "status": "RESOLVED",
            "metadata_json": {"resolution": "Contract extended by 7 days"},
            "created_at": base_time - timedelta(days=16),
            "resolved_at": base_time - timedelta(days=15),
        },
        # Historical Resolved Alert 10: EQX1007 OVERDUE (Resolved by completed check-in)
        {
            "equipment_id": "EQX1007",
            "alert_type": "OVERDUE",
            "severity": "CRITICAL",
            "message": "Rental contract for EQX1007 was overdue following turbine cabling.",
            "status": "RESOLVED",
            "metadata_json": {"resolution": "Off-rent check-in completed early"},
            "created_at": base_time - timedelta(days=4),
            "resolved_at": base_time - timedelta(days=3),
        },
    ]

    for a_data in alerts_data:
        existing = (
            db.query(Alert)
            .filter(
                Alert.equipment_id == a_data["equipment_id"],
                Alert.alert_type == a_data["alert_type"],
                Alert.created_at == a_data["created_at"],
            )
            .first()
        )
        if not existing:
            db.add(Alert(**a_data))

    db.flush()

    # 7. Seed Recommendations (Deterministically matching Recommendation Engine)
    recommendations_data = [
        # Rec 1: EQX1001 REASSIGN
        {
            "equipment_id": "EQX1001",
            "recommendation_type": "REASSIGN",
            "priority": "CRITICAL",
            "explanation": "EQX1001 has remained rented while recording 14.2h idle time and only 11.2% utilization. Reassigning the asset to Kallambella Wind Energy Corridor will eliminate standby costs, saving an estimated ₹37,000.00.",
            "action": "Reallocate asset to Kallambella Wind Energy Corridor to recover utilization",
            "confidence": 0.92,
            "estimated_impact": {
                "impact_type": "IDLE_AVOIDANCE",
                "estimated_savings_usd": 37000.0,
                "daily_rate": 18500.0,
                "avoidable_days": 2.0,
                "calculation_basis": "2.0 avoidable idle days × ₹18,500.00/day rate = ₹37,000.00",
            },
            "status": "PENDING",
            "created_at": base_time - timedelta(hours=8),
            "resolved_at": None,
        },
        # Rec 2: EQX1002 REASSIGN
        {
            "equipment_id": "EQX1002",
            "recommendation_type": "REASSIGN",
            "priority": "CRITICAL",
            "explanation": "EQX1002 has remained rented while recording 1.8h idle time and only 10.0% utilization. Reassigning the asset to Kallambella Wind Energy Corridor will eliminate standby costs, saving an estimated ₹26,000.00.",
            "action": "Reallocate asset to Kallambella Wind Energy Corridor to recover utilization",
            "confidence": 0.92,
            "estimated_impact": {
                "impact_type": "IDLE_AVOIDANCE",
                "estimated_savings_usd": 26000.0,
                "daily_rate": 26000.0,
                "avoidable_days": 1.0,
                "calculation_basis": "1.0 avoidable idle days × ₹26,000.00/day rate = ₹26,000.00",
            },
            "status": "PENDING",
            "created_at": base_time - timedelta(hours=12),
            "resolved_at": None,
        },
        # Rec 3: EQX1006 RETURN
        {
            "equipment_id": "EQX1006",
            "recommendation_type": "RETURN",
            "priority": "CRITICAL",
            "explanation": "Asset EQX1006 is 48.0 hours overdue under Contract. Initiating an off-rent return will immediately eliminate ongoing ₹7,500.00/day surcharge penalties.",
            "action": "Initiate off-rent check-in to eliminate ₹7,500.00/day surcharge",
            "confidence": 0.95,
            "estimated_impact": {
                "impact_type": "OVERDUE_SURCHARGE_AVOIDED",
                "estimated_savings_usd": 20250.0,
                "daily_rate": 7500.0,
                "days_overdue": 2.7,
                "calculation_basis": "2.7 overdue days × ₹7,500.00/day surcharge = ₹20,250.00",
            },
            "status": "PENDING",
            "created_at": base_time - timedelta(days=2),
            "resolved_at": None,
        },
        # Rec 4: EQX1002 INVESTIGATE
        {
            "equipment_id": "EQX1002",
            "recommendation_type": "INVESTIGATE",
            "priority": "HIGH",
            "explanation": "Asset EQX1002 is deployed at Navi Mumbai International Airport without an assigned certified operator. Assigning an authorized driver will unlock scheduled site operations.",
            "action": "Assign certified equipment operator to active deployment",
            "confidence": 0.88,
            "estimated_impact": {
                "impact_type": "UTILIZATION_RECOVERY",
                "estimated_savings_usd": 52000.0,
                "daily_rate": 26000.0,
                "calculation_basis": "2 days deployment recovery × ₹26,000.00/day = ₹52,000.00",
            },
            "status": "IN_PROGRESS",
            "created_at": base_time - timedelta(hours=12),
            "resolved_at": None,
        },
        # Historical Completed Recommendations
        {
            "equipment_id": "EQX1003",
            "recommendation_type": "REASSIGN",
            "priority": "HIGH",
            "explanation": "Reassign wheel loader to Bailadila Deposit 14 to satisfy surging demand.",
            "action": "Reallocate asset to Bailadila Iron Ore Complex to recover utilization",
            "confidence": 0.90,
            "estimated_impact": {"impact_type": "IDLE_AVOIDANCE", "estimated_savings_usd": 45000.0, "daily_rate": 15000.0},
            "status": "COMPLETED",
            "created_at": base_time - timedelta(days=20),
            "resolved_at": base_time - timedelta(days=18),
        },
        {
            "equipment_id": "EQX1005",
            "recommendation_type": "EXTEND",
            "priority": "MEDIUM",
            "explanation": "Extend heavy bulldozer contract for runway compaction phase.",
            "action": "Extend active rental contract to support runway compaction",
            "confidence": 0.90,
            "estimated_impact": {"impact_type": "RECONTRACTING_PREMIUM_AVOIDED", "estimated_savings_usd": 42000.0, "daily_rate": 24000.0},
            "status": "COMPLETED",
            "created_at": base_time - timedelta(days=16),
            "resolved_at": base_time - timedelta(days=15),
        },
        {
            "equipment_id": "EQX1004",
            "recommendation_type": "INVESTIGATE",
            "priority": "MEDIUM",
            "explanation": "Inspect jobsite staging area and verify generator telemetry connection.",
            "action": "Inspect jobsite staging area and verify generator telemetry connection",
            "confidence": 0.85,
            "estimated_impact": {"impact_type": "UTILIZATION_RECOVERY", "estimated_savings_usd": 5500.0, "daily_rate": 5500.0},
            "status": "COMPLETED",
            "created_at": base_time - timedelta(days=12),
            "resolved_at": base_time - timedelta(days=10),
        },
        {
            "equipment_id": "EQX1007",
            "recommendation_type": "RETURN",
            "priority": "CRITICAL",
            "explanation": "Initiate off-rent check-in following wind turbine electrical commissioning.",
            "action": "Initiate off-rent check-in following wind turbine electrical commissioning",
            "confidence": 0.95,
            "estimated_impact": {"impact_type": "EARLY_RETURN", "estimated_savings_usd": 19000.0, "daily_rate": 9500.0},
            "status": "COMPLETED",
            "created_at": base_time - timedelta(days=4),
            "resolved_at": base_time - timedelta(days=3),
        },
    ]

    for r_data in recommendations_data:
        existing = (
            db.query(Recommendation)
            .filter(
                Recommendation.equipment_id == r_data["equipment_id"],
                Recommendation.recommendation_type == r_data["recommendation_type"],
                Recommendation.created_at == r_data["created_at"],
            )
            .first()
        )
        if not existing:
            db.add(Recommendation(**r_data))

    db.flush()

    # Query inserted recommendations to link foreign keys cleanly
    rec_eq1001_reassign = db.query(Recommendation).filter(Recommendation.equipment_id == "EQX1001", Recommendation.recommendation_type == "REASSIGN", Recommendation.status == "PENDING").first()
    rec_eq1002_investigate = db.query(Recommendation).filter(Recommendation.equipment_id == "EQX1002", Recommendation.recommendation_type == "INVESTIGATE").first()
    rec_eq1006_return = db.query(Recommendation).filter(Recommendation.equipment_id == "EQX1006", Recommendation.recommendation_type == "RETURN", Recommendation.status == "PENDING").first()
    rec_eq1003_reassign = db.query(Recommendation).filter(Recommendation.equipment_id == "EQX1003", Recommendation.recommendation_type == "REASSIGN", Recommendation.status == "COMPLETED").first()
    rec_eq1005_extend = db.query(Recommendation).filter(Recommendation.equipment_id == "EQX1005", Recommendation.recommendation_type == "EXTEND", Recommendation.status == "COMPLETED").first()
    rec_eq1004_investigate = db.query(Recommendation).filter(Recommendation.equipment_id == "EQX1004", Recommendation.recommendation_type == "INVESTIGATE", Recommendation.status == "COMPLETED").first()
    rec_eq1007_return = db.query(Recommendation).filter(Recommendation.equipment_id == "EQX1007", Recommendation.recommendation_type == "RETURN", Recommendation.status == "COMPLETED").first()

    alert_eq1001 = db.query(Alert).filter(Alert.equipment_id == "EQX1001", Alert.alert_type == "EXCESSIVE_IDLE", Alert.status == "OPEN").first()
    alert_eq1002 = db.query(Alert).filter(Alert.equipment_id == "EQX1002", Alert.alert_type == "MISSING_ASSIGNMENT", Alert.status == "OPEN").first()
    alert_eq1006 = db.query(Alert).filter(Alert.equipment_id == "EQX1006", Alert.alert_type == "OVERDUE", Alert.status == "OPEN").first()

    # 8. Seed Actions (Action Queue: 3 Active + 4 Completed)
    actions_data = [
        # Action 1: Pending Reassign for EQX1001
        {
            "equipment_id": "EQX1001",
            "recommendation_id": rec_eq1001_reassign.id if rec_eq1001_reassign else None,
            "alert_id": alert_eq1001.id if alert_eq1001 else None,
            "action_type": "REASSIGN",
            "status": "PENDING",
            "priority": "CRITICAL",
            "notes": "Reassign under-utilized excavator from Bailadila to Kallambella Wind Corridor",
            "actor": "Commander Marcus Vance",
            "payload_json": {"target_site_id": "SITE-003", "estimated_savings_usd": 37000.0},
            "created_at": base_time - timedelta(hours=8),
            "completed_at": None,
        },
        # Action 2: In-Progress Investigate for EQX1002
        {
            "equipment_id": "EQX1002",
            "recommendation_id": rec_eq1002_investigate.id if rec_eq1002_investigate else None,
            "alert_id": alert_eq1002.id if alert_eq1002 else None,
            "action_type": "INVESTIGATE",
            "status": "IN_PROGRESS",
            "priority": "HIGH",
            "notes": "Operator dispatch in progress for unassigned bulldozer at NMIA staging",
            "actor": "Commander Marcus Vance",
            "payload_json": {"target_operator_id": "OP-001", "estimated_savings_usd": 52000.0},
            "created_at": base_time - timedelta(hours=6),
            "completed_at": None,
        },
        # Action 3: Pending Return for EQX1006
        {
            "equipment_id": "EQX1006",
            "recommendation_id": rec_eq1006_return.id if rec_eq1006_return else None,
            "alert_id": alert_eq1006.id if alert_eq1006 else None,
            "action_type": "RETURN",
            "status": "PENDING",
            "priority": "CRITICAL",
            "notes": "Initiate return check-in for overdue scissor lift at Kallambella Corridor",
            "actor": "Commander Marcus Vance",
            "payload_json": {"estimated_savings_usd": 20250.0},
            "created_at": base_time - timedelta(hours=12),
            "completed_at": None,
        },
        # Action 4: Completed Reassign for EQX1003 (Historical)
        {
            "equipment_id": "EQX1003",
            "recommendation_id": rec_eq1003_reassign.id if rec_eq1003_reassign else None,
            "alert_id": None,
            "action_type": "REASSIGN",
            "status": "COMPLETED",
            "priority": "HIGH",
            "notes": "Reassigned wheel loader to Bailadila Iron Ore Complex Deposit 14",
            "actor": "Commander Marcus Vance",
            "payload_json": {"target_site_id": "SITE-001"},
            "created_at": base_time - timedelta(days=20),
            "completed_at": base_time - timedelta(days=18),
        },
        # Action 5: Completed Extend for EQX1005 (Historical)
        {
            "equipment_id": "EQX1005",
            "recommendation_id": rec_eq1005_extend.id if rec_eq1005_extend else None,
            "alert_id": None,
            "action_type": "EXTEND",
            "status": "COMPLETED",
            "priority": "MEDIUM",
            "notes": "Seamlessly extended runway compaction contract by 7 days",
            "actor": "Commander Marcus Vance",
            "payload_json": {"extension_days": 7},
            "created_at": base_time - timedelta(days=16),
            "completed_at": base_time - timedelta(days=15),
        },
        # Action 6: Completed Investigate for EQX1004 (Historical)
        {
            "equipment_id": "EQX1004",
            "recommendation_id": rec_eq1004_investigate.id if rec_eq1004_investigate else None,
            "alert_id": None,
            "action_type": "INVESTIGATE",
            "status": "COMPLETED",
            "priority": "MEDIUM",
            "notes": "Verified auxiliary generator sensor linkage at NMIA staging",
            "actor": "Commander Marcus Vance",
            "payload_json": {"target_operator_id": "OP-003"},
            "created_at": base_time - timedelta(days=12),
            "completed_at": base_time - timedelta(days=10),
        },
        # Action 7: Completed Return for EQX1007 (Historical)
        {
            "equipment_id": "EQX1007",
            "recommendation_id": rec_eq1007_return.id if rec_eq1007_return else None,
            "alert_id": None,
            "action_type": "RETURN",
            "status": "COMPLETED",
            "priority": "CRITICAL",
            "notes": "Off-rent return completed on schedule following wind tower cabling",
            "actor": "Commander Marcus Vance",
            "payload_json": {"condition": "clean, full tank"},
            "created_at": base_time - timedelta(days=4),
            "completed_at": base_time - timedelta(days=3),
        },
    ]

    for act_data in actions_data:
        existing = (
            db.query(Action)
            .filter(
                Action.equipment_id == act_data["equipment_id"],
                Action.action_type == act_data["action_type"],
                Action.created_at == act_data["created_at"],
            )
            .first()
        )
        if not existing:
            db.add(Action(**act_data))

    db.flush()

    # Query completed actions to link ImpactRecords
    act_eq1003 = db.query(Action).filter(Action.equipment_id == "EQX1003", Action.action_type == "REASSIGN", Action.status == "COMPLETED").first()
    act_eq1005 = db.query(Action).filter(Action.equipment_id == "EQX1005", Action.action_type == "EXTEND", Action.status == "COMPLETED").first()
    act_eq1004 = db.query(Action).filter(Action.equipment_id == "EQX1004", Action.action_type == "INVESTIGATE", Action.status == "COMPLETED").first()
    act_eq1007 = db.query(Action).filter(Action.equipment_id == "EQX1007", Action.action_type == "RETURN", Action.status == "COMPLETED").first()

    # 9. Seed Impact Records (Realized Savings from Completed Actions)
    # Exact calculation basis verified against app/analytics/impact_engine.py
    impact_data = [
        # Impact 1: EQX1003 IDLE_AVOIDANCE (3 days × ₹15,000 = ₹45,000)
        {
            "action_id": act_eq1003.id if act_eq1003 else None,
            "equipment_id": "EQX1003",
            "site_id": "SITE-001",
            "impact_type": "IDLE_AVOIDANCE",
            "estimated_amount": 45000.0,
            "realized_amount": 45000.0,
            "currency": "INR",
            "calculation_basis": "Reassigned asset to high-demand site (SITE-001): 3.0 avoidable standby days × ₹15,000.00/day = ₹45,000.00",
            "before_state": {"action_type": "REASSIGN", "equipment_id": "EQX1003", "daily_rate": 15000.0},
            "after_state": {"action_status": "COMPLETED", "completed_at": (base_time - timedelta(days=18)).isoformat(), "target_site_id": "SITE-001"},
            "calculated_at": base_time - timedelta(days=18),
        },
        # Impact 2: EQX1005 RECONTRACTING_PREMIUM_AVOIDED (7 days × ₹24,000 × 0.25 = ₹42,000)
        {
            "action_id": act_eq1005.id if act_eq1005 else None,
            "equipment_id": "EQX1005",
            "site_id": "SITE-002",
            "impact_type": "RECONTRACTING_PREMIUM_AVOIDED",
            "estimated_amount": 42000.0,
            "realized_amount": 42000.0,
            "currency": "INR",
            "calculation_basis": "Seamlessly extended contract by 7 days: Avoided re-dispatch overhead = ₹42,000.00",
            "before_state": {"action_type": "EXTEND", "equipment_id": "EQX1005", "daily_rate": 24000.0},
            "after_state": {"action_status": "COMPLETED", "completed_at": (base_time - timedelta(days=15)).isoformat(), "target_site_id": "SITE-002"},
            "calculated_at": base_time - timedelta(days=15),
        },
        # Impact 3: EQX1004 UTILIZATION_RECOVERY (1.0 day × ₹5,500 = ₹5,500)
        {
            "action_id": act_eq1004.id if act_eq1004 else None,
            "equipment_id": "EQX1004",
            "site_id": "SITE-002",
            "impact_type": "UTILIZATION_RECOVERY",
            "estimated_amount": 5500.0,
            "realized_amount": 5500.0,
            "currency": "INR",
            "calculation_basis": "Resolved jobsite staging anomaly: 1.0 day operational recovery × ₹5,500.00/day = ₹5,500.00",
            "before_state": {"action_type": "INVESTIGATE", "equipment_id": "EQX1004", "daily_rate": 5500.0},
            "after_state": {"action_status": "COMPLETED", "completed_at": (base_time - timedelta(days=10)).isoformat(), "target_site_id": "SITE-002"},
            "calculated_at": base_time - timedelta(days=10),
        },
        # Impact 4: EQX1007 EARLY_RETURN (2.0 days × ₹9,500 = ₹19,000)
        {
            "action_id": act_eq1007.id if act_eq1007 else None,
            "equipment_id": "EQX1007",
            "site_id": "SITE-003",
            "impact_type": "EARLY_RETURN",
            "estimated_amount": 19000.0,
            "realized_amount": 19000.0,
            "currency": "INR",
            "calculation_basis": "Off-rent return completed early: 2.0 unused days × ₹9,500.00/day = ₹19,000.00",
            "before_state": {"action_type": "RETURN", "equipment_id": "EQX1007", "daily_rate": 9500.0},
            "after_state": {"action_status": "COMPLETED", "completed_at": (base_time - timedelta(days=3)).isoformat(), "target_site_id": "SITE-003"},
            "calculated_at": base_time - timedelta(days=3),
        },
    ]

    for imp_data in impact_data:
        existing = (
            db.query(ImpactRecord)
            .filter(
                ImpactRecord.equipment_id == imp_data["equipment_id"],
                ImpactRecord.calculated_at == imp_data["calculated_at"],
            )
            .first()
        )
        if not existing:
            db.add(ImpactRecord(**imp_data))

    db.flush()

    # 10. Seed Deterministic Demand Forecasts (72 records: 3 sites × 6 types × 4 weeks)
    forecast_records = generate_demand_forecasts(db=db, horizon_weeks=4, now=base_time)
    sync_forecasts_to_db(db=db, forecasts=forecast_records)

    # 11. Seed Audit Trail History
    audit_events_data = [
        # Checkouts
        {
            "event_type": "CHECKOUT",
            "equipment_id": "EQX1001",
            "actor": "System Dispatch",
            "timestamp": base_time - timedelta(days=5),
            "metadata_json": {"site_id": "SITE-001", "operator_id": "OP-001", "daily_rate": 18500.0},
        },
        {
            "event_type": "CHECKOUT",
            "equipment_id": "EQX1002",
            "actor": "Yard Logistics",
            "timestamp": base_time - timedelta(days=2),
            "metadata_json": {"site_id": "SITE-002", "operator_id": None, "daily_rate": 26000.0},
        },
        {
            "event_type": "CHECKOUT",
            "equipment_id": "EQX1003",
            "actor": "System Dispatch",
            "timestamp": base_time - timedelta(days=4),
            "metadata_json": {"site_id": "SITE-001", "operator_id": "OP-002", "daily_rate": 15000.0},
        },
        {
            "event_type": "CHECKOUT",
            "equipment_id": "EQX1004",
            "actor": "Field Logistics",
            "timestamp": base_time - timedelta(days=6),
            "metadata_json": {"site_id": "SITE-002", "operator_id": "OP-003", "daily_rate": 5500.0},
        },
        {
            "event_type": "CHECKOUT",
            "equipment_id": "EQX1005",
            "actor": "System Dispatch",
            "timestamp": base_time - timedelta(days=8),
            "metadata_json": {"site_id": "SITE-002", "operator_id": "OP-004", "daily_rate": 24000.0},
        },
        {
            "event_type": "CHECKOUT",
            "equipment_id": "EQX1006",
            "actor": "Field Logistics",
            "timestamp": base_time - timedelta(days=10),
            "metadata_json": {"site_id": "SITE-003", "operator_id": "OP-001", "daily_rate": 7500.0},
        },
        # Action Events
        {
            "event_type": "EQUIPMENT_REASSIGNED",
            "equipment_id": "EQX1003",
            "actor": "Commander Marcus Vance",
            "timestamp": base_time - timedelta(days=18),
            "metadata_json": {"action_type": "REASSIGN", "target_site_id": "SITE-001", "realized_savings": 45000.0},
        },
        {
            "event_type": "RENTAL_EXTENDED",
            "equipment_id": "EQX1005",
            "actor": "Commander Marcus Vance",
            "timestamp": base_time - timedelta(days=15),
            "metadata_json": {"action_type": "EXTEND", "extension_days": 7, "realized_savings": 42000.0},
        },
        {
            "event_type": "INVESTIGATION_COMPLETED",
            "equipment_id": "EQX1004",
            "actor": "Commander Marcus Vance",
            "timestamp": base_time - timedelta(days=10),
            "metadata_json": {"action_type": "INVESTIGATE", "target_operator_id": "OP-003", "realized_savings": 5500.0},
        },
        {
            "event_type": "RETURN_COMPLETED",
            "equipment_id": "EQX1007",
            "actor": "Commander Marcus Vance",
            "timestamp": base_time - timedelta(days=3),
            "metadata_json": {"action_type": "RETURN", "condition": "Returned clean, full tank", "realized_savings": 19000.0},
        },
        {
            "event_type": "CHECKIN",
            "equipment_id": "EQX1007",
            "actor": "Rajesh Sharma",
            "timestamp": base_time - timedelta(days=3),
            "metadata_json": {"condition": "Returned clean, full tank", "site_id": "SITE-003"},
        },
        {
            "event_type": "ACTION_CREATED",
            "equipment_id": "EQX1001",
            "actor": "Commander Marcus Vance",
            "timestamp": base_time - timedelta(hours=8),
            "metadata_json": {"action_type": "REASSIGN", "priority": "CRITICAL"},
        },
        {
            "event_type": "ACTION_CREATED",
            "equipment_id": "EQX1002",
            "actor": "Commander Marcus Vance",
            "timestamp": base_time - timedelta(hours=6),
            "metadata_json": {"action_type": "INVESTIGATE", "priority": "HIGH"},
        },
        {
            "event_type": "ACTION_CREATED",
            "equipment_id": "EQX1006",
            "actor": "Commander Marcus Vance",
            "timestamp": base_time - timedelta(hours=12),
            "metadata_json": {"action_type": "RETURN", "priority": "CRITICAL"},
        },
    ]

    for ae_data in audit_events_data:
        existing = (
            db.query(AuditEvent)
            .filter(
                AuditEvent.equipment_id == ae_data["equipment_id"],
                AuditEvent.event_type == ae_data["event_type"],
                AuditEvent.timestamp == ae_data["timestamp"],
            )
            .first()
        )
        if not existing:
            db.add(AuditEvent(**ae_data))

    # 12. Seed only an explicitly configured administrator; tests create their own user.
    admin_users = [
        {
            "id": "00000000-0000-0000-0000-000000000001",
            "email": os.getenv("ADMIN_EMAIL", "admin@rentsense.local"),
            "hashed_password": hash_password(os.environ["ADMIN_PASSWORD"]),
            "role": "admin",
            "is_active": True,
        },
    ] if os.getenv("ADMIN_PASSWORD") else []
    for u_data in admin_users:
        if not db.query(User).filter(User.email == u_data["email"]).first():
            db.add(User(**u_data))

    db.commit()
    print("Database seeding completed successfully.")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Initialize an empty demo database; existing data is preserved by default.")
    parser.add_argument("--reset", action="store_true", help="Explicitly erase domain data in a DISPOSABLE demo database")
    args = parser.parse_args()
    db = SessionLocal()
    try:
        seed_database(db, reset=args.reset)
    finally:
        db.close()
