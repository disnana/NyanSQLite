# NyanSQLite

[![PyPI version](https://img.shields.io/pypi/v/nyansqlite.svg)](https://pypi.org/project/nyansqlite/)
[![Python versions](https://img.shields.io/pypi/pyversions/nyansqlite.svg)](https://pypi.org/project/nyansqlite/)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)
[![PyPI Downloads](https://static.pepy.tech/personalized-badge/nyansqlite?period=total&units=INTERNATIONAL_SYSTEM&left_color=BLACK&right_color=BLUE&left_text=downloads)](https://pepy.tech/projects/nyansqlite)
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

### ⚙️ コンストラクタオプション

```python
db = NyanSQLite(
    path=":memory:",              # DBファイルのパス（デフォルト：インメモリ）
    wal=True,                     # WALモード有効化（デフォルト：True）
    strict_deserialization=False  # 厳格なデータ検証（デフォルト：False）
)
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

# LIKE フィルタ
db.query(Article,
    title__like="%Python%", # LIKE検索
)

# 単純な文字列フィルタも利用できます
# v1.1.4 以降、SQL注入を避けるため明示的な単純比較のみサポートします
db.query(Article, "views > 10")

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
mid_level = db.query(Player, "level > 10", "level < 40") # 文字列形式のフィルタ
db.update(Player, where={"player_id": 1}, score=9999)

# 数を数える
player_count = db.count(Player)
active_count = db.count(Player, level__gte=30)
pro_count = db.count(Player, "level > 40")  # 文字列形式
```

### 📊 パフォーマンス

NyanSQLiteは以下の最適化を実装しています：

- **WAL モード**: 読み書き同時実行性の向上
- **トランザクション**: `insert_many()` はデフォルトでトランザクション内で実行
- **パラメータ化クエリ**: SQL インジェクション対策も兼ねた安全性
- **自動チャンキング**: SQLiteの32766プレースホルダ上限を超える大量データは自動分割

```python
# 10万件をわずか０秒台で挿入（バッチ処理）
import time
players = [Player(player_id=i, ...) for i in range(100000)]
start = time.time()
db.insert_many(players)  # 自動的に適切なサイズにチャンク分割される
print(f"Inserted in {time.time() - start:.4f}s")  # 例: 0.3456s
```

### 🔒 セキュリティ機能（v1.0.0 以降）

#### マルチスレッド対応

すべてのデータベース操作は `threading.Lock` で保護されており、複数スレッドからの安全なアクセスをサポートしています。

```python
import threading
from nyansqlite import NyanSQLite

db = NyanSQLite("thread_safe.db")
db.register(Article)

def worker():
    # 複数スレッドから安全に実行可能
    db.query(Article, ...)
    db.insert(Article(...))

threads = [threading.Thread(target=worker) for _ in range(10)]
for t in threads: t.start()
for t in threads: t.join()
```

#### 非同期サポート (`asyncio`)

`NyanSQLiteAIO` クラスを使用することで、非同期プログラミング（`asyncio`）を完全にサポートします。内部的には `asyncio.to_thread` を活用し、DB操作をスレッドセーフかつノンブロッキングに実行します。

```python
import asyncio
from nyansqlite import NyanSQLiteAIO, Indexed
from pydantic import BaseModel

class User(BaseModel):
    id: int
    name: Indexed[str]

async def main():
    # 1. 非同期コンテキストマネージャによる接続
    async with NyanSQLiteAIO("async.db") as db:
        # 2. モデルの登録（初回のみテーブル作成）
        db.register(User)
        
        # 3. 非同期挿入
        # 内部でスレッドセーフに実行されます
        await db.insert(User(id=1, name="alice"))
        
        # 4. 非同期クエリ
        # Django風のクエリも非同期で利用可能
        users = await db.query(User, name="alice")
        print(f"Found: {users[0].name}")

        # 5. 一括挿入も非同期
        await db.insert_many([
            User(id=i, name=f"user_{i}") for i in range(2, 5)
        ])
        
        # 6. その他のメソッドも await が必要です
        count = await db.count(User)
        print(f"Total users: {count}")

asyncio.run(main())
```

#### 破損データの安全な処理（`strict_deserialization`）

DB内に不正なJSONや日付フォーマットが混入した場合、2つのモードから選択できます：

**寛容モード（デフォルト）:** 警告を出力して生データを返す

```python
db = NyanSQLite("app.db", strict_deserialization=False)

# DBに不正なJSON { invalid } が混入していても
articles = db.query(Article)
# RuntimeWarning: Malformed JSON data: '{ invalid }'. Returning as raw string.
# → 処理は継続され、その値は文字列として返される
```

**厳格モード:** デシリアライズエラーで例外を発生

```python
db = NyanSQLite("app.db", strict_deserialization=True)

try:
    articles = db.query(Article)
except ValueError as e:
    # ValueError: Malformed JSON data: '{ invalid }'. Cannot deserialize as dict.
    print(f"Data corruption: {e}")
    # アプリケーションで適切にハンドリング可能
```

**使い分け:**
- 寛容モード：部分的な破損データでも処理を続けたい場合（ログ解析など）
- 厳格モード：データ整合性が重要で、破損があったら即座に検出したい場合（金額管理など）

#### クエリパラメータの検証

不正なクエリパラメータ（型の不一致など）は `QueryValidationError` として検出されます。

```python
from nyansqlite import QueryValidationError

try:
    # 型が不正な場合は例外が発生
    db.query(Article, views__gt="not_a_number")
except QueryValidationError as e:
    print(f"Invalid query parameter: {e}")
```

#### テーブル名衝突の検知

異なるモデルが同じテーブル名にマッピングされる場合、登録時に `TableNameCollisionError` が発生します：

```python
from nyansqlite import TableNameCollisionError

class UserAuth(BaseModel):
    id: int

class User_Auth(BaseModel):  # CamelCase正規化でも user_auth になる
    id: int

db.register(UserAuth)
try:
    db.register(User_Auth)  # TableNameCollisionError が発生
except TableNameCollisionError as e:
    print(f"Collision detected: {e}")
    # 解決策：__nyan_primary_key__ で明示的にテーブル名を指定
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
recent_titles = db.select(Article, ["title"], "views > 10", "id > 100")
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

**Constructor Options:**

```python
db = NyanSQLite(
    path=":memory:",              # Database file path (default: in-memory)
    wal=True,                     # Enable WAL mode (default: True)
    strict_deserialization=False  # Strict data validation (default: False)
)
```

### 📊 Performance

NyanSQLite implements the following optimizations:

- **WAL Mode**: Improved concurrent read/write performance
- **Transactions**: `insert_many()` runs within a transaction by default
- **Parameterized Queries**: SQL injection prevention
- **Auto-Chunking**: Large datasets exceeding SQLite's 32766 parameter limit are automatically split

```python
# Insert 100,000 records in seconds (batch processing)
import time
posts = [Post(id=i, title=f"Post {i}", author="neko") for i in range(100000)]
start = time.time()
db.insert_many(posts)  # Automatically chunks large datasets
print(f"Inserted in {time.time() - start:.4f}s")  # Example: 0.3456s
```

### 🔒 Security Features (v1.0.0+)

#### Multi-threaded Safety

All database operations are protected by `threading.Lock`, ensuring safe concurrent access from multiple threads:

```python
import threading
from nyansqlite import NyanSQLite

db = NyanSQLite("thread_safe.db")
db.register(Post)

def worker():
    # Safe to call from multiple threads
    db.query(Post, ...)
    db.insert(Post(...))

threads = [threading.Thread(target=worker) for _ in range(10)]
for t in threads: t.start()
for t in threads: t.join()
```

#### Asynchronous Support (`asyncio`)

NyanSQLite provides full support for `asyncio` via the `NyanSQLiteAIO` class. It uses `asyncio.to_thread` internally to keep operations non-blocking and thread-safe.

```python
import asyncio
from nyansqlite import NyanSQLiteAIO, Indexed
from pydantic import BaseModel

class User(BaseModel):
    id: int
    name: Indexed[str]

async def main():
    # 1. Connection via async context manager
    async with NyanSQLiteAIO("async.db") as db:
        # 2. Register models
        db.register(User)
        
        # 3. Async Insert
        await db.insert(User(id=1, name="alice"))
        
        # 4. Async Query
        # Django-like queries are fully supported
        users = await db.query(User, name="alice")
        print(f"Found: {users[0].name}")

        # 5. Bulk insert
        await db.insert_many([
            User(id=i, name=f"user_{i}") for i in range(2, 5)
        ])
        
        # 6. All read/write operations must be awaited
        exists = await db.exists(User, name="user_2")
        print(f"User 2 exists: {exists}")

asyncio.run(main())
```

#### Graceful Data Corruption Handling with `strict_deserialization`

If the database contains malformed JSON or invalid date formats, NyanSQLite can handle them in two ways:

**Lenient Mode (default):** Emits a warning and returns raw data:

```python
db = NyanSQLite("app.db", strict_deserialization=False)

# If DB has invalid JSON like { "invalid": ... }
# It will print a RuntimeWarning but continue processing
articles = db.query(Article)
# Output: RuntimeWarning: Malformed JSON data: '{ "invalid": ... }'. Returning as raw string.
```

**Strict Mode:** Raises `ValueError` on deserialization failure:

```python
db = NyanSQLite("app.db", strict_deserialization=True)

try:
    # Will raise ValueError if any record has corrupted data
    articles = db.query(Article)
except ValueError as e:
    print(f"Data corruption detected: {e}")
    # Application can then handle the error appropriately
```

Use **strict mode** for critical applications where data integrity validation is mandatory, and **lenient mode** for scenarios where partial data recovery is acceptable.

#### Query Parameter Validation

Invalid query parameters (type mismatches) are caught and reported as `QueryValidationError`:

```python
from nyansqlite import QueryValidationError

try:
    # TypeError if parameter type is invalid
    db.query(Post, views__gt="not_a_number")
except QueryValidationError as e:
    print(f"Invalid query parameter: {e}")
```

#### Table Name Collision Detection

If different models map to the same table name, `TableNameCollisionError` is raised at registration time:

```python
from nyansqlite import TableNameCollisionError

class UserAuth(BaseModel):
    id: int

class User_Auth(BaseModel):  # Both normalize to 'user_auth'
    id: int

db.register(UserAuth)
try:
    db.register(User_Auth)  # TableNameCollisionError
except TableNameCollisionError as e:
    print(f"Table name collision: {e}")

### 🔗 Resources

- **Repository**: [github.com/disnana/nyansqlite](https://github.com/disnana/nyansqlite)
- **Issues**: [Report bugs](https://github.com/disnana/nyansqlite/issues)
- **Security**: Thread-safe, injection-resistant, with data corruption handling

---

## License

MIT License – see [LICENSE](LICENSE) for details.
