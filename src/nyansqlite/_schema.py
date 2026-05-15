from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel

try:
    from typing import get_type_hints
except ImportError:  # pragma: no cover
    from typing_extensions import get_type_hints

from ._markers import CompositeIndex
from ._types import is_indexed, is_searchable, python_type_to_sqlite, resolve_type


# ── helpers ────────────────────────────────────────────────────────────── #

def model_to_table_name(model: type[BaseModel]) -> str:
    """``CamelCase`` → ``snake_case``."""
    return re.sub(r"(?<!^)(?=[A-Z])", "_", model.__name__).lower()


def get_primary_key(model: type[BaseModel]) -> str | None:
    """Return the primary-key field name, or ``None`` (rowid implicit)."""
    # Explicit override
    pk = getattr(model, "__nyan_primary_key__", None)
    if pk:
        return pk
    hints = get_type_hints(model, include_extras=True)
    return "id" if "id" in hints else None


def model_hints(model: type[BaseModel]) -> dict[str, Any]:
    return get_type_hints(model, include_extras=True)


# ── DDL ────────────────────────────────────────────────────────────────── #

def model_to_ddl(model: type[BaseModel]) -> str:
    """Generate ``CREATE TABLE IF NOT EXISTS …`` DDL."""
    table = model_to_table_name(model)
    pk    = get_primary_key(model)
    hints = model_hints(model)

    columns: list[str] = []
    for field_name, annotation in hints.items():
        base_type, is_optional = resolve_type(annotation)
        sql_type = python_type_to_sqlite(annotation)

        col = f'"{field_name}" {sql_type}'
        if field_name == pk:
            col += " PRIMARY KEY"
        elif not is_optional:
            col += " NOT NULL"
        columns.append(col)

    col_defs = ",\n  ".join(columns)
    return f'CREATE TABLE IF NOT EXISTS "{table}" (\n  {col_defs}\n)'


# ── indexes ─────────────────────────────────────────────────────────────── #

def model_to_indexes(model: type[BaseModel]) -> list[str]:
    """Generate ``CREATE [UNIQUE] INDEX IF NOT EXISTS …`` statements."""
    table  = model_to_table_name(model)
    pk     = get_primary_key(model)
    hints  = model_hints(model)
    stmts: list[str] = []

    # Per-field indexes from Indexed[T] / UniqueIndexed[T]
    for field_name, annotation in hints.items():
        if field_name == pk:
            continue
        indexed, unique = is_indexed(annotation)
        if not indexed:
            continue
        u   = "UNIQUE " if unique else ""
        idx = f"idx_{table}_{field_name}"
        stmts.append(
            f'CREATE {u}INDEX IF NOT EXISTS "{idx}" ON "{table}"("{field_name}")'
        )

    # Composite indexes from __nyan_indexes__
    for ci in getattr(model, "__nyan_indexes__", []):
        if not isinstance(ci, CompositeIndex):
            continue
        u       = "UNIQUE " if ci.unique else ""
        idx     = f'idx_{table}_{"_".join(ci.fields)}'
        col_sql = ", ".join(f'"{f}"' for f in ci.fields)
        stmts.append(
            f'CREATE {u}INDEX IF NOT EXISTS "{idx}" ON "{table}"({col_sql})'
        )

    return stmts


# ── FTS5 virtual table + sync triggers ────────────────────────────────── #

def model_to_fts5(model: type[BaseModel]) -> tuple[str | None, list[str]]:
    """Return ``(CREATE VIRTUAL TABLE stmt | None, [trigger stmts])``."""
    table  = model_to_table_name(model)
    hints  = model_hints(model)

    s_fields = [f for f, ann in hints.items() if is_searchable(ann)]
    if not s_fields:
        return None, []

    fts  = f"{table}_fts"
    cols = ", ".join(f'"{f}"' for f in s_fields)

    create_fts = (
        f'CREATE VIRTUAL TABLE IF NOT EXISTS "{fts}" USING fts5(\n'
        f"  {cols},\n"
        f'  content="{table}",\n'
        f'  content_rowid="rowid"\n'
        f")"
    )

    new_vals = ", ".join(f'new."{f}"' for f in s_fields)
    old_vals = ", ".join(f'old."{f}"' for f in s_fields)

    triggers = [
        # INSERT
        (
            f'CREATE TRIGGER IF NOT EXISTS "{table}_fts_ai"\n'
            f'  AFTER INSERT ON "{table}" BEGIN\n'
            f'    INSERT INTO "{fts}"(rowid, {cols})\n'
            f"    VALUES(new.rowid, {new_vals});\n"
            f"END"
        ),
        # DELETE
        (
            f'CREATE TRIGGER IF NOT EXISTS "{table}_fts_ad"\n'
            f'  AFTER DELETE ON "{table}" BEGIN\n'
            f'    INSERT INTO "{fts}"("{fts}", rowid, {cols})\n'
            f"    VALUES('delete', old.rowid, {old_vals});\n"
            f"END"
        ),
        # UPDATE
        (
            f'CREATE TRIGGER IF NOT EXISTS "{table}_fts_au"\n'
            f'  AFTER UPDATE ON "{table}" BEGIN\n'
            f'    INSERT INTO "{fts}"("{fts}", rowid, {cols})\n'
            f"    VALUES('delete', old.rowid, {old_vals});\n"
            f'    INSERT INTO "{fts}"(rowid, {cols})\n'
            f"    VALUES(new.rowid, {new_vals});\n"
            f"END"
        ),
    ]

    return create_fts, triggers
