# 非同期サポートについて（計画中）

現在、NyanSQLite v1.0.x 系では、非同期（async/await）のネイティブサポートは含まれていません。

## 現在の状況

現在の `NyanSQLite` クラスは同期的な操作（ブロッキングI/O）を基本として設計されています。
データベース操作は `threading.Lock` によってスレッドセーフに保たれていますが、`asyncio` イベントループを直接考慮した設計にはなっていません。

### 非同期環境での暫定的な使用方法

FastAPI などの非同期フレームワークで NyanSQLite を使用する場合、ブロッキング操作を避けるために `run_in_executor` などを使用して同期メソッドを呼び出す必要があります。

```python
import asyncio
from nyansqlite import NyanSQLite

db = NyanSQLite("app.db")

async def get_article(article_id: int):
    loop = asyncio.get_running_loop()
    # 同期メソッドをエグゼキュータで実行
    return await loop.run_in_executor(None, db.get, Article, id=article_id)
```

## ロードマップ

将来のバージョンでは、以下の機能を含むネイティブな非同期サポート（`AsyncNyanSQLite`）の導入を検討しています：

1. **専用スレッドプール**: データベース操作をバックグラウンドスレッドで実行し、イベントループをブロックしない。
2. **非同期クエリ API**: `await db.query(...)` のような直感的な非同期インターフェース。
3. **接続プール**: 非同期環境での効率的な接続管理。

非同期サポートに関する進捗や要望がある場合は、GitHubのリポジトリにてお知らせください。
