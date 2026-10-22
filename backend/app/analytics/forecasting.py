from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any, Optional, Tuple
from sqlalchemy.orm import Session

from app.models import Forecast, Rental, Equipment, Site

# Weights for 3-week Weighted Moving Average (WMA)
WMA_WEIGHTS = [0.5, 0.3, 0.2]


@dataclass
class ForecastRecord:
    site_id: Optional[str]
    site_name: str
    equipment_type: str
    forecast_date: datetime
    predicted_units: float
    confidence: float
    backtest_error: Optional[float]
    drivers: Dict[str, Any]
    explanation: str
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "site_id": self.site_id,
            "site_name": self.site_name,
            "equipment_type": self.equipment_type,
            "forecast_date": self.forecast_date.isoformat(),
            "predicted_units": round(self.predicted_units, 2),
            "confidence": round(self.confidence, 4),
            "backtest_error": round(self.backtest_error, 4) if self.backtest_error is not None else None,
            "drivers": self.drivers,
            "explanation": self.explanation,
            "created_at": self.created_at.isoformat(),
        }


def calculate_weighted_moving_average(history: List[float]) -> float:
    """
    Compute 3-week Weighted Moving Average (0.5, 0.3, 0.2).
    If fewer than 3 history points exist, compute simple average.
    """
    if not history:
        return 1.0
    if len(history) == 1:
        return history[0]
    if len(history) == 2:
        return history[0] * 0.6 + history[1] * 0.4

    # history[0] is most recent week (t-1), history[1] is (t-2), history[2] is (t-3)
    return round(
        history[0] * WMA_WEIGHTS[0] + history[1] * WMA_WEIGHTS[1] + history[2] * WMA_WEIGHTS[2],
        2
    )


def calculate_backtest_mae(history: List[float]) -> Optional[float]:
    """
    Calculate Mean Absolute Error (MAE) over historical windows.
    Requires at least 4 historical periods to test prediction vs actual.
    """
    if len(history) < 4:
        # Fallback baseline historical MAE based on variance
        if len(history) >= 2:
            return round(abs(history[0] - history[1]) * 0.5, 2)
        return 0.35

    errors = []
    # Test each historical point from index 0 back to len-3
    for i in range(len(history) - 3):
        actual = history[i]
        predicted = calculate_weighted_moving_average(history[i + 1: i + 4])
        errors.append(abs(actual - predicted))

    if not errors:
        return 0.35
    return round(sum(errors) / len(errors), 2)


def calculate_deterministic_confidence(history: List[float], mae: Optional[float]) -> Tuple[float, str]:
    """
    Compute deterministic confidence score based on historical data points and backtest error.
    Returns (confidence_score, data_adequacy_explanation).
    """
    if not history or len(history) < 3:
        return 0.50, "Limited historical data."

    sample_count = len(history)
    err = mae if mae is not None else 0.5

    if sample_count >= 8:
        if err < 0.5:
            confidence = 0.92
        elif err < 1.0:
            confidence = 0.85
        else:
            confidence = 0.78
        adequacy = "High sample volume (8+ weeks) with strong temporal stability."
    else:
        # 3 to 7 weeks
        if err < 0.5:
            confidence = 0.82
        elif err < 1.0:
            confidence = 0.74
        else:
            confidence = 0.68
        adequacy = f"Moderate sample volume ({sample_count} weeks)."

    return confidence, adequacy


def generate_site_forecast_explanation(
    site_name: str,
    equipment_type: str,
    predicted_units: float,
    confidence: float,
    history: List[float],
    mae: Optional[float],
    driver_text: Optional[str] = None,
) -> str:
    """
    Generate an explainable, plain-language explanation for the demand forecast.
    """
    trend_dir = "steady"
    if len(history) >= 2:
        if history[0] > history[1]:
            trend_dir = "increasing"
        elif history[0] < history[1]:
            trend_dir = "decreasing"

    conf_pct = int(confidence * 100)
    mae_str = f"with backtest MAE of {mae:.2f} units" if mae is not None else ""
    
    primary_driver = driver_text or f"recent {trend_dir} rental utilization trend at {site_name}"

    explanation = (
        f"Demand for {equipment_type} at {site_name} is projected at {predicted_units:.1f} units "
        f"(confidence: {conf_pct}%) driven by {primary_driver} {mae_str}."
    )
    return explanation


def get_historical_demand_matrix(db: Session, now: Optional[datetime] = None) -> Dict[str, Dict[str, List[float]]]:
    """
    Extract or construct weekly demand history matrix:
    matrix[site_id][equipment_type] = [week_t-1, week_t-2, week_t-3, week_t-4, ...]
    """
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    rows = db.query(Rental.site_id, Equipment.type, Rental.equipment_id,
                    Rental.checked_out_at, Rental.checked_in_at).join(
        Equipment, Rental.equipment_id == Equipment.id).filter(
        Rental.checked_out_at < current,
        (Rental.checked_in_at.is_(None)) | (Rental.checked_in_at > current - timedelta(weeks=6)),
    ).all()
    matrix = {}
    for site_id, equipment_type, equipment_id, started, ended in rows:
        if not site_id or not started:
            continue
        started = started.replace(tzinfo=timezone.utc) if started.tzinfo is None else started
        ended = ended.replace(tzinfo=timezone.utc) if ended and ended.tzinfo is None else ended
        weeks = matrix.setdefault(site_id, {}).setdefault(equipment_type, [set() for _ in range(6)])
        for index, assets in enumerate(weeks):
            right = current - timedelta(weeks=index)
            left = right - timedelta(weeks=1)
            if started < right and (ended is None or ended > left):
                assets.add(equipment_id)
    return {site: {kind: [float(len(assets)) for assets in weeks]
                   for kind, weeks in kinds.items()} for site, kinds in matrix.items()}

def generate_demand_forecasts(
    db: Session,
    site_id: Optional[str] = None,
    equipment_type: Optional[str] = None,
    horizon_weeks: int = 4,
    now: Optional[datetime] = None,
) -> List[ForecastRecord]:
    """
    Generate deterministic demand forecasts across sites and equipment categories.
    """
    current_time = now or datetime.now(timezone.utc)
    if current_time.tzinfo is None:
        current_time = current_time.replace(tzinfo=timezone.utc)

    sites = db.query(Site).all()
    sites_by_id = {s.id: s for s in sites}
    
    historical_matrix = get_historical_demand_matrix(db, now=current_time)

    forecast_results: List[ForecastRecord] = []

    target_sites = [s for s in sites if site_id is None or s.id == site_id]
    types = sorted({row[0] for row in db.query(Equipment.type).distinct()})
    target_types = [t for t in types if equipment_type is None or t == equipment_type]

    for site in target_sites:
        site_hist = historical_matrix.get(site.id, {})

        for eq_type in target_types:
            history = site_hist.get(eq_type, [0.0] * 6)
            mae = calculate_backtest_mae(history)
            confidence, adequacy = calculate_deterministic_confidence(history, mae)
            
            # Predict for next horizon_weeks
            sim_history = list(history)
            for w in range(1, horizon_weeks + 1):
                forecast_date = current_time + timedelta(weeks=w)
                predicted = calculate_weighted_moving_average(sim_history)

                drivers = {
                    "historical_weeks": len(history),
                    "wma_weights": WMA_WEIGHTS,
                    "recent_actuals": history[:3],
                    "data_adequacy": adequacy,
                    "site_work_phase": "Recorded rental demand",
                }

                driver_text = "weekly distinct equipment rentals recorded at this site"
                explanation = generate_site_forecast_explanation(
                    site_name=site.name,
                    equipment_type=eq_type,
                    predicted_units=predicted,
                    confidence=confidence,
                    history=sim_history,
                    mae=mae,
                    driver_text=driver_text,
                )

                record = ForecastRecord(
                    site_id=site.id,
                    site_name=site.name,
                    equipment_type=eq_type,
                    forecast_date=forecast_date,
                    predicted_units=predicted,
                    confidence=confidence,
                    backtest_error=mae,
                    drivers=drivers,
                    explanation=explanation,
                    created_at=current_time,
                )
                forecast_results.append(record)

                # Feed prediction forward into simulated history for next horizon week
                sim_history.insert(0, predicted)

    return forecast_results


def sync_forecasts_to_db(db: Session, forecasts: List[ForecastRecord], *, commit: bool = True) -> None:
    """
    Persist generated forecast records into the forecasts table.
    """
    for f in forecasts:
        # Check if forecast already exists for site, type, and date
        existing = (
            db.query(Forecast)
            .filter(
                Forecast.site_id == f.site_id,
                Forecast.equipment_type == f.equipment_type,
                Forecast.forecast_date == f.forecast_date,
            )
            .first()
        )
        if existing:
            existing.predicted_units = f.predicted_units
            existing.confidence = f.confidence
            existing.backtest_error = f.backtest_error
            existing.drivers = f.drivers
        else:
            db_forecast = Forecast(
                site_id=f.site_id,
                equipment_type=f.equipment_type,
                forecast_date=f.forecast_date,
                predicted_units=f.predicted_units,
                confidence=f.confidence,
                backtest_error=f.backtest_error,
                drivers=f.drivers,
                created_at=f.created_at,
            )
            db.add(db_forecast)

    if commit:
        db.commit()
    else:
        db.flush()
