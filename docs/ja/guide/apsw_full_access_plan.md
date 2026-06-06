# APSW 全機能アクセス計画

NyanSQLite は Pydantic モデル中心の安全な SQLite API を保ちつつ、APSW が持つ高度な機能にも段階的にアクセスできるようにする。

## 方針

1. 既存 API は安全で簡単な入口として維持する。
2. APSW 固有機能は、利用者が明示的に選んだ場合だけ使えるようにする。
3. sqlite3 フォールバック時は、APSW 専用機能が使えないことを早く分かりやすく伝える。
4. 直接接続を渡す機能には、ロック・トランザクション・スレッド安全性の注意を明記する。

## Phase 1: 安全性と互換性の土台

- 同期版と非同期版の WHERE 検証を共通仕様にそろえる。
- 文字列フィルタは明示的な単純比較だけ許可し、それ以外は `QueryValidationError` にする。
- `date` / `datetime` / `list` / `dict` などのフィルタ値をモデル定義に沿ってシリアライズする。
- `limit` / `offset` は 0 以上の整数だけ許可する。
- `insert_many()` は混在モデルを拒否する。

## Phase 2: APSW 直接アクセス

- `backend == "apsw"` の場合に、APSW 接続へ明示的にアクセスできる API を追加する。
- 候補:
  - `db.raw_connection`
  - `db.apsw_connection`
  - `db.with_raw_connection(callback)`
- 推奨は `with_raw_connection(callback)`。ロックの内側で callback を実行できるため、既存 API との競合を抑えやすい。
- 非同期版は `await db.with_raw_connection(callback)` とし、必要に応じて `asyncio.to_thread()` 内で実行する。

## Phase 3: APSW 機能別の薄いラッパー

需要が高いものから、高水準 API として追加する。

- Backup API
- Blob I/O
- busy timeout / busy handler
- progress handler
- trace / profile
- authorizer
- custom scalar / aggregate / window functions
- virtual table extension
- file control
- config / db_config
- WAL checkpoint
- serialize / deserialize

## Phase 4: ドキュメントとテスト

- APSW がインストールされている環境だけで走る pytest を追加する。
- sqlite3 フォールバック環境では `pytest.skip()` で明確にスキップする。
- ロック内 raw access、ロック外 raw access、トランザクション中 raw access の注意点を文書化する。
- APSW の高度機能はバージョン差が出やすいため、機能検出ベースでテストする。

## 最初に実装する候補

1. `NyanConnection.raw_connection` と `NyanConnection.require_apsw()`
2. `NyanSQLite.with_raw_connection(callback)`
3. `NyanSQLiteAIO.with_raw_connection(callback)`
4. APSW がある場合だけ実行する smoke test
