"""Fixture accounts for disposable browser CI only; never a production provisioning command."""

import os

from sqlalchemy import select
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.auth.bootstrap import create_admin
from app.auth.crypto import hash_password, now
from app.core.config import get_settings
from app.database.session import build_engine
from app.models.identity import User
from app.schemas.identity import Registration


def main() -> None:
    settings = get_settings()
    if (
        settings.app_env != "test"
        or not (make_url(settings.database_url.get_secret_value()).database or "").endswith("_test")
        or not os.environ.get("TEST_DATABASE_URL")
        or os.environ["TEST_DATABASE_URL"] != settings.database_url.get_secret_value()
        or not os.environ.get("E2E_TEST_PASSWORD")
    ):
        raise SystemExit("E2E seed requires an explicitly configured disposable test database.")
    password = os.environ["E2E_TEST_PASSWORD"]
    engine = build_engine(settings)
    try:
        with Session(engine) as db:
            admin = Registration(
                email="admin-e2e@example.com", full_name="Test Administrator", password=password
            )
            if not db.scalar(select(User.id).where(User.email == str(admin.email))):
                create_admin(db, admin)
            if not db.scalar(select(User.id).where(User.email == "contributor-e2e@example.com")):
                db.add(
                    User(
                        email="contributor-e2e@example.com",
                        full_name="Test Contributor",
                        role="contributor",
                        is_active=True,
                        password_hash=hash_password(password),
                        created_at=now(),
                        updated_at=now(),
                    )
                )
                db.commit()
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
