from datetime import datetime, timezone
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.db.session import get_db
from app.models import Equipment, Telemetry
from app.schemas.anomaly import AnomalyResponse, FleetAnomalySummary
from app.analytics.anomaly_engine import (
    evaluate_equipment_anomalies,
    evaluate_fleet_anomalies,
)
from app.services.equipment_service import get_current_rental, get_latest_telemetry, fleet_query, load_fleet

router = APIRouter(prefix="", tags=["Anomalies"])


@router.get("/anomalies", response_model=List[AnomalyResponse])
def get_fleet_anomalies(
    equipment_id: Optional[str] = Query(None, description="Filter by equipment asset ID"),
    severity: Optional[str] = Query(None, description="Filter by severity (CRITICAL, WARNING, INFO)"),
    type: Optional[str] = Query(None, description="Filter by anomaly type (e.g. LOW_UTILIZATION, EXCESSIVE_IDLE)"),
    db: Session = Depends(get_db),
):
    """
    Retrieve deterministic anomaly detection results across the fleet.
    Evaluates operational rules (Excessive Idle, Zero Runtime, Missing Assignment, Overdue, Low Utilization).
    """
    now = datetime.now(timezone.utc)

    if equipment_id:
        equipment = next(iter(load_fleet(fleet_query(db).filter(Equipment.id == equipment_id))), None)
        if not equipment:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Equipment with ID '{equipment_id}' not found",
            )
        latest_tel = get_latest_telemetry(equipment)
        current_rent = get_current_rental(equipment)
        anomalies = evaluate_equipment_anomalies(
            equipment=equipment,
            rental=current_rent,
            latest_telemetry=latest_tel,
            now=now,
        )
    else:
        anomalies = evaluate_fleet_anomalies(db, now=now)

    # Apply filters
    if severity:
        anomalies = [a for a in anomalies if a.severity.upper() == severity.upper()]
    if type:
        anomalies = [a for a in anomalies if a.anomaly_type.upper() == type.upper()]

    return [
        AnomalyResponse(
            equipment_id=a.equipment_id,
            anomaly_type=a.anomaly_type,
            anomaly_score=a.anomaly_score,
            severity=a.severity,
            explanation=a.explanation,
            supporting_signals=a.supporting_signals,
            recommended_action_category=a.recommended_action_category,
            detected_at=a.detected_at,
        )
        for a in anomalies
    ]


@router.get("/equipment/{id}/anomalies", response_model=List[AnomalyResponse])
def get_equipment_anomalies(
    id: str,
    db: Session = Depends(get_db),
):
    """
    Retrieve current active anomaly detection analysis for a specific equipment asset.
    """
    equipment = next(iter(load_fleet(fleet_query(db).filter(Equipment.id == id))), None)
    if not equipment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Equipment with ID '{id}' not found",
        )

    latest_tel = get_latest_telemetry(equipment)
    current_rent = get_current_rental(equipment)
    anomalies = evaluate_equipment_anomalies(
        equipment=equipment,
        rental=current_rent,
        latest_telemetry=latest_tel,
        now=datetime.now(timezone.utc),
    )

    return [
        AnomalyResponse(
            equipment_id=a.equipment_id,
            anomaly_type=a.anomaly_type,
            anomaly_score=a.anomaly_score,
            severity=a.severity,
            explanation=a.explanation,
            supporting_signals=a.supporting_signals,
            recommended_action_category=a.recommended_action_category,
            detected_at=a.detected_at,
        )
        for a in anomalies
    ]
