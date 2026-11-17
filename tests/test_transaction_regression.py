import asyncio
import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest
from pydantic import BaseModel, create_model

from nyansqlite import NyanSQLite, NyanSQLiteAIO
from nyansqlite.exceptions import ModelNotRegisteredError, TableNameCollisionError


class Record(BaseModel):
    id: int


def test_sync_registration_follows_atomic_outcome():
    with NyanSQLite() as db:
        with pytest.raises(RuntimeError, match="rollback"):
            with db.atomic():
                db.register(Record)
                db.insert(Record(id=1))
                assert db.get(Record, id=1) == Record(id=1)
                raise RuntimeError("rollback")
        assert not db.registered_models()
        with pytest.raises(ModelNotRegisteredError):
            db.query(Record)

        with db.atomic():
            db.register(Record)
            db.insert(Record(id=2))
        assert db.query(Record) == [Record(id=2)]


async def test_async_registration_follows_atomic_outcome():
    async with NyanSQLiteAIO() as db:
        with pytest.raises(RuntimeError, match="rollback"):
            async with db.atomic():
                await db.register(Record)
                await db.insert(Record(id=1))
                assert await db.get(Record, id=1) == Record(id=1)

                async def read_registry():
                    assert not db.registered_models()
                    with pytest.raises(ModelNotRegisteredError):
                        await db.query(Record)

                await asyncio.create_task(read_registry())
                raise RuntimeError("rollback")
        assert not db.registered_models()
        with pytest.raises(ModelNotRegisteredError):
            await db.query(Record)

        async with db.atomic():
            await db.register(Record)
        assert db.registered_models() == ["Record"]
        assert not await db.query(Record)


def test_sync_concurrent_registration_rejects_table_name_collision(monkeypatch):
    other_record = create_model("Record", id=(int, ...))
    with NyanSQLite() as db:
        lock = db._lock
        ready = threading.Barrier(2, timeout=5)

        class ConcurrentEntry:
            def __enter__(self):
                ready.wait()
                lock.acquire()

            def __exit__(self, *_):
                lock.release()

        with monkeypatch.context() as patch:
            patch.setattr(db, "_lock", ConcurrentEntry())
            with ThreadPoolExecutor(2) as workers:
                results = [workers.submit(db.register, model) for model in (Record, other_record)]
                errors = [result.exception() for result in results]

        assert sum(error is None for error in errors) == 1
        assert sum(isinstance(error, TableNameCollisionError) for error in errors) == 1
        assert db.registered_models() == ["Record"]


async def test_async_concurrent_registration_rejects_table_name_collision():
    other_record = create_model("Record", id=(int, ...))
    async with NyanSQLiteAIO() as db:
        results = await asyncio.gather(db.register(Record), db.register(other_record), return_exceptions=True)
        assert sum(result is None for result in results) == 1
        assert sum(isinstance(result, TableNameCollisionError) for result in results) == 1
        assert db.registered_models() == ["Record"]


def test_sqlite_automatic_rollback_preserves_constraint_error():
    with NyanSQLite() as db:
        if db.backend == "apsw":
            from apsw import ConstraintError
        else:
            ConstraintError = sqlite3.IntegrityError

        db.register(Record)
        with pytest.raises(ConstraintError):
            with db.atomic():
                db.insert(Record(id=1))
                db.execute_raw("INSERT OR ROLLBACK INTO record (id) VALUES (?)", (1,))
        assert not db.query(Record)
        db.insert(Record(id=1))
        assert db.count(Record) == 1


async def test_second_cancel_during_atomic_cleanup_leaves_no_open_transaction(monkeypatch):
    async with NyanSQLiteAIO() as db:
        await db.register(Record)
        inserted = asyncio.Event()
        cleanup_started = asyncio.Event()
        release_cleanup = threading.Event()
        loop = asyncio.get_running_loop()
        in_transaction = db._conn.in_transaction

        def pause_cleanup():
            active = in_transaction()
            if active:
                loop.call_soon_threadsafe(cleanup_started.set)
                assert release_cleanup.wait(5)
            return active

        monkeypatch.setattr(db._conn, "in_transaction", pause_cleanup)

        async def transaction():
            async with db.atomic():
                await db.insert(Record(id=1))
                inserted.set()
                await asyncio.Event().wait()

        task = asyncio.create_task(transaction())
        try:
            await asyncio.wait_for(inserted.wait(), 3)
            task.cancel()
            await asyncio.wait_for(cleanup_started.wait(), 3)
            task.cancel()
        finally:
            release_cleanup.set()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert not in_transaction()
        assert not await db.query(Record)


async def test_cancellation_during_successful_commit_keeps_registration(monkeypatch):
    async with NyanSQLiteAIO() as db:
        commit_started = asyncio.Event()
        release_commit = threading.Event()
        loop = asyncio.get_running_loop()
        raw = db._conn._raw

        def pause_commit(sql, params=()):
            if sql == "COMMIT":
                loop.call_soon_threadsafe(commit_started.set)
                assert release_commit.wait(5)
            return raw(sql, params)

        monkeypatch.setattr(db._conn, "_raw", pause_commit)

        async def transaction():
            async with db.atomic():
                await db.register(Record)
                await db.insert(Record(id=1))

        task = asyncio.create_task(transaction())
        try:
            await asyncio.wait_for(commit_started.wait(), 3)
            task.cancel()
        finally:
            release_commit.set()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert db.registered_models() == ["Record"]
        assert await db.query(Record) == [Record(id=1)]
