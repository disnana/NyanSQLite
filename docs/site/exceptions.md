# 例外クラス

NyanSQLite が公開する例外は次のとおりです。

| 例外 | 発生する場面 |
| --- | --- |
| `NyanSQLiteError` | 以下のライブラリ固有例外の基底クラス |
| `ModelNotRegisteredError` | 未登録モデルを操作した |
| `FieldNotFoundError` | モデルにないフィールドを指定した |
| `QueryValidationError` | 検索条件やページング指定が不正 |
| `SearchNotEnabledError` | 全文検索対象のないモデルで `search()` した |
| `TableNameCollisionError` | 異なるモデルが同じテーブル名に対応した |
| `SchemaMismatchError` | 既存テーブルと登録するモデルのスキーマが異なる |

モデルの入力・更新値の検証には Pydantic の `ValidationError` が使われます。SQLite 自体のエラーは APSW または `sqlite3` の例外として届き、`NyanSQLiteError` には包まれません。

```python
from pydantic import ValidationError
from nyansqlite import NyanSQLiteError, SchemaMismatchError

try:
    # モデル登録や操作
    ...
except SchemaMismatchError:
    # 明示的なスキーマ移行が必要
    ...
except ValidationError:
    # モデルの値が不正
    ...
except NyanSQLiteError:
    # その他のライブラリ固有エラー
    ...
```
