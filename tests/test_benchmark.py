"""Repeatable in-memory throughput benchmarks; run with pytest-benchmark."""

from itertools import islice, permutations

from pydantic import BaseModel

from nyansqlite import NyanSQLite


class BenchRecord(BaseModel):
    id: int
    name: str
    payload: dict[str, int]


class FilterBenchRecord(BaseModel):
    id: int
    a: int
    b: int
    c: int
    d: int
    e: int
    f: int


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


def test_query_permuted_filters(benchmark):
    """Exercise prepared statement reuse when keyword order changes."""
    fields = ("a", "b", "c", "d", "e", "f")
    filters = [{key: fields.index(key) for key in order} for order in islice(permutations(fields), 240)] * 2

    with NyanSQLite() as db:
        db.register(FilterBenchRecord)
        db.insert(FilterBenchRecord(id=1, a=0, b=1, c=2, d=3, e=4, f=5))

        def run():
            for where in filters:
                db.query(FilterBenchRecord, **where)

        benchmark.pedantic(run, rounds=20, iterations=1)
