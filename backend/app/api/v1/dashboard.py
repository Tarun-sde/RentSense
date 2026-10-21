from collections import defaultdict
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.models import Equipment, Alert
from app.schemas.dashboard import DashboardKPIResponse
from app.services.status_service import derive_status, calculate_utilization, EquipmentStatus
from app.services.equipment_service import get_current_rental, get_latest_telemetry, fleet_query, load_fleet

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


@router.get("", response_model=DashboardKPIResponse)
def get_dashboard_kpis(db: Session = Depends(get_db)):
    """
    Calculate and return real-time fleet KPI metrics and operational status distribution
    for the Control Tower dashboard overview.
    """
    equipment_records = load_fleet(fleet_query(db))
    status_counts = defaultdict(int)

    utilization_values = []

    for eq in equipment_records:
        current_rental = get_current_rental(eq)
        latest_telemetry = get_latest_telemetry(eq)
        status = derive_status(current_rental, latest_telemetry)
        status_counts[status.value] += 1

        if latest_telemetry and latest_telemetry.engine_hours > 0:
            u_rate = calculate_utilization(
                latest_telemetry.engine_hours, latest_telemetry.idle_hours
            )
            utilization_values.append(u_rate)

    open_alerts_count = db.query(Alert).filter(Alert.status == "OPEN").count()

    total_equipment = len(equipment_records)
    active_count = status_counts[EquipmentStatus.ACTIVE.value]
    idle_count = status_counts[EquipmentStatus.IDLE.value]
    due_soon_count = status_counts[EquipmentStatus.DUE_SOON.value]
    overdue_count = status_counts[EquipmentStatus.OVERDUE.value]
    unassigned_count = status_counts[EquipmentStatus.UNASSIGNED.value]

    fleet_utilization_pct = 0.0
    if utilization_values:
        fleet_utilization_pct = round((sum(utilization_values) / len(utilization_values)) * 100.0, 1)

    return DashboardKPIResponse(
        total_equipment=total_equipment,
        active=active_count,
        idle=idle_count,
        due_soon=due_soon_count,
        overdue=overdue_count,
        unassigned=unassigned_count,
        status_counts=dict(status_counts),
        open_alerts=open_alerts_count,
        fleet_utilization_pct=fleet_utilization_pct,
    )
