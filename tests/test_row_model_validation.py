"""Fast model reads still have the constructor's validation behavior."""

import pytest
from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator

from nyansqlite import NyanSQLite, NyanSQLiteAIO
from nyansqlite._row_validation import direct_row_validator


class PlainRecord(BaseModel):
    id: int
    age: int
    label: str


def test_fast_row_validation_keeps_error_details():
    with pytest.raises(ValidationError) as expected:
        PlainRecord(id=1, age="bad", label="ok")

    with NyanSQLite() as db:
        db.register(PlainRecord)
        db.execute_raw('INSERT INTO "plain_record" ("id", "age", "label") VALUES (?, ?, ?)', (1, "bad", "ok"))
        with pytest.raises(ValidationError) as actual:
            db.query(PlainRecord)

    assert actual.value.errors(include_url=False) == expected.value.errors(include_url=False)


def test_field_validator_runs_on_each_fast_row():
    seen = []

    class FieldChecked(BaseModel):
        id: int
        label: str

        @field_validator("label")
        @classmethod
        def observe(cls, value):
            seen.append(value)
            return value.upper()

    with NyanSQLite() as db:
        db.register(FieldChecked)
        db.execute_raw('INSERT INTO "field_checked" ("id", "label") VALUES (?, ?)', (1, "mixed"))
        assert db.query(FieldChecked)[0].label == "MIXED"
    assert seen == ["mixed"]


class ReplacingRecord(BaseModel):
    id: int

    @model_validator(mode="after")
    def replace(self):
        return type(self).model_construct(id=self.id + 10)


def test_model_validator_returning_another_instance_preserves_constructor_behavior():
    with NyanSQLite() as db:
        db.register(ReplacingRecord)
        db.execute_raw('INSERT INTO "replacing_record" ("id") VALUES (?)', (1,))
        with pytest.warns(UserWarning, match="returning a value other than"):
            assert db.query(ReplacingRecord)[0].id == 1


@pytest.mark.asyncio
async def test_async_model_validator_returning_another_instance():
    async with NyanSQLiteAIO() as db:
        await db.register(ReplacingRecord)
        await db.execute_raw('INSERT INTO "replacing_record" ("id") VALUES (?)', (1,))
        with pytest.warns(UserWarning, match="returning a value other than"):
            assert (await db.query(ReplacingRecord))[0].id == 1


def test_custom_construction_and_default_factory_use_the_constructor():
    class CustomInit(BaseModel):
        id: int

        def __init__(self, **data):
            super().__init__(**data)

    class FactoryRecord(BaseModel):
        id: int
        label: str = Field(default_factory=lambda: "generated")

    assert direct_row_validator(CustomInit) is None
    assert direct_row_validator(FactoryRecord) is None
    assert direct_row_validator(ReplacingRecord) is None


def test_model_rebuild_falls_back_to_current_constructor_validator():
    class RebuiltRecord(BaseModel):
        id: int

    with NyanSQLite() as db:
        db.register(RebuiltRecord)
        db.insert(RebuiltRecord(id=1))
        original = db._registry[RebuiltRecord].row_validator
        assert original is not None
        RebuiltRecord.model_rebuild(force=True)
        assert original is not RebuiltRecord.__pydantic_validator__
        assert db.query(RebuiltRecord) == [RebuiltRecord(id=1)]
