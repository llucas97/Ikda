"""DB 연결. DATABASE_URL 이 PostgreSQL 이면 asyncpg, 없으면 SQLite(aiosqlite) 파일.

PostgreSQL 표는 db/migrations/*.sql 로 만든다(db/migrate.py).
SQLite 는 개발·테스트용이라 처음 연결할 때 모델에서 바로 만든다.
"""
from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import AsyncIterator

from sqlalchemy import DateTime, TypeDecorator, event
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import NullPool

DEFAULT_SQLITE = "sqlite+aiosqlite:///./ilgeodeurim.db"


class Base(DeclarativeBase):
    pass


class UTCDateTime(TypeDecorator):
    """timestamptz. 넣을 때 UTC 로 바꾸고, SQLite 처럼 시간대 없이 돌아오면 UTC 를 붙인다."""

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("시간대 없는 datetime 은 넣지 않는다 (utcnow() 를 쓸 것)")
        return value.astimezone(timezone.utc)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def database_url() -> str:
    url = os.getenv("DATABASE_URL", "").strip()
    if not url:
        return DEFAULT_SQLITE
    for prefix in ("postgresql://", "postgres://", "postgresql+psycopg://"):
        if url.startswith(prefix):
            return "postgresql+asyncpg://" + url[len(prefix):]
    if url.startswith("sqlite://") and not url.startswith("sqlite+aiosqlite://"):
        return "sqlite+aiosqlite://" + url[len("sqlite://"):]
    return url


_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None
_ready = False
_lock = asyncio.Lock()


def _make_engine(url: str) -> AsyncEngine:
    if url.startswith("sqlite"):
        # 연결을 이벤트 루프 사이에 돌려쓰지 않는다 (TestClient 는 요청마다 루프가 다를 수 있다).
        engine = create_async_engine(url, poolclass=NullPool, connect_args={"timeout": 15})

        @event.listens_for(engine.sync_engine, "connect")
        def _fk_on(dbapi_conn, _):  # SQLite 는 외래키 검사를 켜야 한다
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA foreign_keys=ON")
            cur.close()

        return engine
    if os.getenv("DB_NULL_POOL") == "1":  # 테스트처럼 이벤트 루프가 여러 개일 때
        return create_async_engine(url, poolclass=NullPool)
    return create_async_engine(url, pool_pre_ping=True)


async def _ensure() -> async_sessionmaker[AsyncSession]:
    global _engine, _sessionmaker, _ready
    if _ready and _sessionmaker is not None:
        return _sessionmaker
    async with _lock:
        if not _ready:
            from .auth import models  # noqa: F401  표 정의를 메타데이터에 올린다
            from .family import models as _family_models  # noqa: F401

            url = database_url()
            _engine = _make_engine(url)
            if url.startswith("sqlite") or os.getenv("DB_AUTO_CREATE") == "1":
                async with _engine.begin() as conn:
                    await conn.run_sync(Base.metadata.create_all)
            _sessionmaker = async_sessionmaker(_engine, expire_on_commit=False)
            _ready = True
    assert _sessionmaker is not None
    return _sessionmaker


@asynccontextmanager
async def session_scope() -> AsyncIterator[AsyncSession]:
    maker = await _ensure()
    async with maker() as session:
        yield session


async def get_session() -> AsyncIterator[AsyncSession]:
    async with session_scope() as session:
        yield session


async def reset() -> None:
    """테스트용: 다음 연결 때 DATABASE_URL 을 다시 읽는다."""
    global _engine, _sessionmaker, _ready
    if _engine is not None:
        await _engine.dispose()
    _engine, _sessionmaker, _ready = None, None, False
