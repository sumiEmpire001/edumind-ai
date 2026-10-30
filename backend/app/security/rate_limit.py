import hashlib
import hmac
import time

from fastapi import HTTPException, Request
from sqlalchemy import text


def consume(request: Request, scope: str, identity: str, limit: int, seconds: int) -> None:
    current = int(time.time())
    end = (current // seconds + 1) * seconds
    secret = request.app.state.settings.jwt_secret.get_secret_value().encode()
    key = hmac.new(secret, f"{scope}:{identity}:{end}".encode(), hashlib.sha256).hexdigest()
    # Separate committed transaction: failed logins must still consume their quota.
    # The atomic UPSERT is shared by all API instances and works under concurrency.
    with request.app.state.engine.begin() as connection:
        hits = connection.scalar(
            text("""
            INSERT INTO rate_limit_buckets (key, hits, expires_at) VALUES (:key, 1, :end)
            ON CONFLICT (key) DO UPDATE SET hits = rate_limit_buckets.hits + 1
            RETURNING hits
        """),
            {"key": key, "end": end},
        )
    if hits > limit:
        raise HTTPException(
            429,
            "Too many requests. Please try again later.",
            headers={"Retry-After": str(end - current)},
        )


def ip_key(request: Request) -> str:
    # Forwarded headers are accepted only through Uvicorn's explicitly trusted proxy config.
    return request.client.host if request.client else "unknown"
