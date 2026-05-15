# NyanSQLite Best Practices

A comprehensive guide for using NyanSQLite effectively in production environments.

## Performance Optimization

### Use `insert_many` for Bulk Inserts

Bulk inserting with `insert_many` is drastically faster than calling `insert` individually. NyanSQLite automatically handles transactions and optimal data chunking.

```python
# ✅ Best Practice: Bulk Insert
users = [User(id=i, name=f"User{i}") for i in range(1000)]
db.insert_many(users)
```

### Leveraging Indexes

Annotate fields that are frequently used in `query` calls with `Indexed[T]`. This creates a B-tree index, making searches significantly faster.

```python
class User(BaseModel):
    id: int
    username: Indexed[str]  # Searches by username will be fast
```

### Proper Use of Full-Text Search

For searching through large amounts of text, use `Searchable[str]` to create an FTS5 index. It is much faster than standard `LIKE` queries.

```python
class Article(BaseModel):
    title: Searchable[str]
    body: Searchable[str]
```

## Security

### Automatic Parameterization

Methods like `query`, `get`, and `delete` in NyanSQLite use parameterized queries (prepared statements) internally. This automatically protects against SQL injection attacks.

### Data Integrity

Using Pydantic models ensures the type safety of data stored in your database. Define detailed type hints and validation rules (like `Field`) in your models whenever possible.

## Operations and Maintenance

### Regular `vacuum`

Frequent deletions can leave empty space (fragmentation) within the SQLite database file. Periodically run `db.vacuum()` to optimize the file and reduce its size.

### Backups

NyanSQLite (via APSW) supports safely backing up a running database.

```python
# Use the underlying connection object to perform a backup
db.backend().backup("backup.db")
```

## Design Patterns

### Shared Models

If multiple applications share the same database, consolidate model definitions into a separate module and import it into each application.

### Use Context Managers

Always initialize NyanSQLite using a `with` statement to ensure resources are properly released.

```python
with NyanSQLite("app.db") as db:
    db.register(MyModel)
    # ... operations
```

## Summary

1. ✅ Use `insert_many` for bulk data insertion.
2. ✅ Specify `Indexed` for fields that are searched frequently.
3. ✅ Use `Searchable` (FTS5) for text-heavy searches.
4. ✅ Always manage resources with a context manager.
5. ✅ Periodically optimize the database with `vacuum`.
