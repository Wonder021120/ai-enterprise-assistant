from __future__ import annotations

from contextlib import nullcontext
from pathlib import Path
import runpy
from unittest.mock import MagicMock

from alembic import context as alembic_context
from alembic.config import Config
from alembic.script import ScriptDirectory

from app.db import session as db_session
from app.db.base import Base
import app.db.models  # noqa: F401 - registers every ORM model on Base.metadata


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ALEMBIC_INI = PROJECT_ROOT / "alembic.ini"
ALEMBIC_DIRECTORY = PROJECT_ROOT / "alembic"
ALEMBIC_ENV = ALEMBIC_DIRECTORY / "env.py"

EXPECTED_TABLES = {
    "analysis_runs",
    "analysis_skill_matches",
    "candidates",
    "job_skills",
    "jobs",
    "learning_plan_items",
    "learning_plans",
    "resumes",
    "skills",
}


def _execute_env(
    monkeypatch,
    *,
    offline: bool,
    database_url: str = "postgresql+psycopg://user:p%25ss@localhost/db",
) -> tuple[
    dict[str, object],
    MagicMock,
    MagicMock,
    MagicMock,
    MagicMock,
    object,
]:
    config = Config()
    configure = MagicMock()
    run_migrations = MagicMock()
    get_engine = MagicMock()
    fake_engine = MagicMock()
    fake_connection = object()
    fake_engine.connect.return_value.__enter__.return_value = fake_connection
    get_engine.return_value = fake_engine

    monkeypatch.setattr(
        alembic_context,
        "config",
        config,
        raising=False,
    )
    monkeypatch.setattr(
        alembic_context,
        "is_offline_mode",
        lambda: offline,
    )
    monkeypatch.setattr(alembic_context, "configure", configure)
    monkeypatch.setattr(
        alembic_context,
        "begin_transaction",
        nullcontext,
    )
    monkeypatch.setattr(alembic_context, "run_migrations", run_migrations)
    monkeypatch.setattr(
        db_session,
        "_get_database_url",
        lambda: database_url,
    )
    monkeypatch.setattr(db_session, "get_engine", get_engine)
    monkeypatch.setattr(
        db_session,
        "load_dotenv",
        MagicMock(side_effect=AssertionError(".env must not be read")),
    )

    namespace = runpy.run_path(str(ALEMBIC_ENV))
    return (
        namespace,
        configure,
        run_migrations,
        get_engine,
        fake_engine,
        fake_connection,
    )


def test_base_metadata_contains_exactly_nine_business_tables() -> None:
    assert set(Base.metadata.tables) == EXPECTED_TABLES


def test_alembic_configuration_is_parseable_and_has_no_database_url() -> None:
    config = Config(str(ALEMBIC_INI))
    script_directory = ScriptDirectory.from_config(config)

    assert Path(config.get_main_option("script_location")).resolve() == (
        ALEMBIC_DIRECTORY.resolve()
    )
    assert config.get_main_option("sqlalchemy.url") == ""
    assert Path(script_directory.dir).resolve() == ALEMBIC_DIRECTORY.resolve()

    ini_content = ALEMBIC_INI.read_text(encoding="utf-8")
    assert "driver://user:pass" not in ini_content
    assert "DATABASE_URL" not in ini_content


def test_standard_migration_layout_and_template_exist() -> None:
    versions_directory = ALEMBIC_DIRECTORY / "versions"
    script_template = ALEMBIC_DIRECTORY / "script.py.mako"

    assert ALEMBIC_ENV.is_file()
    assert (ALEMBIC_DIRECTORY / "README").is_file()
    assert versions_directory.is_dir()
    assert script_template.is_file()

    template_content = script_template.read_text(encoding="utf-8")
    assert "revision: str = ${repr(up_revision)}" in template_content
    assert "def upgrade() -> None:" in template_content
    assert "def downgrade() -> None:" in template_content


def test_offline_environment_uses_base_metadata_without_connecting(
    monkeypatch,
) -> None:
    database_url = (
        "postgresql+psycopg://careerpilot:p%25word@localhost/careerpilot_db"
    )
    (
        namespace,
        configure,
        run_migrations,
        get_engine,
        _fake_engine,
        _fake_connection,
    ) = _execute_env(
        monkeypatch,
        offline=True,
        database_url=database_url,
    )

    assert namespace["target_metadata"] is Base.metadata
    assert set(namespace["target_metadata"].tables) == EXPECTED_TABLES
    get_engine.assert_not_called()
    configure.assert_called_once()
    configure_options = configure.call_args.kwargs
    assert configure_options["url"] == database_url
    assert configure_options["target_metadata"] is Base.metadata
    assert configure_options["literal_binds"] is True
    assert configure_options["compare_type"] is True
    assert configure_options["compare_server_default"] is True
    run_migrations.assert_called_once_with()


def test_online_environment_reuses_shared_engine_without_real_connection(
    monkeypatch,
) -> None:
    (
        namespace,
        configure,
        run_migrations,
        get_engine,
        fake_engine,
        fake_connection,
    ) = _execute_env(
        monkeypatch,
        offline=False,
    )

    assert namespace["target_metadata"] is Base.metadata
    get_engine.assert_called_once_with()
    fake_engine.connect.assert_called_once_with()
    configure.assert_called_once_with(
        connection=fake_connection,
        target_metadata=Base.metadata,
        compare_type=True,
        compare_server_default=True,
    )
    run_migrations.assert_called_once_with()
