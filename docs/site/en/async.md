# Asynchronous Support (`NyanSQLiteAIO`)

Starting from NyanSQLite v1.1.0, the `NyanSQLiteAIO` class has been introduced to natively support asynchronous programming using `asyncio`.

## Features

`NyanSQLiteAIO` offers the following features:

1. **Event-loop-friendly execution**: It uses `asyncio.to_thread` internally so SQLite work runs off the event loop.
2. **Thread Safety**: It uses asynchronous locks for write operations, ensuring safety in multi-threaded and asynchronous environments.
3. **Short read critical sections**: SQLite connection access stays protected, while Pydantic row parsing happens outside that lock whenever possible.

## Basic Usage

`NyanSQLiteAIO` supports asynchronous context managers, allowing for safe connection and disconnection using the `async with` syntax.

```python
import asyncio
from pydantic import BaseModel
from nyansqlite import NyanSQLiteAIO, Indexed

class User(BaseModel):
    id: int
    name: Indexed[str]

async def main():
    # Use asynchronous context manager
    async with NyanSQLiteAIO("app.db") as db:
        await db.register(User)
        
        # Async Insert
        await db.insert(User(id=1, name="alice"))
        
        # Async Query
        users = await db.query(User, name="alice")
        if users:
            print(f"Found: {users[0].name}")

        # Bulk Insert
        await db.insert_many([
            User(id=i, name=f"user_{i}") for i in range(2, 6)
        ])
        
        # Count Operation
        count = await db.count(User)
        print(f"Total users: {count}")

if __name__ == "__main__":
    asyncio.run(main())
```

## Method Overview

It provides almost the same API as `NyanSQLite` (synchronous version) but as asynchronous (awaitable) methods:

- `await db.insert(obj)`
- `await db.insert_many(objs)`
- `await db.query(model, ...)`
- `await db.get(model, ...)`
- `await db.select(model, fields, ...)`
- `await db.search(model, query, ...)`
- `await db.update(model, where, ...)`
- `await db.delete(model, ...)`
- `await db.count(model, ...)`
- `await db.exists(model, ...)`

## Performance Optimization

Since v1.1.0, read operations (`query`, `select`, `search`) have been tuned to keep SQLite connection access short.
After rows are fetched, Python-side deserialization is moved outside the connection lock whenever possible.
