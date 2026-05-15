# Validation Guide

NyanSQLite leverages the powerful validation features of Pydantic v2.

## When to Use Validation

Validation is useful when you want to:

- Reject malformed records before saving them.
- Maintain consistent data types within your database.
- Automatically convert data passed as strings into appropriate types (e.g., int, datetime).

## Automatic Validation via Pydantic

NyanSQLite automatically performs Pydantic validation during insertion and updates when you `register()` a class that inherits from `BaseModel`.

```python
from pydantic import BaseModel, Field, EmailStr
from nyansqlite import NyanSQLite

class User(BaseModel):
    id: int
    name: str = Field(min_length=2)
    email: str # Requires pydantic[email] to use EmailStr
    age: int = Field(ge=0, le=150)

db = NyanSQLite("users.db")
db.register(User)

# OK
db.insert(User(id=1, name="Alice", email="alice@example.com", age=30))

# Validation fails (raises Pydantic's ValidationError)
try:
    db.insert(User(id=2, name="A", email="invalid", age=-1))
except Exception as e:
    print(f"Validation failed: {e}")
```

## Validation During `update()`

When using the `update()` method, the field values are also checked against the Pydantic model definition.

```python
# Attempt to update age to an invalid value
try:
    db.update(User, where={"id": 1}, age=200) # Violates Field(le=150)
except Exception as e:
    print(f"Update failed: {e}")
```

## Validating Complex Types

You can use the full power of Pydantic to safely store lists, dictionaries, enums, and more.

```python
from typing import List, Dict
from enum import Enum

class Role(Enum):
    ADMIN = "admin"
    USER = "user"

class Profile(BaseModel):
    id: int
    roles: List[Role]
    metadata: Dict[str, str]

db.register(Profile)

# Automatically JSON serialized and deserialized back to original types
db.insert(Profile(
    id=1, 
    roles=[Role.ADMIN], 
    metadata={"login": "2024-01-01"}
))
```

## Strict Deserialization (`strict_deserialization`)

When loading data from the database, you can control the behavior for corrupted data (e.g., malformed JSON) via the `NyanSQLite` constructor:

- `strict_deserialization=False` (default): Emits a warning and returns raw data.
- `strict_deserialization=True`: Raises a `ValueError`.

```python
db = NyanSQLite("app.db", strict_deserialization=True)
```

## Related References

- [NyanSQLite API Reference](../api/NyanSQLite.md)
- [Pydantic Documentation](https://docs.pydantic.dev/)
