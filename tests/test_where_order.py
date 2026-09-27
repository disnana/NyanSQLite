"""Keyword filter ordering must keep bindings and validation semantics."""

from types import SimpleNamespace

import pytest
from pydantic import BaseModel

from nyansqlite import FieldNotFoundError, NyanSQLite, NyanSQLiteAIO
from nyansqlite.core import _build_where as sync_build_where
from nyansqlite.core_aio import _build_where as async_build_where


@pytest.mark.parametrize("build_where", [sync_build_where, async_build_where])
def test_equivalent_filters_reuse_sql_with_matching_bindings(build_where):
    first = build_where(("id > 0",), {"b__in": [2, 3], "a__gte": 1, "c__is_null": True})
    second = build_where(("id > 0",), {"c__is_null": True, "a__gte": 1, "b__in": [2, 3]})

    assert first == second
    assert first == ('WHERE "id" > ? AND "a" >= ? AND "b" IN (?, ?) AND "c" IS NULL', [0, 1, 2, 3])
    assert build_where((), {"b__in": [], "a": 1}) == ('WHERE "a" = ? AND 0', [1])


@pytest.mark.parametrize("build_where", [sync_build_where, async_build_where])
def test_first_invalid_filter_still_raises_first(build_where):
    meta = SimpleNamespace(hints={"a": int})

    with pytest.raises(FieldNotFoundError, match="z"):
        build_where((), {"z": 1, "b": 2}, model_meta=meta)


class FilterRecord(BaseModel):
    id: int
    a: int
    b: int


def test_sync_keyword_permutations_return_same_records():
    with NyanSQLite() as db:
        db.register(FilterRecord)
        db.insert(FilterRecord(id=1, a=2, b=3))
        db.insert(FilterRecord(id=2, a=2, b=4))

        assert db.query(FilterRecord, b__in=[3], a=2) == db.query(FilterRecord, a=2, b__in=[3])


@pytest.mark.asyncio
async def test_async_keyword_permutations_return_same_records():
    async with NyanSQLiteAIO() as db:
        await db.register(FilterRecord)
        await db.insert(FilterRecord(id=1, a=2, b=3))
        await db.insert(FilterRecord(id=2, a=2, b=4))

        assert await db.query(FilterRecord, b__in=[3], a=2) == await db.query(FilterRecord, a=2, b__in=[3])
