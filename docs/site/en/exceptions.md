# Exceptions

NyanSQLite exports these exception classes:

| Exception | When it occurs |
| --- | --- |
| `NyanSQLiteError` | Base class for the library-specific exceptions below |
| `ModelNotRegisteredError` | A model is used before registration |
| `FieldNotFoundError` | A field is absent from the model |
| `QueryValidationError` | A filter or pagination value is invalid |
| `SearchNotEnabledError` | `search()` is called on a model without searchable fields |
| `TableNameCollisionError` | Different models map to the same table name |
| `SchemaMismatchError` | An existing table differs from the model being registered |

Invalid model input or update values raise Pydantic's `ValidationError`. SQLite failures retain APSW or `sqlite3` exception types; they are not wrapped in `NyanSQLiteError`.

```python
from pydantic import ValidationError
from nyansqlite import NyanSQLiteError, SchemaMismatchError

try:
    # Register a model or perform an operation.
    ...
except SchemaMismatchError:
    # Explicit schema migration is required.
    ...
except ValidationError:
    # A model value is invalid.
    ...
except NyanSQLiteError:
    # Another library-specific error occurred.
    ...
```
