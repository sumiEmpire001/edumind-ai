import logging
from unittest.mock import patch
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy.exc import OperationalError

from app.core.config import Settings
from app.main import create_app

URL = "postgresql+psycopg://test:test@localhost:5432/edumind"


@pytest.fixture
def client():
    with TestClient(create_app(Settings(database_url=URL, app_env="test"))) as client:
        yield client


def test_liveness_does_not_require_database(client):
    response = client.get("/api/v1/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    UUID(response.headers["x-request-id"])
    assert response.headers["cache-control"] == "no-store"


def test_readiness_success(client):
    with patch("app.api.health.check_database", return_value=True):
        assert client.get("/api/v1/health/ready").json() == {"status": "ready"}


@pytest.mark.parametrize("ready", [False, None])
def test_readiness_requires_schema_and_vector(client, ready):
    with patch("app.api.health.check_database", return_value=ready):
        assert client.get("/api/v1/health/ready").status_code == 503


def test_database_failure_is_sanitized(client):
    error = OperationalError("secret SQL", {}, Exception("private password"))
    with patch("app.api.health.check_database", side_effect=error):
        response = client.get("/api/v1/health/ready")
    assert response.status_code == 503
    assert response.json() == {"status": "unavailable"}
    assert "password" not in response.text


def test_exact_cors_origin(client):
    response = client.get("/api/v1/health/live", headers={"Origin": "http://localhost:5173"})
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
    response = client.get("/api/v1/health/live", headers={"Origin": "https://attacker.example"})
    assert "access-control-allow-origin" not in response.headers


def test_production_hides_docs():
    settings = Settings(
        database_url=URL + "?sslmode=verify-full",
        app_env="production",
        cors_origins=["https://edumind.example"],
    )
    with TestClient(create_app(settings)) as client:
        assert client.get("/docs").status_code == 404
        assert client.get("/openapi.json").status_code == 404


@pytest.mark.parametrize(
    "overrides",
    [
        {"database_url": "sqlite:///test.db"},
        {"cors_origins": ["*"]},
        {"cors_origins": ["https://example.com/path"]},
        {"app_env": "production"},
        {"app_env": "production", "database_url": URL + "?sslmode=verify-full"},
    ],
)
def test_unsafe_configuration_is_rejected(overrides):
    with pytest.raises(ValidationError):
        Settings(**({"database_url": URL} | overrides))


def test_secrets_are_masked():
    assert "test:test" not in repr(Settings(database_url=URL))


def test_unhandled_exception_is_safe(client):
    @client.app.get("/test-error")
    def explode():
        raise RuntimeError("private-provider-error")

    response = client.get("/test-error")
    assert response.status_code == 500
    assert "private-provider-error" not in response.text
    UUID(response.headers["x-request-id"])


def test_logs_are_structured():
    import json

    from app.core.logging import JsonFormatter

    record = logging.LogRecord("edumind", logging.INFO, "", 1, "health_check", (), None)
    assert json.loads(JsonFormatter().format(record))["event"] == "health_check"
