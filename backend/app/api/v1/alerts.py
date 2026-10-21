from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.db.session import get_db
from app.models import Alert
from app.schemas.alert import AlertResponse

router = APIRouter(prefix="", tags=["Alerts"])


@router.get("/alerts", response_model=List[AlertResponse])
def get_alerts(
    severity: Optional[str] = Query(None, description="Filter by severity (CRITICAL, HIGH, MEDIUM, LOW)"),
    status_filter: Optional[str] = Query(None, alias="status", description="Filter by alert status (OPEN, RESOLVED)"),
    equipment_id: Optional[str] = Query(None, description="Filter by equipment ID"),
    type: Optional[str] = Query(None, description="Filter by alert type"),
    limit: int = Query(100, ge=1, le=500, description="Max alerts to retrieve"),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """
    Retrieve fleet operational alerts and exceptions with optional query filters.
    """
    query = db.query(Alert)

    if severity:
        query = query.filter(Alert.severity == severity.upper())
    if status_filter:
        query = query.filter(Alert.status == status_filter.upper())
    if equipment_id:
        query = query.filter(Alert.equipment_id == equipment_id)
    if type:
        query = query.filter(Alert.alert_type == type.upper())

    alerts = query.order_by(desc(Alert.created_at), Alert.id.desc()).offset(offset).limit(limit).all()
    return [AlertResponse.model_validate(a) for a in alerts]


@router.get("/alerts/{id}", response_model=AlertResponse)
def get_alert_by_id(
    id: int,
    db: Session = Depends(get_db),
):
    """
    Retrieve single alert detail by identifier.
    """
    alert = db.query(Alert).filter(Alert.id == id).first()
    if not alert:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Alert with ID {id} not found",
        )
    return AlertResponse.model_validate(alert)
