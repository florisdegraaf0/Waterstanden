from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Nederland Watermonitor"
    environment: str = "local"
    log_level: str = "INFO"

    database_url: str = Field(
        default="postgresql+psycopg://watermonitor:watermonitor@db:5432/watermonitor"
    )
    frontend_origin: str = "http://localhost:3000"
    cors_allow_origins: str | None = None

    rws_wfs_base_url: str = "https://geo.rijkswaterstaat.nl/services/ogc/hws/DDAPI20/ows"
    rws_waterwebservices_base_url: str = "https://ddapi20-waterwebservices.rijkswaterstaat.nl"
    rws_timeout_seconds: float = 20.0
    rws_wfs_max_features: int = 1000
    rws_use_fallback_measurements: bool = True
    active_station_max_age_hours: int = 24
    active_station_recent_check_concurrency: int = 10
    active_station_verify_recent_measurements: bool = False
    seasonal_window_days: int = 14
    seasonal_min_sample_size: int = 150
    seasonal_min_years: int = 10
    anomaly_delta_tolerance_minutes: int = 45
    anomaly_delta_min_window_observations: int = 12
    anomaly_delta_max_window_gap_minutes: int = 180
    anomaly_recent_window_hours: int = 48
    anomaly_stale_after_minutes: int = 180
    overview_cache_ttl_minutes: int = 15
    overview_default_limit: int = 50

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    @field_validator("database_url")
    @classmethod
    def use_installed_postgres_driver(cls, value: str) -> str:
        if value.startswith("postgresql://"):
            return value.replace("postgresql://", "postgresql+psycopg://", 1)
        if value.startswith("postgres://"):
            return value.replace("postgres://", "postgresql+psycopg://", 1)
        return value

    @property
    def allowed_origins(self) -> list[str]:
        value = self.cors_allow_origins or self.frontend_origin
        return [origin.strip() for origin in value.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
