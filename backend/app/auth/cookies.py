from fastapi import Response

from app.core.config import Settings

COOKIE_PATH = "/api/v1/auth"


def set_cookies(response: Response, raw: str, csrf: str, settings: Settings) -> None:
    for name, value in [(settings.refresh_cookie, raw), (settings.csrf_cookie, csrf)]:
        response.set_cookie(
            name,
            value,
            max_age=settings.refresh_token_days * 86400,
            path=COOKIE_PATH,
            secure=settings.secure_cookies,
            httponly=True,
            samesite=settings.cookie_samesite,
        )


def clear_cookies(response: Response, settings: Settings) -> None:
    for name in [settings.refresh_cookie, settings.csrf_cookie]:
        response.delete_cookie(
            name,
            path=COOKIE_PATH,
            secure=settings.secure_cookies,
            httponly=True,
            samesite=settings.cookie_samesite,
        )
