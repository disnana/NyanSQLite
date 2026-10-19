from __future__ import annotations

import re
from functools import lru_cache
from numbers import Integral
from typing import Any, Optional

from pydantic import TypeAdapter

from ._types import serialize_value
from .exceptions import FieldNotFoundError, QueryValidationError

_OP_PATTERN = re.compile(r"^\s*(\w+)\s*(>=|<=|!=|>|<|=)\s*(.*)$")
_OPERATORS = {"eq": "=", "ne": "!=", "gt": ">", "gte": ">=", "lt": "<", "lte": "<="}


def merge_where(where: Optional[dict[str, Any]], kwargs: dict[str, Any]) -> dict[str, Any]:
    if where is None:
        return kwargs
    if not isinstance(where, dict):
        raise QueryValidationError("where must be a dict of field filters")
    duplicate = where.keys() & kwargs.keys()
    if duplicate:
        raise QueryValidationError(f"Duplicate filters in where and keyword arguments: {sorted(duplicate)}")
    return {**where, **kwargs}


@lru_cache(maxsize=256)
def _filter_adapter(base: Any) -> TypeAdapter:
    return TypeAdapter(base)


def _filter_value(meta, field, value, op):
    if value is None:
        if op in ("gt", "gte", "lt", "lte", "like"):
            raise QueryValidationError(f"Cannot apply '{_OPERATORS.get(op, op)}' to None")
        return None
    try:
        if op == "like":
            if not isinstance(value, str):
                raise TypeError("LIKE expects a string pattern")
            return value
        if meta:
            annotation = meta.hints[field]
            base = meta.filter_bases[field]
            # Ignore storage constraints (e.g. ge=0) for search bounds.
            if type(value) is base and base in (str, int, float, bool, bytes):
                return int(value) if base is bool else value
            try:
                adapter = _filter_adapter(base)
            except TypeError:
                adapter = TypeAdapter(base)
            value = adapter.validate_python(value)
            value = serialize_value(value, annotation)
        return value
    except (ValueError, TypeError) as exc:
        raise QueryValidationError(
            f"Cannot apply '{_OPERATORS.get(op, op)}' in filter {field}__{op}={value!r}: {exc}"
        ) from exc


def _build_where(args: tuple[str, ...], kwargs: dict[str, Any], model_meta=None) -> tuple[str, list[Any]]:
    clauses = []
    values = []

    def check_field(field):
        if model_meta and field not in model_meta.hints:
            raise FieldNotFoundError(f"Fields not found on model: ['{field}']. Available: {list(model_meta.hints)}")

    for filt in args:
        match = _OP_PATTERN.match(filt) if isinstance(filt, str) else None
        if not match:
            raise QueryValidationError(f"Unsafe or unsupported string filter: {filt!r}. Use explicit comparisons.")
        field, operator, literal = match.groups()
        check_field(field)
        literal = literal.strip()
        try:
            if len(literal) >= 2 and literal[0] == literal[-1] and literal[0] in ("'", '"'):
                value = literal[1:-1]
            else:
                try:
                    value = int(literal)
                except ValueError:
                    value = float(literal)
        except ValueError as exc:
            raise QueryValidationError(f"Unsafe or unsupported string filter: {filt!r}") from exc
        op = next(key for key, val in _OPERATORS.items() if val == operator)
        clauses.append(f'"{field}" {operator} ?')
        values.append(_filter_value(model_meta, field, value, op))

    for key, value in kwargs.items():
        field, op = key, "eq"
        if "__" in key and not (model_meta and key in model_meta.hints):
            field, op = key.rsplit("__", 1)
        check_field(field)
        quoted = f'"{field}"'
        if op == "is_null":
            if not isinstance(value, bool):
                raise QueryValidationError(f"{key} expects bool, got {type(value).__name__}")
            clauses.append(f"{quoted} IS {'NULL' if value else 'NOT NULL'}")
        elif op == "in":
            try:
                if isinstance(value, (str, bytes, dict)):
                    raise TypeError("expected a collection of values")
                items = list(value)
            except TypeError as exc:
                raise QueryValidationError(
                    f"Filter {key} expects iterable (value must be iterable), got {type(value).__name__}"
                ) from exc
            if not items:
                clauses.append("0")
            else:
                placeholders = ", ".join(["?"] * len(items))
                clauses.append(f"{quoted} IN ({placeholders})")
                base = model_meta.filter_bases[field] if model_meta else None
                if base in (str, int, float, bool, bytes) and all(
                    type(item) is base or item is None for item in items
                ):
                    values.extend(items)
                else:
                    values.extend(_filter_value(model_meta, field, item, "eq") for item in items)
        elif op in _OPERATORS or op == "like":
            if value is None and op in ("eq", "ne"):
                clauses.append(f"{quoted} IS {'NOT ' if op == 'ne' else ''}NULL")
            else:
                clauses.append(f"{quoted} {_OPERATORS.get(op, 'LIKE')} ?")
                values.append(_filter_value(model_meta, field, value, op))
        else:
            raise QueryValidationError(f"Unknown filter operator: __{op}")
    return ("WHERE " + " AND ".join(clauses) if clauses else ""), values


def _order_sql(order_by: Optional[str], desc: bool) -> str:
    if not order_by:
        return ""
    return f' ORDER BY "{order_by}" {"DESC" if desc else "ASC"}'


def _limit_sql(limit: Optional[int], offset: Optional[int]) -> tuple[str, list[int]]:
    sql = ""
    values = []
    for name, value in (("limit", limit), ("offset", offset)):
        if value is not None and (isinstance(value, bool) or not isinstance(value, Integral) or value < 0):
            raise QueryValidationError(f"{name} must be a non-negative integer: {value!r}")
    if limit is not None:
        sql += " LIMIT ?"
        values.append(int(limit))
    if offset is not None:
        if limit is None:
            sql += " LIMIT -1"
        sql += " OFFSET ?"
        values.append(int(offset))
    return sql, values
