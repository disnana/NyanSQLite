# NyanSQLite API Reference

Complete documentation for the Pydantic-native NyanSQLite class.

## NyanSQLite

```python
class NyanSQLite(path: str = ':memory:', wal: bool = True, strict_deserialization: bool = False)
```

Pydantic-native SQLite wrapper.

    Automatic schema creation, B-tree indexes, FTS5 full-text search,
    partial reads/writes, and query operators — powered by apsw.

    Quick start::

        from nyansqlite import NyanSQLite, Indexed, Searchable
        from pydantic import BaseModel

        class Article(BaseModel):
            id:      int
            author:  Indexed[str]
            title:   Searchable[str]
            body:    Searchable[str]
            views:   int = 0

        db = NyanSQLite("blog.sqlite")
        db.register(Article)

        db.insert(Article(id=1, author="neko", title="Hello SQLite", body="…"))
        db.search(Article, "SQLite")
        db.update(Article, where={"id": 1}, views=42)
        db.select(Article, fields=["title", "views"], author="neko")

Initialize NyanSQLite.

#### Parameter

| Parameter | Type | Description |
|---|---|---|
| `path` | `str` | Database file path (default: in-memory) |
| `wal` | `bool` | Enable WAL mode (default: True) |
| `strict_deserialization` | `bool` | If True, raise ValueError on malformed data. If False, emit warning and return raw value. |



---

## Constructor

## Core Methods

### `close`

```python
def close() -> None
```

Close the underlying database connection.


---

## Dictionary Interface

### `update`

```python
def update(model: type[BaseModel], where: dict[str, Any], **fields: Any) -> int
```

Partial update — only the specified *fields* are written.

#### Parameter

| Parameter | Type | Description |
|---|---|---|
| `model` | `type[BaseModel]` |  |
| `where` | `dict[str, Any]` | Exact-match conditions that identify the row(s). **fields: ``field=new_value`` pairs to update. |

#### Returns

**Type:** `int`

Number of rows updated.

::: tip Example
```python

    db.update(User, where={"id": 1}, age=26, bio="updated")
```
:::


---

### `get`

```python
def get(model: type[M], *filters: str, **kwargs: Any) -> Optional[M]
```

Fetch the first matching row as a Pydantic model, or ``None``.

::: tip Example
```python

    user = db.get(User, id=1)
    user = db.get(User, "age > 30", name="Alice")
    user = db.get(User, email="taro@example.com")
```
:::


---

## Query

### `query`

```python
def query(model: type[M], *filters: str, limit: Optional[int] = None, offset: Optional[int] = None, order_by: Optional[str] = None, desc: bool = False, **kwargs: Any) -> list[M]
```

Query rows with optional filtering, ordering, and pagination.

Supports string filters and operator suffixes (``__gt``, ``__like``, …).

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

### `count`

```python
def count(model: type[BaseModel], *filters: str, **kwargs: Any) -> int
```

Return the number of rows matching *filters* and *kwargs*.

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

::: tip Example

    if db.exists(User, email="taro@example.com"):
```python
        
```
    if db.exists(User, "age > 20"):
```python
        
```
:::


---

## Utility Functions

### `vacuum`

```python
def vacuum() -> None
```

VACUUM the database to reclaim disk space.


---

## Other Methods

### `register`

```python
def register(model: type[BaseModel]) -> None
```

Introspect *model* and create table + indexes + FTS5 virtual table.

Raises TableNameCollisionError if a different model is already registered with the same table name.


---

### `insert`

```python
def insert(obj: M) -> M
```

Validate via Pydantic then INSERT. Returns the object unchanged.


---

### `insert_many`

```python
def insert_many(objs: list[M]) -> int
```

Bulk-insert in a single transaction. Returns the number inserted.

Automatically chunks large inserts to respect SQLite's variable binding limit
(default 32766). This prevents SQLITE_TOOBIG errors on very large datasets.

#### Parameter

| Parameter | Type | Description |
|---|---|---|
| `objs` | `list[M]` | List of model instances to insert |

#### Returns

**Type:** `int`

Total number of rows inserted


---

### `delete`

```python
def delete(model: type[BaseModel], *filters: str, **kwargs: Any) -> int
```

Delete all rows matching *filters* and *kwargs*. Returns rows deleted.

::: tip Example
```python

    db.delete(User, id=42)
    db.delete(User, "age > 50")
    db.delete(Session, user_id=1, active=True)
```
:::


---

### `select`

```python
def select(model: type[BaseModel], fields: list[str], *filters: str, limit: Optional[int] = None, offset: Optional[int] = None, order_by: Optional[str] = None, desc: bool = False, **kwargs: Any) -> list[dict[str, Any]]
```

Partial read — fetch only *fields*, returned as plain dicts.

Avoids loading unused columns for large rows.

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

::: tip Example
```python

    db.search(Article, "python sqlite")
    db.search(Article, "python sqlite", limit=5)

For field-scoped search, use FTS5 column filter syntax::

    db.search(Article, "title:python")
```
:::


---

### `rebuild_fts`

```python
def rebuild_fts(model: type[BaseModel]) -> None
```

Rebuild the FTS5 index for *model* (useful after bulk imports).


---

### `execute_raw`

```python
def execute_raw(sql: str, params: tuple = ()) -> list[dict[str, Any]]
```

Execute arbitrary SQL and return rows as dicts.

::: tip Example
```python

    db.execute_raw("SELECT count(*) AS n FROM user WHERE age > ?", (18,))
```
:::


---

### `registered_models`

```python
def registered_models() -> list[str]
```

Names of all registered models.


---

