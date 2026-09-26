# Async Support (`NyanSQLiteAIO`)

NyanSQLite currently provides async support through `NyanSQLiteAIO`.

## Current Behavior

`NyanSQLiteAIO` uses `asyncio.to_thread()` to run SQLite work off the event loop.

1. **Safe connection access**: Access to the SQLite connection itself is serialized to keep the connection consistent.
2. **Exclusive writes**: Write operations such as `insert`, `update`, `delete`, and `atomic()` are protected by an async lock.
3. **Shorter read critical sections**: Pydantic row parsing happens outside the connection lock whenever possible.

## Basic Usage

```python
import asyncio
from pydantic import BaseModel
from nyansqlite import Indexed, NyanSQLiteAIO


class Article(BaseModel):
    id: int
    title: str
    author: Indexed[str]


async def main():
    async with NyanSQLiteAIO("app.db") as db:
        await db.register(Article)
        await db.insert(Article(id=1, title="Hello", author="neko"))

        article = await db.get(Article, id=1)
        print(article.title)

        rows = await db.query(Article, author="neko", order_by="id")
        print(len(rows))


if __name__ == "__main__":
    asyncio.run(main())
```

## Notes

- Most operations, including `register()`, must be awaited.
- Use `async with db.atomic():` to group multiple writes into one transaction.
- Prefer `NyanSQLiteAIO` over wrapping the synchronous client in `run_in_executor()` for new async code.
