---
outline: [2, 3]
---

# CHANGELOG

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
