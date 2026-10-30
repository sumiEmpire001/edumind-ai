import os
import subprocess
import sys
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text

from app.database.session import check_database


@pytest.mark.integration
def test_real_migration_and_pgvector():
    # Must be an explicitly supplied disposable test DB; never default to the application DB.
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL is required for PostgreSQL integration")
    env = {**os.environ, "DATABASE_URL": url, "APP_ENV": "test"}
    engine = create_engine(url)
    probe = "migration_probe_" + uuid4().hex
    with engine.begin() as connection:
        connection.execute(text(f'CREATE TABLE "{probe}" (value INTEGER NOT NULL)'))
        connection.execute(text(f'INSERT INTO "{probe}" VALUES (41)'))
    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], env=env, check=True)
    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], env=env, check=True)
    try:
        assert check_database(engine)
        with engine.begin() as connection:
            assert connection.scalar(text(f'SELECT value FROM "{probe}"')) == 41
            connection.execute(text(f'DROP TABLE "{probe}"'))
        subprocess.run([sys.executable, "-m", "alembic", "check"], env=env, check=True)
        with engine.connect() as connection:
            distance = connection.scalar(text("SELECT '[1,0,0]'::vector <=> '[1,0,0]'::vector"))
            assert distance == 0
    finally:
        engine.dispose()
