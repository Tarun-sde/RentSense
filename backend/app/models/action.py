from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text, JSON
from sqlalchemy.orm import relationship
from app.db.session import Base


class Action(Base):
    __tablename__ = "actions"

    id = Column(Integer, primary_key=True, autoincrement=True, index=True)
    equipment_id = Column(String(50), ForeignKey("equipment.id", ondelete="CASCADE"), nullable=False, index=True)
    recommendation_id = Column(Integer, ForeignKey("recommendations.id", ondelete="SET NULL"), nullable=True, index=True)
    alert_id = Column(Integer, ForeignKey("alerts.id", ondelete="SET NULL"), nullable=True, index=True)
    action_type = Column(String(100), nullable=False, index=True)  # RETURN, REASSIGN, EXTEND, INVESTIGATE
    status = Column(String(50), nullable=False, default="PENDING", index=True)  # PENDING, IN_PROGRESS, COMPLETED, CANCELLED
    priority = Column(String(50), nullable=False, default="MEDIUM", index=True)  # CRITICAL, HIGH, MEDIUM, LOW
    notes = Column(Text, nullable=True)
    actor = Column(String(100), nullable=False, default="Fleet Operator")
    payload_json = Column(JSON, nullable=True)  # Target site_id, operator_id, extension_days, etc.
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False, index=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    equipment = relationship("Equipment")
    recommendation = relationship("Recommendation")
    alert = relationship("Alert")
    impact_record = relationship("ImpactRecord", back_populates="action", uselist=False, cascade="all, delete-orphan")
