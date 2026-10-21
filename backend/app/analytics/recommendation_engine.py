from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.models import Equipment, Rental, Telemetry, Recommendation, Site
from app.analytics.anomaly_engine import AnomalyResult, evaluate_equipment_anomalies
from app.services.equipment_service import get_current_rental, get_latest_telemetry, fleet_query, load_fleet


@dataclass
class RecommendationResult:
    equipment_id: str
    recommendation_type: str  # RETURN, REASSIGN, EXTEND, INVESTIGATE
    priority: str  # CRITICAL, HIGH, MEDIUM, LOW
    explanation: str
    action: str
    confidence: float = 0.90
    estimated_impact: Dict[str, Any] = field(default_factory=dict)
    supporting_signals: Dict[str, Any] = field(default_factory=dict)
    target_site_id: Optional[str] = None
    target_site_name: Optional[str] = None
    status: str = "PENDING"
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "equipment_id": self.equipment_id,
            "recommendation_type": self.recommendation_type,
            "priority": self.priority,
            "explanation": self.explanation,
            "action": self.action,
            "confidence": round(self.confidence, 4),
            "estimated_impact": self.estimated_impact,
            "supporting_signals": self.supporting_signals,
            "target_site_id": self.target_site_id,
            "target_site_name": self.target_site_name,
            "status": self.status,
            "created_at": self.created_at.isoformat(),
        }


def calculate_idle_reassignment_impact(daily_rate: float, idle_hours: float) -> Dict[str, Any]:
    """Calculate deterministic avoided standby cost from reassigning or returning an idle asset."""
    # Assuming standard 3-day recovery window for idle reallocations
    estimated_days = max(1.0, round(idle_hours / 8.0, 1))
    avoided_cost = round(estimated_days * daily_rate, 2)
    return {
        "impact_type": "IDLE_AVOIDANCE",
        "estimated_savings_usd": avoided_cost,
        "daily_rate": daily_rate,
        "avoidable_days": estimated_days,
        "calculation_basis": f"{estimated_days:.1f} avoidable idle days × ₹{daily_rate:,.2f}/day rate = ₹{avoided_cost:,.2f}",
    }


def calculate_overdue_return_impact(daily_rate: float, overdue_hours: float) -> Dict[str, Any]:
    """Calculate deterministic avoided surcharge cost from resolving an overdue asset."""
    days_overdue = max(1.0, round(overdue_hours / 24.0, 1))
    avoided_surcharge = round(days_overdue * daily_rate, 2)
    return {
        "impact_type": "OVERDUE_SURCHARGE_AVOIDED",
        "estimated_savings_usd": avoided_surcharge,
        "daily_rate": daily_rate,
        "days_overdue": days_overdue,
        "calculation_basis": f"{days_overdue:.1f} overdue days × ₹{daily_rate:,.2f}/day surcharge = ₹{avoided_surcharge:,.2f}",
    }


def evaluate_equipment_recommendations(
    equipment: Equipment,
    rental: Optional[Rental] = None,
    latest_telemetry: Optional[Telemetry] = None,
    anomalies: Optional[List[AnomalyResult]] = None,
    now: Optional[datetime] = None,
) -> List[RecommendationResult]:
    """
    Deterministically generate operational recommendations from equipment anomalies and state.
    """
    current_time = now or datetime.now(timezone.utc)
    current_rental = rental or get_current_rental(equipment)
    active_anomalies = anomalies if anomalies is not None else evaluate_equipment_anomalies(
        equipment, rental=current_rental, latest_telemetry=latest_telemetry, now=current_time
    )

    recommendations: List[RecommendationResult] = []
    daily_rate = float(equipment.daily_rate or 18500.0)

    # 1. Evaluate OVERDUE Anomaly -> Recommend RETURN or EXTEND
    overdue_anom = next((a for a in active_anomalies if a.anomaly_type == "OVERDUE"), None)
    if overdue_anom:
        overdue_hours = float(overdue_anom.supporting_signals.get("overdue_hours", 24.0))
        impact = calculate_overdue_return_impact(daily_rate, overdue_hours)
        
        explanation = (
            f"Asset {equipment.id} is {overdue_hours:.1f} hours overdue under Contract #{current_rental.id if current_rental else 'N/A'}. "
            f"Initiating an off-rent return will immediately eliminate ongoing ₹{daily_rate:,.2f}/day surcharge penalties."
        )
        recommendations.append(
            RecommendationResult(
                equipment_id=equipment.id,
                recommendation_type="RETURN",
                priority="CRITICAL",
                explanation=explanation,
                action=f"Initiate off-rent check-in to eliminate ₹{daily_rate:,.2f}/day surcharge",
                confidence=0.95,
                estimated_impact=impact,
                supporting_signals=overdue_anom.supporting_signals,
                status="PENDING",
                created_at=current_time,
            )
        )

    # 2. Evaluate EXCESSIVE_IDLE / LOW_UTILIZATION -> Recommend REASSIGN to higher-demand site or RETURN
    idle_anom = next((a for a in active_anomalies if a.anomaly_type in ["EXCESSIVE_IDLE", "LOW_UTILIZATION"]), None)
    if idle_anom:
        idle_hours = float(idle_anom.supporting_signals.get("idle_hours", 12.0))
        util_rate = float(idle_anom.supporting_signals.get("utilization_rate", 0.10))
        impact = calculate_idle_reassignment_impact(daily_rate, idle_hours)

        # Suggest high-demand destination site (e.g. SITE-003 Kallambella if currently at SITE-001)
        current_site_id = current_rental.site_id if current_rental else None
        target_site_id = "SITE-003" if current_site_id != "SITE-003" else "SITE-002"
        target_site_name = "Kallambella Wind Energy Corridor" if target_site_id == "SITE-003" else "Navi Mumbai International Airport"

        priority = "CRITICAL" if daily_rate >= 24000 or idle_hours >= 14.0 else "HIGH"
        
        explanation = (
            f"{equipment.id} has remained rented while recording {idle_hours:.1f}h idle time "
            f"and only {util_rate * 100:.1f}% utilization. Reassigning the asset to {target_site_name} "
            f"will eliminate standby costs, saving an estimated ₹{impact['estimated_savings_usd']:,.2f}."
        )
        
        recommendations.append(
            RecommendationResult(
                equipment_id=equipment.id,
                recommendation_type="REASSIGN",
                priority=priority,
                explanation=explanation,
                action=f"Reallocate asset to {target_site_name} to recover utilization",
                confidence=0.92,
                estimated_impact=impact,
                supporting_signals=idle_anom.supporting_signals,
                target_site_id=target_site_id,
                target_site_name=target_site_name,
                status="PENDING",
                created_at=current_time,
            )
        )

    # 3. Evaluate MISSING_ASSIGNMENT -> Recommend INVESTIGATE / ASSIGN
    missing_anom = next((a for a in active_anomalies if a.anomaly_type == "MISSING_ASSIGNMENT"), None)
    if missing_anom:
        site_name = current_rental.site.name if current_rental and current_rental.site else "Navi Mumbai Logistics Staging"
        explanation = (
            f"Asset {equipment.id} is deployed at {site_name} without an assigned certified operator. "
            f"Assigning an authorized driver will unlock scheduled site operations."
        )
        recommendations.append(
            RecommendationResult(
                equipment_id=equipment.id,
                recommendation_type="INVESTIGATE",
                priority="HIGH",
                explanation=explanation,
                action="Assign certified equipment operator to active deployment",
                confidence=0.88,
                estimated_impact={
                    "impact_type": "UTILIZATION_RECOVERY",
                    "estimated_savings_usd": round(daily_rate * 2.0, 2),
                    "daily_rate": daily_rate,
                    "calculation_basis": f"2 days deployment recovery × ₹{daily_rate:,.2f}/day = ₹{daily_rate * 2.0:,.2f}",
                },
                supporting_signals=missing_anom.supporting_signals,
                status="PENDING",
                created_at=current_time,
            )
        )

    # 4. Evaluate ZERO_RUNTIME -> Recommend INVESTIGATE
    zero_anom = next((a for a in active_anomalies if a.anomaly_type == "ZERO_RUNTIME"), None)
    if zero_anom:
        explanation = (
            f"Asset {equipment.id} is checked out under Contract #{current_rental.id if current_rental else 'N/A'} "
            f"but shows 0.0h recorded runtime. Inspect jobsite staging area to verify telemetry sensors and site start date."
        )
        recommendations.append(
            RecommendationResult(
                equipment_id=equipment.id,
                recommendation_type="INVESTIGATE",
                priority="MEDIUM",
                explanation=explanation,
                action="Inspect jobsite staging area and verify telemetry sensor connection",
                confidence=0.85,
                estimated_impact={
                    "impact_type": "STANDBY_PREVENTION",
                    "estimated_savings_usd": round(daily_rate * 1.5, 2),
                    "daily_rate": daily_rate,
                    "calculation_basis": f"1.5 days standby prevention × ₹{daily_rate:,.2f}/day = ₹{daily_rate * 1.5:,.2f}",
                },
                supporting_signals=zero_anom.supporting_signals,
                status="PENDING",
                created_at=current_time,
            )
        )

    # Sort recommendations by priority (CRITICAL -> HIGH -> MEDIUM -> LOW)
    priority_order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
    recommendations.sort(key=lambda r: priority_order.get(r.priority, 4))
    return recommendations


def generate_fleet_recommendations(db: Session, now: Optional[datetime] = None) -> List[RecommendationResult]:
    """
    Generate deterministic recommendations across all fleet equipment in the database.
    """
    current_time = now or datetime.now(timezone.utc)
    equipment_list = load_fleet(fleet_query(db))
    fleet_recommendations: List[RecommendationResult] = []

    for eq in equipment_list:
        latest_tel = get_latest_telemetry(eq)
        current_rent = get_current_rental(eq)
        recs = evaluate_equipment_recommendations(
            equipment=eq,
            rental=current_rent,
            latest_telemetry=latest_tel,
            now=current_time,
        )
        fleet_recommendations.extend(recs)

    priority_order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
    fleet_recommendations.sort(key=lambda r: priority_order.get(r.priority, 4))
    return fleet_recommendations


def sync_recommendations_to_db(db: Session, recommendations: List[RecommendationResult], now: Optional[datetime] = None) -> List[Recommendation]:
    """
    Persist or update generated recommendation records in the database with deduplication.
    """
    current_time = now or datetime.now(timezone.utc)
    synced = []
    if not recommendations:
        return synced
    existing_by_key = {(r.equipment_id, r.recommendation_type): r for r in db.query(Recommendation)
        .filter(Recommendation.equipment_id.in_({r.equipment_id for r in recommendations}),
                Recommendation.status == "PENDING").order_by(Recommendation.id.desc()).all()}

    for r in recommendations:
        existing = existing_by_key.get((r.equipment_id, r.recommendation_type))
        if existing:
            existing.priority = r.priority
            existing.explanation = r.explanation
            existing.action = r.action
            existing.confidence = r.confidence
            existing.estimated_impact = r.estimated_impact
            synced.append(existing)
        else:
            new_rec = Recommendation(
                equipment_id=r.equipment_id,
                recommendation_type=r.recommendation_type,
                priority=r.priority,
                explanation=r.explanation,
                action=r.action,
                confidence=r.confidence,
                estimated_impact=r.estimated_impact,
                status="PENDING",
                created_at=current_time,
            )
            db.add(new_rec)
            existing_by_key[(r.equipment_id, r.recommendation_type)] = new_rec
            synced.append(new_rec)

    db.flush()
    ids = [s.id for s in synced]
    db.commit()
    refreshed = {r.id: r for r in db.query(Recommendation).filter(Recommendation.id.in_(ids)).all()}
    return [refreshed[id] for id in ids]
