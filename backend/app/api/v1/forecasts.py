from datetime import datetime, timezone
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.db.session import get_db
from app.models import Forecast, Site
from app.schemas.forecast import ForecastResponse, ForecastFleetSummary
from app.analytics.forecasting import (
    generate_demand_forecasts,
)

router = APIRouter(prefix="", tags=["Forecasts"])


@router.get("/forecasts", response_model=List[ForecastResponse])
def get_demand_forecasts(
    site_id: Optional[str] = Query(None, description="Filter forecast by site ID"),
    equipment_type: Optional[str] = Query(None, description="Filter forecast by equipment type"),
    horizon_weeks: int = Query(4, ge=1, le=12, description="Number of future weeks to forecast"),
    db: Session = Depends(get_db),
):
    """
    Retrieve deterministic equipment demand forecasts by site and category.
    Calculates 3-week Weighted Moving Average (WMA), backtest MAE error, and confidence.
    """
    now = datetime.now(timezone.utc)
    forecast_records = generate_demand_forecasts(
        db=db,
        site_id=site_id,
        equipment_type=equipment_type,
        horizon_weeks=horizon_weeks,
        now=now,
    )

    # Return response records
    responses = []
    for idx, f in enumerate(forecast_records):
        responses.append(
            ForecastResponse(
                id=idx + 1,
                site_id=f.site_id,
                site_name=f.site_name,
                equipment_type=f.equipment_type,
                forecast_date=f.forecast_date,
                predicted_units=f.predicted_units,
                confidence=f.confidence,
                backtest_error=f.backtest_error,
                drivers=f.drivers,
                explanation=f.explanation,
                created_at=f.created_at,
            )
        )
    return responses


@router.get("/forecasts/summary", response_model=ForecastFleetSummary)
def get_forecast_summary(
    site_id: Optional[str] = Query(None, description="Filter forecast by site ID"),
    horizon_weeks: int = Query(4, ge=1, le=12),
    db: Session = Depends(get_db),
):
    """
    Retrieve aggregated fleet demand forecast summary and average confidence.
    """
    now = datetime.now(timezone.utc)
    forecast_records = generate_demand_forecasts(
        db=db,
        site_id=site_id,
        horizon_weeks=horizon_weeks,
        now=now,
    )

    total_units = sum(f.predicted_units for f in forecast_records)
    avg_conf = sum(f.confidence for f in forecast_records) / max(1, len(forecast_records))
    valid_errors = [f.backtest_error for f in forecast_records if f.backtest_error is not None]
    avg_error = sum(valid_errors) / max(1, len(valid_errors)) if valid_errors else None

    responses = [
        ForecastResponse(
            id=idx + 1,
            site_id=f.site_id,
            site_name=f.site_name,
            equipment_type=f.equipment_type,
            forecast_date=f.forecast_date,
            predicted_units=f.predicted_units,
            confidence=f.confidence,
            backtest_error=f.backtest_error,
            drivers=f.drivers,
            explanation=f.explanation,
            created_at=f.created_at,
        )
        for idx, f in enumerate(forecast_records)
    ]

    return ForecastFleetSummary(
        total_forecasted_units=round(total_units, 2),
        avg_confidence=round(avg_conf, 4),
        avg_backtest_error=round(avg_error, 4) if avg_error is not None else None,
        horizon_weeks=horizon_weeks,
        forecasts=responses,
    )
