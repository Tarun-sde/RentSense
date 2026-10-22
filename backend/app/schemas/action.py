from datetime import datetime
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, ConfigDict, Field


class ActionBase(BaseModel):
    equipment_id: str
    recommendation_id: Optional[int] = None
    alert_id: Optional[int] = None
    action_type: str = Field(..., description="RETURN, REASSIGN, EXTEND, INVESTIGATE")
    status: str = Field("PENDING", description="PENDING, IN_PROGRESS, COMPLETED, CANCELLED")
    priority: str = Field("MEDIUM", description="CRITICAL, HIGH, MEDIUM, LOW")
    notes: Optional[str] = None
    actor: str = Field("Fleet Operator", description="Operator executing the action")
    payload_json: Optional[Dict[str, Any]] = None


class ActionCreateRequest(BaseModel):
    equipment_id: str
    action_type: str = Field(..., description="RETURN, REASSIGN, EXTEND, INVESTIGATE")
    recommendation_id: Optional[int] = None
    alert_id: Optional[int] = None
    priority: Optional[str] = "MEDIUM"
    notes: Optional[str] = None
    actor: Optional[str] = "Fleet Operator"
    payload: Optional[Dict[str, Any]] = None


class ActionCompleteRequest(BaseModel):
    notes: Optional[str] = None
    actor: Optional[str] = "Fleet Operator"
    payload: Optional[Dict[str, Any]] = None  # e.g. target site_id, operator_id, extension_days, condition_notes


class ActionCancelRequest(BaseModel):
    reason: Optional[str] = "Operator cancelled"
    actor: Optional[str] = "Fleet Operator"


class AlertResolveRequest(BaseModel):
    resolution_notes: Optional[str] = "Resolved by operator"
    actor: Optional[str] = "Fleet Operator"


class ActionResponse(ActionBase):
    id: int
    created_at: datetime
    completed_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)
