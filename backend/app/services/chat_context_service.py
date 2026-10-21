"""
Optimized Live Fleet Context Service for RentSense AI Chatbot.
Uses smart intent routing, targeted asset queries, and compact formatting
to minimize DB overhead and reduce LLM token processing latency.
"""
import re
from datetime import datetime, timezone
from typing import Dict, Any
from sqlalchemy.orm import Session

from app.models import Equipment, Alert, Recommendation
from app.services.status_service import derive_status, calculate_utilization

from app.services.equipment_service import fleet_query, load_fleet, get_current_rental, get_latest_telemetry

# Regex to detect asset IDs mentioned in query (e.g. EQX1001, EQX-TEST-01)
ASSET_ID_PATTERN = re.compile(r"\b(EQX[0-9A-Z_-]+)\b", re.IGNORECASE)

# Keywords indicating purely general/help questions that do not require live fleet database queries
GENERAL_HELP_PATTERNS = [
    r"\bhow (?:do|can) (?:i|we)\b",
    r"\bwhat does (?:active|idle|due_soon|overdue|unassigned|returned) mean\b",
    r"\bhow is (?:the )?anomaly score\b",
    r"\bhow does (?:the )?forecast\b",
    r"\bhow does (?:the )?anomaly\b",
    r"\bwhat (?:is|are) (?:the )?status (?:definitions|meanings)\b",
    r"\bwhat does the (?:impact|forecast|dashboard|actions|scan) page\b",
    r"\bwhat is rentsense\b",
    r"\bhow (?:is|are) avoided costs?\b",
    r"\bwhat should (?:i|we) do (?:about|for) (?:an )?overdue\b",
]
GENERAL_HELP_REGEX = re.compile("|".join(GENERAL_HELP_PATTERNS), re.IGNORECASE)


def detect_query_intent(user_query: str) -> Dict[str, Any]:
    """
    Classify query intent to fetch only the strictly required data.
    Returns:
      - 'intent': 'ASSET' | 'HELP' | 'FLEET'
      - 'target_asset_ids': List[str]
    """
    query_clean = user_query.strip()
    asset_matches = ASSET_ID_PATTERN.findall(query_clean)
    if asset_matches:
        # Normalize to uppercase unique list
        unique_assets = list(dict.fromkeys([a.upper() for a in asset_matches]))
        return {"intent": "ASSET", "target_asset_ids": unique_assets}

    if GENERAL_HELP_REGEX.search(query_clean) and not any(k in query_clean.lower() for k in ["right now", "currently", "today", "our fleet"]):
        return {"intent": "HELP", "target_asset_ids": []}

    return {"intent": "FLEET", "target_asset_ids": []}


def assemble_live_fleet_context(db: Session, user_query: str = "") -> str:
    """
    Assemble a lean, high-signal snapshot of live fleet data tailored to the query intent.
    Minimizes database query latency and avoids token bloat.
    """
    now = datetime.now(timezone.utc)
    now_str = now.strftime("%Y-%m-%d %H:%M:%S UTC")

    intent_info = detect_query_intent(user_query)
    intent = intent_info["intent"]
    target_assets = intent_info["target_asset_ids"]

    # -------------------------------------------------------------------------
    # INTENT: Pure General Help / Conceptual Q&A
    # -------------------------------------------------------------------------
    if intent == "HELP":
        return f"""[LIVE FLEET STATUS AS OF {now_str}]:
Fleet surveillance active. Query is an application how-to / conceptual question.
Refer to SECTION 2 (GENERAL APP KNOWLEDGE BASE) for authoritative platform behavior."""

    # -------------------------------------------------------------------------
    # INTENT: Targeted Asset Diagnostic (Single or specific machines)
    # -------------------------------------------------------------------------
    if intent == "ASSET":
        target_id = target_assets[0]
        eq = next(iter(load_fleet(fleet_query(db).filter(Equipment.id == target_id))), None)

        if not eq:
            return f"""[TARGETED ASSET LOOKUP AS OF {now_str}]:
Asset ID '{target_id}' was not found in the RentSense fleet database."""

        # Fetch latest telemetry and active rental
        latest_telem = get_latest_telemetry(eq)
        active_rental = get_current_rental(eq)
        status = derive_status(active_rental, latest_telem, now=now).value

        # Open alerts for this asset
        open_alerts = (
            db.query(Alert)
            .filter(Alert.equipment_id == eq.id, Alert.status == "OPEN")
            .all()
        )
        pending_recs = (
            db.query(Recommendation)
            .filter(Recommendation.equipment_id == eq.id, Recommendation.status == "PENDING")
            .all()
        )

        site_name = active_rental.site.name if (active_rental and active_rental.site) else "Depot Yard (Unassigned)"
        operator_name = active_rental.operator.name if (active_rental and active_rental.operator) else "None"
        due_str = active_rental.due_at.strftime("%Y-%m-%d %H:%M UTC") if (active_rental and active_rental.due_at) else "N/A"
        eng_h = f"{latest_telem.engine_hours:.1f}h" if latest_telem else "0.0h"
        idle_h = f"{latest_telem.idle_hours:.1f}h" if latest_telem else "0.0h"
        fuel = f"{latest_telem.fuel_pct:.0f}%" if latest_telem else "N/A"
        util = (
            f"{calculate_utilization(latest_telem.engine_hours, latest_telem.idle_hours) * 100:.1f}%"
            if latest_telem and latest_telem.engine_hours > 0
            else "0.0%"
        )

        alert_lines = [
            f"  * Alert #{a.id} [{a.severity}] {a.alert_type} (Score: {a.metadata_json.get('anomaly_score', 'N/A') if a.metadata_json else 'N/A'}): {a.message}"
            for a in open_alerts
        ]
        rec_lines = [
            f"  * Rec #{r.id} [{r.priority}] {r.recommendation_type} ({r.action}): {r.explanation}"
            for r in pending_recs
        ]

        return f"""[TARGETED ASSET DIAGNOSTIC: {eq.id} ({now_str})]:
- Type: {eq.type} | Dealer: {eq.dealer} | Daily Rate: ${eq.daily_rate:.2f}/day
- Status: {status} | Site: {site_name} | Operator: {operator_name} | Due: {due_str}
- Telemetry: Engine={eng_h}, Idle={idle_h}, Utilization={util}, Fuel={fuel}
- Open Alerts ({len(open_alerts)}):
{chr(10).join(alert_lines) if alert_lines else '  * None (Asset healthy)'}
- Pending Recommendations ({len(pending_recs)}):
{chr(10).join(rec_lines) if rec_lines else '  * None'}"""

    # -------------------------------------------------------------------------
    # INTENT: Full Fleet Overview (KPIs, Active Roster, Open Alerts)
    # -------------------------------------------------------------------------
    equipment_list = load_fleet(fleet_query(db))

    # Batch query open alerts
    open_alerts = (
        db.query(Alert)
        .filter(Alert.status == "OPEN")
        .order_by(Alert.severity.desc())
        .all()
    )
    alerts_by_eq: Dict[str, List[Alert]] = {}
    for a in open_alerts:
        alerts_by_eq.setdefault(a.equipment_id, []).append(a)

    status_counts = {"ACTIVE": 0, "IDLE": 0, "DUE_SOON": 0, "OVERDUE": 0, "UNASSIGNED": 0}
    roster_lines = []

    for eq in equipment_list:
        active_rental = get_current_rental(eq)
        telem = get_latest_telemetry(eq)
        status_val = derive_status(active_rental, telem, now=now).value
        status_counts[status_val] = status_counts.get(status_val, 0) + 1

        site_name = active_rental.site.name if (active_rental and active_rental.site) else "Yard (Unassigned)"
        eng_h = f"{telem.engine_hours:.1f}h" if telem else "0.0h"
        idle_h = f"{telem.idle_hours:.1f}h" if telem else "0.0h"

        eq_alerts = alerts_by_eq.get(eq.id, [])
        alert_tag = f" [Alert: {eq_alerts[0].alert_type} ({eq_alerts[0].severity})]" if eq_alerts else ""

        roster_lines.append(
            f"- {eq.id} ({eq.type}): Status={status_val}, Site={site_name}, Engine={eng_h}, Idle={idle_h}{alert_tag}"
        )


    return f"""[LIVE FLEET SNAPSHOT AS OF {now_str}]:
1. FLEET STATUS COUNTS: Total={len(equipment_list)}, Active={status_counts['ACTIVE']}, Idle={status_counts['IDLE']}, DueSoon={status_counts['DUE_SOON']}, Overdue={status_counts['OVERDUE']}, Unassigned={status_counts['UNASSIGNED']}
2. LIVE ROSTER:
{chr(10).join(roster_lines)}
3. OPEN ALERTS ({len(open_alerts)} TOTAL):
{chr(10).join([f"- Alert #{a.id} [{a.severity}] on {a.equipment_id}: {a.alert_type} - {a.message}" for a in open_alerts]) if open_alerts else '- None'}"""
