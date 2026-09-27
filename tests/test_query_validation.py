from datetime import date, datetime
from typing import Annotated

import pytest
from pydantic import BaseModel, Field, ValidationError, create_model, model_validator

from nyansqlite import CompositeIndex, NyanSQLite, NyanSQLiteAIO, Searchable
from nyansqlite._types import compile_deserializer, deserialize_value
from nyansqlite.exceptions import FieldNotFoundError, QueryValidationError, SchemaMismatchError


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


class Interval(BaseModel):
    id: int
    start: int
    end: int

    @model_validator(mode="after")
    def valid_range(self):
        if self.start > self.end:
            raise ValueError("start must not exceed end")
        return self


def test_deserialize_unhashable_annotated_metadata():
    annotation = Annotated[list[str], {"tag": []}]
    assert deserialize_value('["a", "b"]', annotation) == ["a", "b"]
    assert compile_deserializer(annotation)('["a", "b"]') == ["a", "b"]


@pytest.mark.parametrize(
    ("annotation", "value"),
    [
        (int, 12), (str, "hello"), (bool, 1), (list[str], '["a", "b"]'),
        (dict[str, int], '{"a": 1}'), (datetime, "2026-01-02T03:04:05"),
        (date, "2026-01-02"), (list[str], None), (datetime, None),
        (list[str], ["already decoded"]),
    ],
)
def test_compiled_deserializer_matches_direct_conversion(annotation, value):
    assert compile_deserializer(annotation)(value) == deserialize_value(value, annotation)


def test_json_decoder_preserves_stdlib_surrogate_behavior():
    value = r'{"text":"\ud800"}'
    assert compile_deserializer(dict)(value) == deserialize_value(value, dict)


@pytest.mark.parametrize("annotation,value", [
    (list[str], "not json"), (datetime, "not a date"), (date, "not a date"),
])
def test_compiled_deserializer_preserves_invalid_value_handling(annotation, value):
    with pytest.warns(RuntimeWarning):
        direct = deserialize_value(value, annotation)
    with pytest.warns(RuntimeWarning):
        compiled = compile_deserializer(annotation)(value)
    assert compiled == direct
    with pytest.raises(ValueError) as direct_error:
        deserialize_value(value, annotation, strict=True)
    with pytest.raises(ValueError) as compiled_error:
        compile_deserializer(annotation, strict=True)(value)
    assert str(compiled_error.value) == str(direct_error.value)


def test_sync_update_validates_all_affected_rows():
    with NyanSQLite(":memory:") as db:
        db.register(User)
        db.insert(User(id=1, name="Alice", age=20))
        with pytest.raises(ValidationError):
            db.update(User, where={"id": 1}, age="invalid")
        assert db.get(User, id=1).age == 20

        db.register(Interval)
        db.insert_many([Interval(id=1, start=1, end=10), Interval(id=2, start=10, end=20)])
        with pytest.raises(ValidationError):
            db.update(Interval, where={}, end=5)
        assert [row.end for row in db.query(Interval, order_by="id")] == [10, 20]

        class Positive(BaseModel):
            id: int
            value: int = Field(gt=0)

        db.register(Positive)
        db.insert(Positive(id=1, value=1))
        with pytest.raises(ValidationError):
            db.update(Positive, where={"id": 1}, value=0)
        assert db.get(Positive, id=1).value == 1


@pytest.mark.asyncio
async def test_async_update_validates_all_affected_rows():
    async with NyanSQLiteAIO(":memory:") as db:
        await db.register(User)
        await db.insert(User(id=1, name="Alice", age=20))
        with pytest.raises(ValidationError):
            await db.update(User, where={"id": 1}, age="invalid")
        assert (await db.get(User, id=1)).age == 20

        await db.register(Interval)
        await db.insert_many([Interval(id=1, start=1, end=10), Interval(id=2, start=10, end=20)])
        with pytest.raises(ValidationError):
            await db.update(Interval, where={}, end=5)
        assert [row.end for row in await db.query(Interval, order_by="id")] == [10, 20]


def test_sync_register_rejects_schema_drift(tmp_path):
    path = str(tmp_path / "schema.db")
    old_model = create_model("Record", id=(int, ...), name=(str, ...))
    new_model = create_model("Record", id=(int, ...), name=(str, ...), email=(str, ...))
    with NyanSQLite(path) as db:
        db.register(old_model)
    with NyanSQLite(path) as db:
        with pytest.raises(SchemaMismatchError, match="missing columns=.*email"):
            db.register(new_model)
        assert db.registered_models() == []
        db.register(old_model)
    changed_type = create_model("Record", id=(int, ...), name=(int, ...))
    with NyanSQLite(path) as db:
        with pytest.raises(SchemaMismatchError, match="incompatible columns=.*name"):
            db.register(changed_type)


def test_sync_register_rejects_fts_drift(tmp_path):
    path = str(tmp_path / "fts_schema.db")
    old_model = create_model("Article", id=(int, ...), title=(Searchable[str], ...), body=(str, ...))
    changed_model = create_model("Article", id=(int, ...), title=(str, ...), body=(Searchable[str], ...))
    plain_model = create_model("Article", id=(int, ...), title=(str, ...), body=(str, ...))
    with NyanSQLite(path) as db:
        db.register(old_model)
    with NyanSQLite(path) as db:
        with pytest.raises(SchemaMismatchError, match="searchable columns"):
            db.register(changed_model)
        with pytest.raises(SchemaMismatchError, match="searchable columns"):
            db.register(plain_model)
        assert db.registered_models() == []
        db.register(old_model)


def test_sync_new_fts_indexes_existing_rows(tmp_path):
    path = str(tmp_path / "fts_added.db")
    plain_model = create_model("Article", id=(int, ...), title=(str, ...))
    searchable_model = create_model("Article", id=(int, ...), title=(Searchable[str], ...))
    with NyanSQLite(path) as db:
        db.register(plain_model)
        db.insert(plain_model(id=1, title="existing text"))
    with NyanSQLite(path) as db:
        db.register(searchable_model)
        assert [row.id for row in db.search(searchable_model, "existing")] == [1]


@pytest.mark.asyncio
async def test_async_register_rejects_schema_drift(tmp_path):
    path = str(tmp_path / "schema_async.db")
    old_model = create_model("Record", id=(int, ...), name=(str, ...))
    new_model = create_model("Record", id=(int, ...), name=(str, ...), email=(str, ...))
    async with NyanSQLiteAIO(path) as db:
        await db.register(old_model)
    async with NyanSQLiteAIO(path) as db:
        with pytest.raises(SchemaMismatchError, match="missing columns=.*email"):
            await db.register(new_model)
        assert db.registered_models() == []
        await db.register(old_model)


@pytest.mark.asyncio
async def test_async_register_rejects_fts_drift(tmp_path):
    path = str(tmp_path / "fts_schema_async.db")
    old_model = create_model("Article", id=(int, ...), title=(Searchable[str], ...), body=(str, ...))
    changed_model = create_model("Article", id=(int, ...), title=(str, ...), body=(Searchable[str], ...))
    async with NyanSQLiteAIO(path) as db:
        await db.register(old_model)
    async with NyanSQLiteAIO(path) as db:
        with pytest.raises(SchemaMismatchError, match="searchable columns"):
            await db.register(changed_model)
        assert db.registered_models() == []
        await db.register(old_model)


@pytest.mark.asyncio
async def test_async_new_fts_indexes_existing_rows(tmp_path):
    path = str(tmp_path / "fts_added_async.db")
    plain_model = create_model("Article", id=(int, ...), title=(str, ...))
    searchable_model = create_model("Article", id=(int, ...), title=(Searchable[str], ...))
    async with NyanSQLiteAIO(path) as db:
        await db.register(plain_model)
        await db.insert(plain_model(id=1, title="existing text"))
    async with NyanSQLiteAIO(path) as db:
        await db.register(searchable_model)
        assert [row.id for row in await db.search(searchable_model, "existing")] == [1]


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
    assert [user.id for user in db.query(User, age__gte=20, limit=1, offset=1, order_by="id")] == [2]
    assert db.select(User, ["id"], age__gte=20, limit=1, offset=1, order_by="id") == [{"id": 2}]

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
    assert [user.id for user in await db.query(User, age__gte=20, limit=1, offset=1, order_by="id")] == [2]
    assert await db.select(User, ["id"], age__gte=20, limit=1, offset=1, order_by="id") == [{"id": 2}]

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
