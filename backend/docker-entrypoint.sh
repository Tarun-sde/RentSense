#!/bin/sh
set -eu

if [ "${RUN_MIGRATIONS:-true}" = "true" ]; then
    python -m alembic upgrade head
fi

python - <<'PY'
import os
from app.db.session import SessionLocal
from app.seed.seed import seed_database

if os.getenv("SEED_DEMO_DATA", "false").lower() == "true":
    with SessionLocal() as db:
        seed_database(db)
PY

python - <<'PY'
import os
from app.db.session import SessionLocal
from app.models.user import User
from app.core.security import hash_password

admin_email = os.getenv("ADMIN_EMAIL", "")
admin_password = os.getenv("ADMIN_PASSWORD", "")

if admin_email and admin_password:
    db = SessionLocal()
    try:
        existing = db.query(User).filter(User.email == admin_email).first()
        if not existing:
            user = User(
                email=admin_email,
                hashed_password=hash_password(admin_password),
                role="admin",
                is_active=True,
            )
            db.add(user)
            db.commit()
            print(f"Admin user seeded: {admin_email}")
        else:
            print(f"Admin user already exists: {admin_email}")
    finally:
        db.close()
else:
    print("ADMIN_EMAIL or ADMIN_PASSWORD not set — skipping admin seed")
PY

exec python -m uvicorn main:app --host 0.0.0.0 --port 8000
