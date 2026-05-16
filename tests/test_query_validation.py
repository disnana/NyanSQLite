import pytest
from pydantic import BaseModel

from nyansqlite import NyanSQLite, NyanSQLiteAIO
from nyansqlite.exceptions import FieldNotFoundError, QueryValidationError


class User(BaseModel):
    id: int
    name: str
    age: int

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
    assert "Cannot extend values" in str(excinfo.value)

    # Test null keyword filter
    res = await db.query(User, age=None)
    assert len(res) == 0

    # Test unknown filter operator
    with pytest.raises(ValueError) as excinfo:
        await db.query(User, age__unknown=10)
    assert "Unknown filter operator" in str(excinfo.value)

    # Test raw string filter
    await db.query(User, "age > 0")

def test_sync_field_not_found_in_where():
    db = NyanSQLite(":memory:")
    db.register(User)
    with pytest.raises(FieldNotFoundError):
        db.query(User, non_existent__gt=10)

    with pytest.raises(FieldNotFoundError):
        db.query(User, invalid_field=1)

def test_sync_unknown_operator():
    db = NyanSQLite(":memory:")
    db.register(User)
    with pytest.raises(ValueError) as excinfo:
        db.query(User, age__unknown=10)
    assert "Unknown filter operator" in str(excinfo.value) or "不明なフィルタ演算子" in str(excinfo.value)

def test_sync_in_operator_validation():
    db = NyanSQLite(":memory:")
    db.register(User)
    with pytest.raises(QueryValidationError) as excinfo:
        db.query(User, age__in=123)
    assert "イテラブルである必要があります" in str(excinfo.value) or "must be iterable" in str(excinfo.value)

def test_sync_is_null_operators():
    db = NyanSQLite(":memory:")
    db.register(User)
    db.query(User, age__is_null=True)
    db.query(User, age__is_null=False)
    db.query(User, age=None)
