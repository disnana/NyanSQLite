from datetime import date, datetime

import pytest
from pydantic import BaseModel

from nyansqlite import CompositeIndex, NyanSQLite, NyanSQLiteAIO
from nyansqlite.exceptions import FieldNotFoundError, QueryValidationError


class User(BaseModel):
    id: int
    name: str
    age: int


class Event(BaseModel):
    id: int
    name: str
    happened_on: date
    happened_at: datetime
    tags: list[str]


class OtherUser(BaseModel):
    id: int
    nickname: str


def test_schema_rejects_unsafe_identifiers_and_unknown_composite_fields():
    UnsafeModel = type('User"; DROP TABLE user; --', (BaseModel,), {
        "__annotations__": {"id": int},
    })
    db = NyanSQLite(":memory:")
    with pytest.raises(ValueError, match="Invalid SQLite identifier"):
        db.register(UnsafeModel)

    class InvalidIndexModel(BaseModel):
        id: int
        __nyan_indexes__ = [CompositeIndex("missing")]

    with pytest.raises(ValueError, match="unknown fields"):
        db.register(InvalidIndexModel)

def test_sync_query_validation_errors():
    db = NyanSQLite(":memory:")
    db.register(User)

    # Test __gt with non-comparable type
    class NonComparable:
        pass

    with pytest.raises(QueryValidationError) as excinfo:
        db.query(User, age__gt=NonComparable())
    assert "Cannot apply '>'" in str(excinfo.value) or "演算子を適用できません" in str(excinfo.value)

    # Test __gte with non-comparable type
    with pytest.raises(QueryValidationError):
        db.query(User, age__gte=NonComparable())

    # Test __lt with non-comparable type
    with pytest.raises(QueryValidationError):
        db.query(User, age__lt=NonComparable())

    # Test __lte with non-comparable type
    with pytest.raises(QueryValidationError):
        db.query(User, age__lte=NonComparable())

    # Test __in with non-iterable type
    with pytest.raises(QueryValidationError):
        db.query(User, age__in=123)

    with pytest.raises(QueryValidationError):
        db.query(User, "age > 0 OR 1=1")

    with pytest.raises(QueryValidationError):
        db.query(User, "age BETWEEN 1 AND 10")

@pytest.mark.asyncio
async def test_async_query_validation_errors():
    db = NyanSQLiteAIO(":memory:")
    await db.register(User)

    # Test __gt with non-comparable type
    class NonComparable:
        pass

    with pytest.raises(QueryValidationError) as excinfo:
        await db.query(User, age__gt=NonComparable())
    assert "Cannot apply '>'" in str(excinfo.value)

    # Test other operators
    with pytest.raises(QueryValidationError):
        await db.query(User, age__gte=NonComparable())
    with pytest.raises(QueryValidationError):
        await db.query(User, age__lt=NonComparable())
    with pytest.raises(QueryValidationError):
        await db.query(User, age__lte=NonComparable())

    # Test __in with non-iterable type
    with pytest.raises(QueryValidationError) as excinfo:
        await db.query(User, age__in=123)
    assert "expects iterable" in str(excinfo.value)

    # Test __in with something that fails during extend
    class FakeIterable:
        def __len__(self):
            return 1

        def __iter__(self):
            raise TypeError("Not really iterable")

    with pytest.raises(QueryValidationError) as excinfo:
        await db.query(User, age__in=FakeIterable())
    assert "expects iterable" in str(excinfo.value)

    # Test null keyword filter
    res = await db.query(User, age=None)
    assert len(res) == 0

    # Test unknown filter operator
    with pytest.raises(ValueError) as excinfo:
        await db.query(User, age__unknown=10)
    assert "Unknown filter operator" in str(excinfo.value)

    # Test raw string filter
    await db.query(User, "age > 0")

    with pytest.raises(QueryValidationError):
        await db.query(User, "age > 0 OR 1=1")

    with pytest.raises(QueryValidationError):
        await db.query(User, "age BETWEEN 1 AND 10")

def test_sync_field_not_found_in_where():
    db = NyanSQLite(":memory:")
    db.register(User)
    with pytest.raises(FieldNotFoundError):
        db.query(User, non_existent__gt=10)

    with pytest.raises(FieldNotFoundError):
        db.query(User, invalid_field=1)


@pytest.mark.asyncio
async def test_async_field_not_found_in_where():
    db = NyanSQLiteAIO(":memory:")
    await db.register(User)

    with pytest.raises(FieldNotFoundError):
        await db.query(User, non_existent__gt=10)

    with pytest.raises(FieldNotFoundError):
        await db.query(User, invalid_field=1)

    with pytest.raises(FieldNotFoundError):
        await db.update(User, where={"invalid_field": 1}, name="bad")


def test_sync_filter_values_are_serialized():
    db = NyanSQLite(":memory:")
    db.register(Event)
    event = Event(
        id=1,
        name="release",
        happened_on=date(2026, 6, 6),
        happened_at=datetime(2026, 6, 6, 12, 30, 0),
        tags=["sqlite", "apsw"],
    )
    db.insert(event)

    assert db.count(Event, happened_on=date(2026, 6, 6)) == 1
    assert db.count(Event, happened_at=datetime(2026, 6, 6, 12, 30, 0)) == 1
    assert db.count(Event, tags=["sqlite", "apsw"]) == 1


@pytest.mark.asyncio
async def test_async_filter_values_are_serialized():
    db = NyanSQLiteAIO(":memory:")
    await db.register(Event)
    event = Event(
        id=1,
        name="release",
        happened_on=date(2026, 6, 6),
        happened_at=datetime(2026, 6, 6, 12, 30, 0),
        tags=["sqlite", "apsw"],
    )
    await db.insert(event)

    assert await db.count(Event, happened_on=date(2026, 6, 6)) == 1
    assert await db.count(Event, happened_at=datetime(2026, 6, 6, 12, 30, 0)) == 1
    assert await db.count(Event, tags=["sqlite", "apsw"]) == 1


def test_sync_limit_offset_validation():
    db = NyanSQLite(":memory:")
    db.register(User)
    db.insert_many([
        User(id=1, name="Alice", age=20),
        User(id=2, name="Bob", age=30),
    ])

    assert [user.id for user in db.query(User, offset=1, order_by="id")] == [2]

    with pytest.raises(QueryValidationError):
        db.query(User, limit=-1)

    with pytest.raises(QueryValidationError):
        db.query(User, offset=-1)

    with pytest.raises(QueryValidationError):
        db.query(User, limit="bad")

    for invalid in (1.5, True, "1"):
        with pytest.raises(QueryValidationError):
            db.query(User, limit=invalid)
        with pytest.raises(QueryValidationError):
            db.query(User, offset=invalid)


@pytest.mark.asyncio
async def test_async_limit_offset_validation():
    db = NyanSQLiteAIO(":memory:")
    await db.register(User)
    await db.insert_many([
        User(id=1, name="Alice", age=20),
        User(id=2, name="Bob", age=30),
    ])

    assert [user.id for user in await db.query(User, offset=1, order_by="id")] == [2]

    with pytest.raises(QueryValidationError):
        await db.query(User, limit=-1)

    with pytest.raises(QueryValidationError):
        await db.query(User, offset=-1)

    with pytest.raises(QueryValidationError):
        await db.query(User, limit="bad")

    for invalid in (1.5, True, "1"):
        with pytest.raises(QueryValidationError):
            await db.query(User, limit=invalid)
        with pytest.raises(QueryValidationError):
            await db.query(User, offset=invalid)


def test_sync_insert_many_rejects_mixed_models():
    db = NyanSQLite(":memory:")
    db.register(User)

    with pytest.raises(TypeError):
        db.insert_many([User(id=1, name="Alice", age=30), OtherUser(id=2, nickname="Bob")])


@pytest.mark.asyncio
async def test_async_insert_many_rejects_mixed_models():
    db = NyanSQLiteAIO(":memory:")
    await db.register(User)

    with pytest.raises(TypeError):
        await db.insert_many([User(id=1, name="Alice", age=30), OtherUser(id=2, nickname="Bob")])

def test_sync_unknown_operator():
    db = NyanSQLite(":memory:")
    db.register(User)
    with pytest.raises(ValueError) as excinfo:
        db.query(User, age__unknown=10)
    assert "Unknown filter operator" in str(excinfo.value) or "不明なフィルタ演算子" in str(excinfo.value)

def test_sync_in_operator_validation():
    db = NyanSQLite(":memory:")
    db.register(User)
    db.insert_many([
        User(id=1, name="Alice", age=20),
        User(id=2, name="Bob", age=30),
        User(id=3, name="Carol", age=40),
    ])

    assert {u.name for u in db.query(User, age__in=[20, 40])} == {"Alice", "Carol"}
    assert db.query(User, age__in=[]) == []

    with pytest.raises(QueryValidationError) as excinfo:
        db.query(User, age__in=123)
    assert "イテラブルである必要があります" in str(excinfo.value) or "must be iterable" in str(excinfo.value)


@pytest.mark.asyncio
async def test_async_in_operator_validation():
    db = NyanSQLiteAIO(":memory:")
    await db.register(User)
    await db.insert_many([
        User(id=1, name="Alice", age=20),
        User(id=2, name="Bob", age=30),
        User(id=3, name="Carol", age=40),
    ])

    assert {u.name for u in await db.query(User, age__in=[20, 40])} == {"Alice", "Carol"}
    assert await db.query(User, age__in=[]) == []

    with pytest.raises(QueryValidationError):
        await db.query(User, age__in=123)

def test_sync_is_null_operators():
    db = NyanSQLite(":memory:")
    db.register(User)
    db.query(User, age__is_null=True)
    db.query(User, age__is_null=False)
    db.query(User, age=None)
