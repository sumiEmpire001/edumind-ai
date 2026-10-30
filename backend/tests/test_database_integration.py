import os
import subprocess
import sys

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
    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], env=env, check=True)
    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], env=env, check=True)
    engine = create_engine(url)
    try:
        assert check_database(engine)
        with engine.connect() as connection:
            distance = connection.scalar(text("SELECT '[1,0,0]'::vector <=> '[1,0,0]'::vector"))
            assert distance == 0
    finally:
        engine.dispose()
