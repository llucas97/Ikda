"""db/migrations/V*.sql 을 이름 순서대로 PostgreSQL 에 한 번씩 적용한다.

    DATABASE_URL=postgresql://ilgeo:ilgeo@localhost:5432/ilgeodeurim python db/migrate.py

적용한 파일은 sy_schema_migration 에 남겨 두고, 다음 실행 때 건너뛴다.
파일 하나는 트랜잭션 하나로 적용한다(실패하면 그 파일만 통째로 되돌린다).
"""
from __future__ import annotations

import asyncio
import hashlib
import os
import sys
from pathlib import Path

import asyncpg

MIGRATIONS = Path(__file__).resolve().parent / "migrations"


def _dsn(url: str) -> str:
    # SQLAlchemy 식 'postgresql+asyncpg://' 도 받는다.
    for prefix in ("postgresql+asyncpg://", "postgresql+psycopg://", "postgres://"):
        if url.startswith(prefix):
            return "postgresql://" + url[len(prefix):]
    return url


async def migrate(url: str) -> list[str]:
    conn = await asyncpg.connect(_dsn(url))
    applied: list[str] = []
    try:
        await conn.execute(
            """CREATE TABLE IF NOT EXISTS sy_schema_migration (
                   version VARCHAR(200) PRIMARY KEY,
                   checksum CHAR(64) NOT NULL,
                   applied_at TIMESTAMPTZ NOT NULL DEFAULT now())"""
        )
        done = {r["version"]: r["checksum"] for r in await conn.fetch("SELECT version, checksum FROM sy_schema_migration")}
        for path in sorted(MIGRATIONS.glob("V*.sql")):
            sql = path.read_text(encoding="utf-8")
            checksum = hashlib.sha256(sql.encode("utf-8")).hexdigest()
            if path.name in done:
                if done[path.name] != checksum:
                    print(f"경고: 이미 적용한 {path.name} 내용이 바뀌었어요. 새 V 파일로 고치세요.", file=sys.stderr)
                continue
            async with conn.transaction():
                await conn.execute(sql)
                await conn.execute(
                    "INSERT INTO sy_schema_migration (version, checksum) VALUES ($1, $2)", path.name, checksum
                )
            applied.append(path.name)
    finally:
        await conn.close()
    return applied


def main() -> None:
    url = os.getenv("DATABASE_URL", "")
    if not url.startswith(("postgres", "postgresql")):
        sys.exit("DATABASE_URL 에 PostgreSQL 주소를 넣어 주세요 (SQLite 는 서버가 알아서 만든다).")
    applied = asyncio.run(migrate(url))
    print("적용:", ", ".join(applied) if applied else "새로 적용할 파일 없음")


if __name__ == "__main__":
    main()
