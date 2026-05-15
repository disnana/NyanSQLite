# バリデーションガイド

NyanSQLiteは、Pydantic v2の強力なバリデーション機能をそのまま活用できます。

## どんなときに使うか

バリデーションは次のようなケースで役立ちます。

- 不正なレコードを保存前に弾きたい
- データベース内のデータ型を一貫させたい
- 文字列として渡されたデータを自動的に適切な型（int, datetime等）に変換したい

## Pydanticによる自動バリデーション

NyanSQLiteは `BaseModel` を継承したクラスを `register()` することで、挿入時や更新時に Pydantic のバリデーションを自動的に実行します。

```python
from pydantic import BaseModel, Field, EmailStr
from nyansqlite import NyanSQLite

class User(BaseModel):
    id: int
    name: str = Field(min_length=2)
    email: str # EmailStr を使うには pydantic[email] が必要
    age: int = Field(ge=0, le=150)

db = NyanSQLite("users.db")
db.register(User)

# OK
db.insert(User(id=1, name="Alice", email="alice@example.com", age=30))

# バリデーション失敗 (Pydantic の ValidationError が発生)
try:
    db.insert(User(id=2, name="A", email="invalid", age=-1))
except Exception as e:
    print(f"バリデーション失敗: {e}")
```

## `update()` 時のバリデーション

`update()` メソッドを使用する場合、更新対象のフィールド値も Pydantic モデルの定義に基づいてチェックされます。

```python
# 年齢を不正な値に更新しようとする
try:
    db.update(User, where={"id": 1}, age=200) # Field(le=150) に違反
except Exception as e:
    print(f"更新失敗: {e}")
```

## 複雑な型のバリデーション

Pydantic の機能をフルに活用して、リストや辞書、列挙型（Enum）なども安全に保存できます。

```python
from typing import List, Dict
from enum import Enum

class Role(Enum):
    ADMIN = "admin"
    USER = "user"

class Profile(BaseModel):
    id: int
    roles: List[Role]
    metadata: Dict[str, str]

db.register(Profile)

# 自動的に JSON シリアライズされ、取得時には元の型に戻ります
db.insert(Profile(
    id=1, 
    roles=[Role.ADMIN], 
    metadata={"login": "2024-01-01"}
))
```

## 厳格なデシリアライズ（`strict_deserialization`）

データベースからデータを読み込む際、破損したデータ（不正なJSONなど）があった場合の挙動を `NyanSQLite` のコンストラクタで制御できます。

- `strict_deserialization=False`（デフォルト）: 警告を出して生データを返します。
- `strict_deserialization=True`: `ValueError` を発生させます。

```python
db = NyanSQLite("app.db", strict_deserialization=True)
```

## 関連リファレンス

- [NyanSQLite API リファレンス](../api/NyanSQLite.md)
- [Pydantic 公式ドキュメント](https://docs.pydantic.dev/)
