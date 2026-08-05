"""Application settings, loaded from the environment and from backend/.env.

Environment variables take precedence over the .env file, which is what lets the test
suite point itself at appointment_db_test by exporting DB_NAME before importing the app.
"""

from pathlib import Path
from urllib.parse import quote_plus

from pydantic_settings import BaseSettings, SettingsConfigDict

# config.py lives at backend/app/core/config.py, so parents[2] is backend/.
BACKEND_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_name: str = "Hospital Appointment Booking API"
    api_v1_prefix: str = "/api/v1"

    db_host: str = "127.0.0.1"
    db_port: int = 3306
    db_user: str = "root"
    db_password: str = ""
    db_name: str = "appointment_db"

    jwt_secret: str
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 720

    # 5173 = vite dev, 4173 = vite preview. Both localhost and 127.0.0.1 are listed
    # because they are distinct browser origins even though they resolve to this machine.
    cors_origins: str = (
        "http://localhost:5173,http://127.0.0.1:5173,"
        "http://localhost:4173,http://127.0.0.1:4173"
    )
    sql_echo: bool = False

    # How long the patient at the head of a waiting queue gets exclusive first refusal on
    # a released slot. Never extends past the slot's own start time.
    waitlist_claim_window_minutes: int = 15
    # Background sweep that expires elapsed claim windows and offers the slot to the next
    # patient in line. 0 disables it (the tests do, and expiry still happens lazily on
    # the next booking attempt).
    waitlist_sweep_seconds: int = 60

    @property
    def database_url(self) -> str:
        """SQLAlchemy URL. Credentials are percent-encoded so '@' or ':' in a
        password cannot corrupt the DSN."""
        user = quote_plus(self.db_user)
        password = quote_plus(self.db_password)
        return (
            f"mysql+pymysql://{user}:{password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}?charset=utf8mb4"
        )

    @property
    def server_url(self) -> str:
        """Same as database_url but with no database selected — used by init_db to run
        CREATE DATABASE."""
        user = quote_plus(self.db_user)
        password = quote_plus(self.db_password)
        return (
            f"mysql+pymysql://{user}:{password}"
            f"@{self.db_host}:{self.db_port}/?charset=utf8mb4"
        )

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


settings = Settings()
