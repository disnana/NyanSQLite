# 非同期サポート (`NyanSQLiteAIO`)

NyanSQLite v1.1.0 から、`asyncio` を使用した非同期プログラミングをネイティブにサポートする `NyanSQLiteAIO` クラスが導入されました。

## 特徴

`NyanSQLiteAIO` は、以下の特徴を持っています：

1. **イベントループを塞ぎにくい設計**: 内部で `asyncio.to_thread` を使用し、SQLite 操作をイベントループ外で進めます。
2. **スレッドセーフ**: 書き込み操作には非同期ロックを使用し、マルチスレッド/非同期環境での安全性を確保しています。
3. **短い読み取りクリティカルセクション**: SQLite 接続へのアクセスは保護しつつ、Pydantic モデルへの変換はできるだけロック外で行います。

## 基本的な使い方

`NyanSQLiteAIO` は非同期コンテキストマネージャをサポートしており、`async with` 構文で安全に接続・切断を行えます。

```python
import asyncio
from pydantic import BaseModel
from nyansqlite import NyanSQLiteAIO, Indexed

class User(BaseModel):
    id: int
    name: Indexed[str]

async def main():
    # 非同期コンテキストマネージャを使用
    async with NyanSQLiteAIO("app.db") as db:
        await db.register(User)
        
        # 非同期挿入
        await db.insert(User(id=1, name="alice"))
        
        # 非同期クエリ
        users = await db.query(User, name="alice")
        if users:
            print(f"Found: {users[0].name}")

        # 一括挿入
        await db.insert_many([
            User(id=i, name=f"user_{i}") for i in range(2, 6)
        ])
        
        # カウント操作
        count = await db.count(User)
        print(f"Total users: {count}")

if __name__ == "__main__":
    asyncio.run(main())
```

## メソッド一覧

`NyanSQLite` (同期版) とほぼ同じ API を非同期（`await` 可能）として提供しています：

- `await db.insert(obj)`
- `await db.insert_many(objs)`
- `await db.query(model, ...)`
- `await db.get(model, ...)`
- `await db.select(model, fields, ...)`
- `await db.search(model, query, ...)`
- `await db.update(model, where, ...)`
- `await db.delete(model, ...)`
- `await db.count(model, ...)`
- `await db.exists(model, ...)`

## パフォーマンスの最適化

v1.1.0 以降、読み取り操作（`query`, `select`, `search`）は、SQLite 接続へのアクセス時間を短く保つよう最適化されています。
データ取得後の Python オブジェクト変換は、可能な限り接続ロックの外で進める設計です。
