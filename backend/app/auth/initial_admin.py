"""Optional one-time private deployment bootstrap, disabled unless explicitly enabled."""

import logging
import os

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.auth.bootstrap import create_admin
from app.auth.crypto import now, verify_password
from app.core.config import get_settings
from app.database.session import build_engine
from app.models.identity import AuditLog, User
from app.schemas.identity import Credentials, Registration
from app.services.identity import revoke_sessions


def promote_existing(db: Session, data: Credentials) -> bool:
    user = db.scalar(select(User).where(User.email == str(data.email)).with_for_update())
    if (
        user is None
        or not user.is_active
        or not verify_password(data.password.get_secret_value(), user.password_hash)
    ):
        logging.warning("administrator_promotion_denied; check_private_setup_values")
        return False
    if user.role == "admin":
        logging.info("administrator_promotion_already_applied; remove_private_setup_values")
        return False
    user.role = "admin"
    user.updated_at = now()
    revoke_sessions(db, user.id)
    db.add(
        AuditLog(
            target_id=user.id,
            action="admin.promoted_by_operator",
            request_id="private-deployment",
            created_at=now(),
        )
    )
    db.commit()
    logging.warning("administrator_promotion_applied; remove_private_setup_values")
    return True


def initialize():
    mode = os.environ.get("INITIAL_ADMIN_SETUP")
    if mode not in {"true", "promote"}:
        return False
    email = os.environ.get("INITIAL_ADMIN_EMAIL", "")
    password = os.environ.get("INITIAL_ADMIN_PASSWORD", "")
    try:
        credentials = Credentials(email=email, password=password)
        registration = (
            Registration(
                email=email,
                full_name=os.environ.get("INITIAL_ADMIN_NAME", "Administrator"),
                password=password,
            )
            if mode == "true"
            else None
        )
    except ValueError:
        logging.warning("administrator_setup_invalid; check_private_setup_values")
        return False

    engine = build_engine(get_settings())
    try:
        with Session(engine) as db:
            db.execute(text("SELECT pg_advisory_xact_lock(72640192)"))
            if registration is None:
                return promote_existing(db, credentials)
            if db.scalar(select(User.id).where(User.role == "admin")):
                logging.info("initial_administrator_already_exists; remove_private_setup_values")
                return False
            try:
                create_admin(db, registration)
            except ValueError:
                logging.warning("administrator_setup_account_exists; use_private_promotion")
                return False
        logging.info("initial_administrator_created; remove_private_setup_values")
        return True
    finally:
        engine.dispose()
