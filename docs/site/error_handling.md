# エラーハンドリング

NyanSQLite 固有の例外は `NyanSQLiteError` を継承します。Pydantic の入力検証エラーは `pydantic.ValidationError`、SQLite 自体のエラーは使用中のバックエンドの例外として通知されます。

```python
from pydantic import BaseModel, ValidationError
from nyansqlite import NyanSQLite, QueryValidationError, SchemaMismatchError

class User(BaseModel):
    id: int
    age: int

with NyanSQLite("app.db") as db:
    try:
        db.register(User)
        db.update(User, where={"id": 1}, age="invalid")
    except SchemaMismatchError as exc:
        print(f"既存テーブルとモデルが一致しません: {exc}")
    except ValidationError as exc:
        print(f"更新値がモデルに適合しません: {exc}")
    except QueryValidationError as exc:
        print(f"検索条件が不正です: {exc}")
```

`register()` は既存テーブルの列、型、主キー、NULL 制約、全文検索対象列をモデルと照合します。不一致がある場合は `SchemaMismatchError` を送出し、テーブルやFTS定義を自動変更しません。データをバックアップし、明示的に移行してから再登録してください。

`update()` は通常のモデルでは更新フィールドの型・制約を検証します。独自のフィールド／モデルバリデータやモデル設定がある場合は、対象行をトランザクション内で検証してから更新します。検証に失敗すると書き込みは行われません。

`atomic()` ブロック内で例外が発生するとロールバックします。非同期版でも、キャンセルされた実行中の SQLite 呼び出しが終わるまで接続を保護します。

各例外の一覧は[例外クラス](./exceptions)を参照してください。
