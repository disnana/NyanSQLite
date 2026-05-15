# Tutorial

A step-by-step guide to learning NyanSQLite, from basics to advanced usage.

## Prerequisites

- Python 3.9+
- Basic understanding of Pydantic
- Knowledge of SQLite is helpful but not required

## Installation

```bash
pip install nyansqlite
```

## Lesson 1: Your First Database

NyanSQLite uses Pydantic models as schemas.

### Defining and Registering a Model

```python
from pydantic import BaseModel
from nyansqlite import NyanSQLite

# 1. Define your model (schema)
class User(BaseModel):
    id: int
    name: str
    email: str

# 2. Initialize the database
db = NyanSQLite("tutorial.db")

# 3. Register the model (table is created automatically)
db.register(User)

# 4. Insert data
user = User(id=1, name="Alice", email="alice@example.com")
db.insert(user)

# 5. Retrieve data
retrieved = db.get(User, id=1)
print(retrieved.name)  # Alice

# Close when done
db.close()
```

### Using Context Manager

```python
with NyanSQLite("tutorial.db") as db:
    db.register(User)
    # operations...
# Automatically closed here
```

## Lesson 2: Indexes and Full-Text Search

Leverage NyanSQLite's powerful indexing and FTS5 full-text search capabilities.

```python
from nyansqlite import NyanSQLite, Indexed, Searchable

class Article(BaseModel):
    id: int
    author: Indexed[str]         # B-tree index created
    title: Searchable[str]       # Full-text search target
    body: Searchable[str]        # Full-text search target
    category: str = "general"

db = NyanSQLite("blog.db")
db.register(Article)

# Insert data
db.insert(Article(id=1, author="neko", title="SQLite Basics", body="NyanSQLite is handy."))

# Fast query using index
articles = db.query(Article, author="neko")

# Full-text search
results = db.search(Article, "SQLite")
for hit in results:
    print(hit.title)
```

## Lesson 3: Django-like Queries

Perform complex searches without writing raw SQL.

```python
# Comparison operators
# __gt (>), __gte (>=), __lt (<), __lte (<=), __ne (!=)
old_users = db.query(User, age__gt=30)

# IN clause
selected = db.query(User, id__in=[1, 2, 3])

# LIKE search
search = db.query(User, name__like="Ali%")

# NULL check
null_emails = db.query(User, email__is_null=True)

# Ordering and limits
recent = db.query(User, order_by="id", desc=True, limit=5)
```

## Lesson 4: Bulk Operations (Performance)

Use `insert_many` for handling large datasets.

```python
users = [User(id=i, name=f"User{i}", email=f"user{i}@example.com") for i in range(1000)]

# Automatically runs within a transaction for high speed
db.insert_many(users)
```

## Lesson 5: Maintenance

```python
# Optimize database (reduce file size)
db.vacuum()

# Rebuild full-text search index
db.rebuild_fts(Article)

# Check existence
if db.exists(User, id=1):
    print("User exists")
```

## Next Steps

- See [validation](./validation) for detailed validation.
- See [API Reference](./api) for full method documentation.
