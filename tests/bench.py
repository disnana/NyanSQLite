import pytest
import sqlite3
import apsw
import json
import orjson
from nyansqlite import NyanSQLite

# サンプルデータ生成
DATA = {"name": "TestUser", "settings": {"theme": "light", "volume": 50}}
JSON_BYTES = orjson.dumps(DATA)


@pytest.fixture
def db_setup():
    # 各DBのセットアップ
    # 1. Std SQLite
    conn_std = sqlite3.connect(":memory:")
    conn_std.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, data TEXT)")
    conn_std.execute("INSERT INTO users (data) VALUES (?)", (JSON_BYTES.decode(),))

    # 2. APSW
    conn_apsw = apsw.Connection(":memory:")
    conn_apsw.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, data TEXT)")
    conn_apsw.execute("INSERT INTO users (data) VALUES (?)", (JSON_BYTES,))

    # 3. NyanSQLite
    nyan = NyanSQLite(":memory:")
    nyan.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, data TEXT)")
    nyan.execute("INSERT INTO users (data) VALUES (?)", (JSON_BYTES,))

    yield conn_std, conn_apsw, nyan


def test_full_read_benchmark(db_setup, benchmark):
    """JSON全体を読み込んでPythonでパースする処理の比較"""
    std, ap, nyan = db_setup

    # 標準sqlite3
    def run_std():
        row = std.execute("SELECT data FROM users").fetchone()[0]
        return json.loads(row)

    # APSW + orjson
    def run_apsw():
        row = ap.execute("SELECT data FROM users").fetchone()[0]
        return orjson.loads(row)

    # 比較実行
    benchmark(run_apsw)


def test_partial_read_benchmark(db_setup, benchmark):
    """部分読み込み(json_extract)の比較"""
    std, ap, nyan = db_setup

    # NyanSQLite (SQL側で抽出してPythonは変換なし)
    def run_nyan():
        return nyan.get_json_path("users", 1, "data", "$.settings.volume")

    # 比較実行
    benchmark(run_nyan)