---
outline: [2, 3]
---

# CHANGELOG

## [1.1.7] - 2026-11-17

### 🚀 Performance
- Reused INSERT statements and field encoders for single-row inserts. Sync inserts use SQLite's implicit transaction unless a transaction is already open.
- In five local Python 3.12 benchmark sets, the median time reduction for 10,000 sync inserts into a WAL database was 30.4% on APSW and 24.2% on sqlite3.

### 🐞 Fixed
- Finished async transaction rollback under repeated cancellation and kept committed registrations when cancellation arrived during a successful commit.
- Updated model registration only when the containing transaction commits and rejected concurrent table-name collisions.
- Preserved the original exception when SQLite had already rolled back the transaction.
- Applied Pydantic serializers and field exclusions consistently to single and bulk inserts.

### 🧪 Tests and CI
- Added transaction, registration, and bulk serialization regression tests.
- Ran Python 3.9 CI on Ubuntu 24.04, which provides supported Python 3.9 builds.

---

## [1.1.6] - 2026-09-27

### 🚀 Performance
- Streamed `insert_many()` rows to SQLite within the existing transaction, and prepared field serializers and INSERT SQL when registering a model. SQLite's parameter limit applies to each execution of the single-row INSERT.
- Decoded SQLite tuples directly into the dictionary validated by Pydantic. Normal JSON values use Pydantic Core's parser, with a fallback for values it rejects. Sync and async bulk conversion retain Pydantic validation; the async path runs bulk CPU work off the event loop.
- Reused prepared statements when callers supply the same keyword filters in different orders. Added optional `statement_cache_size` to both constructors; the backend default is unchanged when omitted.
- For ordinary models, used Pydantic Core's validator to reduce per-row construction overhead. Models with custom construction, model validators, or other incompatible features keep the constructor path.

### 🧪 Benchmarks and tests
- Restored sync and async benchmark suites and the result parser; benchmark workflow failures are no longer masked.
- Added regression tests for large inserts and rollback, column order, Pydantic validators, asynchronous conversion, JSON edge cases, SQL parameter binding, and cache configuration.
- In local Python 3.12 in-memory runs, the later model-read improvement changed the median for 1,000 rows from 1.974 to 1.671 ms (sync) and 3.044 to 2.626 ms (async). Reordering six keyword filters across 480 sync queries changed 8.964 to 4.955 ms. Async timings vary; fixed-order six-filter queries have a small overhead.

---

## [1.1.5] - 2026-09-26

### 🚀 Performance
- Prepare field-specific decoders and the update validation route at registration. In a local paired conversion benchmark on 20,000 rows with scalar, datetime, and list fields, median time fell from 0.194 to 0.166 seconds.
- Cached type inspection while decoding rows. In a local 10,000-row benchmark, median query time fell from 0.098 to 0.068 seconds (sync) and from 0.108 to 0.074 seconds (async).
- Bound `LIMIT` and `OFFSET` as SQL parameters. In a local 1,000-query pagination benchmark, median time fell from 0.0341 to 0.0315 seconds.
- Removed unused JSON conversion in `__in` filters. Building 500 filters of 1,000 integers fell from 0.138 to 0.091 seconds locally.

### 🐞 Fixed
- Updated documentation dependencies to address known vulnerabilities and limited the optional `cryptography` dependency to a fixed release on Python 3.10+.
- Protected in-flight SQLite calls after async cancellation and rolled back open transactions; sync transactions also roll back on interruptions.
- `update()` now validates changed values, with affected-row validation for models that have custom validators or configuration.
- `register()` now raises `SchemaMismatchError` when an existing table's columns, types, primary key, nullability, or FTS searchable columns differ from the model.
- Adding full-text search to an existing table now indexes existing rows immediately.

### 📚 Docs
- Corrected the error and exception guides, backup example, projection advice, batched async reads, and continuation-based pagination.

### ⚠️ Compatibility
- On Python 3.9, the `encryption`, `all`, and `dev` extras no longer install `cryptography`. Core Python 3.9 support remains.
- Invalid partial updates now raise Pydantic `ValidationError`. Incompatible existing tables raise `SchemaMismatchError` on registration; migrate them explicitly.

---

## [1.1.4] - 2026-06-22

### 🐞 Fixed
- Validated all generated SQLite identifiers and rejected unknown composite-index fields before constructing schema SQL.
- Hardened string filters so unsupported raw SQL fragments now raise `QueryValidationError` instead of being passed through to SQL.
- Aligned async query validation with the sync implementation, including unknown-field checks and model-aware filter value serialization.
- Fixed async filtering for `date`, `datetime`, `list`, and `dict` values.
- Fixed `__in` handling so normal lists/tuples/sets work consistently and empty collections return no rows.
- Fixed offset-only pagination by emitting SQLite's required unlimited `LIMIT` clause.
- Tightened `limit` / `offset` validation to reject negative values, floats, booleans, and strings.
- Added a clear `TypeError` when `insert_many()` receives mixed model types.
- Serialized reads and connection shutdown with the existing locks so `close()` cannot race active queries.
- Protected `vacuum()` and async `execute_raw()` with the existing connection locks.

### 🧪 Tests
- Added regression tests for unsafe string filters, async field validation, serialized filter values, `__in`, offset-only pagination, strict pagination types, and mixed-model bulk inserts.

### 📚 Docs
- Added an APSW full-access implementation plan.

### ⚠️ Compatibility
- String filters now support only simple comparisons such as `"age > 10"` or `"name = 'Alice'"`. Use keyword filters such as `age__gte=10` for advanced filtering.
- Python 3.9 remains supported for the core package. Some optional and development dependencies cannot provide their latest security-fixed wheels on Python 3.9; use Python 3.10+ for the `speed`, `encryption`, and `dev` extras when processing untrusted input.

---

## [1.1.1] - 2026-05-16

### 🚀 Added
- **Explicit Transactions**: Added `atomic()` context manager to `NyanSQLite` and `async with atomic()` to `NyanSQLiteAIO` for manual transaction control.
- **Nested Transactions**: Added support for nested `atomic()` blocks.

### 🔄 Changed
- **Thread Safety**: Improved thread safety by switching to `threading.RLock` in `NyanSQLite`.
- **Async Safety**: Implemented re-entrant async lock in `NyanSQLiteAIO` to prevent deadlocks when using `atomic()`.

---

## [1.1.0] - 2026-05-16

### 🚀 Added
- **Asynchronous Support**: Full support for `asyncio` via `NyanSQLiteAIO` class.
- **Improved Performance**: Optimized read operations by minimizing thread context switching and processing rows efficiently in `asyncio.to_thread`.
- **Documentation Updates**: Added English and Japanese documentation for asynchronous usage.

### 🔄 Changed
- Internal optimization for `query`, `select`, and `search` methods in `NyanSQLiteAIO`.
- Optimized read operations in synchronous `NyanSQLite` class by minimizing lock duration.

---

## [1.0.1] - 2026-05-15

### 🐞 Fixed
- Minor bug fixes and performance improvements.

---

## [1.0.0] - 2026-05-15

### 🚀 Added
- **Pydantic v2 support**: Models can be used directly as database schemas.
- **Django-like Query Syntax**: Support for intuitive filtering such as `__gte`, `__in`, `__like`, etc.
- **FTS5 Full-Text Search**: Fast full-text search capabilities using SQLite's FTS5 extension.
- **Automatic Index Management**: B-tree indexes are automatically created using `Indexed[T]` and `UniqueIndexed[T]` annotations.
- **Composite Indexes**: Support for `CompositeIndex` via Pydantic's `Field` extra metadata.
- **Transparent Type Handling**: Automatically handles complex types like `dict` and `list` by serializing them to JSON.
- **WAL Mode Support**: Write-Ahead Logging is enabled by default for better performance and concurrency.
- **Context Manager Support**: `NyanSQLite` can be used as a context manager for automatic connection closing.

### 🔄 Changed
- Initial public release of NyanSQLite.

---
