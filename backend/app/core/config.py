from functools import lru_cache
from typing import Literal
from urllib.parse import urlparse

from pydantic import SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", hide_input_in_errors=True)
    app_env: Literal["development", "test", "production"] = "development"
    database_url: SecretStr
    cors_origins: list[str] = ["http://localhost:5173"]
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"

    @field_validator("database_url")
    @classmethod
    def postgres_only(cls, value: SecretStr) -> SecretStr:
        try:
            url = make_url(value.get_secret_value())
            valid = url.drivername == "postgresql+psycopg" and bool(url.database)
        except Exception:
            valid = False
        if not valid:
            raise ValueError("A PostgreSQL psycopg database URL is required")
        return value

    @field_validator("cors_origins")
    @classmethod
    def exact_origins(cls, origins: list[str]) -> list[str]:
        for origin in origins:
            parsed = urlparse(origin)
            if (
                parsed.scheme not in {"http", "https"}
                or not parsed.netloc
                or parsed.path
                or parsed.query
                or parsed.fragment
                or parsed.username
                or parsed.password
                or "*" in origin
            ):
                raise ValueError("Use exact HTTP(S) origins without paths or wildcards")
        return origins

    @model_validator(mode="after")
    def production_transport(self) -> "Settings":
        if self.app_env == "production":
            url = make_url(self.database_url.get_secret_value())
            if url.query.get("sslmode") not in {"verify-ca", "verify-full"}:
                raise ValueError("Production database connections must verify TLS certificates")
            if not self.cors_origins or any(
                not o.startswith("https://") for o in self.cors_origins
            ):
                raise ValueError("Production requires explicit HTTPS frontend origins")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
