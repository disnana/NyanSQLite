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

## 保存と検索の一貫性

`insert()` と `insert_many()` は保存前に値を検証します。生成後に代入した値も対象で、不正な値があれば書き込みを行いません。単純な型は軽量に確認し、制約や独自バリデータのあるモデルはPydanticで検証します。元のインスタンスは変更しません。

`update()` はバリデータが正規化した結果を保存します。モデルバリデータが関連フィールドを変更した場合は、その変更も同じトランザクションで保存します。複数行の途中で検証や一意制約に失敗した場合、その更新全体を取り消します。

入力alias（`Field(alias=...)`、`AliasChoices`、`AliasPath`）は復元時にも扱えます。DB列の名前と検索条件はモデルのフィールド名です。`ClassVar`やプライベート属性は保存対象になりません。

`Field(exclude=True)` はPydanticの出力から除外する指定です。DBへの保存を禁止する指定ではなく、単体・一括挿入ともモデルの全フィールドを保存します。機密情報を保存したくない場合は、保存用モデルからそのフィールドを外してください。

検索では、型が不正な値は `QueryValidationError` になります。`__is_null` はboolだけを受け付け、`field=None` と `field__eq=None` はNULL、`field__ne=None` は非NULLを検索します。数値文字列などPydanticが変換できる値は型を揃えて検索します。検索の境界値には保存用の範囲制約を適用しないため、例えば非負の列に対する `age__gt=-1` も使えます。

## 引数名と同じフィールドを検索する

`query()` と `select()` の `limit`、`offset`、`order_by`、`desc` などと同名のフィールドは `where` 辞書で指定できます。`get()`、`count()`、`exists()`、`delete()` でも同じ辞書を使えます。キーワード条件との重複はエラーになります。

```python
rows = db.query(Job, where={"limit": 10, "where": "ready"}, limit=20)
row = db.get(Job, where={"limit": 10})
```

`select(Model, [])` は `QueryValidationError` です。少なくとも1つのフィールドを指定してください。

既存DBのインデックスが宣言と異なる場合（通常インデックスから `UniqueIndexed` への変更など）、`register()` は `SchemaMismatchError` を送出します。データをバックアップし、明示的に移行してください。テーブル名はモデルの `__tablename__` で指定できます。

以前の版で通常のEnumが `"Role.ADMIN"` のような文字列としてJSON保存されたデータは、自動では書き換えません。Enumの値（例: `"admin"`）へ明示的に移行してください。
