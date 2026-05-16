# NyanSQLite Documentation

A Pydantic-native SQLite wrapper that allows you to use Pydantic models directly as database schemas, providing type safety and high performance.

## Table of Contents

- [Concept](#concept)
- [Installation](#installation)
- [Quick Start](#quick-start)
- [Guides](#guides)
  - [Tutorial](./tutorial)
  - [Validation](./validation)
  - [Async Support](./async)
  - [Transactions](./transactions)
  - [Error Handling](./error_handling)
  - [Best Practices](./best_practices)
  - [Encryption](./encryption)
  - [Exceptions](./exceptions)
- [API Reference](#api-reference)
  - [NyanSQLite](../api)

---

## Concept

### The Problem

Traditional database solutions require learning SQL, managing connections, and handling serialization manually. Also, you often need to write separate validation logic to ensure data integrity.

### The Solution

**NyanSQLite** bridges this gap by mapping Pydantic models directly to SQLite tables:

1. **Type Safe**: Use Pydantic type hints directly as your database schema.
2. **Auto Serialization**: Transparently handle complex types like dict, list, and datetime.
3. **Django-like Queries**: Intuitive syntax for complex filtering without writing SQL.
4. **Fast Search**: Built-in support for SQLite's FTS5 full-text search.
5. **Async Support**: Native `NyanSQLiteAIO` class for `asyncio`.

### Design Principles

1. **Instant Persistence**: Every write operation is immediately persisted to SQLite.
2. **Thread Safe**: Protected by `threading.Lock` and async locks for safe concurrent access.
3. **Zero Config**: Sensible defaults optimized for performance (WAL mode, etc.).

---

## Installation

```bash
pip install nyansqlite
```

**Requirements:**
- Python 3.9+
- Pydantic 2.0+

---

## Quick Start

### Basic Usage

```python
from pydantic import BaseModel
from nyansqlite import NyanSQLite, Indexed, Searchable

# 1. Define your schema
class Article(BaseModel):
    id: int                      # 'id' field becomes the primary key automatically
    author: Indexed[str]         # Indexed column
    title: Searchable[str]       # Full-text search enabled
    body: Searchable[str]        # Full-text search enabled
    views: int = 0

# 2. Initialize DB & Register model
db = NyanSQLite("blog.db")
db.register(Article)

# 3. Insert data
db.insert(Article(
    id=1,
    author="neko",
    title="Mastering SQLite",
    body="NyanSQLite makes data management easy."
))

# 4. Query (Django-like)
articles = db.query(Article, author="neko", views__gte=0)

# 5. Full-text search
results = db.search(Article, "SQLite")
for hit in results:
    print(f"Found: {hit.title}")

db.close()
```

---

## Guides

For more detailed information, please refer to the following guides:

- **[Tutorial](./tutorial)**: Extended examples including multiple tables and advanced features.
- **[Validation](./validation)**: Schema validation and data handling with Pydantic.
- **[Async Support](./async)**: Using NyanSQLite in asynchronous environments.
- **[Transactions](./transactions)**: Ensuring data integrity and optimizing bulk writes.
- **[Error Handling](./error_handling)**: Handling exceptions and troubleshooting.
- **[Best Practices](./best_practices)**: Recommended patterns for production use.
- **[Encryption](./encryption)**: Securing your data at rest.
- **[Exceptions](./exceptions)**: Complete exception class reference.

---

## API Reference

Complete documentation for all classes and methods.

- **[NyanSQLite](../api)**
