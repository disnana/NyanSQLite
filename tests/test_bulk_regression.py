"""Bulk writes remain atomic and serialization stays off the async loop."""

import threading

import pytest
from pydantic import BaseModel, field_validator

from nyansqlite import NyanSQLite, NyanSQLiteAIO


class BulkRecord(BaseModel):
    id: int
    data: dict[str, int]


class ValidatedRecord(BaseModel):
    id: int
    name: str

    @field_validator("name")
    @classmethod
    def normalize(cls, value: str) -> str:
        return value.upper()


def test_large_executemany_and_rollback():
    with NyanSQLite() as db:
        db.register(BulkRecord)
        records = [BulkRecord(id=i, data={"i": i}) for i in range(17000)]
        assert db.insert_many(records) == len(records)
        assert db.get(BulkRecord, id=16999) == records[-1]
        with pytest.raises(Exception):
            db.insert_many([BulkRecord(id=17000, data={"i": 1}), BulkRecord(id=0, data={"i": 2})])
        assert db.get(BulkRecord, id=17000) is None


def test_tuple_rows_respect_column_order_and_pydantic_validation():
    with NyanSQLite() as db:
        # Existing tables can have a different column order from the model.
        db.execute_raw('CREATE TABLE "validated_record" ("name" TEXT NOT NULL, "id" INTEGER PRIMARY KEY)')
        db.register(ValidatedRecord)
        db.execute_raw('INSERT INTO "validated_record" ("name", "id") VALUES (?, ?)', ("mixed", 1))
        assert db.query(ValidatedRecord) == [ValidatedRecord(id=1, name="MIXED")]


@pytest.mark.asyncio
async def test_async_bulk_serialization_on_worker_and_rollback():
    async with NyanSQLiteAIO() as db:
        await db.register(BulkRecord)
        loop_thread = threading.get_ident()
        observed = []
        meta = db._meta(BulkRecord)
        original = meta.encoders["data"]

        def track(value):
            observed.append(threading.get_ident())
            return original(value)

        meta.encoders["data"] = track
        assert await db.insert_many([BulkRecord(id=i, data={"i": i}) for i in range(100)]) == 100
        assert observed and all(t != loop_thread for t in observed)
        with pytest.raises(Exception):
            await db.insert_many([BulkRecord(id=100, data={"i": 100}), BulkRecord(id=0, data={"i": 0})])
        assert await db.get(BulkRecord, id=100) is None
