from pathlib import Path
from datetime import timedelta
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parent / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    db_host: str = "localhost"
    db_port: int = 5432
    db_database: str = "datalang"
    db_user: str = "postgres"
    db_password: str = "postgres"

    kafka_bootstrap: str = "localhost:9092"
    kafka_group_id: str = "main"
    kafka_connect_url: str = "http://localhost:8083"

    session_cookie: str = "meow_meow_envnconfig_pleawse"
    session_ttl: timedelta = timedelta(minutes=30)


settings = Settings()
