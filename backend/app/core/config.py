import os
from pathlib import Path
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List, Optional

# Base backend directory
BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
DEFAULT_DB_PATH = (BACKEND_DIR / "rentsense.db").as_posix()


class Settings(BaseSettings):
    PROJECT_NAME: str = "RentSense Control Tower"
    VERSION: str = "1.0.0"
    API_V1_STR: str = "/api/v1"
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development")
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    DEBUG: bool = os.getenv("DEBUG", "false").lower() in ("true", "1", "yes")

    # Database
    DATABASE_URL: str = os.getenv("DATABASE_URL", f"sqlite:///{DEFAULT_DB_PATH}")

    # URLs & CORS
    FRONTEND_URL: str = os.getenv("FRONTEND_URL", "http://localhost:3000")
    CORS_ORIGINS: str = os.getenv("CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000")

    # Thresholds & Intelligence
    ALERT_DUE_SOON_HOURS: int = int(os.getenv("ALERT_DUE_SOON_HOURS", "48"))
    IDLE_HOURS_THRESHOLD: float = float(os.getenv("IDLE_HOURS_THRESHOLD", "8.0"))
    LOW_UTILIZATION_THRESHOLD: float = float(os.getenv("LOW_UTILIZATION_THRESHOLD", "0.20"))
    TELEMETRY_SIMULATOR_ENABLED: bool = False
    SIMULATOR_INTERVAL_SECONDS: float = 60.0
    SIMULATOR_ACTIVE_VIEWERS_ONLY: bool = True
    SIMULATOR_IDLE_GRACE_SECONDS: float = Field(default=60.0, ge=0.0, le=3600.0)
    SIMULATOR_MAX_EQUIPMENT_PER_CYCLE: int = Field(default=100, ge=1, le=1000)

    # Optional RBAC / Auth Mode (ADMIN, OPERATIONS, VIEWER)
    AUTH_ENABLED: bool = os.getenv("AUTH_ENABLED", "false").lower() in ("true", "1", "yes")

    # JWT Authentication
    JWT_SECRET_KEY: str = os.getenv("JWT_SECRET_KEY", "change-me-in-production-use-256-bit-random-key")
    AUTH_COOKIE_SECURE: Optional[bool] = None
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = int(os.getenv("JWT_EXPIRE_MINUTES", "480"))

    # Admin bootstrap credentials (seeded on first boot, never hardcoded)
    ADMIN_EMAIL: str = os.getenv("ADMIN_EMAIL", "admin@rentsense.local")
    ADMIN_PASSWORD: str = os.getenv("ADMIN_PASSWORD", "")

    # Email Notifications via Resend
    RESEND_API_KEY: Optional[str] = os.getenv("RESEND_API_KEY", None)
    ALERT_NOTIFICATION_EMAIL_TO: Optional[str] = os.getenv("ALERT_NOTIFICATION_EMAIL_TO", None)
    ALERT_NOTIFICATION_EMAIL_FROM: str = os.getenv("ALERT_NOTIFICATION_EMAIL_FROM", "RentSense Alerts <onboarding@resend.dev>")
    ALERT_NOTIFICATION_MIN_SEVERITY: str = os.getenv("ALERT_NOTIFICATION_MIN_SEVERITY", "MEDIUM")

    # AI Chatbot Assistant via Google Gemini
    GEMINI_API_KEY: Optional[str] = os.getenv("GEMINI_API_KEY", None)
    GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-3.6-flash")
    GEMINI_MAX_TURNS: int = int(os.getenv("GEMINI_MAX_TURNS", "6"))

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def cors_origin_list(self) -> List[str]:
        origins = [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]
        if self.FRONTEND_URL and self.FRONTEND_URL not in origins and self.FRONTEND_URL != "*":
            origins.append(self.FRONTEND_URL)
        return origins

    @field_validator("SIMULATOR_INTERVAL_SECONDS")
    @classmethod
    def constrain_simulator_interval(cls, value: float) -> float:
        return min(3600.0, max(10.0, value))

    @property
    def resolved_database_url(self) -> str:
        url = self.DATABASE_URL
        if not url:
            return f"sqlite:///{DEFAULT_DB_PATH}"
        if url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql+psycopg://", 1)
        elif url.startswith("postgresql://") and not url.startswith("postgresql+psycopg://"):
            url = url.replace("postgresql://", "postgresql+psycopg://", 1)
        return url


settings = Settings()
