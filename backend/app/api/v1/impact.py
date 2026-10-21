from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models import ImpactRecord, Action, Equipment
from app.schemas.impact import (
    ImpactResponse,
    ImpactSummaryResponse,
    ImpactDetailResponse,
)
from app.analytics.impact_engine import (
    get_fleet_impact_summary,
    calculate_action_impact_estimate,
)

router = APIRouter(tags=["Financial Impact & Savings"])


@router.get("/impact", response_model=ImpactSummaryResponse)
def get_fleet_impact(
    site_id: Optional[str] = Query(None, description="Filter summary by site ID"),
    db: Session = Depends(get_db),
):
    """
    Get fleet-wide financial impact, total realized savings, and breakdowns by action type and jobsite.
    """
    summary = get_fleet_impact_summary(db, site_id=site_id)
    return summary


@router.get("/actions/{action_id}/impact", response_model=ImpactDetailResponse)
def get_action_impact_detail(
    action_id: int,
    db: Session = Depends(get_db),
):
    """
    Get detailed financial calculation and baseline metrics for a specific operational action.
    """
    action = db.query(Action).filter(Action.id == action_id).first()
    if not action:
        raise HTTPException(status_code=404, detail=f"Action #{action_id} not found")

    equipment = db.query(Equipment).filter(Equipment.id == action.equipment_id).first()
    daily_rate = float(equipment.daily_rate or 350.0) if equipment else 350.0

    impact_rec = db.query(ImpactRecord).filter(ImpactRecord.action_id == action_id).first()
    
    if impact_rec:
        return ImpactDetailResponse(
            action_id=action.id,
            equipment_id=action.equipment_id,
            action_type=action.action_type,
            impact_type=impact_rec.impact_type,
            daily_rate=daily_rate,
            baseline_metrics=impact_rec.before_state or {},
            avoided_cost=impact_rec.estimated_amount,
            realized_savings=impact_rec.realized_amount,
            calculation_basis=impact_rec.calculation_basis,
            status=action.status,
            calculated_at=impact_rec.calculated_at,
        )
    else:
        # Calculate on the fly for pending actions
        est = calculate_action_impact_estimate(
            equipment=equipment,
            action_type=action.action_type,
        )
        return ImpactDetailResponse(
            action_id=action.id,
            equipment_id=action.equipment_id,
            action_type=action.action_type,
            impact_type=est["impact_type"],
            daily_rate=daily_rate,
            baseline_metrics={"daily_rate": daily_rate},
            avoided_cost=est["estimated_amount"],
            realized_savings=0.0,
            calculation_basis=est["calculation_basis"],
            status=action.status,
            calculated_at=action.created_at,
        )
