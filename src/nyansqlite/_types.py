from __future__ import annotations

import json
import sys
from datetime import date, datetime
from typing import Any, Union, get_args, get_origin

try:
    from typing import Annotated, get_type_hints  # 3.9+
except ImportError:  # pragma: no cover
    from typing_extensions import Annotated, get_type_hints

from ._markers import _NyanIndexedMarker, _NyanSearchableMarker

# ── annotation inspection ──────────────────────────────────────────────── #

def is_indexed(annotation: Any) -> tuple[bool, bool]:
    """Return ``(is_indexed, is_unique)``."""
    if get_origin(annotation) is Annotated:
        for meta in get_args(annotation)[1:]:
            if isinstance(meta, _NyanIndexedMarker):
                return True, meta.unique
    return False, False


def is_searchable(annotation: Any) -> bool:
    if get_origin(annotation) is Annotated:
        return any(isinstance(m, _NyanSearchableMarker) for m in get_args(annotation)[1:])
    return False


def unwrap_annotated(annotation: Any) -> Any:
    """Strip the ``Annotated[T, ...]`` wrapper and return ``T``."""
    if get_origin(annotation) is Annotated:
        return get_args(annotation)[0]
    return annotation


def resolve_type(annotation: Any) -> tuple[Any, bool]:
    """Return ``(base_type, is_optional)`` after stripping Annotated and Optional."""
    inner = unwrap_annotated(annotation)

    origin = get_origin(inner)

    # typing.Union / Optional[T]
    if origin is Union:
        args = get_args(inner)
        non_none = [a for a in args if a is not type(None)]
        is_opt = type(None) in args
        return (non_none[0] if len(non_none) == 1 else inner), is_opt

    # Python 3.10+  ``T | None`` syntax
    if sys.version_info >= (3, 10):
        import types as _types
        if isinstance(inner, _types.UnionType):
            args = get_args(inner)
            non_none = [a for a in args if a is not type(None)]
            is_opt = type(None) in args
            return (non_none[0] if len(non_none) == 1 else inner), is_opt

    return inner, False


# ── Python → SQLite type map ───────────────────────────────────────────── #

_PY_TO_SQL: dict[Any, str] = {
    int:      "INTEGER",
    float:    "REAL",
    str:      "TEXT",
    bytes:    "BLOB",
    bool:     "INTEGER",
    datetime: "TEXT",
    date:     "TEXT",
    dict:     "TEXT",   # JSON
    list:     "TEXT",   # JSON
}


def python_type_to_sqlite(annotation: Any) -> str:
    base, _ = resolve_type(annotation)
    origin = get_origin(base)
    if origin in (list, dict):
        return "TEXT"
    return _PY_TO_SQL.get(base, "TEXT")


# ── value serialization ────────────────────────────────────────────────── #

def serialize_value(value: Any, annotation: Any) -> Any:
    """Convert a Python value to a SQLite-storable scalar."""
    if value is None:
        return None
    base, _ = resolve_type(annotation)
    origin = get_origin(base)

    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (dict, list)) or origin in (dict, list):
        return json.dumps(value, ensure_ascii=False, default=str)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return value


def deserialize_value(value: Any, annotation: Any) -> Any:
    """Convert a SQLite scalar back to the correct Python type."""
    if value is None:
        return None
    base, _ = resolve_type(annotation)
    origin = get_origin(base)

    if base is bool:
        return bool(value)
    if origin in (dict, list) or base in (dict, list):
        if isinstance(value, str):
            return json.loads(value)
        return value
    if base is datetime:
        return datetime.fromisoformat(value)
    if base is date:
        return date.fromisoformat(value)
    return value
