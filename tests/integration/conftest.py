from __future__ import annotations

import os
from collections.abc import Generator
from pathlib import Path

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine, URL, make_url
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session


EXPECTED_TEST_DATABASE = "careerpilot_test_db"
PROJECT_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="session")
def test_database_url() -> URL:
    raw_url = os.environ.get("TEST_DATABASE_URL")
    if not raw_url:
        pytest.skip(
            "TEST_DATABASE_URL is not configured; PostgreSQL integration "
            "tests will not fall back to DATABASE_URL."
        )

    try:
        database_url = make_url(raw_url)
    except Exception:
        pytest.fail("TEST_DATABASE_URL is not a valid SQLAlchemy URL.")

    if database_url.get_backend_name() != "postgresql":
        pytest.fail("TEST_DATABASE_URL must use PostgreSQL, not another backend.")
    if database_url.database != EXPECTED_TEST_DATABASE:
        pytest.fail(
            "TEST_DATABASE_URL must target the dedicated "
            f"{EXPECTED_TEST_DATABASE} database."
        )
    return database_url


@pytest.fixture(scope="session")
def postgres_engine(test_database_url: URL) -> Generator[Engine, None, None]:
    engine = create_engine(test_database_url, pool_pre_ping=True)
    try:
        try:
            with engine.connect() as connection:
                actual_database = connection.execute(
                    text("SELECT current_database()")
                ).scalar_one()
                if actual_database != EXPECTED_TEST_DATABASE:
                    pytest.fail(
                        "Connected database is not the dedicated integration "
                        "test database."
                    )

                try:
                    applied_revisions = set(
                        connection.execute(
                            text("SELECT version_num FROM alembic_version")
                        ).scalars()
                    )
                except SQLAlchemyError:
                    pytest.fail(
                        "The integration test database has no readable "
                        "Alembic version table. Apply migrations first."
                    )
        except SQLAlchemyError:
            pytest.fail(
                "Could not connect to the dedicated PostgreSQL test database."
            )

        alembic_config = Config(str(PROJECT_ROOT / "alembic.ini"))
        expected_heads = set(
            ScriptDirectory.from_config(alembic_config).get_heads()
        )
        if applied_revisions != expected_heads:
            pytest.fail(
                "The integration test database is not at the current "
                "Alembic head. Apply migrations before running tests."
            )

        yield engine
    finally:
        engine.dispose()


@pytest.fixture
def db_session(postgres_engine: Engine) -> Generator[Session, None, None]:
    connection = postgres_engine.connect()
    outer_transaction = connection.begin()
    session = Session(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    try:
        yield session
    finally:
        session.close()
        if outer_transaction.is_active:
            outer_transaction.rollback()
        connection.close()
