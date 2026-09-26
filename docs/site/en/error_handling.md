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

`register()` checks an existing table's columns, types, primary key, nullability, and FTS searchable columns against the model. A mismatch raises `SchemaMismatchError`; it does not migrate tables or FTS definitions. Back up and explicitly migrate existing data before registering the changed model.

For ordinary models, `update()` validates the types and constraints of changed fields. With custom field or model validators or model configuration, it validates affected rows inside the transaction before writing. A validation failure leaves the rows unchanged.

An exception inside `atomic()` rolls the transaction back. The async client also keeps the connection protected until an in-flight SQLite call completes after cancellation.

See the [exception reference](./exceptions) for the available classes.
