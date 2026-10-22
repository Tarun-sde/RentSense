import logging
from datetime import datetime, timezone
from typing import List, Optional
from sqlalchemy.orm import Session
from app.models import Alert, Equipment
from app.analytics.anomaly_engine import AnomalyResult
from app.services.equipment_service import get_current_rental
from app.services.notification_service import send_alert_email

logger = logging.getLogger(__name__)


def sync_equipment_alerts(
    db: Session,
    equipment_id: str,
    anomalies: List[AnomalyResult],
    now: Optional[datetime] = None,
    commit: bool = True,
) -> List[Alert]:
    """
    Synchronize detected anomalies with the alerts table using deterministic deduplication.
    - If an anomaly is currently active:
      - Updates existing OPEN alert message, severity, and metadata_json (in-place).
      - Or inserts a new Alert record if none exists.
    - If a previously OPEN alert's condition is no longer present in anomalies:
      - Resolves the alert (sets status='RESOLVED', resolved_at=now).
    - Dispatches email notification via Resend ONLY for newly created alerts (after DB commit).
    """
    current_time = now or datetime.now(timezone.utc)
    if current_time.tzinfo is None:
        current_time = current_time.replace(tzinfo=timezone.utc)

    # 1. Fetch currently open alerts for this equipment
    open_alerts = (
        db.query(Alert)
        .filter(Alert.equipment_id == equipment_id, Alert.status == "OPEN")
        .all()
    )
    open_alerts_by_type = {a.alert_type: a for a in open_alerts}

    active_anomaly_types = set()
    synced_alerts = []
    newly_created_alerts = []

    # 2. Process active anomalies
    for anomaly in anomalies:
        active_anomaly_types.add(anomaly.anomaly_type)
        if anomaly.anomaly_type in open_alerts_by_type:
            # Update existing alert (deduplication — does not re-trigger new alert email)
            existing_alert = open_alerts_by_type[anomaly.anomaly_type]
            existing_alert.message = anomaly.explanation
            existing_alert.severity = anomaly.severity
            existing_alert.metadata_json = {
                **anomaly.supporting_signals,
                "anomaly_score": anomaly.anomaly_score,
                "recommended_action": anomaly.recommended_action_category,
                "last_evaluated_at": current_time.isoformat(),
            }
            synced_alerts.append(existing_alert)
        else:
            # Insert genuinely new alert
            new_alert = Alert(
                equipment_id=equipment_id,
                alert_type=anomaly.anomaly_type,
                severity=anomaly.severity,
                message=anomaly.explanation,
                status="OPEN",
                metadata_json={
                    **anomaly.supporting_signals,
                    "anomaly_score": anomaly.anomaly_score,
                    "recommended_action": anomaly.recommended_action_category,
                },
                created_at=current_time,
                resolved_at=None,
            )
            db.add(new_alert)
            synced_alerts.append(new_alert)
            newly_created_alerts.append((new_alert, anomaly))

    # 3. Auto-resolve alerts whose condition has cleared (excluding non-anomaly system alerts)
    managed_anomaly_types = {
        "EXCESSIVE_IDLE",
        "IDLE",
        "ZERO_RUNTIME",
        "MISSING_ASSIGNMENT",
        "OVERDUE",
        "LOW_UTILIZATION",
    }
    for alert_type, open_alert in open_alerts_by_type.items():
        if alert_type in managed_anomaly_types and alert_type not in active_anomaly_types:
            open_alert.status = "RESOLVED"
            open_alert.resolved_at = current_time

    if not commit:
        db.flush()
        db.info.setdefault("pending_alert_notifications", []).extend(newly_created_alerts)
        return synced_alerts

    db.commit()
    for alert in synced_alerts:
        db.refresh(alert)

    # 4. Dispatch email notification for genuinely NEW alerts after successful DB commit
    _dispatch_alert_notifications(db, newly_created_alerts)

    return synced_alerts


def dispatch_pending_alert_notifications(db: Session) -> None:
    """Send notifications queued by a successfully committed simulator batch."""
    _dispatch_alert_notifications(db, db.info.pop("pending_alert_notifications", []))


def _dispatch_alert_notifications(db: Session, pending) -> None:
    for alert, anomaly in pending:
        try:
            equipment = db.query(Equipment).filter(Equipment.id == alert.equipment_id).first()
            rental = get_current_rental(equipment) if equipment else None
            send_alert_email(
                alert_type=alert.alert_type,
                severity=alert.severity,
                message=alert.message,
                equipment_id=alert.equipment_id,
                equipment_type=equipment.type if equipment else None,
                dealer=equipment.dealer if equipment else None,
                site_name=rental.site.name if rental and rental.site else None,
                operator_name=rental.operator.name if rental and rental.operator else None,
                anomaly_score=anomaly.anomaly_score,
                recommended_action=anomaly.recommended_action_category,
                metadata=alert.metadata_json,
                timestamp=alert.created_at,
            )
        except Exception as notify_err:
            logger.warning("[NOTIFICATION] Non-fatal deferred notification error for %s: %s", alert.equipment_id, notify_err)
