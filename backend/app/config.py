from functools import lru_cache

from pydantic import Field, computed_field
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
    seasonal_window_days: int = 14
    seasonal_min_sample_size: int = 150
    seasonal_min_years: int = 10

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    @computed_field
    @property
    def allowed_origins(self) -> list[str]:
        value = self.cors_allow_origins or self.frontend_origin
        return [origin.strip() for origin in value.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
