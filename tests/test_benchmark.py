"""Repeatable in-memory throughput benchmarks; run with pytest-benchmark."""

from pydantic import BaseModel

from nyansqlite import NyanSQLite


class BenchRecord(BaseModel):
    id: int
    name: str
    payload: dict[str, int]


def test_bulk_insert(benchmark):
    records = [BenchRecord(id=i, name=f"name-{i}", payload={"value": i}) for i in range(1000)]

    def run():
        with NyanSQLite() as db:
            db.register(BenchRecord)
            db.insert_many(records)

    benchmark(run)


def test_query_models(benchmark):
    with NyanSQLite() as db:
        db.register(BenchRecord)
        db.insert_many([BenchRecord(id=i, name=f"name-{i}", payload={"value": i}) for i in range(1000)])
        benchmark(lambda: db.query(BenchRecord))
