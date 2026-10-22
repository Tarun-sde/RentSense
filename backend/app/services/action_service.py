from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any, List
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.models import Action, Recommendation, Alert, Equipment, Rental, AuditEvent, Site, Operator
from app.services.equipment_service import get_current_rental
from app.services.status_service import derive_status
from app.analytics.impact_engine import record_realized_action_savings




def create_action(
    db: Session,
    equipment_id: str,
    action_type: str,
    recommendation_id: Optional[int] = None,
    alert_id: Optional[int] = None,
    priority: str = "MEDIUM",
    notes: Optional[str] = None,
    actor: str = "Fleet Operator",
    payload: Optional[Dict[str, Any]] = None,
    now: Optional[datetime] = None,
) -> Action:
    """
    Create a new operational action and log audit trail event.
    """
    current_time = now or datetime.now(timezone.utc)
    equipment = db.query(Equipment).filter(Equipment.id == equipment_id).first()
    if not equipment:
        raise ValueError(f"Equipment with ID {equipment_id} not found")

    action_type_upper = action_type.upper()
    if action_type_upper not in ["RETURN", "REASSIGN", "EXTEND", "INVESTIGATE"]:
        raise ValueError(f"Invalid action type: {action_type}. Must be RETURN, REASSIGN, EXTEND, or INVESTIGATE.")

    action = Action(
        equipment_id=equipment_id,
        recommendation_id=recommendation_id,
        alert_id=alert_id,
        action_type=action_type_upper,
        status="PENDING",
        priority=priority.upper(),
        notes=notes,
        actor=actor,
        payload_json=payload or {},
        created_at=current_time,
    )
    db.add(action)
    db.flush()

    # Update linked recommendation if present
    if recommendation_id:
        rec = db.query(Recommendation).filter(Recommendation.id == recommendation_id).first()
        if rec and rec.status == "PENDING":
            rec.status = "IN_PROGRESS"

    # Audit event
    audit = AuditEvent(
        event_type="ACTION_CREATED",
        equipment_id=equipment_id,
        actor=actor,
        timestamp=current_time,
        metadata_json={
            "action_id": action.id,
            "action_type": action_type_upper,
            "priority": priority,
            "recommendation_id": recommendation_id,
            "notes": notes,
        },
    )
    db.add(audit)
    db.commit()
    db.refresh(action)
    return action



def complete_action(
    db: Session,
    action_id: int,
    actor: str = "Fleet Operator",
    notes: Optional[str] = None,
    payload: Optional[Dict[str, Any]] = None,
    now: Optional[datetime] = None,
) -> Action:
    """
    Execute state transitions, resolve alerts, record audit logs, and record realized savings.
    """
    current_time = now or datetime.now(timezone.utc)
    action = db.query(Action).filter(Action.id == action_id).first()
    if not action:
        raise ValueError(f"Action with ID {action_id} not found")

    if action.status == "COMPLETED":
        raise ValueError(f"Action #{action_id} is already completed")
    if action.status == "CANCELLED":
        raise ValueError(f"Cannot complete a cancelled action #{action_id}")

    equipment = db.query(Equipment).filter(Equipment.id == action.equipment_id).first()
    if not equipment:
        raise ValueError(f"Equipment {action.equipment_id} not found")

    current_rental = get_current_rental(equipment)
    action_type = action.action_type.upper()
    merged_payload = {**(action.payload_json or {}), **(payload or {})}

    # 1. State Transition based on Action Type
    if action_type == "RETURN":
        if current_rental:
            current_rental.checked_in_at = current_time
            if notes:
                current_rental.condition_notes = notes

        # Auto-resolve matching alerts
        active_alerts = db.query(Alert).filter(
            Alert.equipment_id == equipment.id,
            Alert.status == "OPEN",
        ).all()
        for al in active_alerts:
            al.status = "RESOLVED"
            al.resolved_at = current_time

        audit_type = "RETURN_COMPLETED"
        audit_note = f"Off-rent return completed for {equipment.id}"

    elif action_type == "REASSIGN":
        target_site_id = merged_payload.get("target_site_id") or "SITE-003"
        target_operator_id = merged_payload.get("target_operator_id")

        if current_rental:
            current_rental.site_id = target_site_id
            if target_operator_id:
                current_rental.operator_id = target_operator_id

        active_alerts = db.query(Alert).filter(
            Alert.equipment_id == equipment.id,
            Alert.status == "OPEN",
            Alert.alert_type.in_(["EXCESSIVE_IDLE", "LOW_UTILIZATION", "MISSING_ASSIGNMENT"]),
        ).all()
        for al in active_alerts:
            al.status = "RESOLVED"
            al.resolved_at = current_time

        audit_type = "EQUIPMENT_REASSIGNED"
        audit_note = f"Reassigned {equipment.id} to site {target_site_id}"

    elif action_type == "EXTEND":
        ext_days = int(merged_payload.get("extension_days", 7))
        if current_rental and current_rental.due_at:
            current_rental.due_at = current_rental.due_at + timedelta(days=ext_days)
        elif current_rental:
            current_rental.due_at = current_time + timedelta(days=ext_days)

        active_alerts = db.query(Alert).filter(
            Alert.equipment_id == equipment.id,
            Alert.status == "OPEN",
            Alert.alert_type.in_(["OVERDUE", "DUE_SOON"]),
        ).all()
        for al in active_alerts:
            al.status = "RESOLVED"
            al.resolved_at = current_time

        audit_type = "RENTAL_EXTENDED"
        audit_note = f"Extended rental for {equipment.id} by {ext_days} days"

    else:  # INVESTIGATE
        target_operator_id = merged_payload.get("target_operator_id") or "OP-001"
        if current_rental and not current_rental.operator_id:
            current_rental.operator_id = target_operator_id

        active_alerts = db.query(Alert).filter(
            Alert.equipment_id == equipment.id,
            Alert.status == "OPEN",
        ).all()
        for al in active_alerts:
            al.status = "RESOLVED"
            al.resolved_at = current_time

        audit_type = "INVESTIGATION_COMPLETED"
        audit_note = f"Investigation concluded for {equipment.id}: {notes or 'Operational checks completed'}"

    # 2. Mark Action COMPLETED
    action.status = "COMPLETED"
    action.completed_at = current_time
    if notes:
        action.notes = notes
    if actor:
        action.actor = actor

    # 3. Update associated Recommendation
    if action.recommendation_id:
        rec = db.query(Recommendation).filter(Recommendation.id == action.recommendation_id).first()
        if rec:
            rec.status = "COMPLETED"
            rec.resolved_at = current_time

    # 4. Record Audit Event
    audit = AuditEvent(
        event_type=audit_type,
        equipment_id=equipment.id,
        actor=actor,
        timestamp=current_time,
        metadata_json={
            "action_id": action.id,
            "action_type": action_type,
            "notes": notes,
            "detail": audit_note,
        },
    )
    db.add(audit)

    # 5. Calculate and Record Realized Financial Savings!
    record_realized_action_savings(
        db=db,
        action=action,
        equipment=equipment,
        rental=current_rental,
        payload=merged_payload,
        now=current_time,
    )

    db.commit()
    db.refresh(action)
    return action


def cancel_action(
    db: Session,
    action_id: int,
    actor: str = "Fleet Operator",
    reason: Optional[str] = "Cancelled by operator",
    now: Optional[datetime] = None,
) -> Action:
    """
    Cancel a pending or in-progress action.
    """
    current_time = now or datetime.now(timezone.utc)
    action = db.query(Action).filter(Action.id == action_id).first()
    if not action:
        raise ValueError(f"Action #{action_id} not found")

    if action.status == "COMPLETED":
        raise ValueError("Cannot cancel an already completed action")

    action.status = "CANCELLED"
    action.notes = f"Cancelled: {reason}"

    # Revert recommendation if linked
    if action.recommendation_id:
        rec = db.query(Recommendation).filter(Recommendation.id == action.recommendation_id).first()
        if rec and rec.status == "IN_PROGRESS":
            rec.status = "PENDING"

    audit = AuditEvent(
        event_type="ACTION_CANCELLED",
        equipment_id=action.equipment_id,
        actor=actor,
        timestamp=current_time,
        metadata_json={"action_id": action.id, "reason": reason},
    )
    db.add(audit)
    db.commit()
    db.refresh(action)
    return action


def resolve_alert(
    db: Session,
    alert_id: int,
    actor: str = "Fleet Operator",
    resolution_notes: Optional[str] = "Manually resolved by operator",
    now: Optional[datetime] = None,
) -> Alert:
    """
    Manually resolve an alert and record audit event.
    """
    current_time = now or datetime.now(timezone.utc)
    alert = db.query(Alert).filter(Alert.id == alert_id).first()
    if not alert:
        raise ValueError(f"Alert #{alert_id} not found")

    alert.status = "RESOLVED"
    alert.resolved_at = current_time

    audit = AuditEvent(
        event_type="ALERT_RESOLVED",
        equipment_id=alert.equipment_id,
        actor=actor,
        timestamp=current_time,
        metadata_json={
            "alert_id": alert.id,
            "alert_type": alert.alert_type,
            "resolution_notes": resolution_notes,
        },
    )
    db.add(audit)
    db.commit()
    db.refresh(alert)
    return alert
