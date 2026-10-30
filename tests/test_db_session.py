from importlib.util import find_spec
from unittest.mock import MagicMock, Mock, sentinel

import pytest


SQLALCHEMY_AVAILABLE = find_spec("sqlalchemy") is not None
pytestmark = pytest.mark.skipif(
    not SQLALCHEMY_AVAILABLE,
    reason="SQLAlchemy is not installed in the current environment",
)

if SQLALCHEMY_AVAILABLE:
    from app.db import session as db_session
else:
    db_session = None


@pytest.fixture(autouse=True)
def clear_database_caches():
    db_session.get_session_factory.cache_clear()
    db_session.get_engine.cache_clear()
    yield
    db_session.get_session_factory.cache_clear()
    db_session.get_engine.cache_clear()


def test_missing_database_url_raises_clear_error(monkeypatch):
    load_dotenv = Mock(return_value=False)
    create_engine = Mock()
    monkeypatch.setattr(db_session, "load_dotenv", load_dotenv)
    monkeypatch.setattr(db_session, "create_engine", create_engine)
    monkeypatch.delenv("DATABASE_URL", raising=False)

    with pytest.raises(RuntimeError, match="DATABASE_URL is not configured"):
        db_session.get_engine()

    load_dotenv.assert_called_once_with()
    create_engine.assert_not_called()


def test_engine_is_created_once_with_pre_ping(monkeypatch):
    database_url = (
        "postgresql+psycopg://test_user:test_password@localhost/test_db"
    )
    load_dotenv = Mock(return_value=False)
    create_engine = Mock(return_value=sentinel.engine)
    monkeypatch.setattr(db_session, "load_dotenv", load_dotenv)
    monkeypatch.setattr(db_session, "create_engine", create_engine)
    monkeypatch.setenv("DATABASE_URL", database_url)

    first_engine = db_session.get_engine()
    second_engine = db_session.get_engine()

    assert first_engine is sentinel.engine
    assert second_engine is sentinel.engine
    create_engine.assert_called_once_with(
        database_url,
        pool_pre_ping=True,
    )


def test_session_factory_uses_shared_engine(monkeypatch):
    get_engine = Mock(return_value=sentinel.engine)
    sessionmaker = Mock(return_value=sentinel.session_factory)
    monkeypatch.setattr(db_session, "get_engine", get_engine)
    monkeypatch.setattr(db_session, "sessionmaker", sessionmaker)

    first_factory = db_session.get_session_factory()
    second_factory = db_session.get_session_factory()

    assert first_factory is sentinel.session_factory
    assert second_factory is sentinel.session_factory
    get_engine.assert_called_once_with()
    sessionmaker.assert_called_once_with(
        bind=sentinel.engine,
        class_=db_session.Session,
        autoflush=False,
        expire_on_commit=False,
    )


def test_get_db_closes_session(monkeypatch):
    database_session = Mock()
    session_factory = Mock(return_value=database_session)
    monkeypatch.setattr(
        db_session,
        "get_session_factory",
        Mock(return_value=session_factory),
    )

    database_generator = db_session.get_db()

    assert next(database_generator) is database_session
    with pytest.raises(StopIteration):
        next(database_generator)

    database_session.close.assert_called_once_with()


def test_check_database_connection_executes_select_one(monkeypatch):
    result = Mock()
    result.scalar_one.return_value = 1
    connection = Mock()
    connection.execute.return_value = result
    connection_context = MagicMock()
    connection_context.__enter__.return_value = connection
    connection_context.__exit__.return_value = False
    engine = Mock()
    engine.connect.return_value = connection_context
    query = sentinel.query
    text = Mock(return_value=query)
    monkeypatch.setattr(db_session, "get_engine", Mock(return_value=engine))
    monkeypatch.setattr(db_session, "text", text)

    assert db_session.check_database_connection() is True

    text.assert_called_once_with("SELECT 1")
    connection.execute.assert_called_once_with(query)
    result.scalar_one.assert_called_once_with()
