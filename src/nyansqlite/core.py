import apsw
import orjson

class NyanSQLite:
    def __init__(self, db_path: str):
        # apsw.Connection は極めて高速でオーバーヘッドが少ない
        self.conn = apsw.Connection(db_path)
        self._configure_pragmas()

    def _configure_pragmas(self):
        """パフォーマンスのための最適化設定"""
        # apswではcursorを明示的に作成し、使い終わったらcloseする
        c = self.conn.cursor()
        try:
            c.execute("PRAGMA journal_mode=WAL")
            c.execute("PRAGMA synchronous=NORMAL")
            c.execute("PRAGMA temp_store=MEMORY")
            c.execute("PRAGMA cache_size=-64000")  # 64MBキャッシュ
        finally:
            c.close()

    def execute(self, sql: str, bindings=None):
        """SQLを実行する (書き込み用)"""
        return self.conn.execute(sql, bindings or {})

    def query(self, sql: str, bindings=None):
        """クエリを実行してジェネレータで返す (読み取り用)"""
        return self.conn.execute(sql, bindings or {})

    # --- orjson 対応のヘルパー ---
    def dumps(self, obj):
        return orjson.dumps(obj)  # bytesで返す

    def loads(self, data):
        return orjson.loads(data)

    @staticmethod
    def gen_col(json_col: str, key: str, data_type: str = "INTEGER") -> str:
        """
        生成列定義の文字列を生成するヘルパー
        例: NyanSQLite.gen_col('data', 'score', 'INTEGER')
        """
        return f"{key} {data_type} GENERATED ALWAYS AS (json_extract({json_col}, '$.{key}')) STORED"

    def get_json_path(self, table: str, pk: int, column: str, path: str):
        """
        部分読み込み: json_extract で特定のキーだけを取得
        path例: '$.user.name'
        """
        sql = f"SELECT json_extract({column}, ?) FROM {table} WHERE id = ?"
        cursor = self.conn.execute(sql, (path, pk))
        row = cursor.fetchone()
        return row[0] if row else None

    def update_json_path(self, table: str, pk: int, column: str, path: str, value):
        """
        部分書き込み: json_set で特定のキーだけを更新
        value: 数値や文字列ならそのまま。dictやlistの場合はJSON文字列として渡す
        """
        # 値が dict/list ならJSON文字列化する（SQLiteが受け取れるように）
        if isinstance(value, (dict, list)):
            value = orjson.dumps(value)

        sql = f"UPDATE {table} SET {column} = json_set({column}, ?, ?) WHERE id = ?"
        self.conn.execute(sql, (path, value, pk))

    def remove_json_path(self, table: str, pk: int, column: str, path: str):
        """
        キーの削除: json_remove
        """
        sql = f"UPDATE {table} SET {column} = json_remove({column}, ?) WHERE id = ?"
        self.conn.execute(sql, (path, pk))

    def close(self):
        self.conn.close()