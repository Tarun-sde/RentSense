import asyncio
import logging
import math
import time
from datetime import datetime, timezone

from sqlalchemy import text
from starlette.concurrency import run_in_threadpool

from app.api.v1.telemetry import _persist_telemetry
from app.core.config import settings
from app.db.session import SessionLocal, engine
from app.schemas.telemetry import TelemetryIngestRequest
from app.services.connection_manager import connection_manager
from app.services.equipment_service import fleet_query
from app.services.alert_service import dispatch_pending_alert_notifications


logger = logging.getLogger(__name__)
_LOCK_ID = 0x52454E54  # "RENT"; session advisory lock shared by all backend replicas.

# Site bounds and operating character are adapted from the former standalone simulator.
_PROFILES = {
    "EQX1001": (18.7180, 81.2580, .0006, .35, .31, 2.0),
    "EQX1002": (18.9894, 73.0648, .0001, .04, .04, 1.0),
    "EQX1003": (18.7185, 81.2590, .0008, .72, .05, 5.0),
    "EQX1004": (18.9900, 73.0655, .0000, .80, .05, 7.0),
    "EQX1005": (18.9890, 73.0640, .0010, .90, .04, 8.0),
    "EQX1006": (13.6067, 76.9033, .0004, .42, .10, 3.0),
    "EQX1007": (13.6075, 76.9045, .0002, .00, .00, 0.0),
}


class TelemetrySimulator:
    def __init__(self) -> None:
        self._task: asyncio.Task | None = None
        self._lock_connection = None
        self.cycles = 0
        self.inserted_records = 0

    async def start(self) -> bool:
        if not settings.TELEMETRY_SIMULATOR_ENABLED:
            return False
        if self._task and not self._task.done():
            return False
        if not await run_in_threadpool(self._acquire_ownership):
            logger.warning("Telemetry simulator disabled in this process: another instance owns the database lock")
            return False
        self._task = asyncio.create_task(self._run(), name="telemetry-simulator")
        logger.info(
            "Telemetry simulator started (interval=%ss, active_viewers_only=%s)",
            settings.SIMULATOR_INTERVAL_SECONDS,
            settings.SIMULATOR_ACTIVE_VIEWERS_ONLY,
        )
        return True

    async def stop(self) -> None:
        task, self._task = self._task, None
        if task:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        await run_in_threadpool(self._release_ownership)

    def _acquire_ownership(self) -> bool:
        if engine.dialect.name != "postgresql":
            return True
        connection = engine.connect()
        try:
            if not connection.execute(text("SELECT pg_try_advisory_lock(:key)"), {"key": _LOCK_ID}).scalar():
                connection.close()
                return False
            connection.commit()
            self._lock_connection = connection
            return True
        except Exception:
            connection.close()
            logger.exception("Could not acquire telemetry simulator ownership")
            return False

    def _release_ownership(self) -> None:
        if not self._lock_connection:
            return
        try:
            self._lock_connection.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": _LOCK_ID})
            self._lock_connection.commit()
        finally:
            self._lock_connection.close()
            self._lock_connection = None

    def _ownership_valid(self) -> bool:
        if engine.dialect.name != "postgresql":
            return True
        try:
            self._lock_connection.execute(text("SELECT 1"))
            self._lock_connection.commit()
            return True
        except Exception:
            logger.exception("Telemetry simulator lost its database ownership connection; stopping safely")
            self._lock_connection.close()
            self._lock_connection = None
            return False

    async def _run(self) -> None:
        last_viewer_at: float | None = None
        next_cycle_at = 0.0
        failures = 0
        while True:
            now = time.monotonic()
            if connection_manager.subscriber_count:
                last_viewer_at = now
            within_grace = last_viewer_at is not None and now - last_viewer_at < settings.SIMULATOR_IDLE_GRACE_SECONDS
            if settings.SIMULATOR_ACTIVE_VIEWERS_ONLY and not connection_manager.subscriber_count and not within_grace:
                last_viewer_at = None
                await connection_manager.wait_for_activity_change()
                next_cycle_at = 0.0
                continue

            delay = next_cycle_at - now
            if delay > 0:
                await connection_manager.wait_for_activity_change(delay)
                continue

            try:
                if not await run_in_threadpool(self._ownership_valid):
                    return
                events = await run_in_threadpool(self.run_cycle)
                for event in events:
                    await connection_manager.broadcast("telemetry", event)
                self.cycles += 1
                self.inserted_records += len(events)
                failures = 0
                logger.info("Telemetry simulator cycle stored %d record(s)", len(events))
            except asyncio.CancelledError:
                raise
            except Exception:
                failures += 1
                logger.exception("Telemetry simulator cycle failed; API service remains available")
            retry_delay = min(settings.SIMULATOR_INTERVAL_SECONDS, 5 * 2 ** min(failures, 4)) if failures else settings.SIMULATOR_INTERVAL_SECONDS
            next_cycle_at = time.monotonic() + retry_delay

    def run_cycle(self, elapsed_seconds: float | None = None) -> list[dict]:
        """Persist one shared fleet tick synchronously; caller keeps it off the event loop."""
        now = datetime.now(timezone.utc)
        elapsed_hours = min(elapsed_seconds or settings.SIMULATOR_INTERVAL_SECONDS, settings.SIMULATOR_INTERVAL_SECONDS) / 3600
        events: list[dict] = []
        with SessionLocal() as db:
            try:
                rows = fleet_query(db).limit(settings.SIMULATOR_MAX_EQUIPMENT_PER_CYCLE).all()
                for index, (equipment, rental, latest) in enumerate(rows):
                    equipment._fleet_snapshot = (rental, latest)
                    profile = _PROFILES.get(equipment.id)
                    if profile:
                        base_lat, base_lng, radius, engine_rate, idle_rate, fuel_rate = profile
                    else:
                        site = rental.site if rental else None
                        base_lat = getattr(site, "latitude", None) or getattr(latest, "latitude", None) or 18.7180
                        base_lng = getattr(site, "longitude", None) or getattr(latest, "longitude", None) or 81.2580
                        radius, engine_rate, idle_rate, fuel_rate = .0002, .25, .05, 2.0
                    angle = ((now.timestamp() / settings.SIMULATOR_INTERVAL_SECONDS) * .15 + index) % (2 * math.pi)
                    engine_hours = max(float(latest.engine_hours) if latest else 0.0, 0.0) + engine_rate * elapsed_hours
                    idle_hours = min(engine_hours, max(float(latest.idle_hours) if latest else 0.0, 0.0) + idle_rate * elapsed_hours)
                    fuel = max(0.0, min(100.0, (float(latest.fuel_pct) if latest else 100.0) - fuel_rate * engine_rate * elapsed_hours))
                    payload = TelemetryIngestRequest(
                        equipment_id=equipment.id,
                        timestamp=now,
                        latitude=round(base_lat + radius * math.sin(angle), 6),
                        longitude=round(base_lng + radius * math.cos(angle) * 1.2, 6),
                        engine_hours=round(engine_hours, 4),
                        idle_hours=round(idle_hours, 4),
                        fuel_pct=round(fuel, 2),
                    )
                    _, event = _persist_telemetry(payload, db, equipment, commit=False)
                    events.append(event)
                db.commit()
                dispatch_pending_alert_notifications(db)
                return events
            except Exception:
                db.rollback()
                raise


telemetry_simulator = TelemetrySimulator()
