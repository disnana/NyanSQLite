# NyanSQLite API リファレンス

PydanticネイティブなSQLiteラッパー NyanSQLite クラスのドキュメントです。

## NyanSQLite

```python
class NyanSQLite(path: str = ':memory:', wal: bool = True, strict_deserialization: bool = False)
```

id:      int
            author:  Indexed[str]
            title:   Searchable[str]
            body:    Searchable[str]
            views:   int = 0

#### 引数名

| 引数名 | 型 | 説明 |
|---|---|---|
| `path` | `str` | Database file path (default: in-memory) |
| `wal` | `bool` | Enable WAL mode (default: True) |
| `strict_deserialization` | `bool` | If True, raise ValueError on malformed data. |



---

## コンストラクタ

## コアメソッド

### `close`

```python
def close() -> None
```




---

## 辞書インターフェース

### `update`

```python
def update(model: type[BaseModel], where: dict[str, Any], **fields: Any) -> int
```

#### 引数名

| 引数名 | 型 | 説明 |
|---|---|---|
| `model` | `type[BaseModel]` |  |
| `where` | `dict[str, Any]` | Exact-match conditions that identify the row(s). **fields: ``field=new_value`` pairs to update. |

#### 戻り値

**Type:** `int`



---

### `get`

```python
def get(model: type[M], *filters: str, **kwargs: Any) -> Optional[M]
```

Fetch the first matching row as a Pydantic model, or ``None``.


---

## クエリ

### `query`

```python
def query(model: type[M], *filters: str, limit: Optional[int] = None, offset: Optional[int] = None, order_by: Optional[str] = None, desc: bool = False, **kwargs: Any) -> list[M]
```

Supports string filters and operator suffixes (``__gt``, ``__like``, …).


---

### `count`

```python
def count(model: type[BaseModel], *filters: str, **kwargs: Any) -> int
```

---

### `exists`

```python
def exists(model: type[BaseModel], *filters: str, **kwargs: Any) -> bool
```

Return ``True`` if at least one row matches *filters* and *kwargs*.

::: tip 使用例

```python
        
        
```
:::


---

## ユーティリティ関数

### `vacuum`

```python
def vacuum() -> None
```




---

## その他のメソッド

### `register`

```python
def register(model: type[BaseModel]) -> None
```




---

### `insert`

```python
def insert(obj: M) -> M
```




---

### `insert_many`

```python
def insert_many(objs: list[M]) -> int
```

#### 引数名

| 引数名 | 型 | 説明 |
|---|---|---|
| `objs` | `list[M]` | List of model instances to insert |



---

### `delete`

```python
def delete(model: type[BaseModel], *filters: str, **kwargs: Any) -> int
```

---

### `select`

```python
def select(model: type[BaseModel], fields: list[str], *filters: str, limit: Optional[int] = None, offset: Optional[int] = None, order_by: Optional[str] = None, desc: bool = False, **kwargs: Any) -> list[dict[str, Any]]
```

---

### `search`

```python
def search(model: type[M], query: str, *, limit: Optional[int] = None) -> list[M]
```

Full-text search on all ``Searchable[str]`` fields.

Uses FTS5 ``MATCH`` with BM25 ranking (``ORDER BY rank``).


---

### `rebuild_fts`

```python
def rebuild_fts(model: type[BaseModel]) -> None
```




---

### `execute_raw`

```python
def execute_raw(sql: str, params: tuple = ()) -> list[dict[str, Any]]
```

---

### `registered_models`

```python
def registered_models() -> list[str]
```




---

