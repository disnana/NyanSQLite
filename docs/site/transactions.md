# トランザクションガイド

NyanSQLiteは、SQLiteのトランザクション機能を安全かつ簡単に利用するためのAPIを提供しています。

## NyanSQLiteのトランザクション

NyanSQLiteの `insert_many` メソッドは、内部で自動的にトランザクションを使用します。これにより、大量のデータを高速に、かつアトミックに（すべて成功するかすべて失敗するか）挿入できます。

### 内部的な挙動

NyanSQLiteは、一括処理の際に以下のステップを実行します：

1. `BEGIN` (または `BEGIN IMMEDIATE`) を発行
2. データをチャンク分割して挿入
3. すべて成功すれば `COMMIT`
4. 途中でエラーが発生すれば `ROLLBACK`

## 手動でのトランザクション管理

現在の NyanSQLite では、APSW の接続オブジェクトを直接取得してトランザクションを制御することも可能です。

```python
from nyansqlite import NyanSQLite

db = NyanSQLite("app.db")

# APSW 接続オブジェクトを介したトランザクション
with db.backend().transaction():
    db.insert(item1)
    db.insert(item2)
    # 例外が発生すると自動的にロールバックされます
```

## パフォーマンス最適化

トランザクションを使用すると、SQLiteの書き込みパフォーマンスが劇的に向上します。これは、ディスクへの同期（fsync）回数が減るためです。

### ベストプラクティス

1. **一括挿入には `insert_many` を使用する**: 自分でループを回して `insert` を呼び出すよりもはるかに高速です。
2. **適切なチャンクサイズ**: NyanSQLiteは、SQLiteのプレースホルダ上限（32,766）に合わせて自動的にデータを分割して処理します。
3. **WALモードの活用**: NyanSQLiteはデフォルトで WAL（Write-Ahead Logging）モードを有効にします。これにより、書き込み中でも読み込みをブロックせず、高い並行性を維持できます。

## 関連リファレンス

- [NyanSQLite API リファレンス](../api/NyanSQLite.md)
- [APSW トランザクション・ドキュメント](https://rogerbinns.github.io/apsw/connection.html#apsw.Connection.transaction)

