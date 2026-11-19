"""Schema migration planning and execution shared by the sync and async APIs.

Design notes
------------
* ``register()`` stays strict by default: it never edits an existing table unless the
  caller passes ``on_mismatch="migrate"``.
* ``plan_migration()`` only reads the database and returns a :class:`MigrationPlan`.
* ``migrate()`` applies the plan inside one transaction. Steps that preserve data
  (adding columns, renaming a column, relaxing NOT NULL) run by default. Steps that can
  lose or reject data (dropping a column, changing a type, tightening NOT NULL) need
  ``allow_destructive=True``.
* What cannot be inferred from the types is stated by the caller:
  ``__nyan_renames__`` on the model names renamed columns, and ``fill=`` supplies the
  values of new or converted columns.
* Table rebuilds copy rows into a new table, check that the copied values match the new
  column types, and only then swap the tables. Any failure rolls everything back.
* ``backup=`` copies the database file with ``VACUUM INTO`` before anything is changed.
  It is off by default.
"""
from __future__ import annotations

import math
import os
import time
from collections.abc import Mapping
from dataclasses import dataclass, replace
from typing import Any, Callable, Optional, Union

from pydantic import BaseModel
from pydantic_core import PydanticUndefined

from ._schema import (
    diff_table,
    fts_mismatch,
    get_primary_key,
    model_hints,
    model_to_ddl,
    model_to_table_name,
    quote_identifier,
)
from ._types import compile_serializer, python_type_to_sqlite, resolve_type
from .exceptions import MigrationError

_TYPEOF = {"INTEGER": "integer", "REAL": "real", "TEXT": "text", "BLOB": "blob"}
_CHUNK = 1000
_ROWID = "__nyan_rowid"

BackupOption = Union[bool, str, "os.PathLike[str]", None]


@dataclass(frozen=True)
class Statement:
    """One unit of work.

    ``sql`` runs as written. ``must_be_zero`` turns it into a check that must return ``n == 0``.
    ``run`` replaces the SQL with a Python callable that receives the connection.
    """

    sql: str
    must_be_zero: Optional[str] = None
    run: Optional[Callable[[Any], None]] = None


@dataclass(frozen=True)
class MigrationStep:
    kind: str  # "add_column" | "rename_column" | "rebuild_table" | "rebuild_fts"
    description: str
    statements: tuple[Statement, ...]
    destructive: bool = False


@dataclass(frozen=True)
class MigrationPlan:
    table: str
    steps: tuple[MigrationStep, ...] = ()
    blocked: tuple[str, ...] = ()
    backup_path: Optional[str] = None

    @property
    def is_empty(self) -> bool:
        return not self.steps and not self.blocked

    @property
    def has_destructive(self) -> bool:
        return any(step.destructive for step in self.steps)

    @property
    def sql(self) -> list[str]:
        """Every SQL statement that would run, in order (checks and Python steps excluded)."""
        return [
            st.sql
            for step in self.steps
            for st in step.statements
            if st.must_be_zero is None and st.run is None
        ]

    def describe(self) -> str:
        if self.is_empty:
            return f"{self.table}: no changes"
        lines = [f"{self.table}:"]
        for step in self.steps:
            mark = " [destructive]" if step.destructive else ""
            lines.append(f"  - {step.description}{mark}")
        for reason in self.blocked:
            lines.append(f"  ! blocked: {reason}")
        if self.backup_path:
            lines.append(f"  backup: {self.backup_path}")
        return "\n".join(lines)

    __str__ = describe


# ── defaults ────────────────────────────────────────────────────────────── #

def _sql_literal(value: Any) -> str:
    """Render a serialized default as a SQL literal (DDL cannot bind parameters)."""
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("non-finite float default")
        return repr(value)
    if isinstance(value, str):
        if "\x00" in value:
            raise ValueError("default contains a NUL character")
        return "'" + value.replace("'", "''") + "'"
    if isinstance(value, (bytes, bytearray)):
        return "X'" + bytes(value).hex() + "'"
    raise ValueError(f"unsupported default type: {type(value).__name__}")


def _default_value(model: type[BaseModel], name: str, annotation: Any) -> tuple[bool, Any, Optional[str]]:
    """Return ``(has_default, serialized_value, problem)`` for a field."""
    field = model.model_fields.get(name)
    if field is None:
        return False, None, None
    if field.default_factory is not None:
        return False, None, f"'{name}' uses default_factory, which cannot be applied to existing rows"
    if field.default is PydanticUndefined:
        return False, None, None
    value = compile_serializer(annotation)(field.default)
    try:
        _sql_literal(value)
    except ValueError as error:
        return False, None, f"default of '{name}' cannot be written to SQL: {error}"
    return True, value, None


# ── planning ────────────────────────────────────────────────────────────── #

def _declared_renames(model: type[BaseModel], hints: dict[str, Any], blocked: list[str]) -> dict[str, str]:
    """Read ``__nyan_renames__ = {new_name: old_name}`` and validate it."""
    declared = getattr(model, "__nyan_renames__", None) or {}
    renames: dict[str, str] = {}
    for new, old in dict(declared).items():
        if new not in hints:
            blocked.append(f"__nyan_renames__ names '{new}', which is not a field of {model.__name__}")
            continue
        quote_identifier(new)
        quote_identifier(old)
        renames[new] = old
    clash = sorted(set(renames) & set(renames.values()))
    if clash:
        blocked.append(f"__nyan_renames__ chains renames through {clash}; rename one step at a time")
        return {}
    return renames


def build_plan(
    conn: Any,
    model: type[BaseModel],
    fill: Optional[Mapping[str, Any]] = None,
) -> MigrationPlan:
    table = model_to_table_name(model)
    columns = conn.execute(f'PRAGMA table_info("{table}")')
    fts_name = f"{table}_fts"
    fts_rows = conn.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (fts_name,))
    fts_cols = conn.execute(f'PRAGMA table_info("{fts_name}")') if fts_rows else []
    stale_fts = fts_mismatch(model, fts_rows[0]["sql"] if fts_rows else None, fts_cols)

    if not columns:  # table does not exist yet: register() creates it
        steps = (_drop_fts_step(table),) if stale_fts else ()
        return MigrationPlan(table, steps)

    hints = model_hints(model)
    pk = get_primary_key(model)
    blocked: list[str] = []
    fill = dict(fill or {})
    for name in fill:
        if name not in hints:
            blocked.append(f"fill['{name}'] is not a field of {model.__name__}")

    # Renames come first so that the rest of the plan sees the new column names.
    present = {c["name"] for c in columns}
    applied: dict[str, str] = {}  # old -> new
    rename_steps: list[MigrationStep] = []
    for new, old in _declared_renames(model, hints, blocked).items():
        if old in present and new not in present:
            applied[old] = new
            rename_steps.append(MigrationStep(
                "rename_column",
                f"rename column {old} -> {new}",
                (Statement(f'ALTER TABLE "{table}" RENAME COLUMN {quote_identifier(old)} TO {quote_identifier(new)}'),),
            ))
        elif old in present and new in present:
            blocked.append(f"both '{old}' and '{new}' exist, so '{old}' cannot be renamed to '{new}'")
    effective = [{**c, "name": applied.get(c["name"], c["name"])} for c in columns]
    actual = {c["name"]: c for c in effective}

    missing, extra, incompatible = diff_table(model, effective)
    rows = conn.execute(f'SELECT COUNT(*) AS n FROM "{table}"')[0]["n"]
    fill_cols = [name for name in fill if name in hints and (name in missing or name in incompatible)]

    def new_column_default(name: str) -> tuple[Optional[str], bool]:
        """Return ``(literal, ok)``. ``ok`` is False when existing rows cannot fill the column."""
        if name in fill:
            return None, True
        _, optional = resolve_type(hints[name])
        has, value, problem = _default_value(model, name, hints[name])
        literal = _sql_literal(value) if has else None
        if literal == "NULL":
            literal = None
        if rows and not optional and literal is None:
            blocked.append(
                problem
                or f"'{name}' is required and has no default, so existing rows cannot fill it. "
                   f"Give it a default, make it Optional, or pass fill={{'{name}': ...}}"
            )
            return None, False
        return literal, True

    needs_rebuild = bool(extra or incompatible or (pk in missing) or fill_cols)
    steps: list[MigrationStep] = []
    if fts_rows and (stale_fts or needs_rebuild):
        steps.append(_drop_fts_step(table))
    steps.extend(rename_steps)

    if needs_rebuild:
        for name in missing:
            new_column_default(name)  # records why a column is blocked
        steps.append(_rebuild_step(model, table, hints, pk, actual, missing, extra, incompatible, fill, fill_cols, rows))
    else:
        for name in missing:
            literal, ok = new_column_default(name)
            if not ok:
                continue
            _, optional = resolve_type(hints[name])
            sql_type = python_type_to_sqlite(hints[name])
            ddl = f'ALTER TABLE "{table}" ADD COLUMN {quote_identifier(name)} {sql_type}'
            if not optional:
                ddl += " NOT NULL"
            if literal is not None:
                ddl += f" DEFAULT {literal}"
            if not optional and literal is None:
                # Empty table: SQLite still refuses NOT NULL without a default, so rebuild instead.
                steps.append(_rebuild_step(model, table, hints, pk, actual, missing, extra, incompatible, fill, fill_cols, rows))
                break
            steps.append(MigrationStep("add_column", f"add column {name} ({sql_type})", (Statement(ddl),)))

    return MigrationPlan(table, tuple(steps), tuple(dict.fromkeys(blocked)))


def _drop_fts_step(table: str) -> MigrationStep:
    fts = f"{table}_fts"
    stmts = [Statement(f'DROP TRIGGER IF EXISTS "{table}_fts_{suffix}"') for suffix in ("ai", "ad", "au")]
    stmts.append(Statement(f'DROP TABLE IF EXISTS "{fts}"'))
    return MigrationStep(
        "rebuild_fts",
        f"drop full-text index {fts} (register() recreates it from the table)",
        tuple(stmts),
    )


def _make_copier(
    model: type[BaseModel],
    table: str,
    new: str,
    hints: dict[str, Any],
    old_cols: list[str],
    missing: list[str],
    fill: Mapping[str, Any],
    copy_rowid: bool,
) -> Callable[[Any], None]:
    """Copy rows in Python so that ``fill`` values can be computed per row."""
    target = list(old_cols)
    for name in missing:
        has_default = name in fill or _default_value(model, name, hints[name])[0]
        if has_default:
            target.append(name)
    serializers = {name: compile_serializer(hints[name]) for name in target}
    defaults = {
        name: _default_value(model, name, hints[name])[1]
        for name in missing
        if name not in fill
    }
    columns = (["rowid"] if copy_rowid else []) + target
    col_sql = ", ".join("rowid" if c == "rowid" else quote_identifier(c) for c in columns)
    insert_sql = f'INSERT INTO "{new}" ({col_sql}) VALUES ({", ".join("?" * len(columns))})'
    select_sql = f'SELECT rowid AS "{_ROWID}", * FROM "{table}" WHERE rowid > ? ORDER BY rowid LIMIT {_CHUNK}'

    def copy(conn: Any) -> None:
        last = -(2 ** 63)
        while True:
            batch = conn.execute(select_sql, (last,))
            if not batch:
                return
            out = []
            for row in batch:
                rowid = row.pop(_ROWID)
                last = rowid
                values = []
                for name in target:
                    if name in fill:
                        source = fill[name]
                        values.append(serializers[name](source(dict(row)) if callable(source) else source))
                    elif name in row:
                        values.append(row[name])
                    else:
                        values.append(defaults[name])
                out.append(((rowid,) if copy_rowid else ()) + tuple(values))
            conn.executemany(insert_sql, out)

    return copy


def _rebuild_step(
    model, table, hints, pk, actual, missing, extra, incompatible, fill, fill_cols, rows
) -> MigrationStep:
    new = f"{table}__nyan_new"
    quote_identifier(new)
    old_cols = [name for name in hints if name in actual]          # columns present in both
    pk_is_rowid_alias = pk is not None and python_type_to_sqlite(hints[pk]) == "INTEGER"
    copy_rowid = not pk_is_rowid_alias   # tables without an INTEGER PRIMARY KEY keep their rowids

    statements = [
        Statement(f'DROP TABLE IF EXISTS "{new}"'),
        Statement(model_to_ddl(model, table=new)),
    ]
    if fill_cols:
        # Columns whose values come from ``fill`` are computed in Python, so existing
        # values of converted columns are replaced and new columns receive a value.
        statements.append(Statement(
            f"-- copy rows into {new}, computing {', '.join(fill_cols)} in Python",
            run=_make_copier(
                model, table, new, hints,
                old_cols, missing, fill, copy_rowid,
            ),
        ))
    else:
        copy_cols = list(old_cols)
        select_exprs = [quote_identifier(name) for name in old_cols]
        for name in missing:
            has, value, _ = _default_value(model, name, hints[name])
            if has and value is not None:
                copy_cols.append(name)
                select_exprs.append(_sql_literal(value))
        if copy_rowid:
            copy_cols.insert(0, "rowid")
            select_exprs.insert(0, "rowid")
        col_sql = ", ".join(c if c == "rowid" else quote_identifier(c) for c in copy_cols)
        statements.append(Statement(
            f'INSERT INTO "{new}" ({col_sql}) SELECT {", ".join(select_exprs)} FROM "{table}"'
        ))

    # A column whose declared type changed must really hold that type (SQLite converts silently).
    for name in dict.fromkeys([*incompatible, *fill_cols]):
        expected = python_type_to_sqlite(hints[name])
        statements.append(Statement(
            f'SELECT COUNT(*) AS n FROM "{new}" WHERE {quote_identifier(name)} IS NOT NULL '
            f"AND typeof({quote_identifier(name)}) != '{_TYPEOF.get(expected, 'text')}'",
            must_be_zero=f"column '{name}' has values that cannot be stored as {expected}",
        ))
    statements += [
        Statement(f'DROP TABLE "{table}"'),
        Statement(f'ALTER TABLE "{new}" RENAME TO "{table}"'),
    ]

    parts = []
    destructive = False
    if extra:
        parts.append("drop columns " + ", ".join(extra))
        destructive = True
    for name in incompatible:
        a = actual[name]
        _, optional = resolve_type(hints[name])
        new_type = python_type_to_sqlite(hints[name])
        if a["type"].upper() != new_type or bool(a["pk"]) != (name == pk):
            parts.append(f"change {name}: {a['type'] or '?'} -> {new_type}")
            destructive = True
        else:  # only the NOT NULL flag differs
            tighten = not optional and name != pk
            parts.append(f"{name}: {'NULL' if tighten else 'NOT NULL'} -> {'NOT NULL' if tighten else 'NULL'}")
            destructive = destructive or tighten
    for name in missing:
        parts.append(f"add column {name}")
    if fill_cols:
        parts.append("fill " + ", ".join(fill_cols) + " in Python")
    return MigrationStep(
        "rebuild_table",
        f"rebuild table {table} ({'; '.join(parts)}); {rows} row(s) copied",
        tuple(statements),
        destructive=destructive,
    )


# ── backup ──────────────────────────────────────────────────────────────── #

def _take_backup(conn: Any, backup: BackupOption) -> Optional[str]:
    """Copy the database with ``VACUUM INTO``. Returns the path, or None when not requested."""
    if backup is None or backup is False:
        return None
    path = getattr(conn, "path", None)
    if backup is True:
        if not path or path == ":memory:" or str(path).startswith("file::memory:"):
            raise MigrationError("backup=True needs a database file. Pass a path, or use a file database.")
        target = f"{path}.bak-{time.strftime('%Y%m%d-%H%M%S')}"
    else:
        target = os.fspath(backup)
    if os.path.exists(target):
        raise MigrationError(f"backup target already exists: {target}")
    if conn.in_transaction():
        raise MigrationError("A backup cannot be taken inside a transaction. Migrate before atomic(), or pass backup=False.")
    try:
        conn.execute("VACUUM INTO ?", (target,))
    except Exception as error:
        raise MigrationError(f"backup failed: {error}") from error
    return target


# ── execution ───────────────────────────────────────────────────────────── #

def _check_allowed(plan: MigrationPlan, allow_destructive: bool) -> None:
    if plan.blocked:
        raise MigrationError("Migration is blocked:\n" + plan.describe())
    if plan.has_destructive and not allow_destructive:
        raise MigrationError(
            "This migration can change or discard existing data. Review it with "
            "plan_migration() and pass allow_destructive=True to apply it:\n" + plan.describe()
        )


def run_migration(
    conn: Any,
    model: type[BaseModel],
    *,
    allow_destructive: bool,
    dry_run: bool,
    backup: BackupOption = None,
    fill: Optional[Mapping[str, Any]] = None,
) -> MigrationPlan:
    """Plan and (unless ``dry_run``) apply a migration inside a single transaction."""
    preview = build_plan(conn, model, fill)
    if dry_run or preview.is_empty:
        return preview
    _check_allowed(preview, allow_destructive)
    backup_path = _take_backup(conn, backup) if preview.steps else None

    with conn.transaction():  # plan again inside the transaction so the plan matches what runs
        plan = build_plan(conn, model, fill)
        if plan.is_empty:
            return replace(plan, backup_path=backup_path)
        _check_allowed(plan, allow_destructive)
        for step in plan.steps:
            for statement in step.statements:
                try:
                    if statement.run is not None:
                        statement.run(conn)
                        result = []
                    else:
                        result = conn.execute(statement.sql)
                except Exception as error:
                    raise MigrationError(
                        f"{plan.table}: step '{step.description}' failed and was rolled back: {error}"
                    ) from error
                if statement.must_be_zero is not None and result and result[0]["n"] != 0:
                    raise MigrationError(
                        f"{plan.table}: {statement.must_be_zero} ({result[0]['n']} row(s)); rolled back."
                    )
    return replace(plan, backup_path=backup_path)
