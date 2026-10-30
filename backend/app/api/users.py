from uuid import UUID

from fastapi import APIRouter, Query, Request

from app.auth.dependencies import DB, Admin, Current
from app.schemas.identity import UserPage, UserUpdate, UserView
from app.security.rate_limit import consume
from app.services import identity as service

router = APIRouter(prefix="/api/v1", tags=["users"])


@router.get("/users/me", response_model=UserView)
def me(current: Current):
    return current.user


@router.get("/admin/users", response_model=UserPage)
def users(
    db: DB,
    admin: Admin,
    request: Request,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=25, ge=1, le=100),
):
    consume(request, "admin", str(admin.user.id), 120, 60)
    items, total = service.list_users(db, offset, limit)
    return UserPage(
        items=[UserView.model_validate(u) for u in items], total=total, offset=offset, limit=limit
    )


@router.patch("/admin/users/{user_id}", response_model=UserView)
def update(user_id: UUID, data: UserUpdate, request: Request, db: DB, admin: Admin):
    consume(request, "admin-write", str(admin.user.id), 30, 60)
    return service.update_user(db, request, admin.user, user_id, data)
