# Async Support (Planned)

Currently, NyanSQLite v1.0.x does not include native support for asynchronous operations (async/await).

## Current Status

The current `NyanSQLite` class is designed for synchronous operations (blocking I/O).
While database operations are kept thread-safe via `threading.Lock`, it is not specifically designed for the `asyncio` event loop.

### Temporary Usage in Async Environments

To use NyanSQLite in async frameworks like FastAPI, you should use `run_in_executor` to avoid blocking the event loop.

```python
import asyncio
from nyansqlite import NyanSQLite

db = NyanSQLite("app.db")

async def get_article(article_id: int):
    loop = asyncio.get_running_loop()
    # Execute synchronous method in executor
    return await loop.run_in_executor(None, db.get, Article, id=article_id)
```

## Roadmap

Future versions are planned to include native async support (`AsyncNyanSQLite`) with features such as:

1. **Dedicated Thread Pool**: Running database operations in background threads to avoid blocking the event loop.
2. **Async Query API**: Intuitive async interface like `await db.query(...)`.
3. **Connection Pooling**: Efficient connection management for async environments.

Please let us know on the GitHub repository if you have any feedback or requests regarding async support.
