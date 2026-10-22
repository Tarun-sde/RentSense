import asyncio

import pytest

from app.core.config import Settings, settings
from app.db.session import SessionLocal
from app.models import Equipment, Telemetry
from app.services.connection_manager import connection_manager
from app.services.telemetry_simulator import TelemetrySimulator
import app.services.telemetry_simulator as simulator_module


def test_simulator_is_disabled_by_default_and_interval_is_constrained():
    defaults = Settings(_env_file=None)
    assert defaults.TELEMETRY_SIMULATOR_ENABLED is False
    assert defaults.SIMULATOR_INTERVAL_SECONDS == 60
    assert Settings(_env_file=None, SIMULATOR_INTERVAL_SECONDS=1).SIMULATOR_INTERVAL_SECONDS == 10


def test_cycle_updates_all_assets_with_valid_monotonic_values():
    simulator = TelemetrySimulator()
    with SessionLocal() as db:
        before = {
            equipment_id: (engine, idle)
            for equipment_id, engine, idle in db.query(
                Telemetry.equipment_id, Telemetry.engine_hours, Telemetry.idle_hours
            ).order_by(Telemetry.timestamp, Telemetry.id).all()
        }
        equipment_count = db.query(Equipment).count()
        record_count = db.query(Telemetry).count()

    events = simulator.run_cycle(elapsed_seconds=60)

    assert len(events) == equipment_count
    with SessionLocal() as db:
        assert db.query(Telemetry).count() == record_count + equipment_count
    assert all(0 <= event["fuel_pct"] <= 100 for event in events)
    assert all(event["idle_hours"] <= event["engine_hours"] for event in events)
    assert all(event["engine_hours"] >= before[event["equipment_id"]][0] for event in events)


def test_new_equipment_gets_default_profile():
    equipment_id = "SIM-NEW-ASSET"
    with SessionLocal() as db:
        db.add(Equipment(id=equipment_id, type="Test", dealer="Test", daily_rate=1))
        db.commit()
    try:
        events = TelemetrySimulator().run_cycle(elapsed_seconds=60)
        event = next(event for event in events if event["equipment_id"] == equipment_id)
        assert event["engine_hours"] > 0
        assert -90 <= event["latitude"] <= 90
    finally:
        with SessionLocal() as db:
            db.query(Telemetry).filter(Telemetry.equipment_id == equipment_id).delete()
            db.query(Equipment).filter(Equipment.id == equipment_id).delete()
            db.commit()


def test_failed_batch_rolls_back_and_next_cycle_recovers(monkeypatch):
    simulator = TelemetrySimulator()
    with SessionLocal() as db:
        before = db.query(Telemetry).count()
    original = simulator_module._persist_telemetry
    calls = 0

    def fail_second(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("temporary failure")
        return original(*args, **kwargs)

    monkeypatch.setattr(simulator_module, "_persist_telemetry", fail_second)
    with pytest.raises(RuntimeError):
        simulator.run_cycle(60)
    with SessionLocal() as db:
        assert db.query(Telemetry).count() == before

    monkeypatch.setattr(simulator_module, "_persist_telemetry", original)
    assert simulator.run_cycle(60)


@pytest.mark.anyio
async def test_activity_controls_one_recovering_loop_and_clean_shutdown(monkeypatch):
    simulator = TelemetrySimulator()
    calls = 0

    def cycle():
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("temporary database failure")
        return []

    monkeypatch.setattr(settings, "TELEMETRY_SIMULATOR_ENABLED", True)
    monkeypatch.setattr(settings, "SIMULATOR_INTERVAL_SECONDS", .02)
    monkeypatch.setattr(settings, "SIMULATOR_IDLE_GRACE_SECONDS", .04)
    monkeypatch.setattr(settings, "SIMULATOR_ACTIVE_VIEWERS_ONLY", True)
    monkeypatch.setattr(simulator, "run_cycle", cycle)

    assert await simulator.start() is True
    assert await simulator.start() is False
    await asyncio.sleep(.03)
    assert calls == 0

    first = await connection_manager.connect()
    second = await connection_manager.connect()
    await asyncio.sleep(.07)
    assert 2 <= calls <= 5  # One fleet loop, not one loop per viewer; first failure recovered.

    connection_manager.disconnect(first)
    connection_manager.disconnect(second)
    await asyncio.sleep(.07)
    paused_calls = calls
    await asyncio.sleep(.05)
    assert calls == paused_calls

    resumed = await connection_manager.connect()
    await asyncio.sleep(.03)
    assert calls > paused_calls
    connection_manager.disconnect(resumed)
    await simulator.stop()
    assert simulator._task is None
