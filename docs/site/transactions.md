# トランザクションガイド

NyanSQLiteは、SQLiteのトランザクション機能を安全かつ簡単に利用するためのAPIを提供しています。

## NyanSQLiteのトランザクション

NyanSQLiteの `insert_many` などの一括処理メソッドは、内部で自動的にトランザクションを使用します。これにより、大量のデータを高速に、かつアトミックに（すべて成功するかすべて失敗するか）処理できます。

### 内部的な挙動

NyanSQLiteは、一括処理の際に以下のステップを実行します：

1. `BEGIN` (または `BEGIN IMMEDIATE`) を発行
2. データをチャンク分割して処理
3. すべて成功すれば `COMMIT`
4. 途中でエラーが発生すれば `ROLLBACK`

## 手動でのトランザクション管理 (`atomic`)

`atomic()` コンテキストマネージャを使用すると、複数の操作を一つのトランザクションとして明示的にまとめることができます。

### 同期版 (NyanSQLite)

```python
from nyansqlite import NyanSQLite

db = NyanSQLite("app.db")

with db.atomic():
    db.insert(item1)
    db.insert(item2)
    # 例外が発生すると、自動的にロールバックされます
```

### 非同期版 (NyanSQLiteAIO)

```python
from nyansqlite import NyanSQLiteAIO

db = NyanSQLiteAIO("app.db")

async with db.atomic():
    await db.insert(item1)
    await db.insert(item2)
    # 例外が発生すると、自動的にロールバックされます
```

### ネスト（入れ子）されたトランザクション

内側の `atomic()` や `insert_many()` は SAVEPOINT で保護されます。失敗した処理の範囲は取り消され、外側で例外を捕捉すれば残りの処理を続けられます。例外が最外側の `atomic()` まで伝わった場合は全体がロールバックされます。コミットは最外側のブロックが正常終了したときに行われます。

```python
with db.atomic():
    db.insert(item1)
    with db.atomic(): # 内部のトランザクション
        db.insert(item2)
    # ここでコミットされます
```

## パフォーマンス最適化

トランザクションを使用すると、SQLiteの書き込みパフォーマンスが劇的に向上します。これは、ディスクへの同期（fsync）回数が減るためです。

### ベストプラクティス

1. **一括挿入には `insert_many` を使用する**: 自分でループを回して `insert` を呼び出すよりもはるかに高速です。
2. **適切な範囲を `atomic()` で囲む**: 関連する複数の更新操作は一つの `atomic()` ブロックにまとめることで、データの整合性を保ち、パフォーマンスを向上させます。
3. **WALモードの活用**: NyanSQLiteはデフォルトで WAL（Write-Ahead Logging）モードを有効にします。これにより、書き込み中でも読み込みをブロックせず、高い並行性を維持できます。

## 関連リファレンス

- [NyanSQLite API リファレンス](./api)
- [APSW トランザクション・ドキュメント](https://rogerbinns.github.io/apsw/connection.html#apsw.Connection.transaction)

