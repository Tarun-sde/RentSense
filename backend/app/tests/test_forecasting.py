import pytest
from datetime import datetime, timezone
from app.analytics.forecasting import (
    calculate_weighted_moving_average,
    calculate_backtest_mae,
    calculate_deterministic_confidence,
    generate_site_forecast_explanation,
    generate_demand_forecasts,
)
from app.db.session import SessionLocal

ANCHOR_TIME = datetime(2026, 9, 1, 12, 0, 0, tzinfo=timezone.utc)


def test_calculate_weighted_moving_average():
    # 3 periods: [3.0, 2.0, 1.0] -> 3.0*0.5 + 2.0*0.3 + 1.0*0.2 = 1.5 + 0.6 + 0.2 = 2.3
    wma = calculate_weighted_moving_average([3.0, 2.0, 1.0])
    assert wma == 2.3

    # Flat series: [2.0, 2.0, 2.0] -> 2.0
    wma_flat = calculate_weighted_moving_average([2.0, 2.0, 2.0])
    assert wma_flat == 2.0


def test_forecast_determinism():
    history = [4.0, 3.0, 2.0, 2.0, 1.0]
    res1 = calculate_weighted_moving_average(history)
    res2 = calculate_weighted_moving_average(history)
    assert res1 == res2


def test_backtest_mae_calculation():
    # Constant history: MAE should be 0.0
    mae_zero = calculate_backtest_mae([2.0, 2.0, 2.0, 2.0, 2.0, 2.0])
    assert mae_zero == 0.0

    # Slight variance
    mae_var = calculate_backtest_mae([3.0, 2.0, 2.0, 1.0, 1.0, 1.0])
    assert mae_var is not None
    assert mae_var >= 0.0


def test_confidence_calculation_sufficient_data():
    history = [2.0, 2.0, 2.0, 2.0, 2.0, 2.0, 2.0, 2.0]  # 8 weeks
    conf, desc = calculate_deterministic_confidence(history, mae=0.1)
    assert conf >= 0.88
    assert "High sample volume" in desc


def test_confidence_calculation_insufficient_data():
    history = [1.0, 2.0]  # Only 2 weeks (<3)
    conf, desc = calculate_deterministic_confidence(history, mae=None)
    assert conf == 0.50
    assert "Limited historical data." in desc


def test_explanation_generation_contains_metrics():
    explanation = generate_site_forecast_explanation(
        site_name="Navi Mumbai International Airport",
        equipment_type="Bulldozer",
        predicted_units=2.8,
        confidence=0.85,
        history=[3.0, 2.0, 2.0],
        mae=0.25,
    )
    assert "Bulldozer" in explanation
    assert "Navi Mumbai International Airport" in explanation
    assert "2.8 units" in explanation
    assert "85%" in explanation
    assert "0.25 units" in explanation


def test_generate_demand_forecasts_db_integration():
    db = SessionLocal()
    try:
        forecasts = generate_demand_forecasts(db, horizon_weeks=2, now=ANCHOR_TIME)
        assert len(forecasts) > 0
        
        # Verify fields on first record
        f = forecasts[0]
        assert f.site_id is not None
        assert f.equipment_type is not None
        assert f.predicted_units >= 0
        assert 0.0 < f.confidence <= 1.0
        assert f.explanation != ""
    finally:
        db.close()
