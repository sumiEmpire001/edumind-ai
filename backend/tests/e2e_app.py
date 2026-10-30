"""Explicit test server, unavailable in normal/production startup."""

import os

from sqlalchemy.engine import make_url

from app.core.config import get_settings
from app.main import create_app
from tests.fake_academic import FixtureProvider


def create_e2e_app():
    settings = get_settings()
    database = settings.database_url.get_secret_value()
    if (
        settings.app_env != "test"
        or os.environ.get("TEST_DATABASE_URL") != database
        or not (make_url(database).database or "").endswith("_test")
    ):
        raise RuntimeError("The fixture server requires a named disposable test database")
    return create_app(settings, provider=FixtureProvider())
