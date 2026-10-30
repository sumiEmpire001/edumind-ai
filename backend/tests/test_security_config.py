import pytest
from pydantic import ValidationError

from app.core.config import Settings

URL = "postgresql+psycopg://test:test@localhost/unused"


@pytest.mark.parametrize("key", ["short", "x" * 31, "REPLACE_WITH_AN_INDEPENDENT_RANDOM_SECRET"])
def test_weak_or_placeholder_signing_key_fails_startup(key):
    with pytest.raises(ValidationError):
        Settings(database_url=URL, jwt_secret=key)


def test_missing_secret_has_no_fallback(monkeypatch):
    monkeypatch.delenv("JWT_SECRET")
    with pytest.raises(ValidationError):
        Settings(database_url=URL, _env_file=None)


def test_cross_site_cookies_require_https_production():
    with pytest.raises(ValidationError):
        Settings(database_url=URL, cookie_samesite="none")
