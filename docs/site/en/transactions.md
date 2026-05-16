# Transactions Guide

NyanSQLite provides a safe and easy-to-use API for utilizing SQLite's transaction features.

## Transactions in NyanSQLite

Bulk processing methods such as `insert_many` in NyanSQLite automatically use transactions internally. This allows you to process large amounts of data quickly and atomically (either all succeed or all fail).

### Internal Behavior

NyanSQLite performs the following steps during bulk operations:

1. Issues `BEGIN` (or `BEGIN IMMEDIATE`).
2. Processes data in chunks.
3. Issues `COMMIT` if all operations succeed.
4. Issues `ROLLBACK` if an error occurs.

## Manual Transaction Management (`atomic`)

The `atomic()` context manager allows you to explicitly group multiple operations into a single transaction.

### Synchronous Version (NyanSQLite)

```python
from nyansqlite import NyanSQLite

db = NyanSQLite("app.db")

with db.atomic():
    db.insert(item1)
    db.insert(item2)
    # Automatically rolled back if an exception occurs
```

### Asynchronous Version (NyanSQLiteAIO)

```python
from nyansqlite import NyanSQLiteAIO

db = NyanSQLiteAIO("app.db")

async with db.atomic():
    await db.insert(item1)
    await db.insert(item2)
    # Automatically rolled back if an exception occurs
```

### Nested Transactions

`atomic()` can be nested. The transaction is committed only when the outermost `atomic` block finishes. If an exception occurs in an inner block, the entire transaction is rolled back.

```python
with db.atomic():
    db.insert(item1)
    with db.atomic(): # Inner transaction
        db.insert(item2)
    # Committed here
```

## Performance Optimization

Using transactions drastically improves SQLite's write performance by reducing the number of disk synchronizations (fsync).

### Best Practices

1. **Use `insert_many` for Bulk Inserts**: It is much faster than calling `insert` in a loop manually.
2. **Wrap Related Operations with `atomic()`**: Grouping multiple related update operations into a single `atomic()` block ensures data consistency and improves performance.
3. **Leverage WAL Mode**: NyanSQLite enables WAL (Write-Ahead Logging) mode by default, which allows high concurrency by not blocking reads during writes.

## Related References

- [NyanSQLite API Reference](../api)
- [APSW Transaction Documentation](https://rogerbinns.github.io/apsw/connection.html#apsw.Connection.transaction)
