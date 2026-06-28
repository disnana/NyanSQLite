---
outline: [2, 3]
---

# NyanSQLite API Reference

Complete documentation for the Pydantic-native NyanSQLite class.

## NyanSQLite

```python
class NyanSQLite(path: str = ':memory:', wal: bool = True, strict_deserialization: bool = False)
```

Pydantic-native SQLite wrapper.

## NyanSQLiteAIO

```python
class NyanSQLiteAIO(path: str = ':memory:', wal: bool = True, strict_deserialization: bool = False)
```

Asynchronous version of `NyanSQLite`.

It uses `asyncio.to_thread` to run SQLite work off the event loop while protecting access to the shared connection.
Write operations are handled exclusively, and read operations are implemented to keep connection-lock hold times short.
Most methods are `async` and require `await` when called.

See [Async Support](./async) for usage details.

#### Parameter

| Parameter | Type | Description |
|---|---|---|
| `path` | `str` | Database file path. Defaults to `":memory:"`. |
| `wal` | `bool` | Whether to enable WAL (Write-Ahead Logging) mode. Defaults to `True`. |
| `strict_deserialization` | `bool` | If `True`, raise on malformed stored data during deserialization. If `False`, emit a warning and return the raw value. |



---

## Constructor

## Core Methods

### `register`

```python
def register(model: type[BaseModel]) -> None
```

Register a Pydantic model and create the corresponding table, indexes, and FTS5 virtual table.

#### Parameter

| Parameter | Type | Description |
|---|---|---|
| `model` | `type[BaseModel]` |  |

::: warning Raises
- Raised if another model with the same table name is already registered.
:::


---

### `close`

```python
def close() -> None
```

Close the underlying database connection.


---

### `registered_models`

```python
def registered_models() -> list[str]
```

Names of all registered models.

#### Returns

**Type:** `list[str]`

List of model names.


---

## CRUD Operations

### `insert`

```python
def insert(obj: M) -> M
```

Validate via Pydantic then INSERT. Returns the object unchanged.

#### Parameter

| Parameter | Type | Description |
|---|---|---|
| `obj` | `M` |  |

#### Returns

**Type:** `M`

The inserted object (unchanged).

::: warning Raises
- Raised if the model is not registered.
:::


---

### `insert_many`

```python
def insert_many(objs: list[M]) -> int
```

Bulk-insert multiple model instances in a single transaction.

Automatically chunks large inserts to respect SQLite's variable binding limit
(default 32766). This prevents SQLITE_TOOBIG errors on very large datasets.

#### Parameter

| Parameter | Type | Description |
|---|---|---|
| `objs` | `list[M]` |  |

#### Returns

**Type:** `int`

Total number of rows inserted.

::: warning Raises
- Raised if the model is not registered.
:::


---

### `update`

```python
def update(model: type[BaseModel], where: dict[str, Any], **fields: Any) -> int
```

Partial update — only the specified *fields* are written.

#### Parameter

| Parameter | Type | Description |
|---|---|---|
| `model` | `type[BaseModel]` |  |
| `where` | `dict[str, Any]` |  |

#### Returns

**Type:** `int`

Number of rows updated.

::: warning Raises
- Raised if the model is not registered.
- Raised if any specified field is not found in the model.
:::

::: tip Example
```python
    db.update(User, where={"id": 1}, age=26, bio="updated")
```
:::


---

### `delete`

```python
def delete(model: type[BaseModel], *filters: str, **kwargs: Any) -> int
```

Delete all rows matching *filters* and *kwargs*.

#### Parameter

| Parameter | Type | Description |
|---|---|---|
| `model` | `type[BaseModel]` |  |
| `filters` | `str` |  |

#### Returns

**Type:** `int`

Number of rows deleted.

::: tip Example
```python
    db.delete(User, id=42)
    db.delete(User, "age > 50")
    db.delete(Session, user_id=1, active=True)
```
:::


---

## Query & Search

### `get`

```python
def get(model: type[M], *filters: str, **kwargs: Any) -> Optional[M]
```

Fetch the first matching row as a Pydantic model, or ``None``.

#### Parameter

| Parameter | Type | Description |
|---|---|---|
| `model` | `type[M]` |  |
| `filters` | `str` |  |

#### Returns

**Type:** `Optional[M]`

The retrieved model instance, or None.

::: tip Example
```python
    user = db.get(User, id=1)
    user = db.get(User, "age > 30", name="Alice")
    user = db.get(User, email="taro@example.com")
```
:::


---

### `query`

```python
def query(model: type[M], *filters: str, limit: Optional[int] = None, offset: Optional[int] = None, order_by: Optional[str] = None, desc: bool = False, **kwargs: Any) -> list[M]
```

Query rows with optional filtering, ordering, and pagination.

Supports string filters and operator suffixes (``__gt``, ``__like``, …).
Since v1.1.4dev1, string filters only support explicit simple comparisons for safety.

#### Parameter

| Parameter | Type | Description |
|---|---|---|
| `model` | `type[M]` |  |
| `filters` | `str` |  |
| `limit` | `Optional[int]` |  |
| `offset` | `Optional[int]` |  |
| `order_by` | `Optional[str]` |  |
| `desc` | `bool` |  |

#### Returns

**Type:** `list[M]`

List of matching model instances.

::: tip Example
```python
    db.query(User)                                  # all rows
    db.query(User, age=25)                          # exact match
    db.query(User, "age > 20", limit=10)            # string filters
    db.query(User, age__gte=20, limit=10)           # operator suffixes
    db.query(User, order_by="name", desc=True)      # ordering
    db.query(User, order_by="id", limit=20, offset=40)  # pagination
```
:::


---

### `select`

```python
def select(model: type[BaseModel], fields: list[str], *filters: str, limit: Optional[int] = None, offset: Optional[int] = None, order_by: Optional[str] = None, desc: bool = False, **kwargs: Any) -> list[dict[str, Any]]
```

Partial read — fetch only *fields*, returned as plain dicts.

Avoids loading unused columns for large rows.

#### Parameter

| Parameter | Type | Description |
|---|---|---|
| `model` | `type[BaseModel]` |  |
| `fields` | `list[str]` |  |
| `filters` | `str` |  |
| `limit` | `Optional[int]` |  |
| `offset` | `Optional[int]` |  |
| `order_by` | `Optional[str]` |  |
| `desc` | `bool` |  |

#### Returns

**Type:** `list[dict[str, Any]]`

List of dicts containing specified fields.

::: tip Example
```python
    db.select(Article, ["title", "views"], author="neko", order_by="views", desc=True)
    db.select(Article, ["title"], "views > 100")
```
:::


---

### `search`

```python
def search(model: type[M], query: str, *, limit: Optional[int] = None) -> list[M]
```

Full-text search on all ``Searchable[str]`` fields.

Uses FTS5 ``MATCH`` with BM25 ranking (``ORDER BY rank``).

#### Parameter

| Parameter | Type | Description |
|---|---|---|
| `model` | `type[M]` |  |
| `query` | `str` |  |
| `limit` | `Optional[int]` |  |

#### Returns

**Type:** `list[M]`

List of matching model instances, ordered by relevance.

::: warning Raises
- Raised if the model has no Searchable[str] fields.
:::

::: tip Example
```python
    db.search(Article, "python sqlite")
    db.search(Article, "python sqlite", limit=5)
```

For field-scoped search, use FTS5 column filter syntax:
```python
    db.search(Article, "title:python")
```
:::


---

### `count`

```python
def count(model: type[BaseModel], *filters: str, **kwargs: Any) -> int
```

Return the number of rows matching *filters* and *kwargs*.

#### Parameter

| Parameter | Type | Description |
|---|---|---|
| `model` | `type[BaseModel]` |  |
| `filters` | `str` |  |

#### Returns

**Type:** `int`

Number of matching rows.

::: tip Example
```python
    total  = db.count(User)
    adults = db.count(User, "age >= 18")
    adults = db.count(User, age__gte=18)
```
:::


---

### `exists`

```python
def exists(model: type[BaseModel], *filters: str, **kwargs: Any) -> bool
```

Return ``True`` if at least one row matches *filters* and *kwargs*.

#### Parameter

| Parameter | Type | Description |
|---|---|---|
| `model` | `type[BaseModel]` |  |
| `filters` | `str` |  |

#### Returns

**Type:** `bool`

True if matching rows exist, False otherwise.

::: tip Example
```python
    if db.exists(User, email="taro@example.com"):
        ...
```
:::


---

## Maintenance

### `rebuild_fts`

```python
def rebuild_fts(model: type[BaseModel]) -> None
```

Rebuild the FTS5 index for *model* (useful after bulk imports).

#### Parameter

| Parameter | Type | Description |
|---|---|---|
| `model` | `type[BaseModel]` |  |



---

### `vacuum`

```python
def vacuum() -> None
```

VACUUM the database to reclaim disk space.


---

## Raw SQL Execution

### `execute_raw`

```python
def execute_raw(sql: str, params: tuple = ()) -> list[dict[str, Any]]
```

Execute arbitrary SQL and return rows as dicts.

#### Parameter

| Parameter | Type | Description |
|---|---|---|
| `sql` | `str` |  |
| `params` | `tuple` |  |

#### Returns

**Type:** `list[dict[str, Any]]`

List of result rows as dicts.

::: tip Example
```python
    db.execute_raw("SELECT count(*) AS n FROM user WHERE age > ?", (18,))
```
:::


---

