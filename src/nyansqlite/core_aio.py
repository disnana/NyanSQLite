from __future__ import annotations

import asyncio
import contextvars
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any, Optional, TypeVar

from pydantic import BaseModel

from ._connection import NyanConnection
from ._model import instance_values, validate_model
from ._query import _build_where, _limit_sql, _order_sql, merge_where
from ._schema import (
    check_fts_schema,
    check_index_schema,
    check_table_schema,
    get_primary_key,
    model_hints,
    model_to_ddl,
    model_to_fts5,
    model_to_indexes,
    model_to_table_name,
)
from ._types import compile_deserializer, resolve_type, serialize_value, unwrap_annotated
from ._update_validation import needs_row_validation, prepare_update, update_validated_rows
from .exceptions import (
    FieldNotFoundError,
    ModelNotRegisteredError,
    QueryValidationError,
    SearchNotEnabledError,
    TableNameCollisionError,
)

M = TypeVar("M", bound=BaseModel)


# ── internal model metadata ──────────────────────────────────────────────── #

class _Meta:
    __slots__ = ("table", "pk", "hints", "filter_bases", "decoders", "needs_row_validation", "fts_table", "fts_fields")

    def __init__(
        self,
        table:      str,
        pk:         Optional[str],
        hints:      dict[str, Any],
        model:      type[BaseModel],
        strict_deserialization: bool,
        fts_table:  Optional[str],
        fts_fields: list[str],
    ):
        self.table      = table
        self.pk         = pk
        self.hints      = hints
        self.filter_bases = {name: unwrap_annotated(resolve_type(annotation)[0])
                             for name, annotation in hints.items()}
        self.decoders   = {name: compile_deserializer(annotation, strict_deserialization)
                           for name, annotation in hints.items()}
        self.needs_row_validation = needs_row_validation(model)
        self.fts_table  = fts_table
        self.fts_fields = fts_fields

    def check_fields(self, fields: list[str], model_name: str) -> None:
        bad = [f for f in fields if f not in self.hints]
        if bad:
            raise FieldNotFoundError(
                f"Fields not found on {model_name}: {bad}. "
                f"Available: {list(self.hints)}"
            )


# ── main async class ──────────────────────────────────────────────────── #

class NyanSQLiteAIO:
    """非同期版PydanticネイティブなSQLiteラッパー。

    Async Pydantic-native SQLite wrapper.
    Supports automatic schema creation, B-tree indexes, FTS5 full-text search,
    partial reads/writes, and advanced query operators.
    """

    def __init__(self, path: str = ":memory:", wal: bool = True, strict_deserialization: bool = False):
        """NyanSQLiteAIOを初期化します。
        Initialize NyanSQLiteAIO.

        Args:
            path (str): データベースファイルのパス。デフォルトはメモリ内データベース (":memory:")。
                        Database file path. Defaults to in-memory (":memory:").
            wal (bool): WAL (Write-Ahead Logging) モードを有効にするかどうか。デフォルトは True。
                        Whether to enable WAL (Write-Ahead Logging) mode. Defaults to True.
            strict_deserialization (bool): デシリアライズ時に厳密なチェックを行うかどうか。
                                          Whether to perform strict checks during deserialization.
        """
        self._conn     = NyanConnection(path, wal=wal)
        self._registry: dict[type[BaseModel], _Meta] = {}
        self._conn_lock = asyncio.Lock()   # SQLite接続への実アクセスを短く保護
        self._write_lock = asyncio.Lock()  # 書き込みとトランザクション境界を保護
        self._lock_owner = None            # ロックを保持しているタスク
        self._strict_deserialization = strict_deserialization

    @asynccontextmanager
    async def _write_context(self):
        """リエントラントな書き込みロック。

        書き込み系操作と明示的トランザクションの境界を保護します。
        """
        current_task = asyncio.current_task()
        if self._lock_owner == current_task:
            yield
            return

        async with self._write_lock:
            self._lock_owner = current_task
            try:
                yield
            finally:
                self._lock_owner = None

    async def _run_db_call(self, fn: Any) -> Any:
        """Run a SQLite call under the connection lock.

        SQLite access itself stays serialized for safety, while model
        deserialization can happen outside this lock.
        """
        current_task = asyncio.current_task()
        while self._write_lock.locked() and self._lock_owner != current_task:
            async with self._write_lock:
                pass

        while True:
            await self._conn_lock.acquire()
            # Recheck after taking the connection lock. A transaction may
            # have started between the first check and this acquisition.
            if not self._write_lock.locked() or self._lock_owner == current_task:
                break
            self._conn_lock.release()
            async with self._write_lock:
                pass

        try:
            context = contextvars.copy_context()
            worker = asyncio.get_running_loop().run_in_executor(None, context.run, fn)
            try:
                return await asyncio.shield(worker)
            except asyncio.CancelledError:
                # A running SQLite call cannot be stopped by cancelling the
                # coroutine. Keep the connection locked until it completes.
                while not worker.done():
                    try:
                        await asyncio.shield(worker)
                    except asyncio.CancelledError:
                        pass
                    except Exception:
                        break
                if worker.done() and not worker.cancelled():
                    worker.exception()  # consume a possible worker error
                raise
        finally:
            self._conn_lock.release()

    # ── registration ─────────────────────────────────────────────────── #

    async def register(self, model: type[BaseModel]) -> None:
        """Pydanticモデルを登録し、対応するテーブル、インデックス、FTS5仮想テーブルを作成します。
        Register a Pydantic model and create the corresponding table, indexes, and FTS5 virtual table.

        Args:
            model (type[BaseModel]): 登録するPydanticモデルクラス。
                                    The Pydantic model class to register.

        Raises:
            TableNameCollisionError: 同じテーブル名を持つ別のモデルが既に登録されている場合に発生します。
                                     Raised if another model with the same table name is already registered.
        """
        table  = model_to_table_name(model)
        pk     = get_primary_key(model)
        hints  = model_hints(model)

        # Check for table name collisions with different models
        fts_create, fts_triggers = model_to_fts5(model)
        fts_table:  str | None = None
        fts_fields: list[str]  = []
        if fts_create:
            from ._types import is_searchable
            fts_table  = f"{table}_fts"
            fts_fields = [f for f, ann in hints.items() if is_searchable(ann)]

        async with self._write_context():
            for existing_model, meta in self._registry.items():
                if meta.table == table and existing_model is not model:
                    raise TableNameCollisionError(
                        f"Table name collision detected: "
                        f"{existing_model.__name__} → '{table}' but also "
                        f"{model.__name__} → '{table}'. "
                        f"This can happen with CamelCase variants (e.g., 'UserAuth' and 'User_Auth'). "
                        f"Use explicit __tablename__ override or rename one of the models."
                    )
            def _register_all() -> None:
                with self._conn.transaction():
                    self._conn.execute(model_to_ddl(model))
                    check_table_schema(model, self._conn.execute(f'PRAGMA table_info("{table}")'))
                    fts_name = f"{table}_fts"
                    fts_rows = self._conn.execute(
                        "SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (fts_name,)
                    )
                    check_fts_schema(
                        model,
                        fts_rows[0]["sql"] if fts_rows else None,
                        self._conn.execute(f'PRAGMA table_info("{fts_name}")') if fts_rows else [],
                    )
                    for idx_sql in model_to_indexes(model):
                        self._conn.execute(idx_sql)
                    check_index_schema(model, self._conn)
                    if fts_create:
                        self._conn.execute(fts_create)
                        for trig in fts_triggers:
                            self._conn.execute(trig)
                        if not fts_rows:
                            self._conn.execute(f'INSERT INTO "{fts_name}"("{fts_name}") VALUES (?)', ("rebuild",))

            await self._run_db_call(_register_all)

            self._registry[model] = _Meta(
                table=table, pk=pk, hints=hints, model=model,
                strict_deserialization=self._strict_deserialization,
                fts_table=fts_table, fts_fields=fts_fields,
            )

    def _meta(self, model: type[BaseModel]) -> _Meta:
        meta = self._registry.get(model)
        if meta is None:
            raise ModelNotRegisteredError(
                f"{model.__name__} is not registered. "
                f"Call db.register({model.__name__}) first."
            )
        return meta

    # ── helpers ───────────────────────────────────────────────────────── #

    def _to_row(self, obj: BaseModel, meta: _Meta) -> dict[str, Any]:
        """Pydantic model → serialised dict for SQLite."""
        return dict(zip(meta.hints, instance_values(obj, meta.hints)))

    def _from_row(self, model: type[M], meta: _Meta, row: dict[str, Any]) -> M:
        """SQLite row dict → Pydantic model.

        Args:
            model: Pydantic model class
            meta: Model metadata
            row: Row dict from database

        Returns:
            Instantiated Pydantic model

        Raises:
            ValueError: If strict_deserialization=True and data is malformed
        """
        data = {}
        for k, v in row.items():
            decoder = meta.decoders.get(k)
            if decoder is not None:
                data[k] = decoder(v)
        return validate_model(model, data)

    # ── INSERT ───────────────────────────────────────────────────────── #

    async def insert(self, obj: M) -> M:
        """Pydanticモデルのインスタンスをデータベースに挿入します。
        Validate via Pydantic then INSERT. Returns the object unchanged.

        Args:
            obj (M): 挿入するモデルのインスタンス。
                    The model instance to insert.

        Returns:
            M: 挿入されたオブジェクト（変更なし）。
               The inserted object (unchanged).

        Raises:
            ModelNotRegisteredError: モデルが登録されていない場合に発生します。
                                     Raised if the model is not registered.
        """
        meta = self._meta(type(obj))
        row  = self._to_row(obj, meta)
        cols = ", ".join(f'"{k}"' for k in row)
        ph   = ", ".join("?" * len(row))
        sql  = f'INSERT INTO "{meta.table}" ({cols}) VALUES ({ph})'  # nosec B608

        async with self._write_context():
            await self._run_db_call(
                lambda: self._conn.execute(sql, tuple(row.values()))
            )
        return obj

    async def insert_many(self, objs: list[M]) -> int:
        """複数のモデルインスタンスを1つのトランザクションで一括挿入します。
        Bulk-insert multiple model instances in a single transaction.

        Args:
            objs (list[M]): 挿入するモデルインスタンスのリスト。
                           List of model instances to insert.

        Returns:
            int: 挿入された行数。
                 Total number of rows inserted.

        Raises:
            ModelNotRegisteredError: モデルが登録されていない場合に発生します。
                                     Raised if the model is not registered.
        """
        if not objs:
            return 0
        model_type = type(objs[0])
        if any(type(o) is not model_type for o in objs):
            raise TypeError("insert_many() only accepts instances of the same model type.")
        meta = self._meta(model_type)
        hints = meta.hints
        fields = list(hints.keys())

        # SQLite default limit on parameters is 32766
        rows = []
        for obj in objs:
            rows.append(instance_values(obj, hints))

        cols_count = len(fields)
        params_limit = 32000  # Conservative limit
        chunk_size = max(1, params_limit // cols_count)

        total_inserted = 0
        meta_table = meta.table
        cols = ", ".join(f'"{k}"' for k in fields)
        ph = ", ".join("?" for _ in range(cols_count))
        sql = f'INSERT INTO "{meta_table}" ({cols}) VALUES ({ph})'  # nosec B608

        async with self._write_context():
            def _bulk_insert_all():
                with self._conn.transaction():
                    for chunk_start in range(0, len(rows), chunk_size):
                        chunk = rows[chunk_start:chunk_start + chunk_size]
                        self._conn.executemany(sql, chunk)

            await self._run_db_call(_bulk_insert_all)
            total_inserted = len(rows)

        return total_inserted

    # ── UPDATE ───────────────────────────────────────────────────────── #

    async def update(self, model: type[BaseModel], where: dict[str, Any], **fields: Any) -> int:
        """指定されたフィールドのみを更新する部分更新を行います。
        Partial update; normalized and validator-derived fields are persisted together.

        Args:
            model (type[BaseModel]): 更新対象のモデルクラス。
                                    The model class to update.
            where (dict[str, Any]): 更新対象の行を特定する一致条件。
                                   Exact-match conditions that identify the row(s).
            **fields (Any): 更新する `フィールド名=新しい値` のペア。
                           `field=new_value` pairs to update.

        Returns:
            int: 更新された行数。
                 Number of rows updated.

        Raises:
            ModelNotRegisteredError: モデルが登録されていない場合に発生します。
                                     Raised if the model is not registered.
            FieldNotFoundError: 指定されたフィールドがモデルに存在しない場合に発生します。
                                Raised if any specified field is not found in the model.
        """
        if not fields:
            return 0
        meta = self._meta(model)
        meta.check_fields(list(fields), model.__name__)
        fields, needs_rows = prepare_update(model, fields, meta.needs_row_validation)

        set_parts: list[str] = []
        set_vals:  list[Any] = []
        if not needs_rows:
            for fname, value in fields.items():
                set_parts.append(f'"{fname}" = ?')
                set_vals.append(serialize_value(value, meta.hints[fname]))

        where_clause, where_vals = _build_where((), where, model_meta=meta)
        sql = f'UPDATE "{meta.table}" SET {", ".join(set_parts)} {where_clause}'  # nosec B608

        async with self._write_context():
            def _update_validated() -> int:
                with self._conn.transaction():
                    if needs_rows:
                        return update_validated_rows(model, meta, self._conn, where_clause, where_vals, fields)
                    return self._execute_and_return_changes(sql, tuple(set_vals + where_vals))

            return await self._run_db_call(_update_validated)

    # ── DELETE ───────────────────────────────────────────────────────── #

    async def delete(self, model: type[BaseModel], *filters: str, **kwargs: Any) -> int:
        """フィルタ条件に一致するすべての行を削除します。
        Delete all rows matching *filters* and *kwargs*.

        Args:
            model (type[BaseModel]): 削除対象のモデルクラス。
                                    The model class to delete from.
            *filters (str): 文字列形式のフィルタ条件。
                           String filters (e.g., "age > 50").
            **kwargs (Any): キーワード形式のフィルタ条件。
                           Keyword filters (e.g., id=42).

        Returns:
            int: 削除された行数。
                 Number of rows deleted.
        """
        meta = self._meta(model)
        where_clause, values = _build_where(filters, merge_where(kwargs.pop("where", None), kwargs), model_meta=meta)
        sql = f'DELETE FROM "{meta.table}" {where_clause}'  # nosec B608

        async with self._write_context():
            return await self._run_db_call(
                lambda: self._execute_and_return_changes(sql, tuple(values))
            )

    # ── GET / QUERY ───────────────────────────────────────────────────── #

    async def get(self, model: type[M], *filters: str, **kwargs: Any) -> Optional[M]:
        """条件に一致する最初の行をPydanticモデルとして取得します。一致しない場合は `None` を返します。
        Fetch the first matching row as a Pydantic model, or ``None``.

        Args:
            model (type[M]): 取得対象のモデルクラス。
                            The Pydantic model class.
            *filters (str): 文字列形式のフィルタ条件。
                           String filters.
            **kwargs (Any): キーワード形式のフィルタ条件。
                           Keyword filters.

        Returns:
            Optional[M]: 取得されたモデルインスタンス、または None。
                         The retrieved model instance, or None.
        """
        results = await self.query(model, *filters, limit=1, where=merge_where(kwargs.pop("where", None), kwargs))
        return results[0] if results else None

    async def query(
        self,
        model:    type[M],
        *filters: str,
        limit:    Optional[int] = None,
        offset:   Optional[int] = None,
        order_by: Optional[str] = None,
        desc:     bool = False,
        where:    Optional[dict[str, Any]] = None,
        **kwargs: Any,
    ) -> list[M]:
        """フィルタリング、ソート、ページネーションを使用して行を検索します。
        Query rows with optional filtering, ordering, and pagination.

        Args:
            model (type[M]): 検索対象のモデルクラス。
                            The Pydantic model class.
            *filters (str): 文字列形式のフィルタ条件。
                           String filters.
            limit (Optional[int]): 取得する最大行数。
                                  Maximum number of rows to return.
            offset (Optional[int]): 取得を開始するオフセット行数。
                                   Number of rows to skip.
            order_by (Optional[str]): ソートに使用するフィールド名。
                                     Field name to order by.
            where (dict): 条件辞書。予約引数と同名のフィールドにも使用できます。
            desc (bool): 降順でソートするかどうか。デフォルトは False（昇順）。
                        Whether to order in descending order. Defaults to False (ascending).
            **kwargs (Any): キーワード形式のフィルタ条件。
                           Keyword filters.

        Returns:
            list[M]: 取得されたモデルインスタンスのリスト。
                     List of matching model instances.
        """
        meta = self._meta(model)
        where_clause, values = _build_where(filters, merge_where(where, kwargs), model_meta=meta)

        if order_by:
            meta.check_fields([order_by], model.__name__)

        page_sql, page_values = _limit_sql(limit, offset)
        sql = (
            f'SELECT * FROM "{meta.table}" {where_clause}'  # nosec B608
            + _order_sql(order_by, desc)
            + page_sql
        )

        rows = await self._run_db_call(lambda: self._conn.execute(sql, tuple(values + page_values)))
        return [self._from_row(model, meta, r) for r in rows]

    # ── SELECT (partial read) ─────────────────────────────────────────── #

    async def select(
        self,
        model:    type[BaseModel],
        fields:   list[str],
        *filters: str,
        limit:    Optional[int] = None,
        offset:   Optional[int] = None,
        order_by: Optional[str] = None,
        desc:     bool = False,
        where:    Optional[dict[str, Any]] = None,
        **kwargs: Any,
    ) -> list[dict[str, Any]]:
        """特定のフィールドのみを辞書のリストとして取得します（部分読み込み）。
        Partial read — fetch only *fields*, returned as plain dicts.

        Args:
            model (type[BaseModel]): 取得対象のモデルクラス。
                                    The model class.
            fields (list[str]): 取得するフィールド名のリスト。
                               List of field names to fetch.
            *filters (str): 文字列形式のフィルタ条件。
                           String filters.
            limit (Optional[int]): 取得する最大行数。
                                  Maximum number of rows.
            offset (Optional[int]): オフセット。
                                   Offset.
            order_by (Optional[str]): ソートに使用するフィールド名。
                                     Field name to order by.
            where (dict): 条件辞書。予約引数と同名のフィールドにも使用できます。
            desc (bool): 降順にするかどうか。
                        Descending order.
            **kwargs (Any): キーワード形式のフィルタ条件。
                           Keyword filters.

        Returns:
            list[dict[str, Any]]: 指定されたフィールドを含む辞書のリスト。
                                 List of dicts containing specified fields.
        """
        meta = self._meta(model)
        if not fields:
            raise QueryValidationError("select() requires at least one field")
        meta.check_fields(fields, model.__name__)
        if order_by:
            meta.check_fields([order_by], model.__name__)

        col_sql      = ", ".join(f'"{f}"' for f in fields)
        where_clause, values = _build_where(filters, merge_where(where, kwargs), model_meta=meta)
        page_sql, page_values = _limit_sql(limit, offset)
        sql = (
            f'SELECT {col_sql} FROM "{meta.table}" {where_clause}'  # nosec B608
            + _order_sql(order_by, desc)
            + page_sql
        )

        rows = await self._run_db_call(lambda: self._conn.execute(sql, tuple(values + page_values)))
        return [
            {f: meta.decoders[f](row.get(f)) for f in fields}
            for row in rows
        ]

    # ── FTS5 SEARCH ───────────────────────────────────────────────────── #

    async def search(
        self,
        model:  type[M],
        query:  str,
        *,
        limit:  Optional[int] = None,
    ) -> list[M]:
        """すべての `Searchable[str]` フィールドに対して全文検索を実行します。
        Full-text search on all ``Searchable[str]`` fields.

        Args:
            model (type[M]): 検索対象のモデルクラス。
                            The Pydantic model class.
            query (str): 検索クエリ文字列。
                        FTS5 query string.
            limit (Optional[int]): 取得する最大行数。
                                  Maximum number of rows.

        Returns:
            list[M]: 検索結果に一致するモデルインスタンスのリスト（ランク順）。
                     List of matching model instances, ordered by relevance.

        Raises:
            SearchNotEnabledError: モデルに `Searchable[str]` フィールドが定義されていない場合に発生します。
                                   Raised if the model has no Searchable[str] fields.
        """
        meta = self._meta(model)
        if not meta.fts_table:
            raise SearchNotEnabledError(
                f"{model.__name__} has no Searchable[str] fields. "
                "Annotate at least one str field with Searchable[str] to enable FTS5."
            )

        table = meta.table
        fts   = meta.fts_table
        page_sql, page_values = _limit_sql(limit, None)
        sql = (
            f'SELECT t.* FROM "{table}" t '  # nosec B608
            f'JOIN "{fts}" f ON t.rowid = f.rowid '
            f'WHERE "{fts}" MATCH ? '
            f'ORDER BY rank'
            + page_sql
        )

        rows = await self._run_db_call(lambda: self._conn.execute(sql, (query, *page_values)))
        return [self._from_row(model, meta, r) for r in rows]

    # ── COUNT / EXISTS ────────────────────────────────────────────────── #

    async def count(self, model: type[BaseModel], *filters: str, **kwargs: Any) -> int:
        """フィルタ条件に一致する行数を返します。
        Return the number of rows matching *filters* and *kwargs*.

        Args:
            model (type[BaseModel]): カウント対象のモデルクラス。
                                    The model class.
            *filters (str): 文字列フィルタ。
                           String filters.
            **kwargs (Any): キーワードフィルタ。
                           Keyword filters.

        Returns:
            int: 条件に一致した行数。
                 Number of matching rows.
        """
        meta = self._meta(model)
        where_clause, values = _build_where(filters, merge_where(kwargs.pop("where", None), kwargs), model_meta=meta)
        sql  = f'SELECT COUNT(*) AS n FROM "{meta.table}" {where_clause}'  # nosec B608

        rows = await self._run_db_call(lambda: self._conn.execute(sql, tuple(values)))
        return rows[0]["n"] if rows else 0

    async def exists(self, model: type[BaseModel], *filters: str, **kwargs: Any) -> bool:
        """フィルタ条件に一致する行が少なくとも1つ存在するかどうかを返します。
        Return ``True`` if at least one row matches *filters* and *kwargs*.

        Args:
            model (type[BaseModel]): 確認対象のモデルクラス。
                                    The model class.
            *filters (str): 文字列フィルタ。
                           String filters.
            **kwargs (Any): キーワードフィルタ。
                           Keyword filters.

        Returns:
            bool: 存在する場合は True、そうでない場合は False。
                  True if matching rows exist, False otherwise.
        """
        meta = self._meta(model)
        where_clause, values = _build_where(filters, merge_where(kwargs.pop("where", None), kwargs), model_meta=meta)
        sql  = f'SELECT 1 FROM "{meta.table}" {where_clause} LIMIT 1'  # nosec B608

        result = await self._run_db_call(lambda: self._conn.execute(sql, tuple(values)))
        return bool(result)

    # ── MAINTENANCE ───────────────────────────────────────────────────── #

    async def rebuild_fts(self, model: type[BaseModel]) -> None:
        """モデルの FTS5 インデックスを再構築します。大量のデータインポート後などに有用です。
        Rebuild the FTS5 index for *model* (useful after bulk imports).

        Args:
            model (type[BaseModel]): インデックスを再構築するモデルクラス。
                                    The model class to rebuild index for.
        """
        meta = self._meta(model)
        if not meta.fts_table:
            return

        async with self._write_context():
            await self._run_db_call(
                lambda: self._conn.execute(
                    f'INSERT INTO "{meta.fts_table}"("{meta.fts_table}") VALUES(\'rebuild\')'  # nosec B608
                )
            )

    async def vacuum(self) -> None:
        """データベースを VACUUM してディスク領域を解放します。
        VACUUM the database to reclaim disk space.
        """
        async with self._write_context():
            await self._run_db_call(lambda: self._conn.execute("VACUUM"))

    # ── RAW SQL ───────────────────────────────────────────────────────── #

    async def execute_raw(self, sql: str, params: tuple = ()) -> list[dict[str, Any]]:
        """任意のSQLを実行し、結果を辞書のリストとして返します。
        Execute arbitrary SQL and return rows as dicts.

        Args:
            sql (str): 実行するSQL文。
                      SQL statement to execute.
            params (tuple): SQL文に渡すパラメータ。
                           Parameters for the SQL statement.

        Returns:
            list[dict[str, Any]]: 結果行のリスト（各行は辞書）。
                                 List of result rows as dicts.
        """
        return await self._run_db_call(lambda: self._conn.execute(sql, params))

    @asynccontextmanager
    async def atomic(self) -> AsyncGenerator[None, None]:
        """非同期トランザクション（ATOMICブロック）を開始します。
        ネスト（入れ子）された呼び出しも安全に処理されます。

        Async transaction (ATOMIC block).
        Nested calls are handled safely.

        Example:
            >>> async with db.atomic():
            >>>     await db.insert(User(id=1, name="Taro"))
            >>>     # Raise error to rollback
        """
        async with self._write_context():
            scope = self._conn.transaction_scope()
            try:
                await self._run_db_call(scope.begin)
                yield
                await self._run_db_call(scope.commit)
            except BaseException:
                await self._run_db_call(scope.rollback)
                raise

    # ── context manager + info ────────────────────────────────────────── #

    async def __aenter__(self) -> NyanSQLiteAIO:
        return self

    async def __aexit__(self, *_: Any) -> None:
        await self.close()

    async def close(self) -> None:
        """データベース接続を閉じます。
        Close the underlying database connection.
        """
        async with self._write_context():
            await self._run_db_call(lambda: self._conn.close())

    @property
    def backend(self) -> str:
        """使用中のバックエンド（'apsw' または 'sqlite3'）。
        ``'apsw'`` or ``'sqlite3'`` depending on what was found at import time.
        """
        return self._conn.backend

    def registered_models(self) -> list[str]:
        """登録されているすべてのモデル名を取得します。
        Names of all registered models.

        Returns:
            list[str]: モデル名のリスト。
                       List of model names.
        """
        return [m.__name__ for m in self._registry]

    def _execute_and_return_changes(self, sql: str, params: tuple[Any, ...]) -> int:
        self._conn.execute(sql, params)
        return self._conn.changes()
