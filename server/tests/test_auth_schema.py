"""db/migrations/*.sql 과 SQLAlchemy 모델이 같은 표·컬럼·유니크 인덱스를 갖는지."""
from __future__ import annotations

import re
from pathlib import Path

from app.auth import models  # noqa: F401
from app.db import Base
from app.family import models as family_models  # noqa: F401

SQL = "\n".join(p.read_text(encoding="utf-8") for p in sorted((Path(__file__).parents[1] / "db" / "migrations").glob("V*.sql")))


def _sql_tables() -> dict[str, set[str]]:
    out = {}
    for name, body in re.findall(r"CREATE TABLE IF NOT EXISTS (\w+) \((.*?)\n\);", SQL, re.S):
        cols = {line.strip().split()[0] for line in body.strip().splitlines() if line.strip()}
        out[name] = {c for c in cols if c.upper() not in ("CONSTRAINT", "PRIMARY", "UNIQUE")}
    for table, col in re.findall(r"ALTER TABLE (\w+) ADD COLUMN IF NOT EXISTS (\w+)", SQL):
        out.setdefault(table, set()).add(col)
    return out


def test_migration_matches_models():
    sql = _sql_tables()
    model = {t.name: {c.name for c in t.columns} for t in Base.metadata.sorted_tables}
    assert sql == model


def test_unique_indexes_match():
    sql = set(re.findall(r"CREATE UNIQUE INDEX IF NOT EXISTS (\w+)", SQL))
    model = {i.name for t in Base.metadata.sorted_tables for i in t.indexes if i.unique}
    assert sql == model


def test_all_timestamps_are_timestamptz():
    assert "TIMESTAMP " not in SQL.replace("TIMESTAMPTZ", "") and "timestamp without" not in SQL
