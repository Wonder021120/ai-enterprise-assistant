import os
from collections.abc import Generator
from functools import lru_cache

from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker


def _get_database_url() -> str:
    load_dotenv()
    database_url = os.getenv("DATABASE_URL")

    if not database_url or not database_url.strip():
        raise RuntimeError(
            "DATABASE_URL is not configured. "
            "Set it before using the database connection."
        )

    return database_url.strip()


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    """惰性创建并缓存 SQLAlchemy Engine。"""

    return create_engine(
        _get_database_url(),
        pool_pre_ping=True,
    )


@lru_cache(maxsize=1)
def get_session_factory() -> sessionmaker[Session]:
    """返回基于共享 Engine 的统一 Session 工厂。"""

    return sessionmaker(
        bind=get_engine(),
        class_=Session,
        autoflush=False,
        expire_on_commit=False,
    )


def get_db() -> Generator[Session, None, None]:
    """为单次请求提供 Session，并确保使用后关闭。"""

    database_session = get_session_factory()()

    try:
        yield database_session
    finally:
        database_session.close()


def check_database_connection() -> bool:
    """执行 SELECT 1，验证数据库连接是否可用。"""

    with get_engine().connect() as connection:
        result = connection.execute(text("SELECT 1"))
        return result.scalar_one() == 1
