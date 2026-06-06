# NyanSQLite API Reference

Complete documentation for the Pydantic-native `NyanSQLite` class.

## Class: `NyanSQLite`

```python
class NyanSQLite:
    def __init__(self, path: str = ":memory:", wal: bool = True, strict_deserialization: bool = False)
```

### Constructor

- `path` (str): Path to the database file. Defaults to an in-memory database (`:memory:`).
- `wal` (bool): Whether to enable WAL (Write-Ahead Logging) mode. Defaults to `True`.
- `strict_deserialization` (bool): If `True`, raises an exception on deserialization failure when reading data. If `False` (default), emits a warning and returns the raw data.

---

## Core Methods

### `register`
```python
def register(self, model: type[BaseModel]) -> None
```
Registers a Pydantic model and automatically creates the corresponding table, indexes, and FTS5 virtual table.

### `insert`
```python
def insert(self, obj: BaseModel) -> None
```
Inserts a model instance into the database.

### `insert_many`
```python
def insert_many(self, objs: list[BaseModel]) -> None
```
Inserts multiple model instances in bulk. Automatically uses a transaction for high performance.

### `query`
```python
def query(self, model: type[M], *filters: str, limit: Optional[int] = None, offset: Optional[int] = None, order_by: Optional[str] = None, desc: bool = False, **kwargs: Any) -> list[M]
```
Searches for data using Django-like filtering and returns a list of model instances.

- `filters`: String-based filters like `"age > 20"`. Since v1.1.4dev1, only explicit simple comparisons are supported for safety.
- `kwargs`: Keyword-based filters like `name="Alice"`, `views__gte=100`.
- `limit` / `offset`: Constraints for the number of results and starting position.
- `order_by`: Field name to sort by.
- `desc`: If `True`, sorts in descending order.

### `get`
```python
def get(self, model: type[M], *filters: str, **kwargs: Any) -> Optional[M]
```
Retrieves the first record matching the criteria. Returns `None` if not found.

### `update`
```python
def update(self, model: type[BaseModel], where: dict[str, Any], **fields: Any) -> None
```
Updates records matching the `where` criteria with the specified `fields`.

### `delete`
```python
def delete(self, model: type[BaseModel], *filters: str, **kwargs: Any) -> None
```
Deletes records matching the criteria.

---

## Search and Aggregation

### `search`
```python
def search(self, model: type[M], query: str, *, limit: Optional[int] = None) -> list[M]
```
Executes a full-text search using FTS5. Targets fields annotated with `Searchable`.

### `count`
```python
def count(self, model: type[BaseModel], *filters: str, **kwargs: Any) -> int
```
Returns the count of records matching the criteria.

### `exists`
```python
def exists(self, model: type[BaseModel], *filters: str, **kwargs: Any) -> bool
```
Checks if any record matches the criteria.

### `select`
```python
def select(self, model: type[BaseModel], fields: list[str], *filters: str, **kwargs: Any) -> list[dict[str, Any]]
```
Retrieves only specific fields and returns them as a list of dictionaries.

---

## Maintenance and Management

### `rebuild_fts`
```python
def rebuild_fts(self, model: type[BaseModel]) -> None
```
Rebuilds the full-text search (FTS5) index.

### `vacuum`
```python
def vacuum(self) -> None
```
Runs the SQLite `VACUUM` command to optimize the database file size.

### `close`
```python
def close(self) -> None
```
Closes the database connection.

### `backend`
```python
def backend(self) -> NyanConnection
```
Returns the underlying `NyanConnection` object. Can be used for direct transaction control (`backend().transaction()`).

### `registered_models`
```python
def registered_models(self) -> list[type[BaseModel]]
```
Returns a list of currently registered models.
