from functools import lru_cache
from typing import Literal
from urllib.parse import urlparse

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", hide_input_in_errors=True)
    app_env: Literal["development", "test", "production"] = "development"
    render_private_database_host: str | None = None
    database_url: SecretStr
    cors_origins: list[str] = ["http://localhost:5173"]
    jwt_secret: SecretStr
    jwt_issuer: str = "edumind-api"
    jwt_audience: str = "edumind-web"
    access_token_minutes: int = Field(default=10, ge=1, le=30)
    refresh_token_days: int = Field(default=14, ge=1, le=30)
    cookie_samesite: Literal["lax", "strict", "none"] = "lax"
    login_ip_limit: int = Field(default=20, ge=1)
    login_account_limit: int = Field(default=5, ge=1)
    register_ip_limit: int = Field(default=5, ge=1)
    auth_ip_limit: int = Field(default=60, ge=1)
    blob_read_write_token: SecretStr | None = None
    blob_store_id: str | None = None
    storage_endpoint: str | None = None
    storage_bucket: str | None = None
    storage_access_key: SecretStr | None = None
    storage_secret_key: SecretStr | None = None
    storage_region: str = "eu-central-1"
    embedding_model: str = "gemini-embedding-001"
    rag_enabled: bool = False
    gemini_api_key: SecretStr | None = None
    gemini_model: str = Field(default="gemini-2.5-flash", pattern=r"^[a-zA-Z0-9.\-]+$")
    gemini_attempts: int = Field(default=3, ge=1, le=3)
    gemini_timeout_seconds: float = Field(default=15, ge=10, le=60)
    chat_user_limit: int = Field(default=20, ge=1)
    chat_timeout_seconds: float = Field(default=20, ge=0.05, le=60)
    chat_context_characters: int = Field(default=24000, ge=4000, le=48000)
    max_request_bytes: int = Field(default=16384, ge=1024, le=65536)
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"

    @field_validator("jwt_secret")
    @classmethod
    def strong_signing_key(cls, value: SecretStr) -> SecretStr:
        raw = value.get_secret_value()
        if len(raw.encode()) < 32 or "REPLACE" in raw.upper():
            raise ValueError(
                "JWT_SECRET must be an independently generated secret of at least 32 bytes"
            )
        return value

    @property
    def secure_cookies(self) -> bool:
        return self.app_env == "production"

    @property
    def refresh_cookie(self) -> str:
        return "__Secure-edumind_refresh" if self.secure_cookies else "edumind_refresh"

    @property
    def csrf_cookie(self) -> str:
        return "__Secure-edumind_csrf" if self.secure_cookies else "edumind_csrf"

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
        if self.cookie_samesite == "none" and not self.secure_cookies:
            raise ValueError("SameSite=None requires production HTTPS secure cookies")
        if self.app_env == "production":
            if self.storage_endpoint and not self.storage_endpoint.startswith("https://"):
                raise ValueError("Production object storage endpoints must use HTTPS")
            url = make_url(self.database_url.get_secret_value())
            import os

            private = (
                os.environ.get("RENDER") == "true"
                and self.render_private_database_host == url.host
                and (url.host or "").startswith("dpg-")
                and "." not in (url.host or "")
            )
            if private:
                # Render documents self-signed certificates for its private network.
                url = url.update_query_dict({"sslmode": "require", "sslrootcert": ""})
                self.database_url = SecretStr(url.render_as_string(hide_password=False))
            if not private and url.query.get("sslmode") not in {"verify-ca", "verify-full"}:
                raise ValueError("Production database connections must verify TLS certificates")
            if not self.cors_origins or any(
                not o.startswith("https://") for o in self.cors_origins
            ):
                raise ValueError("Production requires explicit HTTPS frontend origins")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
