from app.config import Settings


def test_database_url_uses_installed_psycopg_driver_for_postgresql_url() -> None:
    settings = Settings(database_url="postgresql://user:pass@db:5432/watermonitor")

    assert settings.database_url == "postgresql+psycopg://user:pass@db:5432/watermonitor"


def test_database_url_uses_installed_psycopg_driver_for_postgres_url() -> None:
    settings = Settings(database_url="postgres://user:pass@db:5432/watermonitor")

    assert settings.database_url == "postgresql+psycopg://user:pass@db:5432/watermonitor"


def test_database_url_preserves_explicit_driver() -> None:
    settings = Settings(database_url="postgresql+psycopg://user:pass@db:5432/watermonitor")

    assert settings.database_url == "postgresql+psycopg://user:pass@db:5432/watermonitor"


def test_allowed_origins_are_derived_from_frontend_origin() -> None:
    settings = Settings(frontend_origin="https://app.example.com,http://localhost:3000")

    assert settings.allowed_origins == ["https://app.example.com", "http://localhost:3000"]
