import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from unittest.mock import patch
from uuid import UUID, uuid4

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, func, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.auth.crypto import digest, now, password_hasher
from app.core.config import Settings
from app.database.base import Base
from app.main import create_app
from app.models.identity import AuditLog, AuthSession, RefreshToken, User

ORIGIN = "http://localhost:5173"
PASSWORD = "A long test passphrase 913!"


@pytest.fixture(scope="module")
def engine():
    url = os.getenv("TEST_DATABASE_URL")
    if url:
        base = create_engine(url)
        schema = "auth_test_" + uuid4().hex
        with base.begin() as c:
            c.execute(text("CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA public"))
            c.execute(text(f'CREATE SCHEMA "{schema}"'))
        isolated = make_url(url).update_query_dict({"options": f"-csearch_path={schema}"})
        env = {
            **os.environ,
            "DATABASE_URL": isolated.render_as_string(hide_password=False),
            "APP_ENV": "test",
        }
        subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], env=env, check=True)
        test_engine = create_engine(isolated)
    else:
        test_engine = create_engine(
            "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
        )

        @event.listens_for(test_engine, "connect")
        def foreign_keys(connection, _):
            connection.execute("PRAGMA foreign_keys=ON")

        Base.metadata.create_all(test_engine)
    yield test_engine
    test_engine.dispose()
    if url:
        # Only the uniquely-created disposable test schema; never reset application data.
        with base.begin() as c:
            c.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        base.dispose()


@pytest.fixture
def api(engine):
    # These tables exist only in an in-memory DB or the random isolated test schema above.
    with engine.begin() as c:
        for table in reversed(Base.metadata.sorted_tables):
            c.execute(table.delete())
    settings = Settings(
        database_url="postgresql+psycopg://test:test@localhost/unused",
        app_env="test",
        login_ip_limit=1000,
        login_account_limit=1000,
        register_ip_limit=1000,
        auth_ip_limit=1000,
    )
    app = create_app(settings)
    with (
        patch("app.main.build_engine", return_value=engine),
        patch.object(engine, "dispose"),
        TestClient(app) as client,
    ):
        client.headers["Origin"] = ORIGIN
        yield client, engine, settings


def register(client, email="student@example.com", **extra):
    return client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": PASSWORD, "full_name": "Test Student", **extra},
    )


def login(client, email="student@example.com", password=PASSWORD):
    return client.post("/api/v1/auth/login", json={"email": email, "password": password})


def auth(result):
    return {"Authorization": "Bearer " + result.json()["access_token"]}


def account(engine, role="admin", email="admin@example.com"):
    with Session(engine) as db:
        user = User(
            email=email,
            full_name="Private Admin",
            role=role,
            is_active=True,
            password_hash=password_hasher.hash(PASSWORD),
            created_at=now(),
            updated_at=now(),
        )
        db.add(user)
        db.commit()
        return user.id


def test_registration_normalization_and_hash(api):
    client, engine, _ = api
    response = register(client, email="Student@EXAMPLE.com")
    assert response.status_code == 201
    assert response.json()["email"] == "student@example.com"
    assert response.json()["role"] == "student"
    assert "password" not in response.text
    with Session(engine) as db:
        user = db.scalar(select(User))
        assert user.password_hash.startswith("$argon2id$")
        assert PASSWORD not in user.password_hash
        assert db.scalar(select(AuditLog.action)) == "user.registered"
    assert register(client).status_code == 409


@pytest.mark.parametrize("extra", [{"role": "admin"}, {"role": "contributor"}, {"is_active": True}])
def test_public_registration_cannot_choose_privileges(api, extra):
    client, _, _ = api
    assert register(client, **extra).status_code == 422


def test_login_me_and_hashed_refresh(api):
    client, engine, settings = api
    register(client)
    result = login(client)
    assert result.status_code == 200
    assert result.json()["expires_in"] == 600
    cookies = result.headers.get_list("set-cookie")
    assert all(
        "HttpOnly" in c and "SameSite=lax" in c and "Path=/api/v1/auth" in c for c in cookies
    )
    raw = client.cookies.get(settings.refresh_cookie)
    with Session(engine) as db:
        stored = db.scalar(select(RefreshToken))
        assert stored.token_hash == digest(raw)
        assert stored.token_hash != raw
    me = client.get("/api/v1/users/me", headers=auth(result))
    assert me.status_code == 200
    assert me.json()["email"] == "student@example.com"
    assert "password_hash" not in me.text


@pytest.mark.parametrize(
    "email,password", [("nobody@example.com", PASSWORD), ("student@example.com", "wrong-password")]
)
def test_invalid_credentials_are_generic(api, email, password):
    client, _, _ = api
    register(client)
    result = login(client, email, password)
    assert result.status_code == 401
    assert result.json()["detail"] == "Incorrect email or password."


def test_inactive_user_cannot_login(api):
    client, engine, _ = api
    uid = UUID(register(client).json()["id"])
    with Session(engine) as db:
        db.get(User, uid).is_active = False
        db.commit()
    assert login(client).status_code == 401


def test_refresh_rotates_and_replay_revokes_family(api):
    client, _, settings = api
    register(client)
    original = login(client)
    old_raw = client.cookies.get(settings.refresh_cookie)
    csrf = original.json()["csrf_token"]
    refreshed = client.post("/api/v1/auth/refresh", headers={"X-CSRF-Token": csrf})
    assert refreshed.status_code == 200
    assert client.cookies.get(settings.refresh_cookie) != old_raw
    assert client.get("/api/v1/users/me", headers=auth(refreshed)).status_code == 200
    # A lost-response retry is intentionally treated as replay; clients must serialize refreshes.
    client.cookies.set(
        settings.refresh_cookie, old_raw, domain="testserver.local", path="/api/v1/auth"
    )
    replay = client.post("/api/v1/auth/refresh", headers={"X-CSRF-Token": csrf})
    assert replay.status_code == 401
    assert client.get("/api/v1/users/me", headers=auth(refreshed)).status_code == 401


def test_refresh_requires_matching_csrf_and_origin(api):
    client, _, _ = api
    register(client)
    result = login(client)
    assert client.post("/api/v1/auth/refresh").status_code == 403
    assert client.post("/api/v1/auth/refresh", headers={"X-CSRF-Token": "bad"}).status_code == 403
    headers = {"X-CSRF-Token": result.json()["csrf_token"], "Origin": "https://evil.example"}
    assert client.post("/api/v1/auth/refresh", headers=headers).status_code == 403
    csrf = client.get("/api/v1/auth/csrf")
    assert csrf.json()["csrf_token"] == result.json()["csrf_token"]
    assert (
        client.post(
            "/api/v1/auth/refresh", headers={"X-CSRF-Token": csrf.json()["csrf_token"]}
        ).status_code
        == 200
    )


def test_missing_origin_is_rejected(api):
    client, _, _ = api
    del client.headers["origin"]
    assert register(client).status_code == 403


def test_logout_revokes_access_and_refresh_and_clears_cookies(api):
    client, _, settings = api
    register(client)
    result = login(client)
    assert client.post("/api/v1/auth/logout").status_code == 403
    response = client.post(
        "/api/v1/auth/logout", headers={"X-CSRF-Token": result.json()["csrf_token"]}
    )
    assert response.status_code == 204
    assert not client.cookies.get(settings.refresh_cookie)
    assert client.get("/api/v1/users/me", headers=auth(result)).status_code == 401
    assert (
        client.post(
            "/api/v1/auth/refresh", headers={"X-CSRF-Token": result.json()["csrf_token"]}
        ).status_code
        == 401
    )
    assert client.post("/api/v1/auth/logout").status_code == 204


def test_logout_all_revokes_every_session(api):
    client, _, _ = api
    register(client)
    first = login(client)
    second = login(client)
    assert client.post("/api/v1/auth/logout-all", headers=auth(second)).status_code == 204
    assert client.get("/api/v1/users/me", headers=auth(first)).status_code == 401
    assert client.get("/api/v1/users/me", headers=auth(second)).status_code == 401


def test_password_change_requires_old_password_and_revokes_sessions(api):
    client, _, _ = api
    register(client)
    result = login(client)
    path = "/api/v1/auth/password"
    assert (
        client.post(
            path,
            headers=auth(result),
            json={"current_password": "incorrect", "new_password": "A different long passphrase!"},
        ).status_code
        == 400
    )
    assert (
        client.post(
            path,
            headers=auth(result),
            json={"current_password": PASSWORD, "new_password": "A different long passphrase!"},
        ).status_code
        == 204
    )
    assert client.get("/api/v1/users/me", headers=auth(result)).status_code == 401
    assert login(client).status_code == 401
    assert login(client, password="A different long passphrase!").status_code == 200


@pytest.mark.parametrize("kind", ["expired", "signature", "audience", "issuer", "type", "subject"])
def test_bad_tokens_are_rejected(api, kind):
    client, _, settings = api
    register(client)
    result = login(client)
    claims = jwt.decode(
        result.json()["access_token"],
        settings.jwt_secret.get_secret_value(),
        algorithms=["HS256"],
        audience=settings.jwt_audience,
    )
    if kind == "expired":
        claims["exp"] = now() - timedelta(seconds=10)
    if kind == "audience":
        claims["aud"] = "other-application"
    if kind == "issuer":
        claims["iss"] = "other-issuer"
    if kind == "type":
        claims["type"] = "refresh"
    if kind == "subject":
        claims["sub"] = "invalid-uuid"
    key = (
        "different-secret-key-at-least-32-bytes"
        if kind == "signature"
        else settings.jwt_secret.get_secret_value()
    )
    token = jwt.encode(claims, key, algorithm="HS256")
    assert (
        client.get("/api/v1/users/me", headers={"Authorization": "Bearer " + token}).status_code
        == 401
    )


def test_expired_refresh_session(api):
    client, engine, _ = api
    register(client)
    result = login(client)
    with Session(engine) as db:
        db.scalar(select(AuthSession)).expires_at = now() - timedelta(seconds=1)
        db.commit()
    assert (
        client.post(
            "/api/v1/auth/refresh", headers={"X-CSRF-Token": result.json()["csrf_token"]}
        ).status_code
        == 401
    )


@pytest.mark.parametrize("role", ["student", "contributor"])
def test_role_restrictions_are_backend_enforced(api, role):
    client, engine, _ = api
    account(engine, role=role, email="member@example.com")
    result = login(client, "member@example.com")
    assert client.get("/api/v1/admin/users", headers=auth(result)).status_code == 403
    assert (
        client.patch(
            "/api/v1/admin/users/" + str(uuid4()), headers=auth(result), json={"is_active": False}
        ).status_code
        == 403
    )


def test_unauthenticated_endpoints_restricted(api):
    client, _, _ = api
    assert client.get("/api/v1/users/me").status_code == 401
    assert client.get("/api/v1/admin/users").status_code == 401


def test_admin_user_management_revokes_sessions(api):
    client, engine, _ = api
    uid = register(client).json()["id"]
    student = login(client)
    account(engine)
    admin = login(client, "admin@example.com")
    listing = client.get("/api/v1/admin/users?limit=1", headers=auth(admin))
    assert listing.status_code == 200 and listing.json()["total"] == 2
    assert len(listing.json()["items"]) == 1
    assert (
        client.patch(
            f"/api/v1/admin/users/{uid}", headers=auth(admin), json={"role": "contributor"}
        ).status_code
        == 200
    )
    assert client.get("/api/v1/users/me", headers=auth(student)).status_code == 401
    contributor = login(client)
    assert contributor.json()["user"]["role"] == "contributor"
    result = client.patch(
        f"/api/v1/admin/users/{uid}", headers=auth(admin), json={"is_active": False}
    )
    assert result.status_code == 200
    assert client.get("/api/v1/users/me", headers=auth(contributor)).status_code == 401
    assert login(client).status_code == 401
    with Session(engine) as db:
        assert (
            db.scalar(
                select(func.count())
                .select_from(AuditLog)
                .where(AuditLog.action == "admin.user_updated")
            )
            == 2
        )


def test_admin_cannot_promote_or_disable_admin_accounts(api):
    client, engine, _ = api
    uid = register(client).json()["id"]
    aid = account(engine)
    admin = login(client, "admin@example.com")
    assert (
        client.patch(
            f"/api/v1/admin/users/{uid}", headers=auth(admin), json={"role": "admin"}
        ).status_code
        == 422
    )
    assert (
        client.patch(
            f"/api/v1/admin/users/{aid}", headers=auth(admin), json={"is_active": False}
        ).status_code
        == 409
    )
    assert (
        client.patch(
            f"/api/v1/admin/users/{uuid4()}", headers=auth(admin), json={"is_active": False}
        ).status_code
        == 404
    )
    assert (
        client.patch(f"/api/v1/admin/users/{uid}", headers=auth(admin), json={}).status_code == 422
    )


def test_deactivation_also_invalidates_a_preexisting_session(api):
    client, engine, _ = api
    uid = UUID(register(client).json()["id"])
    result = login(client)
    with Session(engine) as db:
        db.get(User, uid).is_active = False
        db.commit()
    assert client.get("/api/v1/users/me", headers=auth(result)).status_code == 401


def test_rate_limit_counts_failed_logins_and_survives_clients(api):
    client, _, settings = api
    settings.login_account_limit = 2
    assert login(client, password="wrong").status_code == 401
    assert login(client, password="wrong").status_code == 401
    blocked = login(client, password="wrong")
    assert blocked.status_code == 429
    assert 0 < int(blocked.headers["retry-after"]) <= 60
    # Fresh HTTP cookies cannot reset database-backed account quotas.
    client.cookies.clear()
    assert login(client, password="wrong").status_code == 429


def test_validation_never_echoes_passwords(api):
    client, _, _ = api
    response = register(client, password="tiny-key")
    assert response.status_code == 422
    assert "tiny-key" not in response.text
    assert "input" not in response.text
    assert register(client, full_name="   ").status_code == 422
    assert register(client, email="not-an-email").status_code == 422


def test_request_size_is_bounded(api):
    client, _, _ = api
    response = client.post(
        "/api/v1/auth/login", content=b"x" * 17000, headers={"Content-Type": "application/json"}
    )
    assert response.status_code == 413


def test_database_errors_are_safe_503(api):
    client, _, _ = api
    with patch(
        "app.api.auth.consume",
        side_effect=OperationalError("private-sql", {}, Exception("password")),
    ):
        result = login(client)
    assert result.status_code == 503
    assert "password" not in result.text and "private-sql" not in result.text


def test_production_cookies_are_secure(api):
    client, _, settings = api
    settings.app_env = "production"
    register(client)
    response = login(client)
    assert response.status_code == 200
    assert all(
        "Secure" in c and "HttpOnly" in c and "__Secure-" in c
        for c in response.headers.get_list("set-cookie")
    )


def test_cors_preflight_allows_credentials_and_csrf(api):
    client, _, _ = api
    result = client.options(
        "/api/v1/auth/refresh",
        headers={
            "Origin": ORIGIN,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "X-CSRF-Token",
        },
    )
    assert result.status_code == 200
    assert result.headers["access-control-allow-credentials"] == "true"


@pytest.mark.integration
def test_postgres_rate_limit_is_atomic_across_connections(api):
    client, engine, _ = api
    if engine.dialect.name != "postgresql":
        pytest.skip("PostgreSQL concurrency requires TEST_DATABASE_URL")
    from starlette.requests import Request

    from app.security.rate_limit import consume

    app = client.app
    request = Request({"type": "http", "app": app})

    def hit(_):
        consume(request, "concurrency", "test-identity", 100, 60)

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(hit, range(20)))
    from app.models.identity import RateLimitBucket

    with Session(engine) as db:
        assert db.scalar(select(func.sum(RateLimitBucket.hits))) == 20


@pytest.mark.parametrize(
    "limit_name, endpoint", [("register_ip_limit", "register"), ("login_ip_limit", "login")]
)
def test_ip_limits_ignore_untrusted_forwarded_headers(api, limit_name, endpoint):
    client, _, settings = api
    setattr(settings, limit_name, 1)
    if endpoint == "register":
        assert register(client).status_code == 201
        response = client.post(
            "/api/v1/auth/register",
            headers={"X-Forwarded-For": "192.0.2.40"},
            json={"email": "other@example.com", "password": PASSWORD, "full_name": "Other"},
        )
    else:
        assert login(client).status_code == 401
        response = client.post(
            "/api/v1/auth/login",
            headers={"X-Forwarded-For": "192.0.2.40"},
            json={"email": "other@example.com", "password": PASSWORD},
        )
    assert response.status_code == 429


def test_unknown_refresh_token_is_rejected(api):
    client, _, settings = api
    client.cookies.set(settings.refresh_cookie, "unknown-refresh-token", path="/api/v1/auth")
    assert (
        client.post("/api/v1/auth/refresh", headers={"X-CSRF-Token": "unknown"}).status_code == 401
    )
    assert client.get("/api/v1/auth/csrf").status_code == 401


def test_body_limit_catches_streams_without_content_length(api):
    client, _, _ = api

    def body():
        yield b"x" * 9000
        yield b"x" * 9000

    assert client.post("/api/v1/auth/login", content=body()).status_code == 413


@pytest.mark.integration
def test_concurrent_refresh_fails_closed_on_replay(api):
    client, engine, settings = api
    if engine.dialect.name != "postgresql":
        pytest.skip("Refresh locking requires TEST_DATABASE_URL")
    from threading import Barrier

    register(client)
    result = login(client)
    raw = client.cookies.get(settings.refresh_cookie)
    csrf = result.json()["csrf_token"]
    barrier = Barrier(2)
    headers = {
        "Origin": ORIGIN,
        "X-CSRF-Token": csrf,
        "Cookie": f"{settings.refresh_cookie}={raw}; {settings.csrf_cookie}={csrf}",
    }

    def attempt(_):
        with TestClient(client.app) as other:
            barrier.wait(timeout=10)
            return other.post("/api/v1/auth/refresh", headers=headers)

    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(attempt, range(2)))
    assert sorted(r.status_code for r in responses) == [200, 401]
    success = next(r for r in responses if r.status_code == 200)
    assert client.get("/api/v1/users/me", headers=auth(success)).status_code == 401


@pytest.mark.integration
def test_private_bootstrap_creates_admin_without_promoting_existing_user(api):
    client, engine, _ = api
    if engine.dialect.name != "postgresql":
        pytest.skip("Bootstrap advisory lock requires TEST_DATABASE_URL")
    from app.auth.bootstrap import create_admin
    from app.schemas.identity import Registration

    data = Registration(email="admin@example.com", full_name="Private Admin", password=PASSWORD)
    with Session(engine) as db:
        admin = create_admin(db, data)
        assert admin.role == "admin"
    with Session(engine) as db:
        with pytest.raises(ValueError, match="already exists"):
            create_admin(db, data)
    register(client)
    with Session(engine) as db:
        student = Registration(email="student@example.com", full_name="Test", password=PASSWORD)
        with pytest.raises(ValueError, match="never auto-promoted"):
            create_admin(db, student)
    assert login(client).json()["user"]["role"] == "student"


def test_password_hash_resource_exhaustion_returns_retryable_error(api):
    client, _, _ = api
    with patch("app.auth.crypto._hash_slots.acquire", return_value=False):
        response = register(client)
    assert response.status_code == 503
    assert response.headers["retry-after"] == "1"


def test_https_cookie_session_round_trip(api):
    _, engine, _ = api
    settings = Settings(
        database_url="postgresql+psycopg://test:test@localhost/unused?sslmode=verify-full",
        app_env="production",
        cors_origins=["https://learn.example.com"],
    )
    with (
        patch("app.main.build_engine", return_value=engine),
        TestClient(create_app(settings), base_url="https://api.example.com") as browser,
    ):
        browser.headers["Origin"] = "https://learn.example.com"
        assert register(browser).status_code == 201
        result = login(browser)
        assert result.status_code == 200
        assert (
            browser.post(
                "/api/v1/auth/refresh", headers={"X-CSRF-Token": result.json()["csrf_token"]}
            ).status_code
            == 200
        )
