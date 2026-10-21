"""Small query-budget checks against an isolated database, never production."""
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session
from fastapi.testclient import TestClient
from main import app
from app.db.session import Base
from app.db.session import get_db
from app.models import Equipment
from app.models.user import User
from app.core.security import create_access_token


def test_query_budget_empty_large_and_pagination(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'budget.db'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    statements = []
    event.listen(engine, "before_cursor_execute", lambda conn, cursor, statement, *args: statements.append(statement))
    def database():
        with Session(engine) as db:
            yield db
    app.dependency_overrides[get_db] = database
    try:
        with TestClient(app) as client:
            assert client.get('/api/v1/equipment').json() == []
            assert client.get('/api/v1/dashboard').json()['total_equipment'] == 0
            with Session(engine) as db:
                db.add_all(Equipment(id=f'TEST-{i:03}', type='Excavator', dealer='Test', daily_rate=100) for i in range(100))
                db.add(User(id="budget-test-user", email="budget@example.test", hashed_password="unused", role="admin", is_active=True))
                db.commit()
            client.cookies.set("access_token", create_access_token({"sub": "budget-test-user"}))
            for endpoint, budget in [('equipment', 1), ('dashboard', 2), ('anomalies', 1)]:
                statements.clear()
                response = client.get('/api/v1/' + endpoint)
                assert response.status_code == 200
                assert len(statements) <= budget, (endpoint, statements)
            page = client.get('/api/v1/equipment?limit=2&offset=2&status=UNASSIGNED').json()
            assert [item['id'] for item in page] == ['TEST-002', 'TEST-003']
            assert client.get('/api/v1/equipment?search=TEST-099').json()[0]['id'] == 'TEST-099'
            assert client.get('/api/v1/equipment?search=%25').json() == []
            assert client.get('/api/v1/equipment?offset=100').json() == []
            assert client.get('/api/v1/equipment?limit=0').status_code == 422
            for path in ['alerts', 'actions', 'recommendations', 'equipment/TEST-000/telemetry']:
                assert client.get('/api/v1/' + path + '?offset=-1').status_code == 422
                assert client.get('/api/v1/' + path + '?offset=100').json() == []
            statements.clear()
            assert client.get('/api/v1/forecasts').status_code == 200
            assert not any(s.lstrip().upper().startswith(('INSERT', 'UPDATE', 'DELETE')) for s in statements)
    finally:
        app.dependency_overrides.pop(get_db, None)
        engine.dispose()
