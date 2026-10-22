"""
Shared pytest fixtures for the RentSense test suite.
Provides an authenticated TestClient that tests using protected endpoints can use.
"""
import pytest
from fastapi.testclient import TestClient

import sys, os
import tempfile
import atexit
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

# Tests call destructive reset seeders. Always isolate them before importing settings.
_test_directory = tempfile.TemporaryDirectory(prefix="rentsense-tests-")
atexit.register(_test_directory.cleanup)
os.environ.update(DATABASE_URL=f"sqlite:///{_test_directory.name}/tests.db",
    ENVIRONMENT="development", DEBUG="false", RESEND_API_KEY="", GEMINI_API_KEY="",
    ADMIN_PASSWORD="isolated-test-password", TELEMETRY_SIMULATOR_ENABLED="false")

from main import app
from app.db.session import SessionLocal
from app.models.user import User
from app.core.security import hash_password, create_access_token
from app.seed.seed import seed_database


@pytest.fixture(scope="session", autouse=True)
def initialize_isolated_database():
    with SessionLocal() as db:
        seed_database(db)

_TEST_ID = "00000000-0000-0000-0000-000000000002"
_TEST_EMAIL = "ci-test@rentsense.test"
_TEST_PASSWORD = "CiTest789!"


def _ensure_test_user():
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == _TEST_ID).first()
        if not user:
            db.add(User(
                id=_TEST_ID,
                email=_TEST_EMAIL,
                hashed_password=hash_password(_TEST_PASSWORD),
                role="admin",
                is_active=True,
            ))
            db.commit()
    finally:
        db.close()


@pytest.fixture
def auth_client():
    """A TestClient pre-authenticated with a test admin user (function scoped)."""
    _ensure_test_user()
    token = create_access_token({"sub": _TEST_ID, "email": _TEST_EMAIL, "role": "admin"})
    c = TestClient(app, raise_server_exceptions=True)
    c.cookies.set("access_token", token)
    return c
