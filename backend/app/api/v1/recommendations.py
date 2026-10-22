from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models import Recommendation, Equipment
from app.schemas.recommendation import RecommendationResponse, RecommendationActionRequest
from app.schemas.action import ActionResponse
from app.analytics.recommendation_engine import (
    generate_fleet_recommendations,
    evaluate_equipment_recommendations,
    sync_recommendations_to_db,
)
from app.services.action_service import create_action
from app.services.equipment_service import fleet_query, load_fleet
from app.core.security import get_current_user

router = APIRouter(prefix="/recommendations", tags=["Recommendations"])


@router.get("", response_model=List[RecommendationResponse])
def get_recommendations(
    equipment_id: Optional[str] = Query(None, description="Filter by equipment ID"),
    priority: Optional[str] = Query(None, description="Filter by priority (CRITICAL, HIGH, MEDIUM, LOW)"),
    status: Optional[str] = Query(None, description="Filter by status (PENDING, IN_PROGRESS, COMPLETED)"),
    recommendation_type: Optional[str] = Query(None, description="Filter by type (RETURN, REASSIGN, EXTEND, INVESTIGATE)"),
    limit: int = Query(50, ge=1, le=200, description="Max recommendations to retrieve"),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """
    Get fleet recommendations. Evaluates active conditions and syncs with database.
    """
    # Deterministically generate and sync latest recommendations
    fleet_recs = generate_fleet_recommendations(db)
    sync_recommendations_to_db(db, fleet_recs)

    query = db.query(Recommendation)
    if equipment_id:
        query = query.filter(Recommendation.equipment_id == equipment_id)
    if priority:
        query = query.filter(Recommendation.priority == priority.upper())
    if status:
        query = query.filter(Recommendation.status == status.upper())
    if recommendation_type:
        query = query.filter(Recommendation.recommendation_type == recommendation_type.upper())

    return query.order_by(Recommendation.created_at.desc(), Recommendation.id.desc()).offset(offset).limit(limit).all()



@router.get("/equipment/{equipment_id}", response_model=List[RecommendationResponse])
def get_equipment_recommendations(
    equipment_id: str,
    db: Session = Depends(get_db),
):
    """
    Get active recommendations for a specific equipment asset.
    """
    equipment = next(iter(load_fleet(fleet_query(db).filter(Equipment.id == equipment_id))), None)
    if not equipment:
        raise HTTPException(status_code=404, detail=f"Equipment {equipment_id} not found")

    recs = evaluate_equipment_recommendations(equipment)
    synced = sync_recommendations_to_db(db, recs)
    return synced


@router.post("/{recommendation_id}/action", response_model=ActionResponse, status_code=201)
def trigger_action_from_recommendation(
    recommendation_id: int,
    req: RecommendationActionRequest,
    db: Session = Depends(get_db),
    _current_user=Depends(get_current_user),
):
    """
    Initiate an operational action directly from a recommendation.
    """
    rec = db.query(Recommendation).filter(Recommendation.id == recommendation_id).first()
    if not rec:
        raise HTTPException(status_code=404, detail=f"Recommendation #{recommendation_id} not found")

    action_type = req.action_type or rec.recommendation_type
    try:
        action = create_action(
            db=db,
            equipment_id=rec.equipment_id,
            action_type=action_type,
            recommendation_id=rec.id,
            priority=rec.priority,
            notes=req.notes or f"Initiated from recommendation: {rec.action}",
            actor=req.actor or "Fleet Operator",
            payload=req.payload or rec.estimated_impact,
        )
        return action
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
