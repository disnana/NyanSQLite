import apsw
from pydantic import BaseModel, Field
from typing import Annotated, Type, get_type_hints, Any, get_origin, List


# インデックスや主キーを定義するためのカスタムメタデータ
class SQLMetadata:
    def __init__(self, primary_key: bool = False, index: bool = False, unique: bool = False):
        self.primary_key = primary_key
        self.index = index
        self.unique = unique


class NyanSQLite:
    def __init__(self, db_path: str):
        self.conn = apsw.Connection(db_path)
        self.cursor = self.conn.cursor()

    def _py_to_sql_type(self, py_type: Type) -> str:
        """Pythonの型をSQLiteの型にマッピング"""
        if issubclass(py_type, int):
            return "INTEGER"
        if issubclass(py_type, float):
            return "REAL"
        if issubclass(py_type, bool):
            return "INTEGER"  # SQLite has no boolean
        return "TEXT"

    def create_table(self, model: Type[BaseModel]):
        table_name = model.__name__.lower()
        columns = []
        indices = []

        # 型ヒントからAnnotatedの情報を抽出
        hints = get_type_hints(model, include_extras=True)

        for field_name, field_type in hints.items():
            sql_type = "TEXT"
            constraints = []

            # AnnotatedからMetadataを抽出
            if get_origin(field_type) is Annotated:
                base_type, *metadata = field_type.__metadata__
                sql_type = self._py_to_sql_type(get_type_hints(model)[field_name])

                for meta in metadata:
                    if isinstance(meta, SQLMetadata):
                        if meta.primary_key:
                            constraints.append("PRIMARY KEY")
                        if meta.unique:
                            constraints.append("UNIQUE")
                        if meta.index and not meta.primary_key:
                            indices.append(field_name)
            else:
                sql_type = self._py_to_sql_type(field_type)

            columns.append(f"{field_name} {sql_type} {' '.join(constraints)}")

        # テーブル作成
        create_sql = f"CREATE TABLE IF NOT EXISTS {table_name} ({', '.join(columns)});"
        self.cursor.execute(create_sql)

        # インデックス作成
        for col in indices:
            idx_sql = f"CREATE INDEX IF NOT EXISTS idx_{table_name}_{col} ON {table_name}({col});"
            self.cursor.execute(idx_sql)

    def insert(self, data: BaseModel):
        table_name = data.__class__.__name__.lower()
        fields = data.model_dump()
        keys = list(fields.keys())
        values = list(fields.values())

        placeholders = ", ".join(["?"] * len(keys))
        sql = f"INSERT INTO {table_name} ({', '.join(keys)}) VALUES ({placeholders})"
        self.cursor.execute(sql, values)

    def bulk_insert(self, data_list: List[BaseModel]):
        if not data_list:
            return

        # 最初の要素からテーブル名とフィールド名を抽出
        table_name = data_list[0].__class__.__name__.lower()
        fields = data_list[0].model_dump().keys()

        # SQL文の構築
        keys = list(fields)
        placeholders = ", ".join(["?"] * len(keys))
        sql = f"INSERT INTO {table_name} ({', '.join(keys)}) VALUES ({placeholders})"

        # モデルから値のタプルリストに変換
        rows = [tuple(item.model_dump().values()) for item in data_list]

        # トランザクション内で実行
        with self.conn:
            self.cursor.executemany(sql, rows)