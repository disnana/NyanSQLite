from __future__ import annotations
from typing import Any


class _NyanIndexedMarker:
    def __init__(self, unique: bool = False):
        self.unique = unique

    def __repr__(self) -> str:
        return f"Indexed(unique={self.unique})"


class _NyanSearchableMarker:
    def __repr__(self) -> str:
        return "Searchable"


class Indexed:
    """Mark a field for an automatic B-tree index.

    Usage::

        name: Indexed[str]
        age:  Indexed[int]
    """

    def __class_getitem__(cls, item: Any):
        from typing import Annotated
        return Annotated[item, _NyanIndexedMarker(unique=False)]


class UniqueIndexed:
    """Mark a field for a UNIQUE B-tree index.

    Usage::

        email: UniqueIndexed[str]
    """

    def __class_getitem__(cls, item: Any):
        from typing import Annotated
        return Annotated[item, _NyanIndexedMarker(unique=True)]


class Searchable:
    """Mark a str field for FTS5 full-text search.

    Usage::

        title: Searchable[str]
        body:  Searchable[str]
    """

    def __class_getitem__(cls, item: Any):
        from typing import Annotated
        return Annotated[item, _NyanSearchableMarker()]


class CompositeIndex:
    """Declare a composite (multi-column) index via ``__nyan_indexes__``.

    Usage::

        class Order(BaseModel):
            __nyan_indexes__ = [CompositeIndex("user_id", "created_at")]
            id:         int
            user_id:    int
            created_at: datetime
            amount:     float

        # Unique composite:
        __nyan_indexes__ = [CompositeIndex("tenant_id", "email", unique=True)]
    """

    def __init__(self, *fields: str, unique: bool = False):
        if not fields:
            raise ValueError("CompositeIndex requires at least one field name.")
        self.fields: tuple[str, ...] = fields
        self.unique: bool = unique

    def __repr__(self) -> str:
        u = ", unique=True" if self.unique else ""
        return f"CompositeIndex({', '.join(self.fields)!r}{u})"
