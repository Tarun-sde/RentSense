from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.models import Equipment, Rental, Telemetry
from app.services.status_service import derive_status, calculate_utilization
from app.services.equipment_service import get_current_rental, get_latest_telemetry, fleet_query, load_fleet

# Operational Threshold Constants
IDLE_HOURS_THRESHOLD = 8.0
LOW_UTILIZATION_THRESHOLD = 0.20
MIN_RUNTIME_FOR_UTILIZATION_CHECK = 1.0


@dataclass
class AnomalyResult:
    """
    Structured result representing an explainable, deterministic anomaly detection output.
    """
    equipment_id: str
    anomaly_type: str
    anomaly_score: int
    severity: str
    explanation: str
    supporting_signals: Dict[str, Any] = field(default_factory=dict)
    recommended_action_category: Optional[str] = None
    detected_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "equipment_id": self.equipment_id,
            "anomaly_type": self.anomaly_type,
            "anomaly_score": self.anomaly_score,
            "severity": self.severity,
            "explanation": self.explanation,
            "supporting_signals": self.supporting_signals,
            "recommended_action_category": self.recommended_action_category,
            "detected_at": self.detected_at.isoformat(),
        }


def map_score_to_severity(score: int) -> str:
    """
    Deterministic severity mapping based on numerical anomaly score thresholds.
    Score >= 70  -> CRITICAL
    Score 40-69  -> WARNING
    Score 1-39   -> INFO
    """
    if score >= 70:
        return "CRITICAL"
    elif score >= 40:
        return "WARNING"
    return "INFO"


# =========================================================================
# Pure Functional Anomaly Rules
# =========================================================================

def evaluate_excessive_idle(
    equipment_id: str,
    telemetry: Optional[Telemetry],
    rental: Optional[Rental],
    threshold: float = IDLE_HOURS_THRESHOLD,
    now: Optional[datetime] = None,
) -> Optional[AnomalyResult]:
    """
    Rule A: Excessive Idle Runtime.
    Flags equipment that has accumulated idle runtime exceeding operational threshold.
    """
    if not telemetry or telemetry.idle_hours is None:
        return None

    idle_hours = float(telemetry.idle_hours)
    engine_hours = float(telemetry.engine_hours) if telemetry.engine_hours is not None else 0.0

    if idle_hours > threshold:
        # Deterministic score scaling: base 45 + 5 points per hour over threshold, max 85
        overage = idle_hours - threshold
        score = min(85, int(45 + overage * 5))
        severity = map_score_to_severity(score)
        
        explanation = (
            f"Asset {equipment_id} has accumulated {idle_hours:.1f}h of idle engine time, "
            f"exceeding the acceptable operational threshold of {threshold:.1f}h "
            f"(Total engine runtime: {engine_hours:.1f}h)."
        )
        
        return AnomalyResult(
            equipment_id=equipment_id,
            anomaly_type="EXCESSIVE_IDLE",
            anomaly_score=score,
            severity=severity,
            explanation=explanation,
            supporting_signals={
                "idle_hours": idle_hours,
                "threshold_hours": threshold,
                "engine_hours": engine_hours,
                "idle_overage_hours": round(overage, 2),
            },
            recommended_action_category="REASSIGN_EQUIPMENT",
            detected_at=now or datetime.now(timezone.utc),
        )
    return None


def evaluate_zero_runtime(
    equipment_id: str,
    telemetry: Optional[Telemetry],
    rental: Optional[Rental],
    now: Optional[datetime] = None,
) -> Optional[AnomalyResult]:
    """
    Rule B: Zero Runtime While Checked Out.
    Flags assets with an active rental contract where engine runtime is effectively zero.
    """
    if not rental or rental.checked_in_at is not None:
        return None

    engine_hours = float(telemetry.engine_hours) if telemetry and telemetry.engine_hours is not None else 0.0
    
    if engine_hours < 0.1:
        score = 55
        severity = map_score_to_severity(score)
        site_name = rental.site.name if rental.site else "Assigned Jobsite"
        
        explanation = (
            f"Asset {equipment_id} is actively checked out to {site_name} "
            f"under Contract #{rental.id} but records 0.0h of active engine runtime."
        )
        
        return AnomalyResult(
            equipment_id=equipment_id,
            anomaly_type="ZERO_RUNTIME",
            anomaly_score=score,
            severity=severity,
            explanation=explanation,
            supporting_signals={
                "rental_id": rental.id,
                "engine_hours": engine_hours,
                "checked_out_at": rental.checked_out_at.isoformat() if rental.checked_out_at else None,
            },
            recommended_action_category="INVESTIGATE_DEPLOYMENT",
            detected_at=now or datetime.now(timezone.utc),
        )
    return None


def evaluate_missing_assignment(
    equipment_id: str,
    rental: Optional[Rental],
    now: Optional[datetime] = None,
) -> Optional[AnomalyResult]:
    """
    Rule C: Missing Site or Operator Assignment.
    Flags active rentals missing required certified operator or site bindings.
    """
    if not rental or rental.checked_in_at is not None:
        return None

    missing_fields = []
    if not rental.operator_id:
        missing_fields.append("operator")
    if not rental.site_id:
        missing_fields.append("site")

    if missing_fields:
        score = 65 if "operator" in missing_fields else 50
        severity = map_score_to_severity(score)
        missing_desc = " and ".join(missing_fields)
        
        explanation = (
            f"Asset {equipment_id} has an active rental (Contract #{rental.id}) "
            f"but lacks a certified {missing_desc} assignment."
        )
        
        return AnomalyResult(
            equipment_id=equipment_id,
            anomaly_type="MISSING_ASSIGNMENT",
            anomaly_score=score,
            severity=severity,
            explanation=explanation,
            supporting_signals={
                "rental_id": rental.id,
                "missing_fields": missing_fields,
                "site_id": rental.site_id,
                "operator_id": rental.operator_id,
            },
            recommended_action_category="ASSIGN_OPERATOR" if "operator" in missing_fields else "ASSIGN_SITE",
            detected_at=now or datetime.now(timezone.utc),
        )
    return None


def evaluate_overdue_rental(
    equipment_id: str,
    rental: Optional[Rental],
    daily_rate: float = 0.0,
    now: Optional[datetime] = None,
) -> Optional[AnomalyResult]:
    """
    Rule D: Overdue Rental Contract.
    Flags active rentals whose due timestamp has passed.
    """
    if not rental or rental.checked_in_at is not None or not rental.due_at:
        return None

    current_time = now or datetime.now(timezone.utc)
    due_at = rental.due_at
    if due_at.tzinfo is None:
        due_at = due_at.replace(tzinfo=timezone.utc)
    if current_time.tzinfo is None:
        current_time = current_time.replace(tzinfo=timezone.utc)

    if current_time > due_at:
        overdue_delta = current_time - due_at
        overdue_hours = overdue_delta.total_seconds() / 3600.0
        
        # Deterministic scoring: base 60 + 0.5 points per hour overdue, max 95
        score = min(95, int(60 + overdue_hours * 0.5))
        severity = map_score_to_severity(score)
        rate = rental.daily_rate or daily_rate
        
        explanation = (
            f"Rental contract #{rental.id} for {equipment_id} is {overdue_hours:.1f}h overdue "
            f"(scheduled return was {due_at.strftime('%Y-%m-%d %H:%M UTC')}). "
            f"Rate surcharge is active at ₹{rate:,.2f}/day."
        )
        
        return AnomalyResult(
            equipment_id=equipment_id,
            anomaly_type="OVERDUE",
            anomaly_score=score,
            severity=severity,
            explanation=explanation,
            supporting_signals={
                "rental_id": rental.id,
                "due_at": due_at.isoformat(),
                "overdue_hours": round(overdue_hours, 1),
                "daily_rate": rate,
            },
            recommended_action_category="INITIATE_RETURN",
            detected_at=current_time,
        )
    return None


def evaluate_low_utilization(
    equipment_id: str,
    telemetry: Optional[Telemetry],
    rental: Optional[Rental],
    threshold: float = LOW_UTILIZATION_THRESHOLD,
    now: Optional[datetime] = None,
) -> Optional[AnomalyResult]:
    """
    Rule E: Low Utilization Rate.
    Flags active rentals where utilization ((engine - idle) / engine) falls below 20%.
    """
    if not rental or rental.checked_in_at is not None or not telemetry:
        return None

    engine_hours = float(telemetry.engine_hours) if telemetry.engine_hours is not None else 0.0
    idle_hours = float(telemetry.idle_hours) if telemetry.idle_hours is not None else 0.0

    if engine_hours < MIN_RUNTIME_FOR_UTILIZATION_CHECK:
        return None

    util_rate = calculate_utilization(engine_hours, idle_hours)
    active_hours = max(0.0, engine_hours - idle_hours)

    if util_rate < threshold:
        # Score calculation: base 50 + points proportional to distance from threshold
        util_gap = threshold - util_rate
        score = min(90, int(50 + (util_gap / threshold) * 35))
        severity = map_score_to_severity(score)
        
        explanation = (
            f"Asset {equipment_id} has an active utilization rate of {util_rate * 100:.1f}% "
            f"({active_hours:.1f}h active out of {engine_hours:.1f}h engine runtime), "
            f"falling below the {threshold * 100:.0f}% operational threshold."
        )
        
        return AnomalyResult(
            equipment_id=equipment_id,
            anomaly_type="LOW_UTILIZATION",
            anomaly_score=score,
            severity=severity,
            explanation=explanation,
            supporting_signals={
                "utilization_rate": round(util_rate, 4),
                "threshold": threshold,
                "active_hours": round(active_hours, 2),
                "engine_hours": engine_hours,
                "idle_hours": idle_hours,
            },
            recommended_action_category="REASSIGN_EQUIPMENT",
            detected_at=now or datetime.now(timezone.utc),
        )
    return None


# =========================================================================
# Compound Asset Anomaly Evaluation Pipeline
# =========================================================================

def evaluate_equipment_anomalies(
    equipment: Equipment,
    rental: Optional[Rental] = None,
    latest_telemetry: Optional[Telemetry] = None,
    now: Optional[datetime] = None,
) -> List[AnomalyResult]:
    """
    Evaluate all 5 deterministic anomaly rules against an equipment asset.
    Returns a list of detected AnomalyResult items sorted by anomaly_score descending.
    """
    current_time = now or datetime.now(timezone.utc)
    current_rental = rental or get_current_rental(equipment)
    tel = latest_telemetry or get_latest_telemetry(equipment)
    
    anomalies: List[AnomalyResult] = []

    # 1. Rule A: Excessive Idle
    res_idle = evaluate_excessive_idle(equipment.id, tel, current_rental, now=current_time)

    if res_idle:
        anomalies.append(res_idle)

    # 2. Rule B: Zero Runtime
    res_zero = evaluate_zero_runtime(equipment.id, tel, current_rental, now=current_time)
    if res_zero:
        anomalies.append(res_zero)

    # 3. Rule C: Missing Assignment
    res_missing = evaluate_missing_assignment(equipment.id, current_rental, now=current_time)
    if res_missing:
        anomalies.append(res_missing)

    # 4. Rule D: Overdue Rental
    res_overdue = evaluate_overdue_rental(equipment.id, current_rental, equipment.daily_rate, now=current_time)
    if res_overdue:
        anomalies.append(res_overdue)

    # 5. Rule E: Low Utilization
    res_util = evaluate_low_utilization(equipment.id, tel, current_rental, now=current_time)
    if res_util:
        anomalies.append(res_util)


    # Apply deterministic multi-signal compound boost if multiple distinct anomaly signals coincide
    if len(anomalies) > 1:
        multi_signal_count = len(anomalies)
        boost = min(15, (multi_signal_count - 1) * 5)
        for anom in anomalies:
            anom.anomaly_score = min(100, anom.anomaly_score + boost)
            anom.severity = map_score_to_severity(anom.anomaly_score)

    anomalies.sort(key=lambda x: x.anomaly_score, reverse=True)
    return anomalies


def evaluate_fleet_anomalies(db: Session, now: Optional[datetime] = None) -> List[AnomalyResult]:
    """
    Evaluate anomaly rules across the entire fleet in the database.
    """
    equipment_list = load_fleet(fleet_query(db))
    fleet_anomalies: List[AnomalyResult] = []

    for eq in equipment_list:
        latest_tel = get_latest_telemetry(eq)
        current_rent = get_current_rental(eq)
        eq_anomalies = evaluate_equipment_anomalies(
            equipment=eq,
            rental=current_rent,
            latest_telemetry=latest_tel,
            now=now,
        )
        fleet_anomalies.extend(eq_anomalies)

    fleet_anomalies.sort(key=lambda x: x.anomaly_score, reverse=True)
    return fleet_anomalies
