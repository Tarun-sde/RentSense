from datetime import datetime, timezone
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from app.db.session import get_db
from sqlalchemy import or_, func
from app.models import Equipment, Rental
from app.schemas.equipment import EquipmentCreate, EquipmentListItem, EquipmentDetailResponse
from app.services.equipment_service import build_equipment_list_item, build_equipment_detail, fleet_query, load_fleet
from app.core.security import get_current_user

router = APIRouter(prefix="/equipment", tags=["Equipment"])


@router.get("", response_model=List[EquipmentListItem])
def list_equipment(
    search: Optional[str] = Query(None, description="Search term for ID, type, or dealer"),
    status: Optional[str] = Query(None, description="Filter by derived status (ACTIVE, IDLE, DUE_SOON, OVERDUE, UNASSIGNED)"),
    site_id: Optional[str] = Query(None, description="Filter by current assigned site ID"),
    type: Optional[str] = Query(None, description="Filter by equipment type"),
    limit: Optional[int] = Query(None, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """
    Retrieve fleet equipment assets with real-time derived operational status,
    latest telemetry, and current rental assignment details.
    """
    query = fleet_query(db)

    if type:
        query = query.filter(Equipment.type.ilike(f"%{type}%"))

    if search:
        term = search.lower()
        query = query.filter(or_(
            func.lower(Equipment.id).contains(term, autoescape=True),
            func.lower(Equipment.type).contains(term, autoescape=True),
            func.lower(Equipment.dealer).contains(term, autoescape=True),
            func.lower(Equipment.metadata_json["model"].as_string()).contains(term, autoescape=True),
        ))
    if site_id:
        query = query.filter(Rental.site_id == site_id)
    # Derived status must be filtered before slicing the result page.
    if not status:
        query = query.offset(offset)
        if limit is not None:
            query = query.limit(limit)
    equipment_records = load_fleet(query)
    results: List[EquipmentListItem] = []

    for eq in equipment_records:
        item = build_equipment_list_item(eq)

        # Apply status filter
        if status:
            if item.status.upper() != status.upper():
                continue

        results.append(item)

    return results[offset:offset + limit if limit is not None else None] if status else results


@router.post("", response_model=EquipmentDetailResponse, status_code=status.HTTP_201_CREATED)
def create_equipment(
    payload: EquipmentCreate,
    db: Session = Depends(get_db),
    _current_user=Depends(get_current_user),
):
    """
    Create a new equipment asset. Requires authentication.
    Equipment ID must be unique. QR code is automatically set to the equipment ID.
    """
    # Validate unique ID
    existing = db.query(Equipment).filter(Equipment.id == payload.id).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Equipment with ID '{payload.id}' already exists",
        )

    now = datetime.now(timezone.utc)
    metadata_json: dict = {"qr_code": payload.id}
    if payload.model:
        metadata_json["model"] = payload.model
    if payload.serial:
        metadata_json["serial"] = payload.serial

    equipment = Equipment(
        id=payload.id.upper().strip(),
        type=payload.type,
        dealer=payload.dealer,
        daily_rate=payload.daily_rate,
        metadata_json=metadata_json,
        created_at=now,
        updated_at=now,
    )
    db.add(equipment)
    db.commit()
    db.refresh(equipment)

    return build_equipment_detail(equipment)


@router.get("/{id}", response_model=EquipmentDetailResponse)
def get_equipment_detail(
    id: str,
    history_limit: int = Query(100, ge=1, le=500),
    history_offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """
    Retrieve comprehensive equipment details by ID including current rental,
    latest telemetry, recent telemetry history, full rental history, active alerts,
    and audit event timeline.
    """
    equipment = next(iter(load_fleet(fleet_query(db).filter(Equipment.id == id))), None)
    if not equipment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Equipment with ID '{id}' not found",
        )

    return build_equipment_detail(equipment, history_limit, history_offset)
