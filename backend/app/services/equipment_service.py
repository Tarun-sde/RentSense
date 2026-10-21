from typing import Optional
from sqlalchemy.orm import Session, joinedload, object_session
from sqlalchemy import select
from app.models import Equipment, Rental, Telemetry, Alert, AuditEvent
from app.services.status_service import derive_status, calculate_utilization
from app.schemas.equipment import EquipmentListItem, EquipmentDetailResponse
from app.schemas.rental import RentalResponse
from app.schemas.site import SiteResponse
from app.schemas.operator import OperatorResponse
from app.schemas.telemetry import TelemetryResponse
from app.schemas.alert import AlertResponse
from app.schemas.audit import AuditEventResponse


def fleet_query(db: Session):
    """One row per asset: indexed latest-row lookups, never full history joins."""
    rental_id = (select(Rental.id).where(Rental.equipment_id == Equipment.id,
        Rental.checked_in_at.is_(None)).order_by(Rental.created_at.desc(), Rental.id.desc())
        .limit(1).correlate(Equipment).scalar_subquery())
    telemetry_id = (select(Telemetry.id).where(Telemetry.equipment_id == Equipment.id)
        .order_by(Telemetry.timestamp.desc(), Telemetry.id.desc()).limit(1)
        .correlate(Equipment).scalar_subquery())
    return (db.query(Equipment, Rental, Telemetry)
        .outerjoin(Rental, Rental.id == rental_id)
        .outerjoin(Telemetry, Telemetry.id == telemetry_id)
        .options(joinedload(Rental.site), joinedload(Rental.operator))
        .order_by(Equipment.id))


def load_fleet(query):
    """Read-only request snapshot; do not replace ORM history collections."""
    equipment = []
    for asset, rental, telemetry in query.all():
        asset._fleet_snapshot = (rental, telemetry)
        equipment.append(asset)
    return equipment


def get_current_rental(equipment: Equipment) -> Optional[Rental]:
    """Get the currently open/active rental for an equipment asset."""
    if hasattr(equipment, "_fleet_snapshot"):
        return equipment._fleet_snapshot[0]
    db = object_session(equipment)
    if db is not None:
        return (db.query(Rental).options(joinedload(Rental.site), joinedload(Rental.operator))
            .filter(Rental.equipment_id == equipment.id, Rental.checked_in_at.is_(None))
            .order_by(Rental.created_at.desc(), Rental.id.desc()).first())
    for rental in equipment.rentals:
        if rental.checked_in_at is None:
            return rental
    return None


def get_latest_telemetry(equipment: Equipment) -> Optional[Telemetry]:
    """Get the most recent telemetry record for an equipment asset."""
    if hasattr(equipment, "_fleet_snapshot"):
        return equipment._fleet_snapshot[1]
    db = object_session(equipment)
    if db is not None:
        return (db.query(Telemetry).filter(Telemetry.equipment_id == equipment.id)
            .order_by(Telemetry.timestamp.desc(), Telemetry.id.desc()).first())
    if equipment.telemetry:
        return equipment.telemetry[0]
    return None


def build_equipment_list_item(equipment: Equipment) -> EquipmentListItem:
    """Transform an Equipment ORM object into an enriched EquipmentListItem schema."""
    current_rental = get_current_rental(equipment)
    latest_telemetry = get_latest_telemetry(equipment)
    status = derive_status(current_rental, latest_telemetry)

    utilization_rate = 0.0
    if latest_telemetry:
        utilization_rate = calculate_utilization(
            latest_telemetry.engine_hours, latest_telemetry.idle_hours
        )

    site_resp = None
    op_resp = None
    rental_resp = None

    if current_rental:
        if current_rental.site:
            site_resp = SiteResponse.model_validate(current_rental.site)
        if current_rental.operator:
            op_resp = OperatorResponse.model_validate(current_rental.operator)
        rental_resp = RentalResponse.model_validate(current_rental)

    telem_resp = None
    if latest_telemetry:
        telem_resp = TelemetryResponse.model_validate(latest_telemetry)

    return EquipmentListItem(
        id=equipment.id,
        type=equipment.type,
        dealer=equipment.dealer,
        daily_rate=equipment.daily_rate,
        status=status.value,
        current_rental=rental_resp,
        site=site_resp,
        operator=op_resp,
        latest_telemetry=telem_resp,
        utilization_rate=round(utilization_rate, 4),
        metadata_json=equipment.metadata_json,
        created_at=equipment.created_at,
        updated_at=equipment.updated_at,
    )


def build_equipment_detail(equipment: Equipment, history_limit: int = 100, history_offset: int = 0) -> EquipmentDetailResponse:
    """Transform an Equipment ORM object into an enriched EquipmentDetailResponse schema."""
    current_rental = get_current_rental(equipment)
    latest_telemetry = get_latest_telemetry(equipment)
    status = derive_status(current_rental, latest_telemetry)

    utilization_rate = 0.0
    if latest_telemetry:
        utilization_rate = calculate_utilization(
            latest_telemetry.engine_hours, latest_telemetry.idle_hours
        )

    site_resp = None
    op_resp = None
    rental_resp = None

    if current_rental:
        if current_rental.site:
            site_resp = SiteResponse.model_validate(current_rental.site)
        if current_rental.operator:
            op_resp = OperatorResponse.model_validate(current_rental.operator)
        rental_resp = RentalResponse.model_validate(current_rental)

    telem_resp = None
    if latest_telemetry:
        telem_resp = TelemetryResponse.model_validate(latest_telemetry)

    db = object_session(equipment)
    recent_telemetry = [TelemetryResponse.model_validate(t) for t in db.query(Telemetry)
        .filter(Telemetry.equipment_id == equipment.id)
        .order_by(Telemetry.timestamp.desc(), Telemetry.id.desc()).limit(20).all()]
    rental_history = [RentalResponse.model_validate(r) for r in db.query(Rental)
        .options(joinedload(Rental.site), joinedload(Rental.operator))
        .filter(Rental.equipment_id == equipment.id)
        .order_by(Rental.created_at.desc(), Rental.id.desc()).offset(history_offset).limit(history_limit).all()]
    active_alerts = [AlertResponse.model_validate(a) for a in db.query(Alert)
        .filter(Alert.equipment_id == equipment.id, Alert.status == "OPEN")
        .order_by(Alert.created_at.desc(), Alert.id.desc()).limit(500).all()]
    audit_timeline = [AuditEventResponse.model_validate(a) for a in db.query(AuditEvent)
        .filter(AuditEvent.equipment_id == equipment.id)
        .order_by(AuditEvent.timestamp.desc(), AuditEvent.id.desc()).offset(history_offset).limit(history_limit).all()]

    return EquipmentDetailResponse(
        id=equipment.id,
        type=equipment.type,
        dealer=equipment.dealer,
        daily_rate=equipment.daily_rate,
        status=status.value,
        current_rental=rental_resp,
        site=site_resp,
        operator=op_resp,
        latest_telemetry=telem_resp,
        recent_telemetry=recent_telemetry,
        rental_history=rental_history,
        active_alerts=active_alerts,
        audit_timeline=audit_timeline,
        utilization_rate=round(utilization_rate, 4),
        metadata_json=equipment.metadata_json,
        created_at=equipment.created_at,
        updated_at=equipment.updated_at,
    )
