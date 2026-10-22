import os
import sys
import hashlib
import json
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
from app.analytics.anomaly_engine import evaluate_equipment_anomalies
from app.analytics.impact_engine import record_realized_action_savings
from app.analytics.recommendation_engine import evaluate_equipment_recommendations
from app.services.equipment_service import fleet_query

# Deterministic reference used only by tests; normal seeding uses the current UTC time.
ANCHOR_TIME = datetime(2026, 9, 1, 12, 0, 0, tzinfo=timezone.utc)
DEMO_EQUIPMENT_IDS = tuple(f"EQX{number}" for number in range(1001, 1021))
DEMO_SITE_IDS = tuple(f"SITE-{number:03}" for number in range(1, 6))
DEMO_OPERATOR_IDS = tuple(f"OP-{number:03}" for number in range(1, 11))
DEMO_REFRESH_CONFIRMATION = "REFRESH RENTSENSE DEMO DATA"


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


def seed_database(db: Session, reset: bool = False, anchor_time: datetime | None = None, allow_existing: bool = False, commit: bool = True):
    """
    Deterministic & Idempotent Database Seeder localized for Indian infrastructure operations.
    Seeds 20 fictional equipment assets, 5 sites, 10 operators, active & historical rentals,
    telemetry streams, alerts, recommendations, actions, forecasts, and financial impact records.
    """
    Base.metadata.create_all(bind=db.get_bind())
    if reset:
        reset_database(db)
    elif not allow_existing and any(db.query(model).first() is not None for model in
             (Equipment, Rental, Telemetry, Site, Operator, Alert, Recommendation, Action, ImpactRecord, Forecast, AuditEvent)):
        # Existing data is never moved or partially reseeded on a restart.
        return

    base_time = anchor_time or datetime.now(timezone.utc).replace(microsecond=0)

    # 1. Seed fictional operations at plausible Indian locations.
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
        {"id": "SITE-004", "name": "Ahmedabad Metro Demo Package", "location": "Fictional east corridor works, Gujarat", "latitude": 23.0225, "longitude": 72.5714, "created_at": base_time - timedelta(days=55)},
        {"id": "SITE-005", "name": "Nagpur Logistics Demo Hub", "location": "Fictional multimodal freight yard, Maharashtra", "latitude": 21.1458, "longitude": 79.0882, "created_at": base_time - timedelta(days=50)},
    ]

    for s_data in sites_data:
        existing = db.query(Site).filter(Site.id == s_data["id"]).first()
        if existing:
            for k, v in s_data.items():
                setattr(existing, k, v)
        else:
            db.add(Site(**s_data))

    db.flush()

    # 2. Seed clearly fictional demo operators; no personal contact details.
    operators_data = [
        {
            "id": "OP-001",
            "name": "Demo Operator 01",
            "contact": None,
            "created_at": base_time - timedelta(days=90),
        },
        {
            "id": "OP-002",
            "name": "Demo Operator 02",
            "contact": None,
            "created_at": base_time - timedelta(days=90),
        },
        {
            "id": "OP-003",
            "name": "Demo Operator 03",
            "contact": None,
            "created_at": base_time - timedelta(days=75),
        },
        {
            "id": "OP-004",
            "name": "Demo Operator 04",
            "contact": None,
            "created_at": base_time - timedelta(days=60),
        },
        {"id": "OP-005", "name": "Demo Operator 05", "contact": None, "created_at": base_time - timedelta(days=80)},
        {"id": "OP-006", "name": "Demo Operator 06", "contact": None, "created_at": base_time - timedelta(days=75)},
        {"id": "OP-007", "name": "Demo Operator 07", "contact": None, "created_at": base_time - timedelta(days=70)},
        {"id": "OP-008", "name": "Demo Operator 08", "contact": None, "created_at": base_time - timedelta(days=65)},
        {"id": "OP-009", "name": "Demo Operator 09", "contact": None, "created_at": base_time - timedelta(days=60)},
        {"id": "OP-010", "name": "Demo Operator 10", "contact": None, "created_at": base_time - timedelta(days=55)},
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
        {"id": "EQX1008", "type": "Excavator", "dealer": "Demo Fleet Partners", "daily_rate": 21000.0, "metadata_json": {"model": "ZX210 Demo", "serial": "DEMO-1008", "qr_code": "EQX1008"}, "created_at": base_time - timedelta(days=32)},
        {"id": "EQX1009", "type": "Motor Grader", "dealer": "Demo Fleet Partners", "daily_rate": 23000.0, "metadata_json": {"model": "GD535 Demo", "serial": "DEMO-1009", "qr_code": "EQX1009"}, "created_at": base_time - timedelta(days=29)},
        {"id": "EQX1010", "type": "Mobile Crane", "dealer": "Demo Lift Systems", "daily_rate": 32000.0, "metadata_json": {"model": "75T Demo Crane", "serial": "DEMO-1010", "qr_code": "EQX1010"}, "created_at": base_time - timedelta(days=28)},
        {"id": "EQX1011", "type": "Concrete Pump", "dealer": "Demo Concrete Systems", "daily_rate": 18000.0, "metadata_json": {"model": "42M Demo Pump", "serial": "DEMO-1011", "qr_code": "EQX1011"}, "created_at": base_time - timedelta(days=26)},
        {"id": "EQX1012", "type": "Wheel Loader", "dealer": "Demo Fleet Partners", "daily_rate": 16500.0, "metadata_json": {"model": "L120 Demo", "serial": "DEMO-1012", "qr_code": "EQX1012"}, "created_at": base_time - timedelta(days=24)},
        {"id": "EQX1013", "type": "Generator", "dealer": "Demo Power Rentals", "daily_rate": 6500.0, "metadata_json": {"model": "200kVA Demo DG", "serial": "DEMO-1013", "qr_code": "EQX1013"}, "created_at": base_time - timedelta(days=22)},
        {"id": "EQX1014", "type": "Excavator", "dealer": "Demo Fleet Partners", "daily_rate": 19500.0, "metadata_json": {"model": "PC210 Demo", "serial": "DEMO-1014", "qr_code": "EQX1014"}, "created_at": base_time - timedelta(days=21)},
        {"id": "EQX1015", "type": "Bulldozer", "dealer": "Demo Earthworks", "daily_rate": 27000.0, "metadata_json": {"model": "D6 Demo", "serial": "DEMO-1015", "qr_code": "EQX1015"}, "created_at": base_time - timedelta(days=19)},
        {"id": "EQX1016", "type": "Boom Lift", "dealer": "Demo Access Rentals", "daily_rate": 10500.0, "metadata_json": {"model": "Z60 Demo", "serial": "DEMO-1016", "qr_code": "EQX1016"}, "created_at": base_time - timedelta(days=17)},
        {"id": "EQX1017", "type": "Soil Compactor", "dealer": "Demo Road Systems", "daily_rate": 12500.0, "metadata_json": {"model": "CS12 Demo", "serial": "DEMO-1017", "qr_code": "EQX1017"}, "created_at": base_time - timedelta(days=16)},
        {"id": "EQX1018", "type": "Forklift", "dealer": "Demo Logistics Equipment", "daily_rate": 8000.0, "metadata_json": {"model": "5T Demo Forklift", "serial": "DEMO-1018", "qr_code": "EQX1018"}, "created_at": base_time - timedelta(days=14)},
        {"id": "EQX1019", "type": "Water Tanker", "dealer": "Demo Site Services", "daily_rate": 9000.0, "metadata_json": {"model": "12KL Demo Tanker", "serial": "DEMO-1019", "qr_code": "EQX1019"}, "created_at": base_time - timedelta(days=13)},
        {"id": "EQX1020", "type": "Scissor Lift", "dealer": "Demo Access Rentals", "daily_rate": 8500.0, "metadata_json": {"model": "S4046 Demo", "serial": "DEMO-1020", "qr_code": "EQX1020"}, "created_at": base_time - timedelta(days=11)},
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
            "due_at": base_time - timedelta(days=1),
            "checked_in_at": base_time - timedelta(days=3),
            "daily_rate": 9500.0,
            "condition_notes": "Returned clean, full tank, parked in central depot staging yard.",
            "created_at": base_time - timedelta(days=9),
        },
        {"equipment_id": "EQX1008", "site_id": "SITE-004", "operator_id": "OP-005", "checked_out_at": base_time - timedelta(days=6), "due_at": base_time + timedelta(days=9), "checked_in_at": None, "daily_rate": 21000.0, "condition_notes": "Metro station-box excavation in the fictional demo package.", "created_at": base_time - timedelta(days=6)},
        {"equipment_id": "EQX1009", "site_id": "SITE-004", "operator_id": "OP-006", "checked_out_at": base_time - timedelta(days=5), "due_at": base_time + timedelta(days=8), "checked_in_at": None, "daily_rate": 23000.0, "condition_notes": "Formation grading for the demo corridor.", "created_at": base_time - timedelta(days=5)},
        {"equipment_id": "EQX1010", "site_id": "SITE-005", "operator_id": "OP-007", "checked_out_at": base_time - timedelta(days=4), "due_at": base_time + timedelta(days=11), "checked_in_at": None, "daily_rate": 32000.0, "condition_notes": "Container handling structure erection at the fictional logistics hub.", "created_at": base_time - timedelta(days=4)},
        {"equipment_id": "EQX1011", "site_id": "SITE-004", "operator_id": "OP-008", "checked_out_at": base_time - timedelta(days=3), "due_at": base_time + timedelta(days=6), "checked_in_at": None, "daily_rate": 18000.0, "condition_notes": "Viaduct pier concrete placement.", "created_at": base_time - timedelta(days=3)},
        {"equipment_id": "EQX1012", "site_id": "SITE-005", "operator_id": "OP-009", "checked_out_at": base_time - timedelta(days=7), "due_at": base_time + timedelta(days=5), "checked_in_at": None, "daily_rate": 16500.0, "condition_notes": "Standby loader awaiting inbound aggregate; reassignment candidate.", "created_at": base_time - timedelta(days=7)},
        {"equipment_id": "EQX1013", "site_id": "SITE-005", "operator_id": "OP-010", "checked_out_at": base_time - timedelta(days=5), "due_at": base_time + timedelta(hours=30), "checked_in_at": None, "daily_rate": 6500.0, "condition_notes": "Temporary warehouse commissioning power; return preparation required.", "created_at": base_time - timedelta(days=5)},
        {"equipment_id": "EQX1014", "site_id": "SITE-001", "operator_id": "OP-005", "checked_out_at": base_time - timedelta(days=9), "due_at": base_time - timedelta(days=1), "checked_in_at": None, "daily_rate": 19500.0, "condition_notes": "Demo mining bench cleanup awaiting off-rent inspection.", "created_at": base_time - timedelta(days=9)},
        {"equipment_id": "EQX1015", "site_id": "SITE-002", "operator_id": "OP-006", "checked_out_at": base_time - timedelta(days=4), "due_at": base_time + timedelta(days=10), "checked_in_at": None, "daily_rate": 27000.0, "condition_notes": "Airside demo earthworks.", "created_at": base_time - timedelta(days=4)},
        {"equipment_id": "EQX1016", "site_id": "SITE-003", "operator_id": "OP-007", "checked_out_at": base_time - timedelta(days=3), "due_at": base_time + timedelta(days=7), "checked_in_at": None, "daily_rate": 10500.0, "condition_notes": "Wind-tower demo inspection support.", "created_at": base_time - timedelta(days=3)},
        {"equipment_id": "EQX1017", "site_id": "SITE-004", "operator_id": "OP-008", "checked_out_at": base_time - timedelta(days=6), "due_at": base_time + timedelta(days=7), "checked_in_at": None, "daily_rate": 12500.0, "condition_notes": "Compactor held idle after workfront sequencing changed.", "created_at": base_time - timedelta(days=6)},
        {"equipment_id": "EQX1018", "site_id": "SITE-005", "operator_id": "OP-009", "checked_out_at": base_time - timedelta(days=2), "due_at": base_time + timedelta(days=8), "checked_in_at": None, "daily_rate": 8000.0, "condition_notes": "Active pallet movement in the fictional freight yard.", "created_at": base_time - timedelta(days=2)},
        {"equipment_id": "EQX1019", "site_id": "SITE-005", "operator_id": "OP-010", "checked_out_at": base_time - timedelta(days=12), "due_at": base_time - timedelta(days=5), "checked_in_at": base_time - timedelta(days=6), "daily_rate": 9000.0, "condition_notes": "Completed dust-suppression package and returned to depot.", "created_at": base_time - timedelta(days=12)},
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
        "EQX1008": {"lat": 23.0228, "lng": 72.5711, "engine_base": 31.0, "idle_base": 3.2, "fuel": 63.0},
        "EQX1009": {"lat": 23.0219, "lng": 72.5720, "engine_base": 25.0, "idle_base": 2.5, "fuel": 71.0},
        "EQX1010": {"lat": 21.1462, "lng": 79.0885, "engine_base": 18.0, "idle_base": 1.2, "fuel": 76.0},
        "EQX1011": {"lat": 23.0231, "lng": 72.5708, "engine_base": 21.0, "idle_base": 2.0, "fuel": 69.0},
        "EQX1012": {"lat": 21.1454, "lng": 79.0878, "engine_base": 12.0, "idle_base": 9.5, "fuel": 84.0},
        "EQX1013": {"lat": 21.1460, "lng": 79.0890, "engine_base": 36.0, "idle_base": 2.0, "fuel": 41.0},
        "EQX1014": {"lat": 18.7177, "lng": 81.2586, "engine_base": 29.0, "idle_base": 3.0, "fuel": 58.0},
        "EQX1015": {"lat": 18.9887, "lng": 73.0643, "engine_base": 33.0, "idle_base": 3.5, "fuel": 54.0},
        "EQX1016": {"lat": 13.6069, "lng": 76.9030, "engine_base": 17.0, "idle_base": 1.4, "fuel": 73.0},
        "EQX1017": {"lat": 23.0222, "lng": 72.5718, "engine_base": 10.0, "idle_base": 8.5, "fuel": 88.0},
        "EQX1018": {"lat": 21.1459, "lng": 79.0879, "engine_base": 14.0, "idle_base": 1.0, "fuel": 79.0},
        "EQX1019": {"lat": 21.1448, "lng": 79.0869, "engine_base": 11.0, "idle_base": 1.5, "fuel": 92.0},
        "EQX1020": {"lat": 21.1445, "lng": 79.0865, "engine_base": 0.0, "idle_base": 0.0, "fuel": 100.0},
    }

    for eq_id, profile in telemetry_profiles.items():
        for i in range(6):
            t_offset = timedelta(hours=(5 - i) * 4, minutes=15)
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
        # Historical low utilization resolved by a completed reassignment.
        {
            "equipment_id": "EQX1003",
            "alert_type": "LOW_UTILIZATION",
            "severity": "HIGH",
            "message": "Asset EQX1003 had low utilization during initial staging (historical demo event).",
            "status": "RESOLVED",
            "metadata_json": {"resolution": "Reassigned to Bailadila Deposit 14"},
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
            "alert_type": "DUE_SOON",
            "severity": "MEDIUM",
            "message": "Rental contract for EQX1007 approached its planned return following turbine cabling.",
            "status": "RESOLVED",
            "metadata_json": {"resolution": "Off-rent check-in completed early"},
            "created_at": base_time - timedelta(days=4),
            "resolved_at": base_time - timedelta(days=3),
        },
    ]

    for equipment, rental, latest in fleet_query(db).filter(Equipment.id.in_(DEMO_EQUIPMENT_IDS)).all():
        equipment._fleet_snapshot = (rental, latest)
        for anomaly in evaluate_equipment_anomalies(equipment, rental, latest, now=base_time):
            alerts_data.append(dict(equipment_id=equipment.id, alert_type=anomaly.anomaly_type,
                severity=anomaly.severity, message=anomaly.explanation, status="OPEN",
                metadata_json={**anomaly.supporting_signals, "anomaly_score": anomaly.anomaly_score},
                created_at=base_time, resolved_at=None))
        if rental and rental.due_at and base_time <= rental.due_at.replace(tzinfo=timezone.utc) <= base_time + timedelta(hours=48):
            alerts_data.append(dict(equipment_id=equipment.id, alert_type="DUE_SOON", severity="MEDIUM",
                message=f"Demo rental for {equipment.id} is due within 48 hours.", status="OPEN",
                metadata_json={"site_id": rental.site_id}, created_at=base_time, resolved_at=None))

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

    for equipment, rental, latest in fleet_query(db).filter(Equipment.id.in_(DEMO_EQUIPMENT_IDS)).all():
        equipment._fleet_snapshot = (rental, latest)
        for recommendation in evaluate_equipment_recommendations(equipment, rental, latest, now=base_time):
            recommendations_data.append({key: getattr(recommendation, key) for key in (
                "equipment_id", "recommendation_type", "priority", "explanation", "action",
                "confidence", "estimated_impact", "status", "created_at")})

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
            "actor": "Fleet Operator",
            "payload_json": {"target_site_id": "SITE-003", "estimated_savings_usd": rec_eq1001_reassign.estimated_impact["estimated_savings_usd"]},
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
            "actor": "Fleet Operator",
            "payload_json": {"target_operator_id": "OP-001", "estimated_savings_usd": rec_eq1002_investigate.estimated_impact["estimated_savings_usd"]},
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
            "actor": "Fleet Operator",
            "payload_json": {"estimated_savings_usd": rec_eq1006_return.estimated_impact["estimated_savings_usd"]},
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
            "actor": "Fleet Operator",
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
            "actor": "Fleet Operator",
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
            "actor": "Fleet Operator",
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
            "actor": "Fleet Operator",
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

    for action in db.query(Action).filter(Action.equipment_id.in_(DEMO_EQUIPMENT_IDS), Action.status == "COMPLETED").all():
        equipment = db.get(Equipment, action.equipment_id)
        rental = db.query(Rental).filter(Rental.equipment_id == equipment.id,
            Rental.checked_out_at <= action.completed_at).order_by(Rental.checked_out_at.desc()).first()
        record_realized_action_savings(db, action, equipment, rental,
            action.payload_json, now=action.completed_at.replace(tzinfo=timezone.utc), commit=False)
    db.flush()

    # 10. Seed forecasts inside the caller's transaction.
    forecast_records = [record for record in generate_demand_forecasts(db=db, horizon_weeks=4, now=base_time) if record.site_id in DEMO_SITE_IDS]
    sync_forecasts_to_db(db=db, forecasts=forecast_records, commit=False)

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
            "actor": "Fleet Operator",
            "timestamp": base_time - timedelta(days=18),
            "metadata_json": {"action_type": "REASSIGN", "target_site_id": "SITE-001", "realized_savings": 45000.0},
        },
        {
            "event_type": "RENTAL_EXTENDED",
            "equipment_id": "EQX1005",
            "actor": "Fleet Operator",
            "timestamp": base_time - timedelta(days=15),
            "metadata_json": {"action_type": "EXTEND", "extension_days": 7, "realized_savings": 42000.0},
        },
        {
            "event_type": "INVESTIGATION_COMPLETED",
            "equipment_id": "EQX1004",
            "actor": "Fleet Operator",
            "timestamp": base_time - timedelta(days=10),
            "metadata_json": {"action_type": "INVESTIGATE", "target_operator_id": "OP-003", "realized_savings": 5500.0},
        },
        {
            "event_type": "RETURN_COMPLETED",
            "equipment_id": "EQX1007",
            "actor": "Fleet Operator",
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
            "actor": "Fleet Operator",
            "timestamp": base_time - timedelta(hours=8),
            "metadata_json": {"action_type": "REASSIGN", "priority": "CRITICAL"},
        },
        {
            "event_type": "ACTION_CREATED",
            "equipment_id": "EQX1002",
            "actor": "Fleet Operator",
            "timestamp": base_time - timedelta(hours=6),
            "metadata_json": {"action_type": "INVESTIGATE", "priority": "HIGH"},
        },
        {
            "event_type": "ACTION_CREATED",
            "equipment_id": "EQX1006",
            "actor": "Fleet Operator",
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

    db.flush()
    owner = db.get(Equipment, "EQX1001")
    owner.metadata_json = {**owner.metadata_json, "demo_fingerprint": demo_fingerprint(db)}
    db.flush()
    if commit:
        db.commit()
    print("Database seeding completed successfully.")


def demo_fingerprint(db: Session) -> str:
    """Exact domain snapshot: additions or edits invalidate destructive refresh ownership."""
    snapshot = {}
    for model in (Equipment, Site, Operator, Rental, Telemetry, Alert, Recommendation, Action, ImpactRecord, Forecast, AuditEvent):
        if model is Equipment:
            query = db.query(model).filter(model.id.in_(DEMO_EQUIPMENT_IDS))
        elif model is Site:
            query = db.query(model).filter(model.id.in_(DEMO_SITE_IDS))
        elif model is Operator:
            query = db.query(model).filter(model.id.in_(DEMO_OPERATOR_IDS))
        elif model is Forecast:
            query = db.query(model).filter(model.site_id.in_(DEMO_SITE_IDS))
        else:
            query = db.query(model).filter(model.equipment_id.in_(DEMO_EQUIPMENT_IDS))
        rows = []
        for row in query.order_by(model.id).all():
            values = {}
            for column in model.__table__.columns:
                value = getattr(row, column.name)
                if isinstance(value, datetime):
                    value = value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
                    value = value.isoformat()
                if model is Equipment and column.name == "metadata_json" and value:
                    value = {key: item for key, item in value.items() if key != "demo_fingerprint"}
                # Storing the fingerprint itself triggers this ORM-managed timestamp.
                if model is Equipment and column.name == "updated_at":
                    continue
                values[column.name] = value
            rows.append(values)
        snapshot[model.__tablename__] = rows
    return hashlib.sha256(json.dumps(snapshot, sort_keys=True).encode()).hexdigest()


def demo_refresh_preview(db: Session) -> dict:
    """Describe only known demo-owned rows and flag ambiguous external references."""
    unknown_equipment = ~Rental.equipment_id.in_(DEMO_EQUIPMENT_IDS)
    blockers = db.query(Rental).filter(
        unknown_equipment,
        (Rental.site_id.in_(DEMO_SITE_IDS)) | (Rental.operator_id.in_(DEMO_OPERATOR_IDS)),
    ).count()
    blockers += db.query(Action).filter(~Action.equipment_id.in_(DEMO_EQUIPMENT_IDS),
        Action.recommendation_id.in_(db.query(Recommendation.id).filter(Recommendation.equipment_id.in_(DEMO_EQUIPMENT_IDS))) |
        Action.alert_id.in_(db.query(Alert.id).filter(Alert.equipment_id.in_(DEMO_EQUIPMENT_IDS)))).count()
    blockers += db.query(ImpactRecord).filter(~ImpactRecord.equipment_id.in_(DEMO_EQUIPMENT_IDS),
        ImpactRecord.site_id.in_(DEMO_SITE_IDS) |
        ImpactRecord.action_id.in_(db.query(Action.id).filter(Action.equipment_id.in_(DEMO_EQUIPMENT_IDS)))).count()
    counts = {
        "equipment": db.query(Equipment).filter(Equipment.id.in_(DEMO_EQUIPMENT_IDS)).count(),
        "sites": db.query(Site).filter(Site.id.in_(DEMO_SITE_IDS)).count(),
        "operators": db.query(Operator).filter(Operator.id.in_(DEMO_OPERATOR_IDS)).count(),
        "rentals": db.query(Rental).filter(Rental.equipment_id.in_(DEMO_EQUIPMENT_IDS)).count(),
        "telemetry": db.query(Telemetry).filter(Telemetry.equipment_id.in_(DEMO_EQUIPMENT_IDS)).count(),
        "alerts": db.query(Alert).filter(Alert.equipment_id.in_(DEMO_EQUIPMENT_IDS)).count(),
        "recommendations": db.query(Recommendation).filter(Recommendation.equipment_id.in_(DEMO_EQUIPMENT_IDS)).count(),
        "actions": db.query(Action).filter(Action.equipment_id.in_(DEMO_EQUIPMENT_IDS)).count(),
        "impact_records": db.query(ImpactRecord).filter(ImpactRecord.equipment_id.in_(DEMO_EQUIPMENT_IDS)).count(),
        "forecasts": db.query(Forecast).filter(Forecast.site_id.in_(DEMO_SITE_IDS)).count(),
        "audit_events": db.query(AuditEvent).filter(AuditEvent.equipment_id.in_(DEMO_EQUIPMENT_IDS)).count(),
    }
    owner = db.get(Equipment, "EQX1001")
    fingerprint = (owner.metadata_json or {}).get("demo_fingerprint") if owner else None
    provenance_matches = bool(fingerprint) and fingerprint == demo_fingerprint(db)
    return {"counts": counts, "blockers": blockers, "provenance_matches": provenance_matches,
            "safe_to_execute": blockers == 0 and provenance_matches}


def refresh_demo_data(db: Session, confirmation: str | None = None, anchor_time: datetime | None = None) -> dict:
    """Selectively replace the known demo namespace; users and unrelated domain rows survive."""
    if confirmation is not None and confirmation != DEMO_REFRESH_CONFIRMATION:
        raise ValueError(f"Confirmation must exactly match: {DEMO_REFRESH_CONFIRMATION}")
    if confirmation is not None:
        # Prevent writes between the ownership check and replacement; dry-run never locks.
        if db.get_bind().dialect.name == "postgresql":
            db.execute(text("SET LOCAL lock_timeout = '5s'"))
            db.execute(text("LOCK TABLE equipment, sites, operators, rentals, telemetry, alerts, recommendations, actions, impact_records, forecasts, audit_events IN SHARE ROW EXCLUSIVE MODE"))
        elif db.get_bind().dialect.name == "sqlite":
            db.execute(text("BEGIN IMMEDIATE"))
    preview = demo_refresh_preview(db)
    if confirmation is None:
        return preview
    if not preview["safe_to_execute"]:
        db.rollback()
        raise RuntimeError("Refresh aborted: unproven/changed demo ownership or external references; review a backup branch")
    try:
        db.query(ImpactRecord).filter(ImpactRecord.equipment_id.in_(DEMO_EQUIPMENT_IDS)).delete(synchronize_session=False)
        db.query(Action).filter(Action.equipment_id.in_(DEMO_EQUIPMENT_IDS)).delete(synchronize_session=False)
        db.query(AuditEvent).filter(AuditEvent.equipment_id.in_(DEMO_EQUIPMENT_IDS)).delete(synchronize_session=False)
        db.query(Recommendation).filter(Recommendation.equipment_id.in_(DEMO_EQUIPMENT_IDS)).delete(synchronize_session=False)
        db.query(Alert).filter(Alert.equipment_id.in_(DEMO_EQUIPMENT_IDS)).delete(synchronize_session=False)
        db.query(Telemetry).filter(Telemetry.equipment_id.in_(DEMO_EQUIPMENT_IDS)).delete(synchronize_session=False)
        db.query(Rental).filter(Rental.equipment_id.in_(DEMO_EQUIPMENT_IDS)).delete(synchronize_session=False)
        db.query(Forecast).filter(Forecast.site_id.in_(DEMO_SITE_IDS)).delete(synchronize_session=False)
        db.query(Equipment).filter(Equipment.id.in_(DEMO_EQUIPMENT_IDS)).delete(synchronize_session=False)
        db.query(Operator).filter(Operator.id.in_(DEMO_OPERATOR_IDS)).delete(synchronize_session=False)
        db.query(Site).filter(Site.id.in_(DEMO_SITE_IDS)).delete(synchronize_session=False)
        db.flush()
        db.expire_all()
        seed_database(db, anchor_time=anchor_time, allow_existing=True, commit=False)
        result = demo_refresh_preview(db)
        if not result["safe_to_execute"]:
            raise RuntimeError("Refreshed dataset failed ownership verification")
        db.commit()
        return result
    except Exception:
        db.rollback()
        raise


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Initialize or selectively refresh RentSense demo data.")
    parser.add_argument("--refresh-demo", action="store_true", help="Preview a selective demo-data refresh")
    parser.add_argument("--execute", action="store_true", help="Execute --refresh-demo after exact confirmation")
    parser.add_argument("--confirm", help=f"Required with --execute: {DEMO_REFRESH_CONFIRMATION}")
    args = parser.parse_args()
    if args.execute and (not args.refresh_demo or args.confirm != DEMO_REFRESH_CONFIRMATION):
        parser.error("--execute requires --refresh-demo and the exact --confirm phrase")
    db = SessionLocal()
    try:
        if args.refresh_demo:
            print(refresh_demo_data(db, args.confirm if args.execute else None))
        else:
            seed_database(db)
    finally:
        db.close()
