from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from app.core.config import settings

# Engine configuration
connect_args = {}
pool_options = {}
if settings.resolved_database_url.startswith("sqlite"):
    connect_args = {"check_same_thread": False}
else:
    connect_args = {"connect_timeout": 10}
    # Keep the per-process pool modest on the single small Container App.
    pool_options = {"pool_size": 5, "max_overflow": 2, "pool_timeout": 10}

engine = create_engine(
    settings.resolved_database_url,
    connect_args=connect_args,
    pool_pre_ping=True,
    hide_parameters=True,
    **pool_options,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    """FastAPI dependency for yielding database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
