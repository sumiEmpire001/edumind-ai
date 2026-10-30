"""Single-instance test deployment entrypoint; production uses a release migration job."""

import logging
import os

from alembic.config import Config
from sqlalchemy.exc import SQLAlchemyError

from alembic import command


def main():
    if os.environ.get("RUN_DATABASE_MIGRATIONS") == "true":
        try:
            command.upgrade(Config("alembic.ini"), "head")
        except SQLAlchemyError as exc:
            message = str(exc).lower()
            category = "database_error"
            for needle, label in [
                ("root certificate file", "missing_ca_certificate"),
                ("certificate verify failed", "certificate_verification_failed"),
                ("does not match host name", "certificate_hostname_mismatch"),
                ("does not support ssl", "database_ssl_unsupported"),
                ("password authentication failed", "database_credentials_invalid"),
                ("could not translate host", "database_hostname_invalid"),
                ("connection timed out", "database_connection_timeout"),
            ]:
                if needle in message:
                    category = label
                    break
            logging.error("migration_failed category=%s", category)
            raise SystemExit(1) from None
    os.execvp(
        "uvicorn",
        [
            "uvicorn",
            "app.main:create_app",
            "--factory",
            "--host",
            "0.0.0.0",
            "--port",
            os.environ.get("PORT", "8000"),
            "--no-access-log",
        ],
    )


if __name__ == "__main__":
    main()
