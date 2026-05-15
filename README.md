# NyanSQLite

[![PyPI version](https://img.shields.io/pypi/v/nyansqlite.svg)](https://pypi.org/project/nyansqlite/)
[![Python versions](https://img.shields.io/pypi/pyversions/nyansqlite.svg)](https://pypi.org/project/nyansqlite/)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)
[![Downloads](https://static.pepy.tech/badge/nyansqlite)](https://pepy.tech/project/nyansqlite)
[![Tests](https://github.com/disnana/nyansqlite/actions/workflows/ci.yml/badge.svg)](https://github.com/disnana/nyansqlite/actions/workflows/ci.yml)

**Pythonic SQLite with Pydantic models, Django-like queries, and FTS5 full-text search.**

[English](#english) | [日本語](#日本語)

---

## 日本語

NyanSQLiteは、Pydanticモデルをそのままデータベーススキーマとして利用できる、型安全で高性能なSQLiteラッパーです。  
複雑なSQLを書くことなく、Pythonの型ヒントと直感的なクエリでデータを管理できます。

### 🚀 主な特徴

| 機能 | 説明 |
|-----|------|
| **Pydanticベースのスキーマ** | 型ヒントで自動バリデーション、JSON変換も透過的 |
| **Djangoライクなクエリ** | `__gte`, `__in`, `__like` など直感的なフィルタリング |
| **FTS5全文検索** | テキストデータから高速に検索結果を取得 |
| **自動インデックス管理** | `Indexed[T]` アノテーションで B-tree インデックスを自動構築 |
| **複雑な型を透過的に処理** | dict や list を JSON で保存、自動で Python オブジェクトに戻す |
| **パフォーマンス最適化** | WAL モード、バッチ処理による高速化 |

### 📦 インストール

```bash
pip install nyansqlite
```

Pydantic v2が必須です：

```bash
pip install "pydantic>=2.0"
```

### ⚡ 5分クイックスタート

```python
from pydantic import BaseModel
from nyansqlite import NyanSQLite, Indexed, Searchable

# 1️⃣ スキーマ定義（型ヒント＋Pydantic）
class Article(BaseModel):
    id: int                      # idフィールドが自動的に主キーになる
    author: Indexed[str]         # インデックス付きカラム
    title: Searchable[str]       # 全文検索対象
    body: Searchable[str]        # 全文検索対象
    views: int = 0

# 2️⃣ DB初期化＆テーブル作成
db = NyanSQLite("blog.db")
db.register(Article)

# 3️⃣ データ挿入
db.insert(Article(
    id=1,
    author="neko",
    title="SQLiteを使いこなそう",
    body="NyanSQLiteで簡単にデータ管理ができます。"
))

# 4️⃣ クエリ実行（Django風）
articles = db.query(Article, author="neko", views__gte=0, order_by="id", desc=True)

# 5️⃣ 全文検索（FTS5）
results = db.search(Article, "SQLite")
for hit in results:
    print(f"✨ {hit.title}")

db.close()
```

### 🔍 クエリ演算子リファレンス

```python
# 完全一致
db.query(Article, author="neko")

# 演算子フィルタ
db.query(Article, 
    views__gt=10,           # >
    views__gte=10,          # >=
    views__lt=100,          # <
    views__lte=100,         # <=
    views__ne=50,           # !=
)

# 文字列フィルタ
db.query(Article,
    title__like="%Python%", # LIKE検索
)

# IN句
db.query(Article,
    id__in=[1, 2, 3],
)

# NULL チェック
db.query(Article,
    author__is_null=False,
)
```

### 🎯 実装例：ゲームのプレイヤーシステム

```python
from datetime import datetime
from pydantic import BaseModel

class Player(BaseModel):
    player_id: int                    # 主キー
    username: Indexed[str]            # ユーザー名でインデックス
    level: Indexed[int]               # レベルでインデックス
    score: int = 0
    created_at: datetime

db = NyanSQLite("game.db")
db.register(Player)

# バッチ登録（大量データが高速）
players = [
    Player(player_id=i, username=f"player_{i}", level=i%50, created_at=datetime.now())
    for i in range(1, 1001)
]
db.insert_many(players)

# ランキング取得
top_players = db.query(Player, order_by="score", desc=True, limit=10)

# 条件付き検索＆更新
high_level = db.query(Player, level__gte=40, limit=100)
db.update(Player, where={"player_id": 1}, score=9999)

# 数を数える
player_count = db.count(Player)
active_count = db.count(Player, level__gte=30)
```

### 📊 パフォーマンス

NyanSQLiteは以下の最適化を実装しています：

- **WAL モード**: 読み書き同時実行性の向上
- **トランザクション**: `insert_many()` はデフォルトでトランザクション内で実行
- **パラメータ化クエリ**: SQL インジェクション対策も兼ねた安全性

```python
# 10万件をわずか０秒台で挿入（バッチ処理）
import time
players = [Player(player_id=i, ...) for i in range(100000)]
start = time.time()
db.insert_many(players)
print(f"Inserted in {time.time() - start:.4f}s")  # 例: 0.3456s
```

### 🛠️ 高度な機能

#### 複合インデックス

```python
from nyansqlite import CompositeIndex

class Order(BaseModel):
    __nyan_indexes__ = [
        CompositeIndex("user_id", "created_at"),
        CompositeIndex("product_id", "status", unique=True),
    ]
    id: int
    user_id: int
    product_id: int
    created_at: datetime
    status: str
```

#### 主キーのカスタマイズ

フィールド名が `id` でない場合：

```python
class User(BaseModel):
    __nyan_primary_key__ = "user_id"
    user_id: int
    email: str
    name: str
```

#### コンテキストマネージャー

```python
with NyanSQLite("app.db") as db:
    db.register(Article)
    db.insert(Article(...))
    # 自動的にcloseされる
```

### 🧹 メンテナンス

```python
# インデックスの再構築
db.rebuild_fts(Article)

# データベース最適化（ファイルサイズを縮小）
db.vacuum()

# 存在確認
if db.exists(Article, id=1):
    print("Found!")

# 部分取得（カラムを指定）
titles = db.select(Article, ["title", "author"], views__gte=100)
```

### 🚨 型モデルのベストプラクティス

```python
from pydantic import ConfigDict

class Article(BaseModel):
    # Pydantic v2の設定
    model_config = ConfigDict(
        arbitrary_types_allowed=True,  # 複雑な型をサポート
        validate_assignment=True,
    )
    
    id: int
    # ... その他フィールド
```

---

## English

NyanSQLite is a type-safe, high-performance SQLite wrapper that transforms Pydantic models directly into database schemas. Write minimal SQL while leveraging the power of FTS5 full-text search and Django-inspired query syntax.

### 🚀 Features

| Feature | Benefit |
|---------|---------|
| **Pydantic Integration** | Type-safe validation and automatic JSON serialization |
| **Django-like Queries** | `__gte`, `__in`, `__like` and more—no SQL needed |
| **FTS5 Search** | Lightning-fast full-text search on `Searchable[str]` fields |
| **Auto-Indexing** | Create B-tree indexes with `Indexed[T]` annotations |
| **Complex Types** | Transparent handling of dict, list, and custom types |
| **Performance Optimized** | WAL mode, batch inserts, parameterized queries |

### 📦 Installation

```bash
pip install nyansqlite
```

Requires Python 3.9+ and Pydantic 2.0+.

### ⚡ Quick Start

```python
from pydantic import BaseModel
from nyansqlite import NyanSQLite, Indexed, Searchable

class Post(BaseModel):
    id: int
    title: Searchable[str]
    author: Indexed[str]
    views: int = 0

db = NyanSQLite(":memory:")
db.register(Post)

# Insert
db.insert(Post(id=1, title="Hello SQLite", author="neko"))

# Query
posts = db.query(Post, author="neko", views__gte=0)

# Full-text search
results = db.search(Post, "SQLite")

db.close()
```

### 📚 API Reference

**Core Methods:**

- `register(model)` – Introspect model and create table
- `insert(obj)` – Insert a single record
- `insert_many(objs)` – Bulk insert with transaction
- `query(**kwargs)` – SELECT with filters, ordering, pagination
- `search(query, limit)` – FTS5 full-text search
- `get(**kwargs)` – Fetch one record or None
- `update(where, **fields)` – Partial UPDATE
- `delete(**kwargs)` – Conditional DELETE
- `count(**kwargs)` – COUNT rows matching condition
- `exists(**kwargs)` – Check if any row matches
- `select(fields, **kwargs)` – Fetch specific columns as dicts
- `vacuum()` – Optimize database file
- `close()` – Close connection

### 🔗 Resources

- **Repository**: [github.com/disnana/nyansqlite](https://github.com/disnana/nyansqlite)
- **Issues**: [Report bugs](https://github.com/disnana/nyansqlite/issues)

---

## License

MIT License – see [LICENSE](LICENSE) for details.
