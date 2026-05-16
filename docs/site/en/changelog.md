---
outline: [2, 3]
---

# CHANGELOG

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