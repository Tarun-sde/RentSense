from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.models import ImpactRecord, Action, Equipment, Rental, Site


def calculate_action_impact_estimate(
    equipment: Equipment,
    action_type: str,
    rental: Optional[Rental] = None,
    telemetry_idle_hours: float = 0.0,
    overdue_hours: float = 0.0,
) -> Dict[str, Any]:
    """
    Calculate deterministic estimated financial impact before an action is executed.
    """
    daily_rate = float(equipment.daily_rate or 350.0)
    
    if action_type == "RETURN":
        if overdue_hours > 0:
            days = max(1.0, round(overdue_hours / 24.0, 1))
            amount = round(days * daily_rate, 2)
            impact_type = "OVERDUE_SURCHARGE_AVOIDED"
            basis = f"{days:.1f} overdue days avoided × ₹{daily_rate:,.2f}/day surcharge = ₹{amount:,.2f}"
        else:
            # Unused rental days
            days = 3.0
            amount = round(days * daily_rate, 2)
            impact_type = "EARLY_RETURN"
            basis = f"{days:.1f} unused contract days × ₹{daily_rate:,.2f}/day rate = ₹{amount:,.2f}"
    elif action_type == "REASSIGN":
        idle_days = max(1.0, round(telemetry_idle_hours / 8.0, 1)) if telemetry_idle_hours > 0 else 3.0
        amount = round(idle_days * daily_rate, 2)
        impact_type = "IDLE_AVOIDANCE"
        basis = f"{idle_days:.1f} avoidable idle days × ₹{daily_rate:,.2f}/day rate = ₹{amount:,.2f}"
    elif action_type == "EXTEND":
        extension_days = 7.0
        # Extends contract avoiding immediate emergency re-rental premium (~25% buffer)
        amount = round(extension_days * daily_rate * 0.25, 2)
        impact_type = "RECONTRACTING_PREMIUM_AVOIDED"
        basis = f"{extension_days:.1f} extension days × ₹{daily_rate:,.2f}/day × 25% avoided re-dispatch overhead = ₹{amount:,.2f}"
    else:  # INVESTIGATE
        amount = round(daily_rate * 1.5, 2)
        impact_type = "UTILIZATION_RECOVERY"
        basis = f"1.5 days deployment recovery × ₹{daily_rate:,.2f}/day rate = ₹{amount:,.2f}"

    return {
        "impact_type": impact_type,
        "estimated_amount": max(0.0, amount),
        "daily_rate": daily_rate,
        "calculation_basis": basis,
        "currency": "INR",
    }


def record_realized_action_savings(
    db: Session,
    action: Action,
    equipment: Equipment,
    rental: Optional[Rental] = None,
    payload: Optional[Dict[str, Any]] = None,
    now: Optional[datetime] = None,
    commit: bool = True,
) -> ImpactRecord:
    """
    Record verified realized financial savings when an operational action transitions to COMPLETED.
    """
    current_time = now or datetime.now(timezone.utc)
    daily_rate = float(equipment.daily_rate or 18500.0)
    action_type = action.action_type.upper()
    site_id = rental.site_id if rental else (payload.get("site_id") if payload else None)

    if action_type == "RETURN":
        # Calculate days saved based on rental due date or overdue time
        if rental and rental.due_at:
            due_at = rental.due_at.replace(tzinfo=timezone.utc) if rental.due_at.tzinfo is None else rental.due_at
            if current_time > due_at:
                overdue_days = max(1.0, round((current_time - due_at).total_seconds() / 86400.0, 1))
                realized_amount = round(overdue_days * daily_rate, 2)
                impact_type = "OVERDUE_SURCHARGE_AVOIDED"
                basis = f"Resolved overdue rental: {overdue_days:.1f} days × ₹{daily_rate:,.2f}/day = ₹{realized_amount:,.2f}"
            else:
                unused_days = max(1.0, round((due_at - current_time).total_seconds() / 86400.0, 1))
                realized_amount = round(unused_days * daily_rate, 2)
                impact_type = "EARLY_RETURN"
                basis = f"Off-rent return completed early: {unused_days:.1f} unused days × ₹{daily_rate:,.2f}/day = ₹{realized_amount:,.2f}"
        else:
            realized_amount = round(2.0 * daily_rate, 2)
            impact_type = "EARLY_RETURN"
            basis = f"Standard early return savings: 2.0 days × ₹{daily_rate:,.2f}/day = ₹{realized_amount:,.2f}"

    elif action_type == "REASSIGN":
        target_site = payload.get("target_site_id", "SITE-003") if payload else "SITE-003"
        site_id = target_site
        # 3 days avoided idle standby
        realized_amount = round(3.0 * daily_rate, 2)
        impact_type = "IDLE_AVOIDANCE"
        basis = f"Reassigned asset to high-demand site ({target_site}): 3.0 avoidable standby days × ₹{daily_rate:,.2f}/day = ₹{realized_amount:,.2f}"

    elif action_type == "EXTEND":
        ext_days = float(payload.get("extension_days", 7.0)) if payload else 7.0
        realized_amount = round(ext_days * daily_rate * 0.25, 2)
        impact_type = "RECONTRACTING_PREMIUM_AVOIDED"
        basis = f"Seamlessly extended contract by {ext_days:.0f} days: Avoided re-dispatch overhead = ₹{realized_amount:,.2f}"

    else:  # INVESTIGATE
        realized_amount = round(daily_rate * 1.0, 2)
        impact_type = "UTILIZATION_RECOVERY"
        basis = f"Resolved jobsite staging anomaly: 1.0 day operational recovery × ₹{daily_rate:,.2f}/day = ₹{realized_amount:,.2f}"

    realized_amount = max(0.0, realized_amount)

    # Check if impact record already exists for this action
    existing = db.query(ImpactRecord).filter(ImpactRecord.action_id == action.id).first()
    if existing:
        existing.realized_amount = realized_amount
        existing.calculation_basis = basis
        existing.site_id = site_id
        existing.currency = "INR"
        existing.after_state = {
            "action_status": "COMPLETED",
            "completed_at": current_time.isoformat(),
            "target_site_id": site_id,
        }
        if commit:
            db.commit()
            db.refresh(existing)
        else:
            db.flush()
        return existing

    impact_rec = ImpactRecord(
        action_id=action.id,
        equipment_id=equipment.id,
        site_id=site_id,
        impact_type=impact_type,
        estimated_amount=realized_amount,
        realized_amount=realized_amount,
        currency="INR",
        calculation_basis=basis,
        before_state={
            "action_type": action_type,
            "equipment_id": equipment.id,
            "daily_rate": daily_rate,
        },
        after_state={
            "action_status": "COMPLETED",
            "completed_at": current_time.isoformat(),
            "target_site_id": site_id,
        },
        calculated_at=current_time,
    )
    db.add(impact_rec)
    if commit:
        db.commit()
        db.refresh(impact_rec)
    else:
        db.flush()
    return impact_rec


def get_fleet_impact_summary(db: Session, site_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Aggregate total realized savings, estimated impact, and breakdowns by action type, site, and equipment type.
    """
    # 1. Realized records from completed actions
    records = db.query(ImpactRecord)
    if site_id:
        records = records.filter(ImpactRecord.site_id == site_id)
    total_realized, total_estimated = records.with_entities(
        func.coalesce(func.sum(ImpactRecord.realized_amount), 0),
        func.coalesce(func.sum(ImpactRecord.estimated_amount), 0)).one()

    # Add estimated impact from open recommendations
    from app.models import Recommendation
    open_recs = db.query(func.coalesce(func.sum(
        Recommendation.estimated_impact["estimated_savings_usd"].as_float()), 0)).filter(Recommendation.status == "PENDING")
    if site_id:
        open_recs = open_recs.filter(Recommendation.equipment_id.in_(
            db.query(Rental.equipment_id).filter(Rental.site_id == site_id, Rental.checked_in_at.is_(None))))
    total_estimated += open_recs.scalar()

    # Breakdown by action type
    by_action = {label: round(amount, 2) for label, amount in records.with_entities(
        ImpactRecord.impact_type, func.sum(ImpactRecord.realized_amount)).group_by(ImpactRecord.impact_type).all()}

    # Breakdown by site
    site_label = func.coalesce(Site.name, "Central Logistics")
    by_site = {label: round(amount, 2) for label, amount in records.outerjoin(Site).with_entities(
        site_label, func.sum(ImpactRecord.realized_amount)).group_by(site_label).all()}

    # Breakdown by equipment type
    eq_type = func.coalesce(Equipment.type, "Heavy Machinery")
    by_eq_type = {label: round(amount, 2) for label, amount in records.outerjoin(Equipment).with_entities(
        eq_type, func.sum(ImpactRecord.realized_amount)).group_by(eq_type).all()}

    completed = db.query(Action).filter(Action.status == "COMPLETED")
    if site_id:
        completed = completed.filter(Action.id.in_(records.with_entities(ImpactRecord.action_id)))
    completed_actions_count = completed.count()

    return {
        "total_estimated_impact": round(total_estimated, 2),
        "total_realized_savings": round(total_realized, 2),
        "completed_actions_count": completed_actions_count,
        "savings_by_action_type": by_action,
        "savings_by_site": by_site,
        "savings_by_equipment_type": by_eq_type,
        "recent_impact_records": records.order_by(ImpactRecord.calculated_at.desc(), ImpactRecord.id.desc()).limit(100).all(),
    }
