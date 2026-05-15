# NyanSQLite チュートリアル

基礎から応用まで、NyanSQLiteを段階的に学ぶガイドです。

## 前提条件

- Python 3.9以上
- Pydanticの基本的な理解
- SQLiteの知識があると役立ちますが、必須ではありません

## インストール

```bash
pip install nyansqlite
```

## レッスン1: 最初のデータベース

NyanSQLiteはPydanticモデルをスキーマとして使用します。

### モデルの定義と登録

```python
from pydantic import BaseModel
from nyansqlite import NyanSQLite

# 1. モデル（スキーマ）を定義
class User(BaseModel):
    id: int
    name: str
    email: str

# 2. データベースを初期化
db = NyanSQLite("tutorial.db")

# 3. モデルを登録（テーブルが自動作成されます）
db.register(User)

# 4. データを挿入
user = User(id=1, name="Alice", email="alice@example.com")
db.insert(user)

# 5. データを取得
retrieved = db.get(User, id=1)
print(retrieved.name)  # Alice

# 終了時にクローズ
db.close()
```

### コンテキストマネージャの使用

```python
with NyanSQLite("tutorial.db") as db:
    db.register(User)
    # 操作...
# 自動的にクローズされます
```

## レッスン2: インデックスと全文検索

NyanSQLiteの強力な機能であるインデックスと全文検索（FTS5）を活用しましょう。

```python
from nyansqlite import NyanSQLite, Indexed, Searchable

class Article(BaseModel):
    id: int
    author: Indexed[str]         # B-treeインデックスが作成されます
    title: Searchable[str]       # 全文検索対象
    body: Searchable[str]        # 全文検索対象
    category: str = "general"

db = NyanSQLite("blog.db")
db.register(Article)

# データ挿入
db.insert(Article(id=1, author="neko", title="SQLite入門", body="NyanSQLiteは便利です。"))

# インデックスを利用した高速クエリ
articles = db.query(Article, author="neko")

# 全文検索
results = db.search(Article, "SQLite")
for hit in results:
    print(hit.title)
```

## レッスン3: Djangoライクなクエリ

複雑な検索もSQLを書かずに実現できます。

```python
# 比較演算子
# __gt (>), __gte (>=), __lt (<), __lte (<=), __ne (!=)
old_users = db.query(User, age__gt=30)

# IN句
selected = db.query(User, id__in=[1, 2, 3])

# LIKE検索
search = db.query(User, name__like="Ali%")

# NULLチェック
null_emails = db.query(User, email__is_null=True)

# 順序指定と制限
recent = db.query(User, order_by="id", desc=True, limit=5)
```

## レッスン4: 一括処理（パフォーマンス）

大量のデータを扱う場合は `insert_many` を使用します。

```python
users = [User(id=i, name=f"User{i}", email=f"user{i}@example.com") for i in range(1000)]

# 自動的にトランザクション内で実行され、高速です
db.insert_many(users)
```

## レッスン5: メンテナンス

```python
# データベースの最適化（ファイルサイズの縮小）
db.vacuum()

# 全文検索インデックスの再構築
db.rebuild_fts(Article)

# 存在確認
if db.exists(User, id=1):
    print("User exists")
```

## 次のステップ

- 詳細なバリデーションについては [validation](./validation) を参照
- APIの全容は [APIリファレンス](./api) を参照
