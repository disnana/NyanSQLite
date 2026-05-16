from __future__ import annotations

import re
import threading
from collections.abc import Generator
from contextlib import contextmanager
from typing import Any, Optional, TypeVar

from pydantic import BaseModel

from ._connection import NyanConnection
from ._schema import (
    get_primary_key,
    model_hints,
    model_to_ddl,
    model_to_fts5,
    model_to_indexes,
    model_to_table_name,
)
from ._types import deserialize_value, serialize_value
from .exceptions import (
    FieldNotFoundError,
    ModelNotRegisteredError,
    QueryValidationError,
    SearchNotEnabledError,
    TableNameCollisionError,
)

M = TypeVar("M", bound=BaseModel)


# ── WHERE clause builder ──────────────────────────────────────────────── #

_OP_PATTERN = re.compile(r"^\s*(\w+)\s*(>=|<=|!=|>|<|=)\s*(.*)$")

def _build_where(args: tuple[str, ...], kwargs: dict[str, Any], model_meta: Optional[_Meta] = None) -> tuple[str, list[Any]]:
    """パラメータ化されたWHERE句を文字列フィルタとキーワード引数から構築します。

    文字列フィルタ (args):
        "views > 10", "status = 'active'"

    キーワードフィルタ (kwargs):
        ==  ``field=value``           → ``field = ?``
        ==  ``field__ne=value``       → ``field != ?``
        ==  ``field__gt=value``       → ``field > ?``
        ==  ``field__gte=value``      → ``field >= ?``
        ==  ``field__lt=value``       → ``field < ?``
        ==  ``field__lte=value``      → ``field <= ?``
        ==  ``field__like=value``     → ``field LIKE ?``
        ==  ``field__in=[…]``         → ``field IN (?,?,?)``
        ==  ``field__is_null=True``   → ``field IS NULL``
        ==  ``field__is_null=False``  → ``field IS NOT NULL``

    Raises:
        QueryValidationError: フィルタ値の型変換に失敗した場合
        FieldNotFoundError: 指定されたフィールドがモデルに存在しない場合
    """
    if not args and not kwargs:
        return "", []

    clauses: list[str] = []
    values:  list[Any] = []

    # 位置指定文字列フィルタを処理: "age > 10"
    for filt in args:
        match = _OP_PATTERN.match(filt)
        if match:
            field, op, val_str = match.groups()
            clauses.append(f'"{field}" {op} ?')
            # val_strをPythonリテラル(int, floatなど)に変換を試みる
            # 引用符で囲まれた文字列の場合、引用符を削除
            val_str = val_str.strip()
            if (val_str.startswith("'") and val_str.endswith("'")) or \
               (val_str.startswith('"') and val_str.endswith('"')):
                values.append(val_str[1:-1])
            elif val_str.isdigit():
                values.append(int(val_str))
            else:
                try:
                    values.append(float(val_str))
                except ValueError:
                    values.append(val_str)
        else:
            # シンプルな演算子パターンに一致しない場合、SQLインジェクションのリスクがあるため、
            # 現時点では明示的な演算子のみをサポート
            clauses.append(filt)

    # キーワードフィルタを処理: age__gt=10
    for key, value in kwargs.items():
        field_name = key.split("__")[0]
        if model_meta and field_name not in model_meta.hints:
            raise FieldNotFoundError(
                f"モデルにフィールド '{field_name}' が見つかりません。 "
                f"利用可能なフィールド: {list(model_meta.hints.keys())}"
            )

        # モデルのヒントに基づいて値をシリアライズ
        serialized_value = value
        if model_meta and field_name in model_meta.hints:
            serialized_value = serialize_value(value, model_meta.hints[field_name])

        if "__" in key:
            field, op = key.rsplit("__", 1)
            q = f'"{field}"'
            if op == "ne":
                clauses.append(f"{q} != ?")
                values.append(serialized_value)
            elif op == "gt":
                clauses.append(f"{q} > ?")
                # 値が比較可能であることを検証
                try:
                    _ref = serialized_value
                    _ = serialized_value > _ref  # シンプルな型チェック
                except TypeError as e:
                    raise QueryValidationError(
                        f"フィルタ {key}={value!r} で型不一致が発生しました。 "
                        f"'{type(value).__name__}' に '>' 演算子を適用できません。 "
                        f"エラー: {e}"
                    ) from e
                values.append(serialized_value)
            elif op == "gte":
                clauses.append(f"{q} >= ?")
                # 値が比較可能であることを検証
                try:
                    _ref = serialized_value
                    _ = serialized_value >= _ref  # シンプルな型チェック
                except TypeError as e:
                    raise QueryValidationError(
                        f"フィルタ {key}={value!r} で型不一致が発生しました。 "
                        f"'{type(value).__name__}' に '>=' 演算子を適用できません。 "
                        f"エラー: {e}"
                    ) from e
                values.append(serialized_value)
            elif op == "lt":
                clauses.append(f"{q} < ?")
                # 値が比較可能であることを検証
                try:
                    _ref = serialized_value
                    _ = serialized_value < _ref  # シンプルな型チェック
                except TypeError as e:
                    raise QueryValidationError(
                        f"フィルタ {key}={value!r} で型不一致が発生しました。 "
                        f"'{type(value).__name__}' に '<' 演算子を適用できません。 "
                        f"エラー: {e}"
                    ) from e
                values.append(serialized_value)
            elif op == "lte":
                clauses.append(f"{q} <= ?")
                # 値が比較可能であることを検証
                try:
                    _ref = serialized_value
                    _ = serialized_value <= _ref  # シンプルな型チェック
                except TypeError as e:
                    raise QueryValidationError(
                        f"フィルタ {key}={value!r} で型不一致が発生しました。 "
                        f"'{type(value).__name__}' に '<=' 演算子を適用できません。 "
                        f"エラー: {e}"
                    ) from e
                values.append(serialized_value)
            elif op == "like":
                clauses.append(f"{q} LIKE ?")
                values.append(serialized_value)
            elif op == "in":
                try:
                    # 'in' 演算子には値がイテラブルであることを確認
                    if not isinstance(serialized_value, (list, tuple, set)):
                        raise TypeError("'in' 演算子の値はイテラブルである必要があります。")
                    ph = ", ".join("?" * len(serialized_value))
                except TypeError as e:
                    raise QueryValidationError(
                        f"フィルタ {key} はイテラブルを期待していますが、'{type(serialized_value).__name__}' を受け取りました。 "
                        f"エラー: {e}"
                    ) from e
                clauses.append(f"{q} IN ({ph})")
                values.extend(serialized_value)
            elif op == "is_null":
                clauses.append(f"{q} IS {'NULL' if value else 'NOT NULL'}")
            else:
                raise ValueError(f"不明なフィルタ演算子: __{op}")
        elif value is None:
            clauses.append(f'"{key}" IS NULL')
        else:
            clauses.append(f'"{key}" = ?')
            values.append(serialized_value)

    return "WHERE " + " AND ".join(clauses), values


def _order_sql(order_by: Optional[str], desc: bool) -> str:
    """ORDER BY句を構築します。"""
    if not order_by:
        return ""
    return f' ORDER BY "{order_by}" {"DESC" if desc else "ASC"}'


def _limit_sql(limit: Optional[int], offset: Optional[int]) -> str:
    """LIMITおよびOFFSET句を構築します。"""
    sql = ""
    if limit is not None:
        sql += f" LIMIT {int(limit)}"
    if offset is not None:
        sql += f" OFFSET {int(offset)}"
    return sql


# ── internal model metadata ───────────────────────────────────────────── #

class _Meta:
    """モデルの内部メタデータ。"""
    __slots__ = ("table", "pk", "hints", "fts_table", "fts_fields")

    def __init__(
        self,
        table:      str,
        pk:         Optional[str],
        hints:      dict[str, Any],
        fts_table:  Optional[str],
        fts_fields: list[str],
    ):
        self.table      = table
        self.pk         = pk
        self.hints      = hints
        self.fts_table  = fts_table
        self.fts_fields = fts_fields

    def check_fields(self, fields: list[str], model_name: str) -> None:
        """指定されたフィールドがモデルに存在するかをチェックします。"""
        bad = [f for f in fields if f not in self.hints]
        if bad:
            raise FieldNotFoundError(
                f"モデル '{model_name}' にフィールド {bad} が見つかりません。 "
                f"利用可能なフィールド: {list(self.hints)}"
            )


# ── main class ────────────────────────────────────────────────────────── #

class NyanSQLite:
    """PydanticネイティブなSQLiteラッパー。

    自動的なスキーマ作成、B-treeインデックス、FTS5全文検索、
    部分的な読み書き、および高度なクエリ演算子をサポートします。
    バックエンドには高速な `apsw` を使用しています。

    Pydantic-native SQLite wrapper.
    Supports automatic schema creation, B-tree indexes, FTS5 full-text search,
    partial reads/writes, and advanced query operators.
    Powered by the high-performance `apsw` backend.

    Quick start::

        from nyansqlite import NyanSQLite, Indexed, Searchable
        from pydantic import BaseModel

        class Article(BaseModel):
            id:      int
            author:  Indexed[str]
            title:   Searchable[str]
            body:    Searchable[str]
            views:   int = 0

        db = NyanSQLite("blog.sqlite")
        db.register(Article)

        db.insert(Article(id=1, author="neko", title="Hello SQLite", body="…"))
        db.search(Article, "SQLite")
        db.update(Article, where={"id": 1}, views=42)
        db.select(Article, fields=["title", "views"], author="neko")
    """

    def __init__(self, path: str = ":memory:", wal: bool = True, strict_deserialization: bool = False):
        """NyanSQLiteを初期化します。

        Args:
            path (str): データベースファイルのパス。デフォルトはメモリ内データベース (":memory:")。
            wal (bool): WAL (Write-Ahead Logging) モードを有効にするかどうか。デフォルトは True。
            strict_deserialization (bool): デシリアライズ時に厳密なチェックを行うかどうか。
                                         Trueの場合、不正なデータに対して ValueError を発生させます。
                                         Falseの場合、警告を出して生の値を返します。
        """
        self._conn     = NyanConnection(path, wal=wal)
        self._registry: dict[type[BaseModel], _Meta] = {}
        self._lock     = threading.RLock()
        self._strict_deserialization = strict_deserialization

    # ── registration ─────────────────────────────────────────────────── #

    def register(self, model: type[BaseModel]) -> None:
        """Pydanticモデルを登録し、対応するテーブル、インデックス、FTS5仮想テーブルを作成します。

        Args:
            model (type[BaseModel]): 登録するPydanticモデルクラス。

        Raises:
            TableNameCollisionError: 同じテーブル名を持つ別のモデルが既に登録されている場合に発生します。
        """
        table  = model_to_table_name(model)
        pk     = get_primary_key(model)
        hints  = model_hints(model)

        # 異なるモデルとのテーブル名衝突をチェック
        for existing_model, meta in self._registry.items():
            if meta.table == table and existing_model is not model:
                raise TableNameCollisionError(
                    f"テーブル名衝突を検出: "
                    f"{existing_model.__name__} → '{table}' と {model.__name__} → '{table}'。 "
                    f"これはCamelCaseのバリアント (例: 'UserAuth' と 'User_Auth') で発生する可能性があります。 "
                    f"明示的な __tablename__ のオーバーライドを使用するか、いずれかのモデルの名前を変更してください。"
                )

        with self._lock:
            with self._conn.transaction():
                self._conn.execute(model_to_ddl(model))
                for idx_sql in model_to_indexes(model):
                    self._conn.execute(idx_sql)

                fts_create, fts_triggers = model_to_fts5(model)
                fts_table:  str | None = None
                fts_fields: list[str]  = []
                if fts_create:
                    self._conn.execute(fts_create)
                    for trig in fts_triggers:
                        self._conn.execute(trig)
                    from ._types import is_searchable
                    fts_table  = f"{table}_fts"
                    fts_fields = [f for f, ann in hints.items() if is_searchable(ann)]

            self._registry[model] = _Meta(
                table=table, pk=pk, hints=hints,
                fts_table=fts_table, fts_fields=fts_fields,
            )

    def _meta(self, model: type[BaseModel]) -> _Meta:
        """モデルのメタデータを取得します。"""
        meta = self._registry.get(model)
        if meta is None:
            raise ModelNotRegisteredError(
                f"{model.__name__} は登録されていません。 "
                f"最初に db.register({model.__name__}) を呼び出してください。"
            )
        return meta

    # ── helpers ───────────────────────────────────────────────────────── #

    def _to_row(self, obj: BaseModel, meta: _Meta) -> dict[str, Any]:
        """Pydanticモデル → SQLite用のシリアライズされた辞書。"""
        # Pydantic v2 if available
        if hasattr(obj, "model_dump"):
            dump = obj.model_dump()
        else:
            dump = obj.dict()

        hints = meta.hints
        return {k: serialize_value(v, hints[k]) for k, v in dump.items() if k in hints}

    def _from_row(self, model: type[M], meta: _Meta, row: dict[str, Any]) -> M:
        """SQLiteの行辞書 → Pydanticモデル。

        Args:
            model: Pydanticモデルクラス
            meta: モデルメタデータ
            row: データベースからの行辞書

        Returns:
            インスタンス化されたPydanticモデル

        Raises:
            ValueError: strict_deserialization=Trueでデータが不正な場合
        """
        data = {}
        for k, v in row.items():
            if k in meta.hints:
                data[k] = deserialize_value(
                    v, meta.hints[k],
                    strict=self._strict_deserialization
                )
        return model(**data)

    # ── INSERT ───────────────────────────────────────────────────────── #

    def insert(self, obj: M) -> M:
        """Pydanticモデルのインスタンスをデータベースに挿入します。
        Pydanticによる検証後、INSERTします。オブジェクトは変更されずに返されます。

        Args:
            obj (M): 挿入するモデルのインスタンス。

        Returns:
            M: 挿入されたオブジェクト（変更なし）。

        Raises:
            ModelNotRegisteredError: モデルが登録されていない場合に発生します。
        """
        meta = self._meta(type(obj))
        row  = self._to_row(obj, meta)
        cols = ", ".join(f'"{k}"' for k in row)
        ph   = ", ".join("?" * len(row))
        sql  = f'INSERT INTO "{meta.table}" ({cols}) VALUES ({ph})'
        with self._lock:
            with self._conn.transaction():
                self._conn.execute(sql, tuple(row.values()))
        return obj

    def insert_many(self, objs: list[M]) -> int:
        """複数のモデルインスタンスを1つのトランザクションで一括挿入します。

        SQLiteの変数バインド制限（デフォルト 32766）を考慮し、大きなデータセットは自動的に分割して挿入されます。
        これにより、非常に大きなデータセットでのSQLITE_TOOBIGエラーを防ぎます。

        Args:
            objs (list[M]): 挿入するモデルインスタンスのリスト。

        Returns:
            int: 挿入された行数。

        Raises:
            ModelNotRegisteredError: モデルが登録されていない場合に発生します。
        """
        if not objs:
            return 0
        meta = self._meta(type(objs[0]))
        hints = meta.hints
        fields = list(hints.keys())

        # Pydantic v2 の高速な属性アクセスを利用
        # model_dump() を介さず、serialize_value もインライン化に近い形で呼び出す
        rows = []
        for o in objs:
            row_tuple = tuple(serialize_value(getattr(o, f), hints[f]) for f in fields)
            rows.append(row_tuple)

        cols_count = len(fields)
        params_limit = 32000  # 控えめな制限
        chunk_size = max(1, params_limit // cols_count)

        total_inserted = 0
        meta_table = meta.table
        cols = ", ".join(f'"{k}"' for k in fields)
        ph = ", ".join("?" for _ in range(cols_count))
        sql = f'INSERT INTO "{meta_table}" ({cols}) VALUES ({ph})'

        with self._lock:
            with self._conn.transaction():
                for chunk_start in range(0, len(rows), chunk_size):
                    chunk = rows[chunk_start:chunk_start + chunk_size]
                    self._conn.executemany(sql, chunk)
                    total_inserted += len(chunk)

        return total_inserted

    # ── UPDATE ───────────────────────────────────────────────────────── #

    def update(self, model: type[BaseModel], where: dict[str, Any], **fields: Any) -> int:
        """指定されたフィールドのみを更新する部分更新を行います。

        Args:
            model (type[BaseModel]): 更新対象のモデルクラス。
            where (dict[str, Any]): 更新対象の行を特定する一致条件（例: `{"id": 1}`）。
            **fields (Any): 更新する `フィールド名=新しい値` のペア。

        Returns:
            int: 更新された行数。

        Raises:
            ModelNotRegisteredError: モデルが登録されていない場合に発生します。
            FieldNotFoundError: 指定されたフィールドがモデルに存在しない場合に発生します。

        Example:
            >>> db.update(User, where={"id": 1}, age=26, bio="updated")
        """
        if not fields:
            return 0
        meta = self._meta(model)
        meta.check_fields(list(fields), model.__name__)

        set_parts: list[str] = []
        set_vals:  list[Any] = []
        for fname, value in fields.items():
            set_parts.append(f'"{fname}" = ?')
            set_vals.append(serialize_value(value, meta.hints[fname]))

        where_clause, where_vals = _build_where((), where, model_meta=meta)
        sql = f'UPDATE "{meta.table}" SET {", ".join(set_parts)} {where_clause}'

        with self._lock:
            with self._conn.transaction():
                self._conn.execute(sql, tuple(set_vals + where_vals))
            return self._conn.changes()

    # ── DELETE ───────────────────────────────────────────────────────── #

    def delete(self, model: type[BaseModel], *filters: str, **kwargs: Any) -> int:
        """フィルタ条件に一致するすべての行を削除します。

        Args:
            model (type[BaseModel]): 削除対象のモデルクラス。
            *filters (str): 文字列形式のフィルタ条件（例: `"age > 50"`）。
            **kwargs (Any): キーワード形式のフィルタ条件（例: `id=42`）。

        Returns:
            int: 削除された行数。

        Example:
            >>> db.delete(User, id=42)
            >>> db.delete(User, "age > 50")
            >>> db.delete(Session, user_id=1, active=True)
        """
        meta = self._meta(model)
        where_clause, values = _build_where(filters, kwargs, model_meta=meta)
        sql = f'DELETE FROM "{meta.table}" {where_clause}'
        with self._lock:
            with self._conn.transaction():
                self._conn.execute(sql, tuple(values))
            return self._conn.changes()

    # ── GET / QUERY ───────────────────────────────────────────────────── #

    def get(self, model: type[M], *filters: str, **kwargs: Any) -> Optional[M]:
        """条件に一致する最初の行をPydanticモデルとして取得します。一致しない場合は `None` を返します。

        Args:
            model (type[M]): 取得対象のモデルクラス。
            *filters (str): 文字列形式のフィルタ条件。
            **kwargs (Any): キーワード形式のフィルタ条件。

        Returns:
            Optional[M]: 取得されたモデルインスタンス、または None。

        Example:
            >>> user = db.get(User, id=1)
            >>> user = db.get(User, "age > 30", name="Alice")
            >>> user = db.get(User, email="taro@example.com")
        """
        results = self.query(model, *filters, limit=1, **kwargs)
        return results[0] if results else None

    def query(
        self,
        model:    type[M],
        *filters: str,
        limit:    Optional[int] = None,
        offset:   Optional[int] = None,
        order_by: Optional[str] = None,
        desc:     bool = False,
        **kwargs: Any,
    ) -> list[M]:
        """フィルタリング、ソート、ページネーションを使用して行を検索します。

        文字列フィルタおよび演算子サフィックス（`__gt`, `__like` など）をサポートしています。

        Args:
            model (type[M]): 検索対象のモデルクラス。
            *filters (str): 文字列形式のフィルタ条件。
            limit (Optional[int]): 取得する最大行数。
            offset (Optional[int]): 取得を開始するオフセット行数。
            order_by (Optional[str]): ソートに使用するフィールド名。
            desc (bool): 降順でソートするかどうか。デフォルトは False（昇順）。
            **kwargs (Any): キーワード形式のフィルタ条件。

        Returns:
            list[M]: 取得されたモデルインスタンスのリスト。

        Example:
            >>> db.query(User)                                  # 全ての行
            >>> db.query(User, age=25)                          # 完全一致
            >>> db.query(User, "age > 20", limit=10)            # 文字列フィルタ
            >>> db.query(User, age__gte=20, limit=10)           # 演算子サフィックス
            >>> db.query(User, order_by="name", desc=True)      # ソート
            >>> db.query(User, order_by="id", limit=20, offset=40)  # ページネーション
        """
        meta = self._meta(model)
        where_clause, values = _build_where(filters, kwargs, model_meta=meta)

        if order_by:
            meta.check_fields([order_by], model.__name__)

        sql = (
            f'SELECT * FROM "{meta.table}" {where_clause}'
            + _order_sql(order_by, desc)
            + _limit_sql(limit, offset)
        )
        rows = self._conn.execute(sql, tuple(values))
        return [self._from_row(model, meta, r) for r in rows]

    # ── SELECT (partial read) ─────────────────────────────────────────── #

    def select(
        self,
        model:    type[BaseModel],
        fields:   list[str],
        *filters: str,
        limit:    Optional[int] = None,
        offset:   Optional[int] = None,
        order_by: Optional[str] = None,
        desc:     bool = False,
        **kwargs: Any,
    ) -> list[dict[str, Any]]:
        """特定のフィールドのみを辞書のリストとして取得します（部分読み込み）。

        大きな行を持つテーブルで、未使用の列をロードするのを避けることができます。

        Args:
            model (type[BaseModel]): 取得対象のモデルクラス。
            fields (list[str]): 取得するフィールド名のリスト。
            *filters (str): 文字列形式のフィルタ条件。
            limit (Optional[int]): 取得する最大行数。
            offset (Optional[int]): オフセット。
            order_by (Optional[str]): ソートに使用するフィールド名。
            desc (bool): 降順にするかどうか。
            **kwargs (Any): キーワード形式のフィルタ条件。

        Returns:
            list[dict[str, Any]]: 指定されたフィールドを含む辞書のリスト。

        Example:
            >>> db.select(Article, ["title", "views"], author="neko", order_by="views", desc=True)
            >>> db.select(Article, ["title"], "views > 100")
        """
        meta = self._meta(model)
        meta.check_fields(fields, model.__name__)
        if order_by:
            meta.check_fields([order_by], model.__name__)

        col_sql      = ", ".join(f'"{f}"' for f in fields)
        where_clause, values = _build_where(filters, kwargs, model_meta=meta)
        sql = (
            f'SELECT {col_sql} FROM "{meta.table}" {where_clause}'
            + _order_sql(order_by, desc)
            + _limit_sql(limit, offset)
        )
        rows = self._conn.execute(sql, tuple(values))
        return [
            {f: deserialize_value(row.get(f), meta.hints[f], strict=self._strict_deserialization) for f in fields}
            for row in rows
        ]

    # ── FTS5 SEARCH ───────────────────────────────────────────────────── #

    def search(
        self,
        model:  type[M],
        query:  str,
        *,
        limit:  Optional[int] = None,
    ) -> list[M]:
        """すべての `Searchable[str]` フィールドに対して全文検索を実行します。

        FTS5の `MATCH` を使用し、BM25アルゴリズムでランク付け（`ORDER BY rank`）されます。

        Args:
            model (type[M]): 検索対象のモデルクラス。
            query (str): FTS5検索クエリ文字列。
            limit (Optional[int]): 取得する最大行数。

        Returns:
            list[M]: 検索結果に一致するモデルインスタンスのリスト（関連度順）。

        Raises:
            SearchNotEnabledError: モデルに `Searchable[str]` フィールドが定義されていない場合に発生します。

        Example:
            >>> db.search(Article, "python sqlite")
            >>> db.search(Article, "python sqlite", limit=5)

        フィールドを限定した検索には FTS5 のカラム指定構文が使用できます:
            >>> db.search(Article, "title:python")
        """
        meta = self._meta(model)
        if not meta.fts_table:
            raise SearchNotEnabledError(
                f"{model.__name__} に Searchable[str] フィールドがありません。 "
                "FTS5を有効にするには、少なくとも1つのstrフィールドに Searchable[str] をアノテーションしてください。"
            )

        table = meta.table
        fts   = meta.fts_table
        sql = (
            f'SELECT t.* FROM "{table}" t '
            f'JOIN "{fts}" f ON t.rowid = f.rowid '
            f'WHERE "{fts}" MATCH ? '
            f'ORDER BY rank'
            + _limit_sql(limit, None)
        )
        rows = self._conn.execute(sql, (query,))
        return [self._from_row(model, meta, r) for r in rows]

    # ── COUNT / EXISTS ────────────────────────────────────────────────── #

    def count(self, model: type[BaseModel], *filters: str, **kwargs: Any) -> int:
        """フィルタ条件に一致する行数を返します。

        Args:
            model (type[BaseModel]): カウント対象のモデルクラス。
            *filters (str): 文字列フィルタ。
            **kwargs (Any): キーワードフィルタ。

        Returns:
            int: 条件に一致した行数。

        Example:
            >>> total  = db.count(User)
            >>> adults = db.count(User, "age >= 18")
            >>> adults = db.count(User, age__gte=18)
        """
        meta = self._meta(model)
        where_clause, values = _build_where(filters, kwargs, model_meta=meta)
        sql  = f'SELECT COUNT(*) AS n FROM "{meta.table}" {where_clause}'
        rows = self._conn.execute(sql, tuple(values))
        return rows[0]["n"] if rows else 0

    def exists(self, model: type[BaseModel], *filters: str, **kwargs: Any) -> bool:
        """フィルタ条件に一致する行が少なくとも1つ存在するかどうかを返します。

        Args:
            model (type[BaseModel]): 確認対象のモデルクラス。
            *filters (str): 文字列フィルタ。
            **kwargs (Any): キーワードフィルタ。

        Returns:
            bool: 存在する場合は True、そうでない場合は False。

        Example:
            >>> if db.exists(User, email="taro@example.com"):
            >>>     ...
        """
        meta = self._meta(model)
        where_clause, values = _build_where(filters, kwargs, model_meta=meta)
        sql  = f'SELECT 1 FROM "{meta.table}" {where_clause} LIMIT 1'
        rows = self._conn.execute(sql, tuple(values))
        return bool(rows)

    # ── MAINTENANCE ───────────────────────────────────────────────────── #

    def rebuild_fts(self, model: type[BaseModel]) -> None:
        """モデルの FTS5 インデックスを再構築します（大量のデータインポート後などに有用です）。

        Args:
            model (type[BaseModel]): インデックスを再構築するモデルクラス。
        """
        meta = self._meta(model)
        if not meta.fts_table:
            return
        with self._lock:
            self._conn.execute(
                f'INSERT INTO "{meta.fts_table}"("{meta.fts_table}") VALUES(\'rebuild\')'
            )

    def vacuum(self) -> None:
        """データベースを VACUUM してディスク領域を解放します。"""
        self._conn.execute("VACUUM")

    # ── RAW SQL ───────────────────────────────────────────────────────── #

    def execute_raw(self, sql: str, params: tuple = ()) -> list[dict[str, Any]]:
        """任意のSQLを実行し、結果を辞書のリストとして返します。

        Args:
            sql (str): 実行するSQL文。
            params (tuple): SQL文に渡すパラメータ。

        Returns:
            list[dict[str, Any]]: 結果行のリスト（各行は辞書）。

        Example:
            >>> db.execute_raw("SELECT count(*) AS n FROM user WHERE age > ?", (18,))
        """
        # execute_rawは読み取り/書き込み両方ありうるためロックを維持
        with self._lock:
            return self._conn.execute(sql, params)

    @contextmanager
    def atomic(self) -> Generator[None, None, None]:
        """トランザクション（ATOMICブロック）を開始します。
        ネスト（入れ子）された呼び出しも安全に処理されます。

        Example:
            >>> with db.atomic():
            >>>     db.insert(User(id=1, name="Taro"))
            >>>     # ここで例外が発生するとロールバックされます
        """
        with self._lock:
            with self._conn.transaction():
                yield

    # ── context manager + info ────────────────────────────────────────── #

    def __enter__(self) -> NyanSQLite:
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()

    def close(self) -> None:
        """基盤となるデータベース接続を閉じます。"""
        with self._lock: # 接続クローズも排他的に
            self._conn.close()

    @property
    def backend(self) -> str:
        """使用中のバックエンド（'apsw' または 'sqlite3'）。"""
        return self._conn.backend

    def registered_models(self) -> list[str]:
        """登録されているすべてのモデル名を取得します。

        Returns:
            list[str]: モデル名のリスト。
        """
        # 読み取り操作なのでロックは不要だが、_registryへのアクセス保護のため維持
        with self._lock:
            return [m.__name__ for m in self._registry]
