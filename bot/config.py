from __future__ import annotations

from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Telegram
    bot_token: str

    # Admin IDs (comma-separated in .env, e.g. "123,456")
    admin_ids: list[int] = []

    @field_validator("admin_ids", mode="before")
    @classmethod
    def parse_admin_ids(cls, v):
        if isinstance(v, str):
            return [int(x.strip()) for x in v.split(",") if x.strip()]
        if isinstance(v, int):
            return [v]
        return v

    # Database
    database_url: str = "sqlite+aiosqlite:///./data/appointments.db"

    # Sentry
    sentry_dsn: str = ""

    # Timezone
    timezone: str = "Europe/Moscow"

    # Booking
    booking_horizon_days: int = 30
    min_cancel_hours: int = 72  # 3 days


@lru_cache
def get_settings() -> Settings:
    return Settings()
