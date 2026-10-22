import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from starlette.concurrency import run_in_threadpool
from sqlalchemy.orm import Session
from sqlalchemy import desc
from app.db.session import get_db
from app.models import Equipment, Telemetry, Rental
from app.schemas.telemetry import (
    TelemetryResponse,
    TelemetryIngestRequest,
    TelemetryStreamEvent,
)
from app.services.connection_manager import connection_manager
from app.services.status_service import derive_status, calculate_utilization
from app.services.equipment_service import get_current_rental
from app.analytics.anomaly_engine import evaluate_equipment_anomalies
from app.services.alert_service import sync_equipment_alerts


logger = logging.getLogger(__name__)
router = APIRouter(prefix="", tags=["Telemetry"])


@router.post("/telemetry", response_model=TelemetryResponse, status_code=status.HTTP_201_CREATED)
async def ingest_telemetry(
    payload: TelemetryIngestRequest,
    db: Session = Depends(get_db),
):
    record, event = await run_in_threadpool(_persist_telemetry, payload, db)
    await connection_manager.broadcast("telemetry", event)
    return record


def _persist_telemetry(
    payload: TelemetryIngestRequest,
    db: Session,
    equipment: Equipment | None = None,
    commit: bool = True,
):
    """
    Ingest a real-time telemetry point for an equipment asset.
    Validates physical parameters, stores in database, recalculates derived status,
    and broadcasts the event to all active Server-Sent Event (SSE) subscribers.
    """
    equipment = equipment or db.query(Equipment).filter(Equipment.id == payload.equipment_id).first()
    if not equipment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Equipment with ID '{payload.equipment_id}' not found",
        )

    ts = payload.timestamp or datetime.now(timezone.utc)
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)

    telemetry_record = Telemetry(
        equipment_id=payload.equipment_id,
        timestamp=ts,
        latitude=payload.latitude,
        longitude=payload.longitude,
        engine_hours=payload.engine_hours,
        idle_hours=payload.idle_hours,
        fuel_pct=payload.fuel_pct,
        created_at=datetime.now(timezone.utc),
    )
    db.add(telemetry_record)
    if commit:
        db.commit()
        db.refresh(telemetry_record)
    else:
        db.flush()

    # Recalculate derived status for broadcast
    current_rental = get_current_rental(equipment)
    derived_status = derive_status(current_rental, telemetry_record, now=ts)
    utilization_rate = calculate_utilization(payload.engine_hours, payload.idle_hours)

    # Evaluate anomaly rules and synchronize deduplicated alerts
    try:
        anomalies = evaluate_equipment_anomalies(
            equipment=equipment,
            rental=current_rental,
            latest_telemetry=telemetry_record,
            now=ts,
        )
        sync_equipment_alerts(db, equipment.id, anomalies, now=ts, commit=commit)
    except Exception as e:
        db.rollback()
        if not commit:
            raise
        logger.warning(f"Failed to sync anomalies for equipment {equipment.id}: {e}")

    stream_event = TelemetryStreamEvent(
        equipment_id=payload.equipment_id,
        timestamp=ts,
        latitude=payload.latitude,
        longitude=payload.longitude,
        engine_hours=payload.engine_hours,
        idle_hours=payload.idle_hours,
        fuel_pct=payload.fuel_pct,
        utilization_rate=round(utilization_rate, 4),
        status=derived_status.value,
    )

    return TelemetryResponse.model_validate(telemetry_record), stream_event.model_dump(mode="json")


@router.get("/equipment/{id}/telemetry/latest", response_model=TelemetryResponse)
def get_latest_equipment_telemetry(
    id: str,
    db: Session = Depends(get_db),
):
    """Retrieve the single most recent telemetry record for an equipment asset."""
    equipment = db.query(Equipment).filter(Equipment.id == id).first()
    if not equipment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Equipment with ID '{id}' not found",
        )

    latest = (
        db.query(Telemetry)
        .filter(Telemetry.equipment_id == id)
        .order_by(desc(Telemetry.timestamp), Telemetry.id.desc())
        .first()
    )
    if not latest:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No telemetry records found for equipment '{id}'",
        )

    return TelemetryResponse.model_validate(latest)


@router.get("/equipment/{id}/telemetry", response_model=List[TelemetryResponse])
def get_equipment_telemetry_history(
    id: str,
    limit: int = Query(100, ge=1, le=1000, description="Max telemetry history records to return"),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """Retrieve chronologically ordered historical telemetry for an asset."""
    equipment = db.query(Equipment).filter(Equipment.id == id).first()
    if not equipment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Equipment with ID '{id}' not found",
        )

    records = (
        db.query(Telemetry)
        .filter(Telemetry.equipment_id == id)
        .order_by(desc(Telemetry.timestamp), Telemetry.id.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    return [TelemetryResponse.model_validate(r) for r in records]


async def sse_event_generator(request: Request, queue: asyncio.Queue):
    """Yields SSE events from the subscriber queue with periodic keep-alive pings."""
    try:
        # Initial comment handshake to immediately establish SSE stream
        yield ": connected\n\n"
        while True:
            if await request.is_disconnected():
                break

            try:
                # Wait for event with timeout for keepalive
                payload = await asyncio.wait_for(queue.get(), timeout=15.0)
                event_type = payload.get("type", "telemetry")
                event_data = json.dumps(payload.get("data", {}))
                yield f"event: {event_type}\ndata: {event_data}\n\n"
            except asyncio.TimeoutError:
                # Send comment keep-alive to keep connection open
                yield ": keepalive\n\n"
    except asyncio.CancelledError:
        pass
    finally:
        connection_manager.disconnect(queue)


@router.get("/telemetry/stream")
async def stream_telemetry(request: Request):
    """
    Server-Sent Events (SSE) stream endpoint.
    Broadcasts real-time telemetry events to connected Control Tower frontend clients.
    """
    queue = await connection_manager.connect()
    return StreamingResponse(
        sse_event_generator(request, queue),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
