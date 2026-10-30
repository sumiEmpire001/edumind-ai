"""Bounded cleanup: python -m app.auth.maintenance. Schedule operationally, never at login."""

import time

from sqlalchemy import delete, select

from app.core.config import get_settings
from app.database.session import build_engine
from app.models.identity import RateLimitBucket


def main() -> None:
    engine = build_engine(get_settings())
    try:
        with engine.begin() as connection:
            expired = (
                select(RateLimitBucket.key)
                .where(RateLimitBucket.expires_at < int(time.time()))
                .limit(1000)
            )
            result = connection.execute(
                delete(RateLimitBucket).where(RateLimitBucket.key.in_(expired))
            )
            print(f"Removed {result.rowcount} expired rate-limit buckets (maximum 1000).")
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
