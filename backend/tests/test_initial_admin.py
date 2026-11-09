from unittest.mock import patch

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.initial_admin import initialize
from app.models.identity import AuditLog, User
from tests.test_auth import PASSWORD, auth, login, register
from tests.test_auth import api as api
from tests.test_auth import engine as engine


def test_setup_is_disabled_by_default(monkeypatch):
    monkeypatch.delenv("INITIAL_ADMIN_SETUP", raising=False)
    with patch("app.auth.initial_admin.build_engine") as build:
        assert initialize() is False
    build.assert_not_called()


def test_setup_invalid_values_do_not_echo_credentials(monkeypatch, caplog):
    monkeypatch.setenv("INITIAL_ADMIN_SETUP", "true")
    monkeypatch.setenv("INITIAL_ADMIN_EMAIL", "invalid-email")
    monkeypatch.setenv("INITIAL_ADMIN_PASSWORD", "a-private-sentinel")
    assert initialize() is False
    assert "administrator_setup_invalid" in caplog.text
    assert "a-private-sentinel" not in caplog.text


@pytest.mark.integration
def test_private_bootstrap_is_once_only_and_never_resets_password(api, monkeypatch):
    _, db_engine, settings = api
    if db_engine.dialect.name != "postgresql":
        pytest.skip("PostgreSQL advisory lock required")
    monkeypatch.setenv("INITIAL_ADMIN_SETUP", "true")
    monkeypatch.setenv("INITIAL_ADMIN_EMAIL", "initial-admin@example.com")
    monkeypatch.setenv("INITIAL_ADMIN_PASSWORD", PASSWORD)
    # The shared fixture owns the engine; keep initialize() from disposing it in this test.
    with (
        patch("app.auth.initial_admin.get_settings", return_value=settings),
        patch("app.auth.initial_admin.build_engine", return_value=db_engine),
        patch.object(db_engine, "dispose"),
    ):
        assert initialize() is True
        with Session(db_engine) as db:
            before = db.scalar(select(User.password_hash).where(User.role == "admin"))
        monkeypatch.setenv("INITIAL_ADMIN_PASSWORD", "A different secret password 123!")
        assert initialize() is False
        with Session(db_engine) as db:
            assert db.scalar(select(User.password_hash).where(User.role == "admin")) == before


@pytest.mark.integration
def test_private_promotion_checks_password_and_revokes_existing_sessions(api, monkeypatch):
    client, db_engine, settings = api
    if db_engine.dialect.name != "postgresql":
        pytest.skip("PostgreSQL advisory lock required")
    email = "existing-admin@example.com"
    original = register(client, email=email).json()
    student = auth(login(client, email=email))
    assert client.get("/api/v1/admin/users", headers=student).status_code == 403
    monkeypatch.setenv("INITIAL_ADMIN_SETUP", "promote")
    monkeypatch.setenv("INITIAL_ADMIN_EMAIL", email)
    monkeypatch.setenv("INITIAL_ADMIN_PASSWORD", "Wrong promotion password")
    with (
        patch("app.auth.initial_admin.get_settings", return_value=settings),
        patch("app.auth.initial_admin.build_engine", return_value=db_engine),
        patch.object(db_engine, "dispose"),
    ):
        assert initialize() is False
        assert client.get("/api/v1/users/me", headers=student).json()["role"] == "student"
        monkeypatch.setenv("INITIAL_ADMIN_PASSWORD", PASSWORD)
        assert initialize() is True
        assert initialize() is False
    assert client.get("/api/v1/users/me", headers=student).status_code == 401
    promoted = login(client, email=email)
    assert promoted.json()["user"] == {**original, "role": "admin"}
    assert client.get("/api/v1/admin/users", headers=auth(promoted)).status_code == 200
    with Session(db_engine) as db:
        assert (
            len(
                list(
                    db.scalars(
                        select(AuditLog).where(AuditLog.action == "admin.promoted_by_operator")
                    )
                )
            )
            == 1
        )
