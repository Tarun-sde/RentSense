"""Local, disposable SQLite API benchmark. Never opens the configured database."""
import json
import os
import statistics
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main():
    with tempfile.TemporaryDirectory(prefix="rentsense-benchmark-") as directory:
        os.environ.update(
            DATABASE_URL=f"sqlite:///{directory}/benchmark.db",
            ENVIRONMENT="development", DEBUG="false", RESEND_API_KEY="", GEMINI_API_KEY="",
            ADMIN_PASSWORD="benchmark-only-password",
        )
        from sqlalchemy import event
        from fastapi.testclient import TestClient
        from main import app
        from app.db.session import engine, SessionLocal
        from app.seed.seed import seed_database, ANCHOR_TIME
        from app.models import Equipment

        with SessionLocal() as db:
            seed_database(db, reset=True, anchor_time=ANCHOR_TIME)
        counts, sql_times = [], []
        starts = []

        @event.listens_for(engine, "before_cursor_execute")
        def before(*args):
            counts.append(1)
            starts.append(time.perf_counter())

        @event.listens_for(engine, "after_cursor_execute")
        def after(*args):
            sql_times.append(time.perf_counter() - starts.pop())

        client = TestClient(app)
        for size in (20, 100):
            if size > 20:
                with SessionLocal() as db:
                    current = db.query(Equipment).count()
                    db.add_all(Equipment(id=f"BENCH-{i:05}", type="Excavator", dealer="Benchmark", daily_rate=100) for i in range(current, size))
                    db.commit()
            for path in ("equipment", "dashboard", "anomalies", "recommendations", "forecasts", "impact", "equipment/EQX1001"):
                samples, statements, sql_ms = [], [], []
                for _ in range(5):
                    counts.clear()
                    sql_times.clear()
                    start = time.perf_counter()
                    response = client.get(f"/api/v1/{path}")
                    elapsed = (time.perf_counter() - start) * 1000
                    assert response.status_code == 200, (path, response.status_code)
                    samples.append(elapsed)
                    statements.append(len(counts))
                    sql_ms.append(sum(sql_times) * 1000)
                print(json.dumps(dict(assets=size, endpoint=path, queries=statements,
                    median_ms=round(statistics.median(samples), 2),
                    median_sql_ms=round(statistics.median(sql_ms), 2), bytes=len(response.content))))
        engine.dispose()


if __name__ == "__main__":
    main()
