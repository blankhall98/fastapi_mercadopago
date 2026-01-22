from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    # App Basics
    app_env: str = "dev"
    app_name: str = "Mercado Pago Demo"
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    log_level: str = "info"

    # Database
    database_url: str = "sqlite:///./dev.db"
    db_echo: bool = False

    # JWT
    jwt_secret: str = "secret_key"
    jwt_alg: str = "HS256"
    jwt_access_ttl_min: int = 60

    # Mercado Pago
    mp_access_token: str = ""
    mp_webhook_url: str = ""
    app_base_url: str = "http://localhost:8000"
    mp_currency: str = "MXN"

    # Tell pydantic to read from .env file
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="",
        extra="ignore",
    )

settings = Settings()