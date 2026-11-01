from __future__ import annotations

import os
import sys
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from dotenv import load_dotenv
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import SQLAlchemyError


EXPECTED_DATABASE_NAME = "careerpilot_test_db"
PROJECT_ROOT = Path(__file__).resolve().parent


class TestServerVerificationError(RuntimeError):
    """The verified test server cannot be started safely."""


def _configure_test_database() -> None:
    load_dotenv(PROJECT_ROOT / ".env", override=False)

    if not os.getenv("DEEPSEEK_API_KEY", "").strip():
        raise TestServerVerificationError(
            "DEEPSEEK_API_KEY is not configured."
        )

    test_database_url = os.getenv("TEST_DATABASE_URL", "").strip()
    if not test_database_url:
        raise TestServerVerificationError(
            "TEST_DATABASE_URL is not configured."
        )

    try:
        parsed_url = make_url(test_database_url)
    except Exception as exc:
        raise TestServerVerificationError(
            "TEST_DATABASE_URL is not a valid SQLAlchemy URL."
        ) from exc

    if parsed_url.get_backend_name() != "postgresql":
        raise TestServerVerificationError(
            "TEST_DATABASE_URL must use PostgreSQL."
        )
    if parsed_url.database != EXPECTED_DATABASE_NAME:
        raise TestServerVerificationError(
            "TEST_DATABASE_URL must target careerpilot_test_db."
        )

    # app.db.session reads DATABASE_URL lazily.  Set it before importing that
    # module so its cached Engine is created from the verified test URL.
    os.environ["DATABASE_URL"] = test_database_url


def _project_migration_heads() -> frozenset[str]:
    config_path = PROJECT_ROOT / "alembic.ini"
    if not config_path.is_file():
        raise TestServerVerificationError("alembic.ini is missing.")

    try:
        config = Config(str(config_path))
        script_directory = ScriptDirectory.from_config(config)
        heads = frozenset(script_directory.get_heads())
    except Exception as exc:
        raise TestServerVerificationError(
            "The project Alembic migration heads could not be read."
        ) from exc

    if not heads:
        raise TestServerVerificationError(
            "The project does not contain an Alembic migration head."
        )
    return heads


def _verify_database() -> tuple[str, frozenset[str]]:
    # This is the only Engine created by the launcher.  get_engine() is cached,
    # so app.main -> get_db() later reuses this exact Engine object.
    from app.db.session import get_engine

    try:
        engine = get_engine()
    except Exception as exc:
        raise TestServerVerificationError(
            "The SQLAlchemy Engine could not be created "
            f"({type(exc).__name__})."
        ) from None
    if engine.url.get_backend_name() != "postgresql":
        raise TestServerVerificationError(
            "The SQLAlchemy Engine is not configured for PostgreSQL."
        )
    if engine.url.database != EXPECTED_DATABASE_NAME:
        raise TestServerVerificationError(
            "The SQLAlchemy Engine does not target careerpilot_test_db."
        )

    try:
        with engine.connect() as connection:
            actual_database = connection.execute(
                text("SELECT current_database()")
            ).scalar_one()
            database_heads = frozenset(
                connection.execute(
                    text("SELECT version_num FROM alembic_version")
                ).scalars()
            )
    except SQLAlchemyError as exc:
        raise TestServerVerificationError(
            "Database verification failed "
            f"({type(exc).__name__})."
        ) from None

    if actual_database != EXPECTED_DATABASE_NAME:
        raise TestServerVerificationError(
            "The live database connection is not careerpilot_test_db."
        )
    if not database_heads:
        raise TestServerVerificationError(
            "The test database has no Alembic revision."
        )

    project_heads = _project_migration_heads()
    if database_heads != project_heads:
        raise TestServerVerificationError(
            "The test database Alembic revision does not match all "
            "project migration heads."
        )

    return actual_database, database_heads


def main() -> int:
    try:
        _configure_test_database()
        actual_database, migration_heads = _verify_database()
    except TestServerVerificationError as exc:
        print(f"Safety verification failed: {exc}", file=sys.stderr)
        return 1

    print(
        "Safety verification passed: "
        f"database={actual_database}"
    )
    print(
        "Safety verification passed: alembic_heads="
        + ",".join(sorted(migration_heads))
    )
    print(
        "Starting verified test server at http://127.0.0.1:8000 "
        "with reload=False and workers=1"
    )

    # Import only after every database safety check has passed.  app.main uses
    # app.db.session.get_db(), which resolves the already-cached Engine above.
    from app.main import app
    import uvicorn

    uvicorn.run(
        app,
        host="127.0.0.1",
        port=8000,
        reload=False,
        workers=1,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
