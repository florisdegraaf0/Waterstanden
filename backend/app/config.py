from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Nederland Watermonitor"
    environment: str = "local"
    log_level: str = "INFO"

    database_url: str = Field(
        default="postgresql+psycopg://watermonitor:watermonitor@db:5432/watermonitor"
    )
    frontend_origin: str = "http://localhost:3000"

    rws_wfs_base_url: str = "https://geo.rijkswaterstaat.nl/services/ogc/hws/DDAPI20/ows"
    rws_waterwebservices_base_url: str = "https://ddapi20-waterwebservices.rijkswaterstaat.nl"
    rws_timeout_seconds: float = 20.0
    rws_use_fallback_measurements: bool = True

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


@lru_cache
def get_settings() -> Settings:
    return Settings()

