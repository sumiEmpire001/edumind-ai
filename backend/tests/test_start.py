from unittest.mock import patch

import pytest
from sqlalchemy.exc import OperationalError

from app.start import main


def test_migration_is_opt_in(monkeypatch):
    monkeypatch.delenv("RUN_DATABASE_MIGRATIONS", raising=False)
    with patch("app.start.command.upgrade") as migrate, patch("app.start.os.execvp") as run:
        main()
    migrate.assert_not_called()
    assert run.call_args.args[0] == "uvicorn"


def test_migrates_before_start(monkeypatch):
    monkeypatch.setenv("RUN_DATABASE_MIGRATIONS", "true")
    with patch("app.start.command.upgrade") as migrate, patch("app.start.os.execvp") as run:
        main()
    assert migrate.call_args.args[1] == "head"
    run.assert_called_once()


def test_failed_migration_stops_without_secret_logs(monkeypatch, caplog):
    monkeypatch.setenv("RUN_DATABASE_MIGRATIONS", "true")
    error = OperationalError("SECRET", {}, Exception("root certificate file SECRET"))
    with patch("app.start.command.upgrade", side_effect=error), patch("app.start.os.execvp") as run:
        with pytest.raises(SystemExit):
            main()
    run.assert_not_called()
    assert "missing_ca_certificate" in caplog.text
    assert "SECRET" not in caplog.text
