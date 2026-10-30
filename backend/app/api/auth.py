from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response

from app.auth.cookies import clear_cookies, set_cookies
from app.auth.dependencies import DB, Current, trusted_origin
from app.schemas.identity import Credentials, PasswordChange, Registration, TokenView, UserView
from app.security.rate_limit import consume, ip_key
from app.services import identity as service

router = APIRouter(
    prefix="/api/v1/auth", tags=["authentication"], dependencies=[Depends(trusted_origin)]
)


def auth_limit(request: Request) -> None:
    consume(request, "auth", ip_key(request), request.app.state.settings.auth_ip_limit, 60)


AuthLimit = Annotated[None, Depends(auth_limit)]


@router.post("/register", response_model=UserView, status_code=201)
def register(data: Registration, request: Request, db: DB, _: AuthLimit):
    consume(
        request, "registration", ip_key(request), request.app.state.settings.register_ip_limit, 3600
    )
    return service.register(db, request, data)


@router.post("/login", response_model=TokenView)
def login(data: Credentials, request: Request, response: Response, db: DB, _: AuthLimit):
    settings = request.app.state.settings
    consume(request, "login-ip", ip_key(request), settings.login_ip_limit, 60)
    consume(request, "login-account", str(data.email), settings.login_account_limit, 60)
    result, raw = service.login(db, request, data)
    set_cookies(response, raw, result.csrf_token, settings)
    return result


@router.post("/refresh", response_model=TokenView)
def refresh(request: Request, response: Response, db: DB, _: AuthLimit):
    result, raw = service.refresh(db, request)
    set_cookies(response, raw, result.csrf_token, request.app.state.settings)
    return result


@router.get("/csrf")
def csrf(request: Request, db: DB, _: AuthLimit) -> dict[str, str]:
    return {"csrf_token": service.csrf_token(db, request)}


@router.post("/logout", status_code=204)
def logout(request: Request, response: Response, db: DB, _: AuthLimit):
    service.logout(db, request)
    clear_cookies(response, request.app.state.settings)


@router.post("/logout-all", status_code=204)
def logout_all(request: Request, response: Response, db: DB, current: Current, _: AuthLimit):
    service.revoke_sessions(db, current.user.id)
    service.audit(db, request, "auth.logout_all", current.user.id)
    db.commit()
    clear_cookies(response, request.app.state.settings)


@router.post("/password", status_code=204)
def password(
    data: PasswordChange,
    request: Request,
    response: Response,
    db: DB,
    current: Current,
    _: AuthLimit,
):
    consume(request, "password", str(current.user.id), 5, 3600)
    service.change_password(
        db,
        request,
        current,
        data.current_password.get_secret_value(),
        data.new_password.get_secret_value(),
    )
    clear_cookies(response, request.app.state.settings)
