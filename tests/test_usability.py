import inspect
import sys
from contextlib import asynccontextmanager
from enum import Enum
from typing import ClassVar, Optional

import pytest
from pydantic import (
    AliasChoices,
    AliasPath,
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)

from nyansqlite import (
    CompositeIndex,
    Indexed,
    NyanSQLite,
    NyanSQLiteAIO,
    QueryValidationError,
    SchemaMismatchError,
    Searchable,
    TableNameCollisionError,
    UniqueIndexed,
)


class Item(BaseModel):
    id: int
    age: int
    label: Optional[str] = None


class Normalized(BaseModel):
    id: int
    label: str

    @field_validator("label")
    @classmethod
    def normalize(cls, value):
        return value.strip().lower()


class AliasItem(BaseModel):
    id: int
    label: str = Field(alias="name")


class Tagged(BaseModel):
    category: ClassVar[str] = "a"
    id: int


class Role(Enum):
    ADMIN = "admin"


class Profile(BaseModel):
    id: int
    roles: list[Role]


class Excluded(BaseModel):
    id: int
    secret: str = Field(exclude=True)


class Account(BaseModel):
    id: int
    email: UniqueIndexed[str]


class API:
    def __init__(self, db):
        self.db = db

    async def call(self, method, *args, **kwargs):
        result = getattr(self.db, method)(*args, **kwargs)
        return await result if inspect.isawaitable(result) else result

    @asynccontextmanager
    async def atomic(self):
        if isinstance(self.db, NyanSQLiteAIO):
            async with self.db.atomic():
                yield
        else:
            with self.db.atomic():
                yield


@pytest.fixture(params=[NyanSQLite, NyanSQLiteAIO], ids=["sync", "async"])
async def api(request, backend):
    adapter = API(request.param())
    try:
        yield adapter
    finally:
        await adapter.call("close")


@pytest.fixture(params=["apsw", "sqlite3"])
def backend(request, monkeypatch):
    if request.param == "sqlite3":
        monkeypatch.setitem(sys.modules, "apsw", None)
    return request.param


pytestmark = pytest.mark.asyncio


async def test_failed_batch_is_atomic(api):
    await api.call("register", Item)
    await api.call("insert", Item(id=1, age=1))
    async with api.atomic():
        with pytest.raises(Exception):
            await api.call("insert_many", [Item(id=2, age=2), Item(id=1, age=3)])
    assert await api.call("count", Item, id=2) == 0


async def test_caught_inner_atomic_rolls_back(api):
    await api.call("register", Item)
    async with api.atomic():
        try:
            async with api.atomic():
                await api.call("insert", Item(id=1, age=1))
                raise ValueError("inner failure")
        except ValueError:
            pass
    assert await api.call("count", Item) == 0


async def test_update_saves_normalized_value(api):
    await api.call("register", Normalized)
    await api.call("insert", Normalized(id=1, label="abc"))
    await api.call("update", Normalized, {"id": 1}, label=" XYZ ")
    assert await api.call("select", Normalized, ["label"]) == [{"label": "xyz"}]


async def test_existing_index_enforces_uniqueness(api):
    await api.call("execute_raw", "CREATE TABLE account(id INTEGER PRIMARY KEY, email TEXT NOT NULL)")
    await api.call("execute_raw", "CREATE INDEX idx_account_email ON account(email)")
    with pytest.raises(SchemaMismatchError, match="index"):
        await api.call("register", Account)
    assert api.db.registered_models() == []



async def test_enum_list_roundtrip(api):
    await api.call("register", Profile)
    obj = Profile(id=1, roles=[Role.ADMIN])
    await api.call("insert", obj)
    assert await api.call("get", Profile, id=1) == obj


async def test_alias_roundtrip(api):
    await api.call("register", AliasItem)
    obj = AliasItem(id=1, name="alice")
    await api.call("insert", obj)
    assert await api.call("get", AliasItem, id=1) == obj


async def test_classvar_is_not_a_column(api):
    await api.call("register", Tagged)
    columns = await api.call("execute_raw", 'PRAGMA table_info("tagged")')
    assert [col["name"] for col in columns] == ["id"]


async def test_excluded_field_has_consistent_insert_behavior(api):
    await api.call("register", Excluded)
    await api.call("insert_many", [Excluded(id=1, secret="a")])
    await api.call("insert", Excluded(id=2, secret="b"))
    assert await api.call("count", Excluded) == 2


async def test_insert_revalidates_mutated_instance(api):
    await api.call("register", Item)
    obj = Item(id=1, age=1)
    obj.age = "invalid"
    with pytest.raises(ValidationError):
        await api.call("insert", obj)
    assert await api.call("count", Item) == 0


async def test_filter_rejects_invalid_integer(api):
    await api.call("register", Item)
    await api.call("insert", Item(id=1, age=1))
    with pytest.raises(QueryValidationError):
        await api.call("query", Item, age__gt="not_a_number")


async def test_not_equal_none_matches_nonnull_rows(api):
    await api.call("register", Item)
    await api.call("insert_many", [Item(id=1, age=1), Item(id=2, age=2, label="x")])
    assert [obj.id for obj in await api.call("query", Item, label__ne=None)] == [2]


async def test_is_null_rejects_string_boolean(api):
    await api.call("register", Item)
    with pytest.raises(QueryValidationError):
        await api.call("query", Item, label__is_null="False")


async def test_caught_inner_failure_preserves_outer_work(api):
    await api.call("register", Item)
    async with api.atomic():
        await api.call("insert", Item(id=1, age=1))
        with pytest.raises(ValueError):
            async with api.atomic():
                await api.call("insert", Item(id=2, age=2))
                raise ValueError("discard inner only")
        await api.call("insert", Item(id=3, age=3))
    assert [row.id for row in await api.call("query", Item, order_by="id")] == [1, 3]


async def test_failed_batch_without_outer_transaction_rolls_back(api):
    await api.call("register", Item)
    with pytest.raises(Exception):
        await api.call("insert_many", [Item(id=1, age=1), Item(id=1, age=2)])
    assert await api.call("count", Item) == 0


async def test_full_update_persists_row_dependent_fields_and_fts(api):
    class Article(BaseModel):
        id: int
        title: Searchable[str]
        suffix: str

        @model_validator(mode="after")
        def normalize(self):
            self.title = self.title.strip().lower()
            self.suffix = f"{self.title}-{self.id}"
            return self

    await api.call("register", Article)
    await api.call("insert_many", [Article(id=i, title="old", suffix="") for i in (1, 2)])
    assert await api.call("update", Article, {}, title=" NEW ") == 2
    assert await api.call("select", Article, ["title", "suffix"], order_by="id") == [
        {"title": "new", "suffix": "new-1"}, {"title": "new", "suffix": "new-2"},
    ]
    assert len(await api.call("search", Article, "new")) == 2
    assert await api.call("search", Article, "old") == []


async def test_validated_update_rolls_back_database_constraint_errors(api):
    class Named(BaseModel):
        id: int
        label: UniqueIndexed[str]

        @field_validator("label")
        @classmethod
        def normalize(cls, value):
            return value.strip().lower()

    await api.call("register", Named)
    await api.call("insert_many", [Named(id=1, label="a"), Named(id=2, label="b")])
    with pytest.raises(Exception):
        await api.call("update", Named, {}, label=" SAME ")
    assert [row.label for row in await api.call("query", Named, order_by="id")] == ["a", "b"]


async def test_nested_aliases_exclusions_and_enums_roundtrip(api):
    class Inner(BaseModel):
        value: str = Field(alias="text", exclude=True)

    class Outer(BaseModel):
        id: int
        inner: Inner
        items: list[Inner]
        roles: list[Role]

    Outer.model_rebuild(_types_namespace={"Inner": Inner})
    obj = Outer(id=1, inner=Inner(text="private"), items=[Inner(text="nested")], roles=[Role.ADMIN])
    await api.call("register", Outer)
    await api.call("insert", obj)
    restored = await api.call("get", Outer, id=1)
    assert restored == obj
    obj.id = 2
    assert await api.call("insert_many", [obj]) == 1
    assert await api.call("get", Outer, id=2) == obj
    obj.inner.value = 123
    with pytest.raises(ValidationError):
        await api.call("insert", obj)


async def test_alias_choices_paths_and_alias_update(api):
    class Aliased(BaseModel):
        id: int
        first: str = Field(validation_alias=AliasChoices("name", "first"))
        second: str = Field(validation_alias=AliasPath("parts", 1))
        third: int = Field(validation_alias=AliasPath("other", -1))

    obj = Aliased(id=1, name="a", parts=[None, "b"], other=[3])
    await api.call("register", Aliased)
    await api.call("insert", obj)
    assert await api.call("get", Aliased, id=1) == obj
    assert await api.call("update", Aliased, {"id": 1}, first="new") == 1
    assert (await api.call("get", Aliased, id=1)).first == "new"


async def test_field_constraints_and_bulk_mutation_validation(api):
    class Positive(BaseModel):
        id: int
        age: int = Field(ge=0)

    await api.call("register", Positive)
    bad = Positive(id=1, age=1)
    bad.age = -1
    with pytest.raises(ValidationError):
        await api.call("insert_many", [Positive(id=2, age=2), bad])
    assert await api.call("count", Positive) == 0
    await api.call("insert", Positive(id=3, age=3))
    assert len(await api.call("query", Positive, age__gt=-100)) == 1


async def test_reserved_field_names_and_empty_select(api):
    class Reserved(BaseModel):
        id: int
        limit: int
        offset: int
        order_by: str
        desc: bool
        where: str

    await api.call("register", Reserved)
    await api.call("insert_many", [
        Reserved(id=1, limit=1, offset=2, order_by="x", desc=True, where="y"),
        Reserved(id=2, limit=2, offset=2, order_by="z", desc=False, where="y"),
    ])
    rows = await api.call("query", Reserved, where={"limit": 1, "where": "y"}, limit=1)
    assert [row.id for row in rows] == [1]
    assert (await api.call("get", Reserved, limit=2)).id == 2
    assert await api.call("select", Reserved, ["id"], where={"order_by": "x"}) == [{"id": 1}]
    assert await api.call("count", Reserved, where={"limit": 1}) == 1
    assert await api.call("exists", Reserved, where={"desc": False})
    assert await api.call("delete", Reserved, where={"limit": 2}) == 1
    with pytest.raises(QueryValidationError, match="Duplicate"):
        await api.call("query", Reserved, where={"id": 1}, id=2)
    with pytest.raises(QueryValidationError, match="at least one"):
        await api.call("select", Reserved, [])


async def test_filter_iterables_null_and_errors_are_consistent(api):
    await api.call("register", Item)
    await api.call("insert_many", [Item(id=1, age=1), Item(id=2, age=2, label="x")])
    assert len(await api.call("query", Item, id__in=(i for i in (1, 2)))) == 2
    assert [row.id for row in await api.call("query", Item, label__eq=None)] == [1]
    assert await api.call("delete", Item, age__in=[]) == 0
    with pytest.raises(QueryValidationError):
        await api.call("delete", Item, age__in=["invalid"])
    with pytest.raises(QueryValidationError):
        await api.call("update", Item, {"age__gt": "invalid"}, age=4)
    with pytest.raises(QueryValidationError):
        await api.call("query", Item, age__unknown=1)
    assert await api.call("count", Item) == 2


async def test_custom_table_name_and_collision(api):
    class First(BaseModel):
        __tablename__ = "chosen_table"
        id: int
        text: Searchable[str]

    class Second(BaseModel):
        __tablename__ = "chosen_table"
        id: int
        text: str

    await api.call("register", First)
    await api.call("insert", First(id=1, text="hello"))
    assert (await api.call("search", First, "hello"))[0].id == 1
    with pytest.raises(TableNameCollisionError):
        await api.call("register", Second)
    assert await api.call("execute_raw", 'SELECT id FROM "chosen_table"') == [{"id": 1}]


@pytest.mark.parametrize("definition", [
    'CREATE INDEX idx_account_email ON account(email)',
    'CREATE UNIQUE INDEX idx_account_email ON account(id)',
    'CREATE UNIQUE INDEX idx_account_email ON account(email) WHERE id > 1',
    'CREATE UNIQUE INDEX idx_account_email ON account(email COLLATE NOCASE)',
])
async def test_index_drift_is_detected_without_mutating_data(api, definition):
    await api.call("execute_raw", "CREATE TABLE account(id INTEGER PRIMARY KEY, email TEXT NOT NULL)")
    await api.call("execute_raw", definition)
    await api.call("execute_raw", "INSERT INTO account VALUES (1, 'a')")
    with pytest.raises(SchemaMismatchError):
        await api.call("register", Account)
    assert await api.call("execute_raw", "SELECT * FROM account") == [{"id": 1, "email": "a"}]


async def test_composite_indexes_are_checked(api):
    class Pair(BaseModel):
        __nyan_indexes__ = [CompositeIndex("left", "right", unique=True)]
        id: int
        left: str
        right: str

    await api.call("execute_raw", "CREATE TABLE pair(id INTEGER PRIMARY KEY, left TEXT NOT NULL, right TEXT NOT NULL)")
    await api.call("execute_raw", "CREATE UNIQUE INDEX idx_pair_left_right ON pair(right, left)")
    with pytest.raises(SchemaMismatchError):
        await api.call("register", Pair)


async def test_constrained_and_configured_models_still_validate(api):
    class Configured(BaseModel):
        model_config = ConfigDict(str_strip_whitespace=True)
        id: int
        label: Indexed[str]

    await api.call("register", Configured)
    obj = Configured(id=1, label="old")
    obj.label = " new "
    await api.call("insert", obj)
    assert await api.call("select", Configured, ["label"]) == [{"label": "new"}]
    await api.call("update", Configured, {"id": 1}, label=" updated ")
    assert await api.call("select", Configured, ["label"]) == [{"label": "updated"}]


async def test_missing_mutated_fields_raise_validation_error(api):
    await api.call("register", Item)
    obj = Item(id=1, age=1)
    del obj.age
    with pytest.raises(ValidationError):
        await api.call("insert", obj)
    assert await api.call("count", Item) == 0


async def test_alias_paths_sharing_positive_and_negative_indices(api):
    class Ends(BaseModel):
        id: int
        first: str = Field(validation_alias=AliasPath("parts", 0))
        last: str = Field(validation_alias=AliasPath("parts", -1))

    await api.call("register", Ends)
    obj = Ends(id=1, parts=["first", "last"])
    await api.call("insert", obj)
    assert await api.call("get", Ends, id=1) == obj
