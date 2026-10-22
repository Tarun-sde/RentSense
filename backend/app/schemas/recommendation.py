from datetime import datetime
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, ConfigDict, Field


class RecommendationBase(BaseModel):
    equipment_id: str
    recommendation_type: str = Field(..., description="RETURN, REASSIGN, EXTEND, INVESTIGATE")
    priority: str = Field(..., description="CRITICAL, HIGH, MEDIUM, LOW")
    explanation: str = Field(..., description="Plain-language justification for the recommendation")
    action: str = Field(..., description="Concrete operational action suggested")
    confidence: float = Field(0.9, ge=0.0, le=1.0)
    estimated_impact: Optional[Dict[str, Any]] = None
    status: str = Field("PENDING", description="PENDING, IN_PROGRESS, COMPLETED, DISMISSED")


class RecommendationResponse(RecommendationBase):
    id: int
    created_at: datetime
    resolved_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class RecommendationActionRequest(BaseModel):
    action_type: Optional[str] = None
    notes: Optional[str] = None
    actor: Optional[str] = "Fleet Operator"
    payload: Optional[Dict[str, Any]] = None
