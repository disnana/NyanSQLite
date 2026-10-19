from __future__ import annotations

import re
from typing import Any, Optional

from pydantic import BaseModel

from ._markers import CompositeIndex
from ._types import is_indexed, is_searchable, python_type_to_sqlite, resolve_type
from .exceptions import SchemaMismatchError

# ── helpers ────────────────────────────────────────────────────────────── #

_IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def quote_identifier(identifier: str) -> str:
    """Validate and quote an internally generated SQLite identifier."""
    if not isinstance(identifier, str) or not _IDENTIFIER_PATTERN.fullmatch(identifier):
        raise ValueError(f"Invalid SQLite identifier: {identifier!r}")
    return f'"{identifier}"'


def model_to_table_name(model: type[BaseModel]) -> str:
    """``CamelCase`` → ``snake_case``."""
    table = getattr(model, "__tablename__", None)
    if table is None:
        table = re.sub(r"(?<!^)(?=[A-Z])", "_", model.__name__).lower()
    quote_identifier(table)
    return table


def get_primary_key(model: type[BaseModel]) -> Optional[str]:
    """Return the primary-key field name, or ``None`` (rowid implicit)."""
    # Explicit override
    pk = getattr(model, "__nyan_primary_key__", None)
    if pk:
        if pk not in model.model_fields:
            raise ValueError(f"Unknown primary key field: {pk!r}")
        return pk
    return "id" if "id" in model.model_fields else None


def model_hints(model: type[BaseModel]) -> dict[str, Any]:
    if not model.model_fields:
        raise ValueError("A registered model must have at least one persistent field")
    return {name: field.rebuild_annotation() for name, field in model.model_fields.items()}


# ── DDL ────────────────────────────────────────────────────────────────── #

def model_to_ddl(model: type[BaseModel]) -> str:
    """Generate ``CREATE TABLE IF NOT EXISTS …`` DDL."""
    table = model_to_table_name(model)
    pk    = get_primary_key(model)
    hints = model_hints(model)
    for field_name in hints:
        quote_identifier(field_name)

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


def check_table_schema(model: type[BaseModel], columns: list[dict[str, Any]]) -> None:
    """Fail early when an existing table cannot represent the model."""
    hints = model_hints(model)
    pk = get_primary_key(model)
    actual = {column["name"]: column for column in columns}
    missing = sorted(set(hints) - set(actual))
    extra = sorted(set(actual) - set(hints))
    incompatible = []
    for name, annotation in hints.items():
        column = actual.get(name)
        if column is None:
            continue
        _, optional = resolve_type(annotation)
        expected_type = python_type_to_sqlite(annotation)
        expected_pk = name == pk
        expected_not_null = not optional and not expected_pk
        if (
            column["type"].upper() != expected_type
            or bool(column["pk"]) != expected_pk
            or bool(column["notnull"]) != expected_not_null
        ):
            incompatible.append(name)
    if missing or extra or incompatible:
        raise SchemaMismatchError(
            f"Existing table '{model_to_table_name(model)}' differs from model {model.__name__}: "
            f"missing columns={missing}, extra columns={extra}, "
            f"incompatible columns={incompatible}. Migrate the table before register()."
        )


def check_fts_schema(
    model: type[BaseModel], existing_sql: str | None, columns: list[dict[str, Any]]
) -> None:
    """Reject an FTS definition left behind by a changed Searchable annotation."""
    expected = [name for name, ann in model_hints(model).items() if is_searchable(ann)]
    if existing_sql is None:
        return  # register() will create FTS5 when the model needs it.
    actual = [column["name"] for column in columns]
    if not expected or "using fts5" not in existing_sql.lower() or actual != expected:
        raise SchemaMismatchError(
            f"Existing FTS table '{model_to_table_name(model)}_fts' differs from "
            f"model {model.__name__}: searchable columns={actual}, expected={expected}. "
            "Migrate the FTS table and triggers before register()."
        )


# ── indexes ─────────────────────────────────────────────────────────────── #

def index_specs(model: type[BaseModel]) -> dict[str, tuple[tuple[str, ...], bool]]:
    """One source of truth for index creation and existing-schema checks."""
    table  = model_to_table_name(model)
    pk     = get_primary_key(model)
    hints  = model_hints(model)
    specs: dict[str, tuple[tuple[str, ...], bool]] = {}

    # Per-field indexes from Indexed[T] / UniqueIndexed[T]
    for field_name, annotation in hints.items():
        if field_name == pk:
            continue
        indexed, unique = is_indexed(annotation)
        if not indexed:
            continue
        idx = f"idx_{table}_{field_name}"
        specs[idx] = ((field_name,), unique)

    # Composite indexes from __nyan_indexes__
    for ci in getattr(model, "__nyan_indexes__", []):
        if not isinstance(ci, CompositeIndex):
            continue
        missing = [field for field in ci.fields if field not in hints]
        if missing:
            raise ValueError(
                f"Composite index contains unknown fields {missing}; "
                f"available fields: {list(hints)}"
            )
        for field in ci.fields:
            quote_identifier(field)
        idx     = f'idx_{table}_{"_".join(ci.fields)}'
        spec = (ci.fields, ci.unique)
        if idx in specs and specs[idx] != spec:
            raise ValueError(f"Conflicting index definitions: {idx}")
        specs[idx] = spec
    return specs


def model_to_indexes(model: type[BaseModel]) -> list[str]:
    table = model_to_table_name(model)
    stmts = []
    for name, (fields, unique) in index_specs(model).items():
        columns = ", ".join(quote_identifier(field) for field in fields)
        qualifier = "UNIQUE " if unique else ""
        stmts.append(f'CREATE {qualifier}INDEX IF NOT EXISTS "{name}" ON "{table}"({columns})')

    return stmts


def check_index_schema(model: type[BaseModel], connection: Any) -> None:
    table = model_to_table_name(model)
    existing = {row["name"]: row for row in connection.execute(f'PRAGMA index_list("{table}")')}
    for name, (fields, unique) in index_specs(model).items():
        actual = existing.get(name)
        columns = connection.execute(f'PRAGMA index_xinfo("{name}")')
        keys = [column for column in columns if column["key"]]
        if (
            actual is None or bool(actual["unique"]) != unique or actual["partial"]
            or tuple(column["name"] for column in keys) != fields
            or any(column["desc"] or column["coll"].upper() != "BINARY" for column in keys)
        ):
            raise SchemaMismatchError(
                f"Existing index '{name}' differs from model {model.__name__}. "
                "Migrate the index before register()."
            )


# ── FTS5 virtual table + sync triggers ────────────────────────────────── #

def model_to_fts5(model: type[BaseModel]) -> tuple[Optional[str], list[str]]:
    """Return ``(CREATE VIRTUAL TABLE stmt | None, [trigger stmts])``."""
    table  = model_to_table_name(model)
    hints  = model_hints(model)

    s_fields = [f for f, ann in hints.items() if is_searchable(ann)]
    if not s_fields:
        return None, []

    fts  = f"{table}_fts"
    cols = ", ".join(f'"{f}"' for f in s_fields)

    create_fts = (  # nosec B608 -- all identifiers are validated model metadata
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
            f'CREATE TRIGGER IF NOT EXISTS "{table}_fts_ai"\n'  # nosec B608
            f'  AFTER INSERT ON "{table}" BEGIN\n'
            f'    INSERT INTO "{fts}"(rowid, {cols})\n'
            f"    VALUES(new.rowid, {new_vals});\n"
            f"END"
        ),
        # DELETE
        (
            f'CREATE TRIGGER IF NOT EXISTS "{table}_fts_ad"\n'  # nosec B608
            f'  AFTER DELETE ON "{table}" BEGIN\n'
            f'    INSERT INTO "{fts}"("{fts}", rowid, {cols})\n'
            f"    VALUES('delete', old.rowid, {old_vals});\n"
            f"END"
        ),
        # UPDATE
        (
            f'CREATE TRIGGER IF NOT EXISTS "{table}_fts_au"\n'  # nosec B608
            f'  AFTER UPDATE ON "{table}" BEGIN\n'
            f'    INSERT INTO "{fts}"("{fts}", rowid, {cols})\n'
            f"    VALUES('delete', old.rowid, {old_vals});\n"
            f'    INSERT INTO "{fts}"(rowid, {cols})\n'
            f"    VALUES(new.rowid, {new_vals});\n"
            f"END"
        ),
    ]

    return create_fts, triggers
