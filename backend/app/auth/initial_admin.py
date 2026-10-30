"""Optional one-time private deployment bootstrap, disabled unless explicitly enabled."""

import logging
import os

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.auth.bootstrap import create_admin
from app.core.config import get_settings
from app.database.session import build_engine
from app.models.identity import User
from app.schemas.identity import Registration


def initialize():
    if os.environ.get("INITIAL_ADMIN_SETUP") != "true":
        return False
    try:
        data = Registration(
            email=os.environ.get("INITIAL_ADMIN_EMAIL", ""),
            full_name=os.environ.get("INITIAL_ADMIN_NAME", "Administrator"),
            password=os.environ.get("INITIAL_ADMIN_PASSWORD", ""),
        )
    except ValueError:
        raise RuntimeError("Private administrator setup values are incomplete or invalid") from None
    engine = build_engine(get_settings())
    try:
        with Session(engine) as db:
            db.execute(text("SELECT pg_advisory_xact_lock(72640192)"))
            if db.scalar(select(User.id).where(User.role == "admin")):
                logging.info("initial_administrator_already_exists; remove_private_setup_values")
                return False
            try:
                create_admin(db, data)
            except ValueError:
                raise RuntimeError(
                    "Existing public accounts cannot become initial administrators"
                ) from None
        logging.info("initial_administrator_created; remove_private_setup_values")
        return True
    finally:
        engine.dispose()
