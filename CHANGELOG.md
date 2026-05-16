# CHANGELOG

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
