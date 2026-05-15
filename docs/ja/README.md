# NyanSQLite ドキュメント

Pydanticモデルをそのままデータベーススキーマとして利用できる、型安全で高性能なSQLiteラッパー。

## 目次

- [コンセプト](#コンセプト)
- [インストール](#インストール)
- [クイックスタート](#クイックスタート)
- [ガイド](#ガイド)
  - [チュートリアル](guide/tutorial.md)
  - [バリデーション](guide/validation.md)
  - [非同期サポート](guide/async.md)
  - [トランザクション](guide/transactions.md)
  - [エラーハンドリング](guide/error_handling.md)
  - [パフォーマンス](guide/performance.md)
  - [ベストプラクティス](guide/best_practices.md)
  - [暗号化](guide/encryption.md)
  - [例外クラス](guide/exceptions.md)
- [APIリファレンス](api.md)

---

## コンセプト

### 課題

従来のデータベースソリューションはSQLの学習、接続管理、シリアライズの手動処理が必要です。また、データの整合性を保つためのバリデーションコードを別途記述する必要があります。

### 解決策

**NyanSQLite**はPydanticモデルをSQLiteのテーブルに直接マッピングし、このギャップを埋めます：

1. **型安全**: Pydanticの型ヒントをそのままデータベーススキーマとして利用。
2. **自動シリアライズ**: dictやlist、datetimeなどの複雑な型を自動的にシリアライズ/デシリアライズ。
3. **Djangoライクなクエリ**: 直感的な構文で複雑な検索を実現。
4. **高速な全文検索**: SQLiteのFTS5をサポート。

### 設計原則

1. **即時永続化**: すべての書き込み操作は即座にSQLiteに保存。
2. **スレッドセーフ**: `threading.Lock`による安全なマルチスレッドアクセス。
3. **設定不要**: パフォーマンス最適化された合理的なデフォルト（WALモード等）。

---

## インストール

```bash
pip install nyansqlite
```

**必要条件:**
- Python 3.9以上
- Pydantic 2.0以上

---

## クイックスタート

### 基本的な使い方

```python
from pydantic import BaseModel
from nyansqlite import NyanSQLite, Indexed, Searchable

# 1. スキーマ定義
class Article(BaseModel):
    id: int                      # idフィールドが自動的に主キーになります
    author: Indexed[str]         # インデックス付きカラム
    title: Searchable[str]       # 全文検索対象
    body: Searchable[str]        # 全文検索対象
    views: int = 0

# 2. DB初期化＆テーブル作成
db = NyanSQLite("blog.db")
db.register(Article)

# 3. データ挿入
db.insert(Article(
    id=1,
    author="neko",
    title="SQLiteを使いこなそう",
    body="NyanSQLiteで簡単にデータ管理ができます。"
))

# 4. クエリ実行
articles = db.query(Article, author="neko", views__gte=0)

# 5. 全文検索
results = db.search(Article, "SQLite")
for hit in results:
    print(f"Found: {hit.title}")

db.close()
```

---

## ガイド

詳細な情報は以下のガイドを参照してください：

- **[チュートリアル](guide/tutorial.md)**: 複数テーブルや高度な機能を含む詳細な例。
- **[バリデーション](guide/validation.md)**: Pydanticによるスキーマ検証とデータ型の扱い。
- **[非同期サポート](guide/async.md)**: 非同期環境での使用方法。
- **[トランザクション](guide/transactions.md)**: データの整合性と一括書き込みの最適化。
- **[エラーハンドリング](guide/error_handling.md)**: 例外処理とトラブルシューティング。
- **[パフォーマンス](guide/performance.md)**: NyanSQLiteの速度チューニング。
- **[ベストプラクティス](guide/best_practices.md)**: 本番環境での推奨パターン。
- **[暗号化](guide/encryption.md)**: データの安全な保存。
- **[例外クラス](guide/exceptions.md)**: 例外クラスの詳細リファレンス。

---

## APIリファレンス

全クラス・メソッドの完全なドキュメント。

- **[NyanSQLite](api/NyanSQLite.md)**
