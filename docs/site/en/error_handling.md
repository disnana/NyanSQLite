# Error Handling

NyanSQLite-specific errors inherit from `NyanSQLiteError`. Pydantic input failures raise `pydantic.ValidationError`; SQLite failures retain the exception type of the active backend.

```python
from pydantic import BaseModel, ValidationError
from nyansqlite import NyanSQLite, QueryValidationError, SchemaMismatchError

class User(BaseModel):
    id: int
    age: int

with NyanSQLite("app.db") as db:
    try:
        db.register(User)
        db.update(User, where={"id": 1}, age="invalid")
    except SchemaMismatchError as exc:
        print(f"Existing table differs from the model: {exc}")
    except ValidationError as exc:
        print(f"Invalid update value: {exc}")
    except QueryValidationError as exc:
        print(f"Invalid filter: {exc}")
```

`register()` checks an existing table's columns, types, primary key, nullability, and FTS searchable columns against the model. A mismatch raises `SchemaMismatchError`; it does not migrate tables or FTS definitions. Preview the steps with `db.plan_migration(Model)`, apply them with `db.migrate(Model)`, then register the model (see Schema migration below).

For ordinary models, `update()` validates the types and constraints of changed fields. With custom field or model validators or model configuration, it validates affected rows inside the transaction before writing. A validation failure leaves the rows unchanged.

An exception inside `atomic()` rolls the transaction back. The async client also keeps the connection protected until an in-flight SQLite call completes after cancellation.

See the [exception reference](./exceptions) for the available classes.

## Schema migration

After changing a model, bring the existing table in line with `migrate()` before `register()`.

```python
plan = db.plan_migration(User)   # reads only; nothing is changed
print(plan)                      # readable summary
print(plan.sql)                  # the SQL that would run

db.migrate(User)                 # applies data-preserving changes directly
db.register(User)
```

| Change | Behavior |
| --- | --- |
| Add a column (`Optional` or has a default) | Runs directly (`ALTER TABLE ... ADD COLUMN`) |
| NOT NULL -> nullable | Runs directly (the table is rebuilt) |
| Drop a column, change a type, nullable -> NOT NULL | Needs `allow_destructive=True` |
| Add a required column with no default to a table that has rows | Blocked with `MigrationError`; add a default or make it `Optional` |
| Change `Searchable` fields | Rebuilds only the full-text table; source data is untouched |

```python
db.migrate(User, allow_destructive=True)   # allow drops and type changes
```

- Everything runs in one transaction and rolls back on failure. Inside `atomic()` it rolls back with the outer block.
- A table rebuild copies rows into a new table and checks that the values fit the new types before swapping. Moving `"abc"` into an integer column raises `MigrationError` and leaves the original table unchanged.
- Defaults come from the field's `default=`. `default_factory` produces a different value per call, so it cannot fill existing rows.
- Take a backup first with `VACUUM INTO` if you need one.
- Async: `await db.migrate(...)` and `await db.plan_migration(...)`.

### Stating what cannot be inferred

Changes that the types cannot express are written by the caller.

**Renaming a column**: put `__nyan_renames__ = {"new_name": "old_name"}` on the model. Without it, a rename is treated as dropping the old column and adding a new one, and the values are not carried over.

```python
class User(BaseModel):
    __nyan_renames__ = {"email": "email_address"}
    id: int
    name: str
    email: str
```

**Values for new or converted columns**: pass `fill=`. Each value is a constant or a function that receives an existing row (a dict of column name to stored value).

```python
db.migrate(User, fill={
    "tier": lambda row: "pro" if row["age"] >= 20 else "free",   # new required column
    "day": lambda row: int(row["day"].replace("/", "")),          # type change (also needs allow_destructive=True)
})
```

- `__nyan_renames__` and `fill=` are ignored for columns that are already migrated, so they can stay in your start-up code and run again safely.
- Values returned by `fill=` are checked against the new column type. A mismatch raises `MigrationError` and rolls everything back.
- A migration that uses `fill=` still needs `allow_destructive=True` when it drops columns or changes types.

### Migrating during registration

```python
db.register(User)                                   # default: SchemaMismatchError on a mismatch
db.register(User, on_mismatch="migrate")            # apply data-preserving changes automatically
db.register(User, on_mismatch="migrate", allow_destructive=True)   # also drops and type changes
```

Even with `on_mismatch="migrate"`, changes that can alter data need `allow_destructive=True`. `allow_destructive`, `backup`, and `fill` are passed to `migrate()`.

### Backup

```python
db.migrate(User, allow_destructive=True, backup=True)          # copies to app.db.bak-<timestamp>
db.migrate(User, allow_destructive=True, backup="before.db")   # choose the location
```

No backup is taken by default. SQLite's `VACUUM INTO` runs before any change.

- Nothing is copied when there are no changes, or when the migration is refused for lack of permission.
- An existing target file raises `MigrationError`.
- It cannot be used with `:memory:` databases or inside `atomic()`.
- The path is available as `plan.backup_path` on the returned plan.
