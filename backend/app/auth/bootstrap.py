"""Private admin creation: python -m app.auth.bootstrap (password is never an argument)."""

import getpass

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.auth.crypto import hash_password, now
from app.core.config import get_settings
from app.database.session import build_engine
from app.models.identity import AuditLog, User
from app.schemas.identity import Registration


def create_admin(db: Session, data: Registration) -> User:
    # Serialize private bootstrap operations; never promote an existing public account.
    db.execute(text("SELECT pg_advisory_xact_lock(72640192)"))
    if db.scalar(select(User.id).where(User.email == str(data.email))):
        raise ValueError("Account already exists. Existing accounts are never auto-promoted.")
    user = User(
        email=str(data.email),
        full_name=data.full_name,
        role="admin",
        is_active=True,
        password_hash=hash_password(data.password.get_secret_value()),
        created_at=now(),
        updated_at=now(),
    )
    db.add(user)
    db.flush()
    db.add(
        AuditLog(
            actor_id=user.id,
            target_id=user.id,
            action="admin.bootstrapped",
            request_id="private-cli",
            created_at=now(),
        )
    )
    db.commit()
    return user


def main() -> None:
    print("Create a new administrator; existing accounts cannot be promoted.")
    email, full_name = input("Email: ").strip(), input("Full name: ").strip()
    password = getpass.getpass("Password (15–128 characters): ")
    if password != getpass.getpass("Confirm password: "):
        raise SystemExit("Passwords do not match.")
    try:
        data = Registration(email=email, full_name=full_name, password=password)
    except ValueError:
        raise SystemExit("Invalid email, name or password length.") from None
    engine = build_engine(get_settings())
    try:
        with Session(engine) as db:
            try:
                create_admin(db, data)
            except ValueError as exc:
                raise SystemExit(str(exc)) from None
        print("Administrator created. Credentials are not written to files.")
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
