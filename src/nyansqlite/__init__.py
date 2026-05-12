"""
NanaSQLite: A dict-like SQLite wrapper with instant persistence and intelligent caching.

Example:
    >>> from nyansqlite import NanaSQLite
    >>> db = NanaSQLite("mydata.db")
    >>> db["user"] = {"name": "Nana", "age": 20}
    >>> print(db["user"])
    {'name': 'Nana', 'age': 20}

Async Example:
    >>> import asyncio
    >>> from nyansqlite import AsyncNanaSQLite
    >>>
    >>> async def main():
    ...     async with AsyncNanaSQLite("mydata.db") as db:
    ...         await db.aset("user", {"name": "Nana", "age": 20})
    ...         user = await db.aget("user")
    ...         print(user)
    >>>
    >>> asyncio.run(main())
"""

from __future__ import annotations

# from .async_core import AsyncNanaSQLite
from .core import NyanSQLite

__version__ = "1.0.0b2"
__author__ = "Disnana"
__all__ = [
    "NyanSQLite",
]
