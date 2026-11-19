import sqlite3
from typing import Optional

import pytest
from pydantic import BaseModel, Field

from nyansqlite import (
    Indexed,
    MigrationError,
    NyanSQLite,
    NyanSQLiteAIO,
    SchemaMismatchError,
    Searchable,
)


def make_v1():
    class User(BaseModel):
        id: int
        name: str
        age: int

    return User


def table_sql(path, name="user"):
    with sqlite3.connect(path) as raw:
        return raw.execute("SELECT sql FROM sqlite_master WHERE name=?", (name,)).fetchone()[0]


@pytest.fixture
def path(tmp_path):
    return str(tmp_path / "m.db")


@pytest.fixture
def seeded(path):
    User = make_v1()
    with NyanSQLite(path) as db:
        db.register(User)
        db.insert_many([User(id=1, name="a", age=3), User(id=2, name="b", age=4)])
    return path


# ── additive changes ────────────────────────────────────────────────────── #

def test_register_still_refuses_changed_model(seeded):
    class User(BaseModel):
        id: int
        name: str
        age: int
        email: str = ""

    with NyanSQLite(seeded) as db:
        with pytest.raises(SchemaMismatchError, match="plan_migration"):
            db.register(User)


def test_add_columns_with_default_and_optional(seeded):
    class User(BaseModel):
        id: int
        name: str
        age: int
        email: str = "none@example.com"
        nick: Optional[str] = None
        score: float = 1.5
        active: bool = True
        tags: list[str] = []

    with NyanSQLite(seeded) as db:
        plan = db.migrate(User)
        assert [step.kind for step in plan.steps] == ["add_column"] * 5
        assert not plan.has_destructive
        db.register(User)
        rows = db.query(User)
        assert [r.email for r in rows] == ["none@example.com"] * 2
        assert all(r.nick is None and r.score == 1.5 and r.active and r.tags == [] for r in rows)
        db.insert(User(id=3, name="c", age=5, email="x@y"))
        assert db.get(User, id=3).email == "x@y"


def test_default_with_quote_is_escaped(seeded):
    class User(BaseModel):
        id: int
        name: str
        age: int
        note: str = "it's; DROP TABLE user; --"

    with NyanSQLite(seeded) as db:
        db.migrate(User)
        db.register(User)
        assert db.get(User, id=1).note == "it's; DROP TABLE user; --"
        assert db.count(User) == 2


def test_dry_run_does_not_touch_database(seeded):
    class User(BaseModel):
        id: int
        name: str
        age: int
        email: str = ""

    before = table_sql(seeded)
    with NyanSQLite(seeded) as db:
        plan = db.plan_migration(User)
        assert plan.sql and "ADD COLUMN" in plan.sql[0]
        assert "email" in str(plan)
        assert db.migrate(User, dry_run=True).sql == plan.sql
    assert table_sql(seeded) == before


def test_no_changes_is_empty_plan(seeded):
    with NyanSQLite(seeded) as db:
        plan = db.plan_migration(make_v1())
        assert plan.is_empty and not plan.sql


def test_missing_table_is_empty_plan(path):
    with NyanSQLite(path) as db:
        assert db.migrate(make_v1()).is_empty


# ── blocked / needs permission ──────────────────────────────────────────── #

def test_required_field_without_default_is_blocked_when_rows_exist(seeded):
    class User(BaseModel):
        id: int
        name: str
        age: int
        email: str

    with NyanSQLite(seeded) as db:
        plan = db.plan_migration(User)
        assert plan.blocked and not plan.steps
        with pytest.raises(MigrationError, match="no default"):
            db.migrate(User)


def test_default_factory_is_blocked_when_rows_exist(seeded):
    class User(BaseModel):
        id: int
        name: str
        age: int
        tags: list[str] = Field(default_factory=list)

    with NyanSQLite(seeded) as db:
        with pytest.raises(MigrationError, match="default_factory"):
            db.migrate(User)


def test_required_field_on_empty_table_rebuilds(path):
    with NyanSQLite(path) as db:
        db.register(make_v1())

    class User(BaseModel):
        id: int
        name: str
        age: int
        email: str

    with NyanSQLite(path) as db:
        plan = db.migrate(User)
        assert plan.steps[-1].kind == "rebuild_table"
        db.register(User)
        db.insert(User(id=1, name="a", age=1, email="e"))


def test_drop_column_requires_allow_destructive(seeded):
    class User(BaseModel):
        id: int
        name: str

    before = table_sql(seeded)
    with NyanSQLite(seeded) as db:
        plan = db.plan_migration(User)
        assert plan.has_destructive
        with pytest.raises(MigrationError, match="allow_destructive"):
            db.migrate(User)
    assert table_sql(seeded) == before

    with NyanSQLite(seeded) as db:
        db.migrate(User, allow_destructive=True)
        db.register(User)
        assert [r.name for r in db.query(User)] == ["a", "b"]
    assert "age" not in table_sql(seeded)


# ── type changes ────────────────────────────────────────────────────────── #

def test_type_change_converts_values(seeded):
    class User(BaseModel):
        id: int
        name: str
        age: str

    with NyanSQLite(seeded) as db:
        db.migrate(User, allow_destructive=True)
        db.register(User)
        assert [r.age for r in db.query(User)] == ["3", "4"]


def test_type_change_with_unconvertible_values_rolls_back(path):
    class Before(BaseModel):
        id: int
        label: str

    with NyanSQLite(path) as db:
        db.register(Before)
        db.insert_many([Before(id=1, label="12"), Before(id=2, label="abc")])

    class Before(BaseModel):  # same table name "before"
        id: int
        label: int

    original = table_sql(path, "before")
    with NyanSQLite(path) as db:
        with pytest.raises(MigrationError, match="cannot be stored as INTEGER"):
            db.migrate(Before, allow_destructive=True)
    assert table_sql(path, "before") == original
    with sqlite3.connect(path) as raw:
        assert raw.execute("SELECT label FROM before ORDER BY id").fetchall() == [("12",), ("abc",)]
        names = [r[0] for r in raw.execute("SELECT name FROM sqlite_master WHERE type='table'")]
        assert "before__nyan_new" not in names


def test_tighten_not_null_fails_and_rolls_back(path):
    class Item(BaseModel):
        id: int
        memo: Optional[str] = None

    with NyanSQLite(path) as db:
        db.register(Item)
        db.insert_many([Item(id=1, memo="x"), Item(id=2)])

    class Item(BaseModel):
        id: int
        memo: str

    with NyanSQLite(path) as db:
        with pytest.raises(MigrationError, match="rolled back"):
            db.migrate(Item, allow_destructive=True)
        assert table_sql(path, "item").count("NOT NULL") == 0


def test_relaxing_not_null_needs_no_flag(path):
    class Item(BaseModel):
        id: int
        memo: str

    with NyanSQLite(path) as db:
        db.register(Item)
        db.insert(Item(id=1, memo="x"))

    class Item(BaseModel):
        id: int
        memo: Optional[str] = None

    with NyanSQLite(path) as db:
        plan = db.migrate(Item)
        assert not plan.has_destructive
        db.register(Item)
        db.insert(Item(id=2))
        assert db.count(Item) == 2


# ── indexes, FTS, rowid ─────────────────────────────────────────────────── #

def test_rebuild_keeps_indexes_and_search(path):
    class Post(BaseModel):
        id: int
        author: Indexed[str]
        title: Searchable[str]
        views: int = 0

    with NyanSQLite(path) as db:
        db.register(Post)
        db.insert_many([Post(id=1, author="neko", title="SQLite intro"),
                        Post(id=2, author="inu", title="Pydantic notes")])

    class Post(BaseModel):
        id: int
        author: Indexed[str]
        title: Searchable[str]
        views: str = "0"   # int -> str forces a rebuild

    with NyanSQLite(path) as db:
        plan = db.migrate(Post, allow_destructive=True)
        assert [s.kind for s in plan.steps] == ["rebuild_fts", "rebuild_table"]
        db.register(Post)
        assert [p.id for p in db.search(Post, "SQLite")] == [1]
        assert db.query(Post, author="inu")[0].views == "0"
        db.insert(Post(id=3, author="neko", title="Another SQLite post"))
        assert {p.id for p in db.search(Post, "SQLite")} == {1, 3}
    with sqlite3.connect(path) as raw:
        assert raw.execute("SELECT name FROM sqlite_master WHERE name='idx_post_author'").fetchone()


def test_searchable_change_rebuilds_only_the_fts_table(path):
    class Post(BaseModel):
        id: int
        title: str
        body: str

    with NyanSQLite(path) as db:
        db.register(Post)
        db.insert(Post(id=1, title="hello world", body="cats"))

    class Post(BaseModel):
        id: int
        title: Searchable[str]
        body: str

    with NyanSQLite(path) as db:
        db.register(Post)  # no fts table yet: nothing to migrate

    class Post(BaseModel):
        id: int
        title: str
        body: Searchable[str]

    with NyanSQLite(path) as db:
        with pytest.raises(SchemaMismatchError):
            db.register(Post)
        plan = db.migrate(Post)
        assert [s.kind for s in plan.steps] == ["rebuild_fts"] and not plan.has_destructive
        db.register(Post)
        assert [p.id for p in db.search(Post, "cats")] == [1]


def test_table_without_id_keeps_rowid_values(path):
    class Note(BaseModel):
        text: str
        n: int

    with NyanSQLite(path) as db:
        db.register(Note)
        db.insert_many([Note(text="a", n=1), Note(text="b", n=2), Note(text="c", n=3)])
    with sqlite3.connect(path) as raw:
        raw.execute("DELETE FROM note WHERE text='a'")
        before = raw.execute("SELECT rowid, text FROM note ORDER BY rowid").fetchall()

    class Note(BaseModel):
        text: str
        n: str

    with NyanSQLite(path) as db:
        db.migrate(Note, allow_destructive=True)
    with sqlite3.connect(path) as raw:
        assert raw.execute("SELECT rowid, text FROM note ORDER BY rowid").fetchall() == before


# ── transactions and async ──────────────────────────────────────────────── #

def test_migrate_inside_atomic_rolls_back_with_outer_transaction(seeded):
    class User(BaseModel):
        id: int
        name: str
        age: int
        email: str = ""

    def migrate_then_abort(db):
        with db.atomic():
            db.migrate(User)
            raise RuntimeError("abort")

    before = table_sql(seeded)
    db = NyanSQLite(seeded)
    try:
        with pytest.raises(RuntimeError):
            migrate_then_abort(db)
    finally:
        db.close()
    assert table_sql(seeded) == before


async def test_async_migrate_roundtrip(seeded):
    class User(BaseModel):
        id: int
        name: str
        age: int
        email: str = "e"

    async with NyanSQLiteAIO(seeded) as db:
        with pytest.raises(SchemaMismatchError):
            await db.register(User)
        plan = await db.plan_migration(User)
        assert plan.sql
        await db.migrate(User)
        await db.register(User)
        assert [r.email for r in await db.query(User)] == ["e", "e"]


async def test_async_destructive_needs_flag(seeded):
    class User(BaseModel):
        id: int
        name: str

    async with NyanSQLiteAIO(seeded) as db:
        with pytest.raises(MigrationError):
            await db.migrate(User)
        await db.migrate(User, allow_destructive=True)
        await db.register(User)
        assert await db.count(User) == 2


# ── renames ─────────────────────────────────────────────────────────────── #

def make_renamed():
    class User(BaseModel):
        __nyan_renames__ = {"email": "email_address"}
        id: int
        name: str
        age: int
        email: str

    return User


@pytest.fixture
def seeded_email(path):
    class User(BaseModel):
        id: int
        name: str
        age: int
        email_address: str

    with NyanSQLite(path) as db:
        db.register(User)
        db.insert_many([User(id=1, name="a", age=3, email_address="a@x"),
                        User(id=2, name="b", age=4, email_address="b@x")])
    return path


def test_rename_keeps_values_and_is_not_destructive(seeded_email):
    User = make_renamed()
    with NyanSQLite(seeded_email) as db:
        plan = db.plan_migration(User)
        assert [s.kind for s in plan.steps] == ["rename_column"] and not plan.has_destructive
        assert 'RENAME COLUMN "email_address" TO "email"' in plan.sql[0]
        db.migrate(User)
        db.register(User)
        assert [r.email for r in db.query(User)] == ["a@x", "b@x"]


def test_rename_is_idempotent(seeded_email):
    User = make_renamed()
    with NyanSQLite(seeded_email) as db:
        db.migrate(User)
        assert db.plan_migration(User).is_empty
        db.migrate(User)  # runs again without error
        db.register(User)


def test_without_declared_rename_the_old_column_is_a_drop(seeded_email):
    class User(BaseModel):
        id: int
        name: str
        age: int
        email: str

    with NyanSQLite(seeded_email) as db:
        plan = db.plan_migration(User)
        assert plan.has_destructive and plan.blocked  # nothing can fill the new required column


def test_rename_with_other_changes(seeded_email):
    class User(BaseModel):
        __nyan_renames__ = {"email": "email_address"}
        id: int
        name: str
        age: int
        email: str
        active: bool = True

    with NyanSQLite(seeded_email) as db:
        plan = db.migrate(User)
        assert [s.kind for s in plan.steps] == ["rename_column", "add_column"]
        db.register(User)
        assert [(r.email, r.active) for r in db.query(User)] == [("a@x", True), ("b@x", True)]


def test_rename_where_both_columns_exist_is_blocked(path):
    class Before(BaseModel):
        id: int
        a: str
        b: str

    with NyanSQLite(path) as db:
        db.register(Before)

    class Before(BaseModel):
        __nyan_renames__ = {"b": "a"}
        id: int
        b: str

    with NyanSQLite(path) as db:
        assert "cannot be renamed" in db.plan_migration(Before).blocked[0]


def test_rename_of_unknown_field_is_blocked(seeded):
    class User(BaseModel):
        __nyan_renames__ = {"missing_field": "age"}
        id: int
        name: str
        age: int

    with NyanSQLite(seeded) as db:
        assert "not a field" in db.plan_migration(User).blocked[0]


# ── fill ────────────────────────────────────────────────────────────────── #

def test_fill_supplies_value_for_required_column(seeded):
    class User(BaseModel):
        id: int
        name: str
        age: int
        label: str

    with NyanSQLite(seeded) as db:
        with pytest.raises(MigrationError, match="fill="):
            db.migrate(User)
        plan = db.migrate(User, fill={"label": lambda row: f"{row['name']}-{row['age']}"})
        assert not plan.has_destructive and "Python" in plan.steps[-1].description
        db.register(User)
        assert [r.label for r in db.query(User)] == ["a-3", "b-4"]


def test_fill_constant_and_idempotent(seeded):
    class User(BaseModel):
        id: int
        name: str
        age: int
        score: int

    with NyanSQLite(seeded) as db:
        db.migrate(User, fill={"score": 10})
        db.register(User)
        assert [r.score for r in db.query(User)] == [10, 10]
        # The same call on every start-up is harmless once the table is migrated.
        assert db.migrate(User, fill={"score": 10}).is_empty


def test_fill_converts_existing_column(path):
    class Event(BaseModel):
        id: int
        day: str

    with NyanSQLite(path) as db:
        db.register(Event)
        db.insert_many([Event(id=1, day="2026/11/19"), Event(id=2, day="2026/12/01")])

    class Event(BaseModel):
        id: int
        day: int   # yyyymmdd as an integer

    to_int = lambda row: int(row["day"].replace("/", ""))  # noqa: E731
    with NyanSQLite(path) as db:
        with pytest.raises(MigrationError, match="allow_destructive"):
            db.migrate(Event, fill={"day": to_int})
        db.migrate(Event, allow_destructive=True, fill={"day": to_int})
        db.register(Event)
        assert [e.day for e in db.query(Event)] == [20261119, 20261201]


def test_fill_wrong_type_or_exception_rolls_back(seeded):
    class User(BaseModel):
        id: int
        name: str
        age: int
        score: int

    before = table_sql(seeded)
    with NyanSQLite(seeded) as db:
        with pytest.raises(MigrationError, match="cannot be stored as INTEGER"):
            db.migrate(User, fill={"score": "not a number"})
        with pytest.raises(MigrationError, match="rolled back"):
            db.migrate(User, fill={"score": lambda row: 1 / 0})
    assert table_sql(seeded) == before


def test_fill_for_unknown_field_is_blocked(seeded):
    with NyanSQLite(seeded) as db:
        with pytest.raises(MigrationError, match="not a field"):
            db.migrate(make_v1(), fill={"nope": 1})


def test_fill_handles_more_rows_than_one_chunk(path):
    class Row(BaseModel):
        id: int

    with NyanSQLite(path) as db:
        db.register(Row)
        db.insert_many([Row(id=i) for i in range(2500)])

    class Row(BaseModel):
        id: int
        double: int

    with NyanSQLite(path) as db:
        db.migrate(Row, fill={"double": lambda r: r["id"] * 2})
        db.register(Row)
        assert db.count(Row) == 2500
        assert db.get(Row, id=2499).double == 4998


# ── register(on_mismatch=...) ───────────────────────────────────────────── #

def test_register_on_mismatch_migrate_applies_safe_changes(seeded):
    class User(BaseModel):
        id: int
        name: str
        age: int
        email: str = ""

    with NyanSQLite(seeded) as db:
        with pytest.raises(SchemaMismatchError, match="on_mismatch"):
            db.register(User)
        db.register(User, on_mismatch="migrate")
        assert [r.email for r in db.query(User)] == ["", ""]


def test_register_on_mismatch_migrate_still_needs_permission_for_destructive(seeded):
    class User(BaseModel):
        id: int
        name: str

    before = table_sql(seeded)
    with NyanSQLite(seeded) as db:
        with pytest.raises(MigrationError, match="allow_destructive"):
            db.register(User, on_mismatch="migrate")
        db.register(User, on_mismatch="migrate", allow_destructive=True)
    assert table_sql(seeded) != before


def test_register_rejects_unknown_on_mismatch(seeded):
    with NyanSQLite(seeded) as db:
        with pytest.raises(ValueError, match="on_mismatch"):
            db.register(make_v1(), on_mismatch="auto")


def test_register_on_mismatch_migrate_creates_missing_tables(path):
    with NyanSQLite(path) as db:
        User = make_v1()
        db.register(User, on_mismatch="migrate")
        assert db.count(User) == 0


# ── backup ──────────────────────────────────────────────────────────────── #

def test_backup_is_off_by_default(seeded, tmp_path):
    class User(BaseModel):
        id: int
        name: str
        age: int
        email: str = ""

    with NyanSQLite(seeded) as db:
        plan = db.migrate(User)
    assert plan.backup_path is None
    assert not [p for p in tmp_path.iterdir() if ".bak" in p.name]


def test_backup_true_copies_database_before_changes(seeded, tmp_path):
    class User(BaseModel):
        id: int
        name: str

    with NyanSQLite(seeded) as db:
        plan = db.migrate(User, allow_destructive=True, backup=True)
    assert plan.backup_path and plan.backup_path.startswith(seeded + ".bak-")
    with sqlite3.connect(plan.backup_path) as raw:
        assert raw.execute("SELECT id, name, age FROM user ORDER BY id").fetchall() == [(1, "a", 3), (2, "b", 4)]
    assert "age" not in table_sql(seeded)


def test_backup_to_explicit_path(seeded, tmp_path):
    target = tmp_path / "before.db"

    class User(BaseModel):
        id: int
        name: str
        age: int
        email: str = ""

    with NyanSQLite(seeded) as db:
        db.migrate(User, backup=target)
    assert target.exists()
    assert "email" not in table_sql(str(target))
    class Later(BaseModel):
        id: int
        name: str
        age: int
        email: str = ""
        note: str = ""

    Later.__name__ = "User"
    with NyanSQLite(seeded) as db:
        with pytest.raises(MigrationError, match="already exists"):
            db.migrate(Later, backup=target)


def test_backup_not_taken_when_nothing_changes(seeded, tmp_path):
    with NyanSQLite(seeded) as db:
        plan = db.migrate(make_v1(), backup=True)
    assert plan.backup_path is None
    assert not [p for p in tmp_path.iterdir() if ".bak" in p.name]


def test_backup_is_not_taken_when_migration_is_refused(seeded, tmp_path):
    class User(BaseModel):
        id: int
        name: str

    with NyanSQLite(seeded) as db:
        with pytest.raises(MigrationError):
            db.migrate(User, backup=True)  # destructive without permission
    assert not [p for p in tmp_path.iterdir() if ".bak" in p.name]


def test_backup_needs_a_file_database():
    class User(BaseModel):
        id: int
        name: str
        age: int
        extra: str = ""

    with NyanSQLite() as db:
        db.register(make_v1())
        with pytest.raises(MigrationError, match="database file"):
            db.migrate(User, backup=True)


def test_backup_inside_atomic_is_refused(seeded):
    class User(BaseModel):
        id: int
        name: str
        age: int
        email: str = ""

    with NyanSQLite(seeded) as db:
        with db.atomic():
            with pytest.raises(MigrationError, match="transaction"):
                db.migrate(User, backup=True)


# ── async ───────────────────────────────────────────────────────────────── #

async def test_async_rename_fill_and_backup(seeded_email, tmp_path):
    class User(BaseModel):
        __nyan_renames__ = {"email": "email_address"}
        id: int
        name: str
        age: int
        email: str
        tier: str

    async with NyanSQLiteAIO(seeded_email) as db:
        plan = await db.migrate(User, fill={"tier": lambda row: "pro" if row["age"] > 3 else "free"}, backup=True)
        assert plan.backup_path
        await db.register(User)
        assert [(r.email, r.tier) for r in await db.query(User)] == [("a@x", "free"), ("b@x", "pro")]


async def test_async_register_on_mismatch_migrate(seeded):
    class User(BaseModel):
        id: int
        name: str
        age: int
        email: str = "e"

    async with NyanSQLiteAIO(seeded) as db:
        await db.register(User, on_mismatch="migrate")
        assert [r.email for r in await db.query(User)] == ["e", "e"]


def test_plan_migration_accepts_fill_without_changing_the_database(seeded):
    class User(BaseModel):
        id: int
        name: str
        age: int
        label: str

    before = table_sql(seeded)
    with NyanSQLite(seeded) as db:
        assert db.plan_migration(User).blocked          # no value for the new required column
        plan = db.plan_migration(User, fill={"label": "x"})
        assert not plan.blocked and "Python" in plan.steps[-1].description
    assert table_sql(seeded) == before


async def test_async_plan_migration_accepts_fill(seeded):
    class User(BaseModel):
        id: int
        name: str
        age: int
        label: str

    async with NyanSQLiteAIO(seeded) as db:
        plan = await db.plan_migration(User, fill={"label": "x"})
        assert not plan.blocked
