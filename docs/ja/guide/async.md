# 非同期サポート (`NyanSQLiteAIO`)

現在の NyanSQLite では、`asyncio` 向けに `NyanSQLiteAIO` を利用できます。

## 現在の挙動

`NyanSQLiteAIO` は `asyncio.to_thread()` を使って SQLite 操作をイベントループ外で実行します。

1. **安全な接続アクセス**: SQLite 接続へのアクセス自体は直列化し、接続の一貫性を保ちます。
2. **書き込みの排他制御**: `insert`, `update`, `delete`, `atomic()` などの書き込み系は非同期ロックで保護されます。
3. **読み取りの待ち時間を削減**: クエリ結果の Pydantic 変換は、できるだけ接続ロックの外で進めます。

## 基本的な使い方

```python
import asyncio
from pydantic import BaseModel
from nyansqlite import Indexed, NyanSQLiteAIO


class Article(BaseModel):
    id: int
    title: str
    author: Indexed[str]


async def main():
    async with NyanSQLiteAIO("app.db") as db:
        await db.register(Article)
        await db.insert(Article(id=1, title="Hello", author="neko"))

        article = await db.get(Article, id=1)
        print(article.title)

        rows = await db.query(Article, author="neko", order_by="id")
        print(len(rows))


if __name__ == "__main__":
    asyncio.run(main())
```

## メモ

- `register()` を含め、ほとんどの操作は `await` が必要です。
- `async with db.atomic():` を使うと、複数の書き込みを1つのトランザクションとして扱えます。
- 同期版 `NyanSQLite` を `run_in_executor()` で包むより、基本的には `NyanSQLiteAIO` を使う方が素直です。
