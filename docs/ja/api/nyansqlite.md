# NyanSQLite API リファレンス

PydanticネイティブなSQLiteラッパー `NyanSQLite` クラスのドキュメントです。

## クラス: `NyanSQLite`

```python
class NyanSQLite:
    def __init__(self, path: str = ":memory:", wal: bool = True, strict_deserialization: bool = False)
```

### コンストラクタ

- `path` (str): データベースファイルのパス。デフォルトはメモリ内データベース (`:memory:`)。
- `wal` (bool): WAL (Write-Ahead Logging) モードを有効にするかどうか。デフォルトは `True`。
- `strict_deserialization` (bool): `True` の場合、データ読み込み時のデシリアライズ失敗で例外を発生させます。`False`（デフォルト）の場合、警告を出して生データを返します。

---

## 主要メソッド

### `register`
```python
def register(self, model: type[BaseModel]) -> None
```
Pydanticモデルを登録し、対応するテーブル、インデックス、FTS5仮想テーブルを自動的に作成します。

### `insert`
```python
def insert(self, obj: BaseModel) -> None
```
モデルのインスタンスをデータベースに挿入します。

### `insert_many`
```python
def insert_many(self, objs: list[BaseModel]) -> None
```
複数のモデルインスタンスを一括で挿入します。内部で自動的にトランザクションが使用され、大量のデータも高速に処理されます。

### `query`
```python
def query(self, model: type[M], *filters: str, limit: Optional[int] = None, offset: Optional[int] = None, order_by: Optional[str] = None, desc: bool = False, **kwargs: Any) -> list[M]
```
Djangoライクなフィルタリングを使用してデータを検索し、モデルインスタンスのリストを返します。

- `filters`: `"age > 20"` のような文字列形式のフィルタ。v1.1.4dev1 以降は、安全のため明示的な単純比較のみサポートします。
- `kwargs`: `name="Alice"`, `views__gte=100` のようなキーワード形式のフィルタ。
- `limit` / `offset`: 取得件数と開始位置の制限。
- `order_by`: ソート対象のフィールド名。
- `desc`: `True` の場合、降順でソート。

### `get`
```python
def get(self, model: type[M], *filters: str, **kwargs: Any) -> Optional[M]
```
条件に一致する最初の1件を取得します。見つからない場合は `None` を返します。

### `update`
```python
def update(self, model: type[BaseModel], where: dict[str, Any], **fields: Any) -> None
```
条件（`where`）に一致するレコードを指定した値（`fields`）で更新します。

### `delete`
```python
def delete(self, model: type[BaseModel], *filters: str, **kwargs: Any) -> None
```
条件に一致するレコードを削除します。

---

## 検索と集計

### `search`
```python
def search(self, model: type[M], query: str, *, limit: Optional[int] = None) -> list[M]
```
FTS5を使用した全文検索を実行します。`Searchable` アノテーションが付いたフィールドが対象となります。

### `count`
```python
def count(self, model: type[BaseModel], *filters: str, **kwargs: Any) -> int
```
条件に一致するレコード数を返します。

### `exists`
```python
def exists(self, model: type[BaseModel], *filters: str, **kwargs: Any) -> bool
```
条件に一致するレコードが存在するかどうかを返します。

### `select`
```python
def select(self, model: type[BaseModel], fields: list[str], *filters: str, **kwargs: Any) -> list[dict[str, Any]]
```
特定のフィールドのみを取得し、辞書のリストとして返します。

---

## メンテナンスと管理

### `rebuild_fts`
```python
def rebuild_fts(self, model: type[BaseModel]) -> None
```
全文検索（FTS5）インデックスを再構築します。

### `vacuum`
```python
def vacuum(self) -> None
```
データベースの `VACUUM` を実行し、ファイルサイズを最適化します。

### `close`
```python
def close(self) -> None
```
データベース接続を閉じます。

### `backend`
```python
def backend(self) -> NyanConnection
```
下位層の `NyanConnection` オブジェクトを返します。直接的なトランザクション制御（`backend().transaction()`）などに使用できます。

### `registered_models`
```python
def registered_models(self) -> list[type[BaseModel]]
```
現在登録されているモデルのリストを返します。
