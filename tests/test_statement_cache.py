"""Statement cache settings reach both SQLite backends without changing defaults."""

import sys

import pytest
from pydantic import BaseModel

from nyansqlite import NyanSQLite, NyanSQLiteAIO


class CacheRecord(BaseModel):
    id: int


def test_sync_statement_cache_size():
    with NyanSQLite(statement_cache_size=256) as db:
        db.register(CacheRecord)
        db.insert(CacheRecord(id=1))
        assert db.query(CacheRecord, id=1) == [CacheRecord(id=1)]
        if db.backend == "apsw":
            assert db._conn._conn.cache_stats()["size"] == 256


@pytest.mark.asyncio
async def test_async_statement_cache_size():
    async with NyanSQLiteAIO(statement_cache_size=256) as db:
        await db.register(CacheRecord)
        await db.insert(CacheRecord(id=1))
        assert await db.query(CacheRecord, id=1) == [CacheRecord(id=1)]
        if db.backend == "apsw":
            assert db._conn._conn.cache_stats()["size"] == 256


@pytest.mark.parametrize("size", [-1, True, 1.5, "256"])
def test_statement_cache_size_rejects_invalid_values(size):
    with pytest.raises(ValueError, match="statement_cache_size"):
        NyanSQLite(statement_cache_size=size)
    with pytest.raises(ValueError, match="statement_cache_size"):
        NyanSQLiteAIO(statement_cache_size=size)


def test_sqlite_fallback_accepts_statement_cache_size(monkeypatch):
    monkeypatch.setitem(sys.modules, "apsw", None)
    with NyanSQLite(statement_cache_size=256) as db:
        assert db.backend == "sqlite3"
        db.register(CacheRecord)
        db.insert(CacheRecord(id=1))
        assert db.query(CacheRecord, id=1) == [CacheRecord(id=1)]
