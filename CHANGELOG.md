# CHANGELOG

## [1.1.5] - 2026-09-26

### 🚀 Performance
- Prepared field-specific SQLite decoders and the update validation route when a model is registered. In a paired local Python 3.11 benchmark converting 20,000 rows with scalar, datetime, and list fields, median conversion time fell from 0.194 to 0.166 seconds; scalar-only rows were effectively unchanged.
- Reduced repeated type inspection while converting SQLite rows to Pydantic models. In a local Python 3.11 benchmark reading 10,000 rows with scalar, datetime, and list fields, median query time fell from 0.098 to 0.068 seconds (sync) and from 0.108 to 0.074 seconds (async).
- Bound `LIMIT` and `OFFSET` as SQL parameters so paginated queries can reuse the same statement shape. In a local 1,000-query pagination benchmark, median time fell from 0.0341 to 0.0315 seconds.
- Removed an unused whole-collection JSON conversion from `__in` filters. Building 500 filters with 1,000 integer values each fell from 0.138 to 0.091 seconds in a local benchmark.

### 🐞 Fixed
- Kept the async connection locked until an in-flight SQLite call finishes after cancellation, and rolled back open `atomic()` transactions when cancelled.
- Rolled back synchronous `atomic()` transactions on interruptions as well as ordinary exceptions.
- `update()` now validates changed fields before writing. Models with custom validators or configuration validate each affected row inside the transaction, so a failed multi-row update leaves every row unchanged.
- `register()` now reports incompatible existing columns, types, primary keys, nullability, or FTS searchable columns immediately with `SchemaMismatchError` instead of failing on a later write or silently reusing stale FTS definitions.
- Adding full-text search to an existing table now indexes its existing rows, so they appear in search results immediately.

### 🧪 Tests
- Added parity tests for prepared decoders, including strict and warning behavior on malformed data.
- Added regression coverage for cancellation, transaction isolation, pagination parameters, and unhashable `Annotated` metadata.
- Added sync and async regression coverage for invalid updates, multi-row rollback, table schema drift, and FTS column drift.

### 📚 Docs
- Replaced the published error and exception guides that described a different library, corrected the backup example, and documented projection, batched async reads, and continuation-based pagination.

### ⚠️ Compatibility
- Invalid partial updates now raise Pydantic `ValidationError`. Registering an incompatible existing table now raises `SchemaMismatchError`; migrate the table explicitly before registering the changed model.

---

## [1.1.4] - 2026-06-22

### 🐞 Fixed
- Validated all generated SQLite identifiers and rejected unknown composite-index fields before constructing schema SQL.
- Hardened string filters so unsupported raw SQL fragments now raise `QueryValidationError` instead of being passed through to SQL.
- Aligned async query validation with the sync implementation, including unknown-field checks and model-aware filter value serialization.
- Fixed async filtering for `date`, `datetime`, `list`, and `dict` values.
- Fixed `__in` handling so normal lists/tuples/sets work consistently and empty collections return no rows.
- Fixed offset-only pagination by emitting SQLite's required unlimited `LIMIT` clause.
- Tightened `limit` / `offset` validation to reject negative values, floats, booleans, and strings.
- Added a clear `TypeError` when `insert_many()` receives mixed model types.
- Serialized reads and connection shutdown with the existing locks so `close()` cannot race active queries.
- Protected `vacuum()` and async `execute_raw()` with the existing connection locks.

### 🧪 Tests
- Added regression tests for unsafe string filters, async field validation, serialized filter values, `__in`, offset-only pagination, strict pagination types, and mixed-model bulk inserts.

### 📚 Docs
- Added an APSW full-access implementation plan.

### ⚠️ Compatibility
- String filters now support only simple comparisons such as `"age > 10"` or `"name = 'Alice'"`. Use keyword filters such as `age__gte=10` for advanced filtering.
- Python 3.9 remains supported for the core package. Some optional and development dependencies cannot provide their latest security-fixed wheels on Python 3.9; use Python 3.10+ for the `speed`, `encryption`, and `dev` extras when processing untrusted input.

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

## [1.1.5] - 2026-09-26

### 🚀 高速化
- モデル登録時にフィールド別のSQLite値変換器と更新時の検証経路を準備するようにしました。基本型・日時・リストを含む2万行の変換を比較したPython 3.11のローカル測定では、中央値が0.194秒から0.166秒になりました。基本型だけの行ではほぼ同等でした。
- SQLiteの行をPydanticモデルへ変換する際、型情報の解析を繰り返さないようにしました。Python 3.11で基本型・日時・リストを含む1万行を取得したローカル測定では、中央値が同期版で0.098秒から0.068秒、非同期版で0.108秒から0.074秒になりました。
- `LIMIT` と `OFFSET` をSQLパラメータに変更し、ページ位置が変わっても同じ形のSQLを再利用できるようにしました。1,000回のページング検索を行うローカル測定では、中央値が0.0341秒から0.0315秒になりました。
- `__in` フィルタで使われないコレクション全体のJSON変換を削除しました。整数1,000件の条件を500回生成するローカル測定では、0.138秒から0.091秒になりました。

### 🐞 修正
- 非同期処理をキャンセルしても実行中のSQLite呼び出しが終わるまで接続を保護し、開いた `atomic()` トランザクションをロールバックするようにしました。
- 同期版の `atomic()` でも通常の例外に加え、割り込み時にロールバックするようにしました。
- `update()` が更新値を検証するようにしました。独自バリデータやモデル設定がある場合はトランザクション内で対象行を検証し、複数行のうち1件でも失敗すれば全件の更新を取り消します。
- 既存テーブルの列、型、主キー、NULL制約、全文検索対象列がモデルと異なる場合、`register()` で `SchemaMismatchError` を送出するようにしました。古いFTS定義の再利用も防ぎます。
- 既存テーブルへ全文検索を追加したとき、登録済みの行も検索インデックスへ取り込むようにしました。

### 🧪 テスト
- 準備済み変換器と従来の変換処理が、不正値での厳格モードや警告を含めて同じ結果になることを検証しました。
- キャンセル、トランザクションの分離、ページング用パラメータ、ハッシュ化できない `Annotated` メタデータの回帰テストを追加しました。
- 同期・非同期の無効な更新、複数行更新の取り消し、テーブルとFTSのスキーマ不一致を検証する回帰テストを追加しました。

### 📚 ドキュメント
- 別ライブラリのAPIが残っていた公開エラー／例外ガイドを修正し、バックアップ例と必要列だけの取得・非同期の一括取得・続き位置ページングの例を更新しました。

### ⚠️ 互換性
- 無効な部分更新はPydanticの `ValidationError`、互換性のない既存テーブルの登録は `SchemaMismatchError` を送出します。モデル変更時はテーブルを明示的に移行してください。

---

## [1.1.4] - 2026-06-22

### 🐞 修正
- SQLite識別子をSQL生成前に検証し、複合インデックスに未知のフィールドが含まれる場合は拒否するようにしました。
- 未対応の生SQL断片を文字列フィルタとして渡した場合、SQLへ素通しせず `QueryValidationError` を送出するようにしました。
- 非同期版のクエリ検証を同期版と揃え、未知フィールド検証とモデル定義に基づくフィルタ値シリアライズを追加しました。
- 非同期版で `date` / `datetime` / `list` / `dict` のフィルタが正しく動くようにしました。
- `__in` の通常ケースを修正し、空コレクションは0件一致として扱うようにしました。
- `offset` のみを指定した場合もSQLiteで有効な無制限 `LIMIT` 句を生成するようにしました。
- `limit` / `offset` で負数、小数、真偽値、文字列を拒否するよう検証を厳格化しました。
- `insert_many()` に異なるモデル型が混在した場合、明確に `TypeError` を送出するようにしました。
- 読み取り処理と接続終了を既存ロックで直列化し、実行中のクエリと `close()` が競合しないようにしました。
- `vacuum()` と非同期版の `execute_raw()` を既存ロックで保護しました。

### 🧪 テスト
- 危険な文字列フィルタ、非同期版のフィールド検証、シリアライズ対象フィルタ値、`__in`、offset単独指定、ページネーション型検証、混在モデル一括挿入の回帰テストを追加しました。

### 📚 ドキュメント
- APSW 全機能アクセスに向けた段階的な実装計画を追加しました。

### ⚠️ 互換性
- 文字列フィルタは `"age > 10"` や `"name = 'Alice'"` のような単純比較のみサポートします。複雑な条件は `age__gte=10` のようなキーワードフィルタ、または明示的な raw SQL を使ってください。
- コアパッケージのPython 3.9対応は維持します。ただし、一部の開発・オプション依存関係はPython 3.9向けに最新のセキュリティ修正版ホイールを提供していません。信頼できない入力を扱う場合、`speed`・`encryption`・`dev` extrasはPython 3.10以上で利用してください。

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
