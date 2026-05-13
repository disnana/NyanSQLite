import os
import orjson
from src.nyansqlite import NyanSQLite

# DBファイルのリセット（テスト用）
db_path = "example_data.db"
if os.path.exists(db_path): os.remove(db_path)

db = NyanSQLite(db_path)

# テーブル作成
db.execute("""
    CREATE TABLE users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        data TEXT
    )
""")

# 1. データの初期挿入
initial_json = {
    "name": "NyanUser",
    "settings": {"theme": "light", "volume": 50},
    "tags":["python", "sqlite"]
}
db.execute("INSERT INTO users (data) VALUES (?)", (orjson.dumps(initial_json),))
user_id = 1 # 今回挿入されたID

print("--- 初期状態 ---")
full_data = db.query("SELECT data FROM users WHERE id = ?", (user_id,)).fetchone()[0]
print(full_data)

# 2. 部分読み込み (themeだけ取得)
# Python側で json.loads("...") を行う必要がない
theme = db.get_json_path("users", user_id, "data", "$.settings.theme")
print(f"\n--- 部分読み込み (theme) ---: {theme}")

# 3. 部分更新 (volumeを80に変更)
# JSON全体をロードせず、SQLite側で一部だけ更新
db.update_json_path("users", user_id, "data", "$.settings.volume", 80)
print("\n--- 部分更新 (volume: 80) 完了 ---")

# 4. JSON階層への追加 (新しい設定項目を追加)
db.update_json_path("users", user_id, "data", "$.settings.font_size", 14)
print("--- 部分更新 (font_size: 14 追加) 完了 ---")

# 5. 部分削除 (tagsを削除)
db.remove_json_path("users", user_id, "data", "$.tags")
print("--- 部分削除 (tags) 完了 ---")

# 最終結果を確認
final_data = db.query("SELECT data FROM users WHERE id = ?", (user_id,)).fetchone()[0]
print(f"\n--- 最終状態 ---")
print(final_data)

db.close()