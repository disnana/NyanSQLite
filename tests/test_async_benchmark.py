"""Async bulk insert and model read benchmarks."""

import asyncio
from itertools import islice, permutations

from pydantic import BaseModel

from nyansqlite import NyanSQLiteAIO


class AsyncBenchRecord(BaseModel):
    id: int
    name: str
    payload: dict[str, int]


class AsyncFilterBenchRecord(BaseModel):
    id: int
    a: int
    b: int
    c: int
    d: int
    e: int
    f: int


def test_bulk_insert_async(benchmark):
    records = [AsyncBenchRecord(id=i, name=f"name-{i}", payload={"value": i}) for i in range(1000)]

    async def run():
        async with NyanSQLiteAIO() as db:
            await db.register(AsyncBenchRecord)
            await db.insert_many(records)

    benchmark.pedantic(lambda: asyncio.run(run()), rounds=10, iterations=1)


def test_query_models_async(benchmark):
    loop = asyncio.new_event_loop()
    try:
        db = NyanSQLiteAIO()
        loop.run_until_complete(db.register(AsyncBenchRecord))
        loop.run_until_complete(
            db.insert_many([AsyncBenchRecord(id=i, name=f"name-{i}", payload={"value": i}) for i in range(1000)])
        )
        benchmark.pedantic(lambda: loop.run_until_complete(db.query(AsyncBenchRecord)), rounds=30, iterations=1)
    finally:
        loop.run_until_complete(db.close())
        loop.close()


def test_query_permuted_filters_async(benchmark):
    fields = ("a", "b", "c", "d", "e", "f")
    filters = [{key: fields.index(key) for key in order} for order in islice(permutations(fields), 240)] * 2
    loop = asyncio.new_event_loop()
    try:
        db = NyanSQLiteAIO()
        loop.run_until_complete(db.register(AsyncFilterBenchRecord))
        loop.run_until_complete(db.insert(AsyncFilterBenchRecord(id=1, a=0, b=1, c=2, d=3, e=4, f=5)))

        async def run():
            for where in filters:
                await db.query(AsyncFilterBenchRecord, **where)

        benchmark.pedantic(lambda: loop.run_until_complete(run()), rounds=10, iterations=1)
    finally:
        loop.run_until_complete(db.close())
        loop.close()
