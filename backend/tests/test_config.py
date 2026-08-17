from app.config import Settings


def test_allowed_origins_defaults_to_frontend_origin() -> None:
    settings = Settings(frontend_origin="https://frontend.example")

    assert settings.allowed_origins == ["https://frontend.example"]


def test_allowed_origins_supports_comma_separated_deployment_origins() -> None:
    settings = Settings(
        frontend_origin="https://frontend.example",
        cors_allow_origins="https://one.example, https://two.example",
    )

    assert settings.allowed_origins == ["https://one.example", "https://two.example"]
