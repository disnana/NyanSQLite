---
outline: [2, 3]
---

# NyanSQLite API リファレンス

PydanticネイティブなSQLiteラッパー NyanSQLite クラスのドキュメントです。

## NyanSQLite

```python
class NyanSQLite(path: str = ':memory:', wal: bool = True, strict_deserialization: bool = False)
```

PydanticネイティブなSQLiteラッパー。

## NyanSQLiteAIO

```python
class NyanSQLiteAIO(path: str = ':memory:', wal: bool = True, strict_deserialization: bool = False)
```

`NyanSQLite` の非同期版です。

内部では `asyncio.to_thread` を使って SQLite 操作をイベントループ外で実行しつつ、接続アクセスを安全に保護します。
書き込み系操作は排他的に処理され、読み取り系は接続ロックの保持時間を短く保つよう実装されています。
ほとんどのメソッドは `async` で定義されているため、呼び出し時に `await` が必要です。

詳細は [非同期サポート](./async) を参照してください。

NyanSQLiteを初期化します。

#### 引数名

| 引数名 | 型 | 説明 |
|---|---|---|
| `path` | `str` | データベースファイルのパス。デフォルトは `":memory:"` です。 |
| `wal` | `bool` | WAL (Write-Ahead Logging) モードを有効にするかどうか。デフォルトは `True` です。 |
| `strict_deserialization` | `bool` | デシリアライズ時に厳密なチェックを行うかどうか。`True` の場合は不正データで例外を投げ、`False` の場合は警告を出して生の値を返します。 |



---

## コンストラクタ

## コアメソッド

### `register`

```python
def register(model: type[BaseModel]) -> None
```

Pydanticモデルを登録し、対応するテーブル、インデックス、FTS5仮想テーブルを作成します。

#### 引数名

| 引数名 | 型 | 説明 |
|---|---|---|
| `model` | `type[BaseModel]` | 登録するPydanticモデルクラス。 |

::: warning 例外
- TableNameCollisionError: 同じテーブル名を持つ別のモデルが既に登録されている場合に発生します。
:::


---

### `close`

```python
def close() -> None
```

データベース接続を閉じます。


---

### `registered_models`

```python
def registered_models() -> list[str]
```

登録されているすべてのモデル名を取得します。

#### 戻り値

**Type:** `list[str]`

list[str]: モデル名のリスト。


---

## CRUD操作

### `insert`

```python
def insert(obj: M) -> M
```

Pydanticモデルのインスタンスをデータベースに挿入します。

#### 引数名

| 引数名 | 型 | 説明 |
|---|---|---|
| `obj` | `M` | 挿入するモデルのインスタンス。 |

#### 戻り値

**Type:** `M`

M: 挿入されたオブジェクト（変更なし）。
       The inserted object (unchanged).

::: warning 例外
- ModelNotRegisteredError: モデルが登録されていない場合に発生します。
:::


---

### `insert_many`

```python
def insert_many(objs: list[M]) -> int
```

複数のモデルインスタンスを1つのトランザクションで一括挿入します。
Bulk-insert multiple model instances in a single transaction.

SQLiteの変数バインド制限（デフォルト 32766）を考慮し、大きなデータセットは自動的に分割して挿入されます。
(default 32766). This prevents SQLITE_TOOBIG errors on very large datasets.

#### 引数名

| 引数名 | 型 | 説明 |
|---|---|---|
| `objs` | `list[M]` | 挿入するモデルインスタンスのリスト。 |

#### 戻り値

**Type:** `int`

int: 挿入された行数。

::: warning 例外
- ModelNotRegisteredError: モデルが登録されていない場合に発生します。
:::


---

### `update`

```python
def update(model: type[BaseModel], where: dict[str, Any], **fields: Any) -> int
```

指定されたフィールドのみを更新する部分更新を行います。

#### 引数名

| 引数名 | 型 | 説明 |
|---|---|---|
| `model` | `type[BaseModel]` | 更新対象のモデルクラス。 |
| `where` | `dict[str, Any]` | 更新対象の行を特定する一致条件（例: `{"id": 1}`）。 |
| `fields` |  | 更新する `フィールド名=新しい値` のペア。 |

#### 戻り値

**Type:** `int`

int: 更新された行数。

::: warning 例外
- ModelNotRegisteredError: モデルが登録されていない場合に発生します。
- FieldNotFoundError: 指定されたフィールドがモデルに存在しない場合に発生します。
:::

::: tip 使用例
```python
    db.update(User, where={"id": 1}, age=26, bio="updated")
```
:::


---

### `delete`

```python
def delete(model: type[BaseModel], *filters: str, **kwargs: Any) -> int
```

フィルタ条件に一致するすべての行を削除します。

#### 引数名

| 引数名 | 型 | 説明 |
|---|---|---|
| `model` | `type[BaseModel]` | 削除対象のモデルクラス。 |
| `filters` | `str` | 文字列形式のフィルタ条件（例: `"age > 50"`）。 |
| `kwargs` |  | キーワード形式のフィルタ条件（例: `id=42`）。 |

#### 戻り値

**Type:** `int`

int: 削除された行数。

::: tip 使用例
```python
    db.delete(User, id=42)
    db.delete(User, "age > 50")
    db.delete(Session, user_id=1, active=True)
```
:::


---

## クエリ & 検索

### `get`

```python
def get(model: type[M], *filters: str, **kwargs: Any) -> Optional[M]
```

条件に一致する最初の行をPydanticモデルとして取得します。一致しない場合は `None` を返します。
Fetch the first matching row as a Pydantic model, or ``None``.

#### 引数名

| 引数名 | 型 | 説明 |
|---|---|---|
| `model` | `type[M]` | 取得対象のモデルクラス。 |
| `filters` | `str` | 文字列形式のフィルタ条件。 |
| `kwargs` |  | キーワード形式のフィルタ条件。 |

#### 戻り値

**Type:** `Optional[M]`

Optional[M]: 取得されたモデルインスタンス、または None。

::: tip 使用例
```python
    user = db.get(User, id=1)
    user = db.get(User, "age > 30", name="Alice")
    user = db.get(User, email="taro@example.com")
```
:::


---

### `query`

```python
def query(model: type[M], *filters: str, limit: Optional[int] = None, offset: Optional[int] = None, order_by: Optional[str] = None, desc: bool = False, **kwargs: Any) -> list[M]
```

フィルタリング、ソート、ページネーションを使用して行を検索します。

文字列フィルタおよび演算子サフィックス（`__gt`, `__like` など）をサポートしています。
v1.1.4dev1 以降、文字列フィルタは安全のため明示的な単純比較のみサポートします。
Supports string filters and operator suffixes (``__gt``, ``__like``, …).

#### 引数名

| 引数名 | 型 | 説明 |
|---|---|---|
| `model` | `type[M]` | 検索対象のモデルクラス。 |
| `filters` | `str` | 文字列形式のフィルタ条件。 |
| `limit` | `Optional[int]` | 取得する最大行数。 |
| `offset` | `Optional[int]` | 取得を開始するオフセット行数。 |
| `order_by` | `Optional[str]` | ソートに使用するフィールド名。 |
| `desc` | `bool` | 降順でソートするかどうか。デフォルトは False（昇順）。 Whether to order in descending order. Defaults to False (ascending). **kwargs (Any): キーワード形式のフィルタ条件。 |
| `kwargs` |  | キーワード形式のフィルタ条件。 |

#### 戻り値

**Type:** `list[M]`

list[M]: 取得されたモデルインスタンスのリスト。

::: tip 使用例
```python
    db.query(User)                                  # all rows
    db.query(User, age=25)                          # exact match
    db.query(User, "age > 20", limit=10)            # string filters
    db.query(User, age__gte=20, limit=10)           # operator suffixes
    db.query(User, order_by="name", desc=True)      # ordering
    db.query(User, order_by="id", limit=20, offset=40)  # pagination
```
:::


---

### `select`

```python
def select(model: type[BaseModel], fields: list[str], *filters: str, limit: Optional[int] = None, offset: Optional[int] = None, order_by: Optional[str] = None, desc: bool = False, **kwargs: Any) -> list[dict[str, Any]]
```

特定のフィールドのみを辞書のリストとして取得します（部分読み込み）。

大きな行を持つテーブルで、未使用の列をロードするのを避けることができます。

#### 引数名

| 引数名 | 型 | 説明 |
|---|---|---|
| `model` | `type[BaseModel]` | 取得対象のモデルクラス。 |
| `fields` | `list[str]` | 取得するフィールド名のリスト。 |
| `filters` | `str` | 文字列形式のフィルタ条件。 |
| `limit` | `Optional[int]` | 取得する最大行数。 |
| `offset` | `Optional[int]` | オフセット。 |
| `order_by` | `Optional[str]` | ソートに使用するフィールド名。 |
| `desc` | `bool` | 降順にするかどうか。 **kwargs (Any): キーワード形式のフィルタ条件。 |
| `kwargs` |  | キーワード形式のフィルタ条件。 |

#### 戻り値

**Type:** `list[dict[str, Any]]`

list[dict[str, Any]]: 指定されたフィールドを含む辞書のリスト。

::: tip 使用例
```python
    db.select(Article, ["title", "views"], author="neko", order_by="views", desc=True)
    db.select(Article, ["title"], "views > 100")
```
:::


---

### `search`

```python
def search(model: type[M], query: str, *, limit: Optional[int] = None) -> list[M]
```

すべての `Searchable[str]` フィールドに対して全文検索を実行します。
Full-text search on all ``Searchable[str]`` fields.

FTS5の `MATCH` を使用し、BM25アルゴリズムでランク付け（`ORDER BY rank`）されます。
Uses FTS5 ``MATCH`` with BM25 ranking (``ORDER BY rank``).

#### 引数名

| 引数名 | 型 | 説明 |
|---|---|---|
| `model` | `type[M]` | 検索対象のモデルクラス。 |
| `query` | `str` | 検索クエリ文字列。 limit (Optional[int]): 取得する最大行数。 |
| `limit` | `Optional[int]` | 取得する最大行数。 |

#### 戻り値

**Type:** `list[M]`

list[M]: 検索結果に一致するモデルインスタンスのリスト（ランク順）。

::: warning 例外
- SearchNotEnabledError: モデルに `Searchable[str]` フィールドが定義されていない場合に発生します。
- Raised if the model has no Searchable[str] fields.
:::

::: tip 使用例
```python
    db.search(Article, "python sqlite")
    db.search(Article, "python sqlite", limit=5)
```

フィールドを限定した検索には FTS5 のカラム指定構文が使用できます:
For field-scoped search, use FTS5 column filter syntax:
```python
    db.search(Article, "title:python")
```
:::


---

### `count`

```python
def count(model: type[BaseModel], *filters: str, **kwargs: Any) -> int
```

フィルタ条件に一致する行数を返します。

#### 引数名

| 引数名 | 型 | 説明 |
|---|---|---|
| `model` | `type[BaseModel]` | カウント対象のモデルクラス。 |
| `filters` | `str` | 文字列フィルタ。 |
| `kwargs` |  | キーワードフィルタ。 |

#### 戻り値

**Type:** `int`

int: 条件に一致した行数。

::: tip 使用例
```python
    total  = db.count(User)
    adults = db.count(User, "age >= 18")
    adults = db.count(User, age__gte=18)
```
:::


---

### `exists`

```python
def exists(model: type[BaseModel], *filters: str, **kwargs: Any) -> bool
```

フィルタ条件に一致する行が少なくとも1つ存在するかどうかを返します。
Return ``True`` if at least one row matches *filters* and *kwargs*.

#### 引数名

| 引数名 | 型 | 説明 |
|---|---|---|
| `model` | `type[BaseModel]` | 確認対象のモデルクラス。 |
| `filters` | `str` | 文字列フィルタ。 |
| `kwargs` |  | キーワードフィルタ。 |

#### 戻り値

**Type:** `bool`

bool: 存在する場合は True、そうでない場合は False。

::: tip 使用例
```python
    if db.exists(User, email="taro@example.com"):
        ...
```
:::


---

## メンテナンス

### `rebuild_fts`

```python
def rebuild_fts(model: type[BaseModel]) -> None
```

モデルの FTS5 インデックスを再構築します。大量のデータインポート後などに有用です。
Rebuild the FTS5 index for *model* (useful after bulk imports).

#### 引数名

| 引数名 | 型 | 説明 |
|---|---|---|
| `model` | `type[BaseModel]` | インデックスを再構築するモデルクラス。 |



---

### `vacuum`

```python
def vacuum() -> None
```

データベースを VACUUM してディスク領域を解放します。


---

## 生のSQL実行

### `execute_raw`

```python
def execute_raw(sql: str, params: tuple = ()) -> list[dict[str, Any]]
```

任意のSQLを実行し、結果を辞書のリストとして返します。

#### 引数名

| 引数名 | 型 | 説明 |
|---|---|---|
| `sql` | `str` | 実行するSQL文。 |
| `params` | `tuple` | SQL文に渡すパラメータ。 |

#### 戻り値

**Type:** `list[dict[str, Any]]`

list[dict[str, Any]]: 結果行のリスト（各行は辞書）。

::: tip 使用例
```python
    db.execute_raw("SELECT count(*) AS n FROM user WHERE age > ?", (18,))
```
:::


---

