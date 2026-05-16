from __future__ import annotations

import json
import sys
from datetime import date, datetime
from typing import Any, Union, get_args, get_origin

try:
    from typing import Annotated  # 3.9+
except ImportError:  # pragma: no cover
    from typing import Annotated

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


def unwrap_annotated(annotation: Any, _depth: int = 0, _max_depth: int = 10) -> Any:
    """Strip the ``Annotated[T, ...]`` wrapper and return ``T``.

    Args:
        annotation: Type annotation to unwrap
        _depth: Internal recursion depth counter
        _max_depth: Maximum recursion depth (default 10)

    Returns:
        Unwrapped base type

    Raises:
        RecursionError: If nesting exceeds max_depth (guards against pathological types)
    """
    if _depth > _max_depth:
        raise RecursionError(
            f"Type annotation nesting exceeds maximum depth of {_max_depth}. "
            f"This may indicate a malformed or recursive type definition. "
            f"Annotation: {annotation!r}"
        )
    if get_origin(annotation) is Annotated:
        return unwrap_annotated(get_args(annotation)[0], _depth + 1, _max_depth)
    return annotation


def resolve_type(annotation: Any, _depth: int = 0, _max_depth: int = 10) -> tuple[Any, bool]:
    """Return ``(base_type, is_optional)`` after stripping Annotated and Optional.

    Args:
        annotation: Type annotation to resolve
        _depth: Internal recursion depth counter
        _max_depth: Maximum recursion depth (default 10)

    Returns:
        Tuple of (resolved_type, is_optional)

    Raises:
        RecursionError: If nesting exceeds max_depth
    """
    if _depth > _max_depth:
        raise RecursionError(
            f"Type annotation nesting exceeds maximum depth of {_max_depth}. "
            f"This may indicate a malformed or recursive type definition. "
            f"Annotation: {annotation!r}"
        )

    inner = unwrap_annotated(annotation, _depth=_depth, _max_depth=_max_depth)

    origin = get_origin(inner)

    # typing.Union / Optional[T] / Python 3.10+ T | None
    if origin is Union or (sys.version_info >= (3, 10) and _is_union_type(inner)):
        args = get_args(inner)
        non_none = [a for a in args if a is not type(None)]
        is_opt = type(None) in args
        return (non_none[0] if len(non_none) == 1 else inner), is_opt

    return inner, False


def _is_union_type(tp: Any) -> bool:
    import types
    return isinstance(tp, getattr(types, "UnionType", type(None)))


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

    # 頻出する基本型を型チェックで先に処理し、resolve_type を回避する
    if isinstance(value, str):
        return value
    if isinstance(value, int):
        # bool は int のサブクラスなので here で処理される可能性があるが、
        # SQLite では bool も int(0/1) として扱うので問題ない。
        # ただし明示的に bool を 0/1 にしたい場合は先にチェックが必要。
        if isinstance(value, bool):
            return int(value)
        return value
    if isinstance(value, float):
        return value

    base, _ = resolve_type(annotation)
    origin = get_origin(base)

    if isinstance(value, (dict, list)) or origin in (dict, list):
        return json.dumps(value, ensure_ascii=False, default=str)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return value


def deserialize_value(value: Any, annotation: Any, strict: bool = False) -> Any:
    """Convert a SQLite scalar back to the correct Python type.

    Args:
        value: SQLite scalar value
        annotation: Target type annotation
        strict: If True, raise ValueError on malformed data.
               If False, emit warning and return raw/None value (default).

    Returns:
        Deserialized Python value

    Raises:
        ValueError: If strict=True and deserialization fails
    """
    if value is None:
        return None
    base, _ = resolve_type(annotation)
    origin = get_origin(base)

    if base is bool:
        return bool(value)
    if origin in (dict, list) or base in (dict, list):
        if isinstance(value, str):
            try:
                return json.loads(value)
            except (json.JSONDecodeError, ValueError) as e:
                if strict:
                    raise ValueError(
                        f"Malformed JSON data: {value!r}. Cannot deserialize as {base}. "
                        f"Error: {e}"
                    ) from e
                import warnings
                warnings.warn(
                    f"Malformed JSON data: {value!r}. Returning as raw string. "
                    f"Error: {e}",
                    category=RuntimeWarning,
                    stacklevel=2
                )
                return value
        return value
    if base is datetime:
        try:
            return datetime.fromisoformat(value)
        except (ValueError, TypeError, AttributeError) as e:
            if strict:
                raise ValueError(
                    f"Invalid datetime format: {value!r}. Expected ISO8601 format (YYYY-MM-DDTHH:MM:SS). "
                    f"Error: {e}"
                ) from e
            import warnings
            warnings.warn(
                f"Invalid datetime format: {value!r}. Expected ISO8601 format. "
                f"Returning as raw value. Error: {e}",
                category=RuntimeWarning,
                stacklevel=2
            )
            return value
    if base is date:
        try:
            return date.fromisoformat(value)
        except (ValueError, TypeError, AttributeError) as e:
            if strict:
                raise ValueError(
                    f"Invalid date format: {value!r}. Expected ISO8601 format (YYYY-MM-DD). "
                    f"Error: {e}"
                ) from e
            import warnings
            warnings.warn(
                f"Invalid date format: {value!r}. Expected ISO8601 format (YYYY-MM-DD). "
                f"Returning as raw value. Error: {e}",
                category=RuntimeWarning,
                stacklevel=2
            )
            return value
    return value
