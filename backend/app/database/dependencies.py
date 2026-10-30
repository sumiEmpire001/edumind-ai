from collections.abc import Generator

from fastapi import Request
from sqlalchemy.orm import Session


def get_db(request: Request) -> Generator[Session, None, None]:
    with Session(request.app.state.engine, expire_on_commit=False) as session:
        yield session
