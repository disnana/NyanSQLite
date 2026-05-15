from __future__ import annotations
from pydantic import BaseModel
from typing import Annotated

from src.nyansqlite import NyanSQLite, Indexed, Searchable
import numpy as np

# 1. モデルの定義
class Article(BaseModel):
    id: int                            # フィールド名が "id" で自動的に主キーになる
    author: Indexed[str]               # B-tree インデックスが貼られる
    title: Searchable[str]             # 全文検索対象
    body: Searchable[str]              # 全文検索対象
    category: str
    views: int = 0
    is_published: bool = True

class Users(BaseModel):
    id: int
    username: Indexed[str]
    settings: dict

# 2. データベースの初期化と登録
db = NyanSQLite(":memory:")
db.register(Article)
db.register(Users)

# 3. データの挿入 (INSERT)
new_post = Article(
    id=1,
    author="neko_sensei",
    title="PythonとSQLiteの美味しい関係",
    body="Pydanticを使うとデータベース操作がもっと楽しくなります。ニャン！",
    category="tech"
)
db.insert(new_post)

# バルクインサートも可能
db.insert_many([
    Article(id=2, author="kuro", title="SQLiteの基本", body="SQLは大事です。", category="tech"),
    Article(id=3, author="neko_sensei", title="今日のご飯", body="マグロの缶詰でした。", category="diary"),
])

# 4. クエリ (SELECT / WHERE)
# Django風の演算子を利用
tech_articles = db.query(
    Article, 
    category="tech", 
    views__gte=0,          # 0ビュー以上
    author__in=["neko_sensei", "kuro"],
    order_by="id",
    desc=True
)

for art in tech_articles:
    print(f"[{art.category}] {art.title} by {art.author}")

# 5. 全文検索 (FTS5)
# "Python" または "SQLite" を含む記事を検索
search_results = db.search(Article, "Python SQLite")
print(f"検索ヒット数: {len(search_results)}")

# 6. 更新 (UPDATE)
# ID=1 の記事のビュー数を 42 に更新
db.update(Article, where={"id": 1}, views=42)

# 7. 削除 (DELETE)
# 特定の著者の日記カテゴリを削除
db.delete(Article, author="neko_sensei", category="diary")

# 8. Extra Test
user1 = Users(
    id=1,
    username="neko_sensei",
    settings={
        "pin": 1234,
        "nickname": "neko"
    }
)
user2 = Users(
    id=2,
    username="kuro",
    settings={
        "pin": 1111,
        "nickname": "kuro"
    }
)
db.insert(user1)
db.insert(user2)
users = db.query(Users)
for user in users:
    print(f"ユーザー: {user.username}, 設定: {user.settings}")

# 8. メンテナンスと終了
db.vacuum()
db.close()