# Transactions Guide

NyanSQLite provides a safe and easy-to-use API for utilizing SQLite's transaction features.

## Transactions in NyanSQLite

The `insert_many` method in NyanSQLite automatically uses a transaction internally. This allows you to insert large amounts of data quickly and atomically (either all succeed or all fail).

### Internal Behavior

NyanSQLite performs the following steps during bulk operations:

1. Issues `BEGIN` (or `BEGIN IMMEDIATE`).
2. Inserts data in chunks.
3. Issues `COMMIT` if all inserts succeed.
4. Issues `ROLLBACK` if an error occurs.

## Manual Transaction Management

In the current version of NyanSQLite, you can also directly obtain the APSW connection object to control transactions manually.

```python
from nyansqlite import NyanSQLite

db = NyanSQLite("app.db")

# Transaction via APSW connection object
with db.backend().transaction():
    db.insert(item1)
    db.insert(item2)
    # Automatically rolled back if an exception occurs
```

## Performance Optimization

Using transactions drastically improves SQLite's write performance by reducing the number of disk synchronizations (fsync).

### Best Practices

1. **Use `insert_many` for Bulk Inserts**: It is much faster than calling `insert` in a loop manually.
2. **Appropriate Chunk Size**: NyanSQLite automatically splits data into chunks to stay within SQLite's placeholder limit (32,766).
3. **Leverage WAL Mode**: NyanSQLite enables WAL (Write-Ahead Logging) mode by default, which allows high concurrency by not blocking reads during writes.

## Related References

- [NyanSQLite API Reference](../api/NyanSQLite.md)
- [APSW Transaction Documentation](https://rogerbinns.github.io/apsw/connection.html#apsw.Connection.transaction)
