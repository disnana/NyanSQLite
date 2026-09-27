"""Async bulk insert and model read benchmarks."""

import asyncio

from pydantic import BaseModel

from nyansqlite import NyanSQLiteAIO


class AsyncBenchRecord(BaseModel):
    id: int
    name: str
    payload: dict[str, int]


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
        loop.run_until_complete(db.insert_many([
            AsyncBenchRecord(id=i, name=f"name-{i}", payload={"value": i}) for i in range(1000)
        ]))
        benchmark.pedantic(lambda: loop.run_until_complete(db.query(AsyncBenchRecord)), rounds=30, iterations=1)
    finally:
        loop.run_until_complete(db.close())
        loop.close()
