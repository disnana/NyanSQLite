# CHANGELOG

## [1.1.4] - 2026-06-22

### 🐞 Fixed
- Hardened string filters so unsupported raw SQL fragments now raise `QueryValidationError` instead of being passed through to SQL.
- Aligned async query validation with the sync implementation, including unknown-field checks and model-aware filter value serialization.
- Fixed async filtering for `date`, `datetime`, `list`, and `dict` values.
- Fixed `__in` handling so normal lists/tuples/sets work consistently and empty collections return no rows.
- Added validation for negative or invalid `limit` / `offset` values.
- Added a clear `TypeError` when `insert_many()` receives mixed model types.
- Protected `vacuum()`, async `execute_raw()`, async `vacuum()`, and async `close()` with the existing connection locks.

### 🧪 Tests
- Added regression tests for unsafe string filters, async field validation, serialized filter values, `__in`, pagination bounds, and mixed-model bulk inserts.

### 📚 Docs
- Added an APSW full-access implementation plan.

### ⚠️ Compatibility
- String filters now support only simple comparisons such as `"age > 10"` or `"name = 'Alice'"`. Use keyword filters such as `age__gte=10` for advanced filtering.

---

## [1.1.1] - 2026-05-16

### 🚀 Added
- **Explicit Transactions**: Added `atomic()` context manager to `NyanSQLite` and `async with atomic()` to `NyanSQLiteAIO` for manual transaction control.
- **Nested Transactions**: Added support for nested `atomic()` blocks.

### 🔄 Changed
- **Thread Safety**: Improved thread safety by switching to `threading.RLock` in `NyanSQLite`.
- **Async Safety**: Implemented re-entrant async lock in `NyanSQLiteAIO` to prevent deadlocks when using `atomic()`.

---

## [1.1.0] - 2026-05-16

### 🚀 Added
- **Asynchronous Support**: Full support for `asyncio` via `NyanSQLiteAIO` class.
- **Improved Performance**: Optimized read operations by minimizing thread context switching and processing rows efficiently in `asyncio.to_thread`.
- **Documentation Updates**: Added English and Japanese documentation for asynchronous usage.

### 🔄 Changed
- Internal optimization for `query`, `select`, and `search` methods in `NyanSQLiteAIO`.
- Optimized read operations in synchronous `NyanSQLite` class by minimizing lock duration.

---

## [1.0.1] - 2026-05-15

### 🐞 Fixed
- Minor bug fixes and performance improvements.

---

## [1.0.0] - 2026-05-15

### 🚀 Added
- **Pydantic v2 support**: Models can be used directly as database schemas.
- **Django-like Query Syntax**: Support for intuitive filtering such as `__gte`, `__in`, `__like`, etc.
- **FTS5 Full-Text Search**: Fast full-text search capabilities using SQLite's FTS5 extension.
- **Automatic Index Management**: B-tree indexes are automatically created using `Indexed[T]` and `UniqueIndexed[T]` annotations.
- **Composite Indexes**: Support for `CompositeIndex` via Pydantic's `Field` extra metadata.
- **Transparent Type Handling**: Automatically handles complex types like `dict` and `list` by serializing them to JSON.
- **WAL Mode Support**: Write-Ahead Logging is enabled by default for better performance and concurrency.
- **Context Manager Support**: `NyanSQLite` can be used as a context manager for automatic connection closing.

### 🔄 Changed
- Initial public release of NyanSQLite.

---

# 更新履歴

## [1.1.4] - 2026-06-22

### 🐞 修正
- 未対応の生SQL断片を文字列フィルタとして渡した場合、SQLへ素通しせず `QueryValidationError` を送出するようにしました。
- 非同期版のクエリ検証を同期版と揃え、未知フィールド検証とモデル定義に基づくフィルタ値シリアライズを追加しました。
- 非同期版で `date` / `datetime` / `list` / `dict` のフィルタが正しく動くようにしました。
- `__in` の通常ケースを修正し、空コレクションは0件一致として扱うようにしました。
- 負数または不正な `limit` / `offset` を拒否するようにしました。
- `insert_many()` に異なるモデル型が混在した場合、明確に `TypeError` を送出するようにしました。
- `vacuum()`、非同期版の `execute_raw()` / `vacuum()` / `close()` を既存ロックで保護しました。

### 🧪 テスト
- 危険な文字列フィルタ、非同期版のフィールド検証、シリアライズ対象フィルタ値、`__in`、ページネーション境界、混在モデル一括挿入の回帰テストを追加しました。

### 📚 ドキュメント
- APSW 全機能アクセスに向けた段階的な実装計画を追加しました。

### ⚠️ 互換性
- 文字列フィルタは `"age > 10"` や `"name = 'Alice'"` のような単純比較のみサポートします。複雑な条件は `age__gte=10` のようなキーワードフィルタ、または明示的な raw SQL を使ってください。

---

## [1.1.3] - 2026-05-16

### 🐞 修正
- insert_manyの処理が1.2秒以上かかっていたのを0.6秒程度まで高速化。

---

## [1.1.2] - 2026-05-16

### 🐞 修正
- 無駄な改行の削除とCIの改良。

---

## [1.1.1] - 2026-05-16

### 🚀 追加
- **明示的トランザクション**: 手動でトランザクションを制御するための `atomic()` コンテキストマネージャを `NyanSQLite` に、`async with atomic()` を `NyanSQLiteAIO` に追加しました。
- **入れ子構造のトランザクション**: ネスト（入れ子）された `atomic()` ブロックのサポートを追加しました。

### 🔄 変更
- **スレッドセーフ**: `NyanSQLite` で `threading.RLock` を使用するように変更し、スレッド安全性を向上させました。
- **非同期安全性**: `NyanSQLiteAIO` において、`atomic()` 使用時のデッドロックを防ぐためにリエントラントな非同期ロックを実装しました。

---

## [1.1.0] - 2026-05-16

### 🚀 追加
- **非同期サポート**: `NyanSQLiteAIO` クラスによる `asyncio` の完全サポート。
- **パフォーマンス向上**: `asyncio.to_thread` 内での効率的な行処理により、読み取り操作を最適化。
- **ドキュメント更新**: 非同期利用に関する日英のドキュメントを追加。

### 🔄 変更
- `NyanSQLiteAIO` の `query`, `select`, `search` メソッドの内部最適化。
- 同期版 `NyanSQLite` クラスにおいて、読み取り操作のロック保持時間を最小化。

---

## [1.0.1] - 2026-05-15

### 🐞 修正
- 軽微なバグ修正とパフォーマンスの改善。

---

## [1.0.0] - 2026-05-15

### 🚀 追加
- **Pydantic v2 対応**: Pydanticモデルをそのままデータベーススキーマとして利用可能。
- **Djangoライクなクエリ構文**: `__gte`, `__in`, `__like` などの直感的なフィルタリングをサポート。
- **FTS5 全文検索**: SQLiteのFTS5拡張を利用した高速な全文検索機能。
- **自動インデックス管理**: `Indexed[T]` や `UniqueIndexed[T]` アノテーションによるB-treeインデックスの自動生成。
- **複合インデックス**: Pydanticの `Field` メタデータを介した `CompositeIndex` のサポート。
- **透過的な型処理**: `dict` や `list` などの複雑な型を自動的にJSONとしてシリアライズ/デシリアライズ。
- **WALモードのサポート**: パフォーマンスと並行性の向上のため、デフォルトでWAL（Write-Ahead Logging）モードを有効化。
- **コンテキストマネージャ対応**: `with` 構文による自動的なコネクション終了処理。

### 🔄 変更
- NyanSQLite の初期公開リリース。
