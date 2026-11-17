from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import date, datetime
from itertools import groupby
from typing import Annotated, Any, Union, get_args, get_origin

from pydantic import BaseModel

from ._connection import NyanConnection
from ._markers import _NyanIndexedMarker, _NyanSearchableMarker
from ._types import _is_union_type


def model_insert_row(obj: BaseModel, encoders: dict[str, Callable[[Any], Any]]) -> dict[str, Any]:
    return {name: encoders[name](value) for name, value in obj.model_dump().items() if name in encoders}


def insert_statement(table: str, fields: tuple[str, ...]) -> str:
    if not fields:
        return f'INSERT INTO "{table}" DEFAULT VALUES'
    columns = ", ".join(f'"{name}"' for name in fields)
    placeholders = ", ".join("?" for _ in fields)
    return f'INSERT INTO "{table}" ({columns}) VALUES ({placeholders})'


def _plain_annotation(annotation: Any) -> bool:
    if annotation in (str, int, float, bool, bytes, date, datetime, type(None)):
        return True
    origin = get_origin(annotation)
    args = get_args(annotation)
    if origin is Annotated:
        return _plain_annotation(args[0]) and all(
            isinstance(marker, (_NyanIndexedMarker, _NyanSearchableMarker)) for marker in args[1:]
        )
    if origin in (dict, list, Union) or _is_union_type(annotation):
        return all(_plain_annotation(arg) for arg in args)
    return False


def can_bind_fields_directly(model: type[BaseModel], hints: dict[str, Any]) -> bool:
    decorators = model.__pydantic_decorators__
    return (
        model.model_dump is BaseModel.model_dump
        and not decorators.model_serializers
        and not decorators.field_serializers
        and model.model_config.get("extra") != "allow"
        and not model.model_config.get("serialize_by_alias")
        and hints.keys() == model.model_fields.keys()
        and all(
            not field.exclude and getattr(field, "exclude_if", None) is None and _plain_annotation(hints[name])
            for name, field in model.model_fields.items()
        )
    )


def insert_dumped_rows(
    conn: NyanConnection,
    table: str,
    encoders: dict[str, Callable[[Any], Any]],
    objs: Sequence[BaseModel],
) -> None:
    rows = (model_insert_row(obj, encoders) for obj in objs)
    # A serializer can omit columns on a per-row basis. Group only adjacent rows
    # with the same columns to retain input order and stream through the batch.
    for fields, group in groupby(rows, tuple):
        conn.executemany(insert_statement(table, fields), (tuple(row.values()) for row in group))
