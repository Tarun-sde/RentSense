from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models import Action, Alert
from app.schemas.action import (
    ActionResponse,
    ActionCreateRequest,
    ActionCompleteRequest,
    ActionCancelRequest,
    AlertResolveRequest,
)
from app.schemas.alert import AlertResponse
from app.services.action_service import (
    create_action,
    complete_action,
    cancel_action,
    resolve_alert,
)

router = APIRouter(tags=["Actions & Alert Resolution"])


@router.get("/actions", response_model=List[ActionResponse])
def list_actions(
    status: Optional[str] = Query(None, description="Filter by status (PENDING, IN_PROGRESS, COMPLETED, CANCELLED)"),
    equipment_id: Optional[str] = Query(None, description="Filter by equipment ID"),
    action_type: Optional[str] = Query(None, description="Filter by action type (RETURN, REASSIGN, EXTEND, INVESTIGATE)"),
    priority: Optional[str] = Query(None, description="Filter by priority (CRITICAL, HIGH, MEDIUM, LOW)"),
    limit: int = Query(100, ge=1, le=500, description="Max actions to retrieve"),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """
    List operational actions across the fleet with optional filters.
    """
    query = db.query(Action)
    if status:
        query = query.filter(Action.status == status.upper())
    if equipment_id:
        query = query.filter(Action.equipment_id == equipment_id)
    if action_type:
        query = query.filter(Action.action_type == action_type.upper())
    if priority:
        query = query.filter(Action.priority == priority.upper())

    return query.order_by(Action.created_at.desc(), Action.id.desc()).offset(offset).limit(limit).all()



@router.get("/actions/{action_id}", response_model=ActionResponse)
def get_action_detail(
    action_id: int,
    db: Session = Depends(get_db),
):
    """
    Get detailed information for a single operational action.
    """
    action = db.query(Action).filter(Action.id == action_id).first()
    if not action:
        raise HTTPException(status_code=404, detail=f"Action #{action_id} not found")
    return action


@router.post("/actions", response_model=ActionResponse, status_code=201)
def create_operational_action(
    req: ActionCreateRequest,
    db: Session = Depends(get_db),
):
    """
    Create a new operational action for fleet equipment.
    """
    try:
        action = create_action(
            db=db,
            equipment_id=req.equipment_id,
            action_type=req.action_type,
            recommendation_id=req.recommendation_id,
            alert_id=req.alert_id,
            priority=req.priority or "MEDIUM",
            notes=req.notes,
            actor=req.actor or "Fleet Operator",
            payload=req.payload,
        )
        return action
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/actions/{action_id}/complete", response_model=ActionResponse)
def complete_operational_action(
    action_id: int,
    req: ActionCompleteRequest,
    db: Session = Depends(get_db),
):
    """
    Complete an action, execute database state transitions, auto-resolve alerts, and calculate realized financial savings.
    """
    try:
        action = complete_action(
            db=db,
            action_id=action_id,
            actor=req.actor or "Fleet Operator",
            notes=req.notes,
            payload=req.payload,
        )
        return action
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/actions/{action_id}/cancel", response_model=ActionResponse)
def cancel_operational_action(
    action_id: int,
    req: ActionCancelRequest,
    db: Session = Depends(get_db),
):
    """
    Cancel an active operational action.
    """
    try:
        action = cancel_action(
            db=db,
            action_id=action_id,
            actor=req.actor or "Fleet Operator",
            reason=req.reason or "Cancelled by operator",
        )
        return action
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/alerts/{alert_id}/resolve", response_model=AlertResponse)
def resolve_fleet_alert(
    alert_id: int,
    req: AlertResolveRequest,
    db: Session = Depends(get_db),
):
    """
    Manually resolve an operational alert and record audit trail history.
    """
    try:
        alert = resolve_alert(
            db=db,
            alert_id=alert_id,
            actor=req.actor or "Fleet Operator",
            resolution_notes=req.resolution_notes or "Manually resolved",
        )
        return alert
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
