# NyanSQLite ベストプラクティス

本番環境でNyanSQLiteを効果的に使用するための包括的なガイドです。

## パフォーマンス最適化

### 一括挿入には `insert_many` を使用する

個別に `insert` を呼び出すよりも、`insert_many` を使用して一括で挿入する方が圧倒的に高速です。NyanSQLiteは内部で自動的にトランザクションを使用し、SQLiteの制限に合わせて最適にデータを分割します。

```python
# ✅ ベストプラクティス: 一括挿入
users = [User(id=i, name=f"User{i}") for i in range(1000)]
db.insert_many(users)
```

### インデックスの活用

頻繁に検索（`query`）するフィールドには `Indexed[T]` アノテーションを付けてください。これにより B-tree インデックスが作成され、検索が高速化されます。

```python
class User(BaseModel):
    id: int
    username: Indexed[str]  # username による検索が高速になります
```

### 全文検索の適切な使用

大量のテキストデータを検索する場合は、`Searchable[str]` を使用して FTS5 インデックスを作成してください。通常の `LIKE` 検索よりも劇的に高速です。

```python
class Article(BaseModel):
    title: Searchable[str]
    body: Searchable[str]
```

## セキュリティ

### 自動的なパラメータ化

NyanSQLiteの `query`, `get`, `delete` などのメソッドは、内部でパラメータ化クエリ（プリペアードステートメント）を使用しています。これにより、SQLインジェクション攻撃を自動的に防ぎます。

### データの整合性

Pydanticモデルを使用することで、データベースに保存されるデータの型安全性が保証されます。可能な限り詳細な型ヒントとバリデーションルール（`Field` など）をモデルに定義してください。

## 運用・メンテナンス

### 定期的な `vacuum`

データの削除を繰り返すと、SQLiteのデータベースファイル内に空き領域（断片化）が生じます。定期的に `db.vacuum()` を実行して、ファイルを最適化しサイズを縮小してください。

### バックアップ

NyanSQLite（APSW）は、実行中のデータベースを安全にバックアップする機能を持っています。

```python
# 下位層の接続オブジェクトを使用してバックアップ
db.backend().backup("backup.db")
```

## デザインパターン

### モデルの共通化

複数のアプリケーションで同じデータベースを共有する場合、モデル定義を独立したモジュールにまとめ、それを各アプリケーションからインポートするようにしてください。

### コンテキストマネージャの使用

常に `with` 文を使用して NyanSQLite を初期化し、リソースが確実に解放されるようにしてください。

```python
with NyanSQLite("app.db") as db:
    db.register(MyModel)
    # ... 操作
```

## まとめ

1. ✅ 大量データの挿入には `insert_many` を使用。
2. ✅ 検索頻度の高いフィールドには `Indexed` を指定。
3. ✅ テキスト検索には `Searchable` (FTS5) を活用。
4. ✅ 常にコンテキストマネージャでリソース管理。
5. ✅ 定期的に `vacuum` でデータベースを最適化。
