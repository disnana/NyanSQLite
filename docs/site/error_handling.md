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

`register()` は既存テーブルの列、型、主キー、NULL 制約、全文検索対象列をモデルと照合します。不一致がある場合は `SchemaMismatchError` を送出し、テーブルやFTS定義を自動変更しません。`db.plan_migration(Model)` で手順を確認し、`db.migrate(Model)` で移行してから再登録してください。詳しくは「スキーマの移行」を参照してください。

`update()` は通常のモデルでは更新フィールドの型・制約を検証します。独自のフィールド／モデルバリデータやモデル設定がある場合は、対象行をトランザクション内で検証してから更新します。検証に失敗すると書き込みは行われません。

`atomic()` ブロック内で例外が発生するとロールバックします。非同期版でも、キャンセルされた実行中の SQLite 呼び出しが終わるまで接続を保護します。

各例外の一覧は[例外クラス](./exceptions)を参照してください。

## スキーマの移行

モデルを変更したら、`register()` の前に `migrate()` で既存テーブルを合わせます。

```python
plan = db.plan_migration(User)   # DBは変更せず、手順だけを返す
print(plan)                      # 人が読める説明
print(plan.sql)                  # 実行されるSQL

db.migrate(User)                 # データを失わない変更だけなら、そのまま実行
db.register(User)
```

| 変更 | 扱い |
| --- | --- |
| カラムの追加(`Optional` または既定値あり) | そのまま実行(`ALTER TABLE ... ADD COLUMN`) |
| NOT NULL → NULL許可 | そのまま実行(テーブルを作り直す) |
| カラムの削除、型の変更、NULL許可 → NOT NULL | `allow_destructive=True` が必要 |
| 既存行がある表への、既定値なしの必須カラム追加 | 実行不可(`MigrationError`)。既定値を付けるか `Optional` にする |
| `Searchable` の変更 | 全文検索の表だけを作り直す。元データは変更しない |

```python
db.migrate(User, allow_destructive=True)   # 削除・型変更を許可
```

- すべての変更は1つのトランザクションで実行され、失敗すると元に戻ります。`atomic()` の中で呼べば、外側の処理と一緒にロールバックします。
- テーブルの作り直しでは、新しいテーブルへ行をコピーし、型が合うことを確認してから入れ替えます。`"abc"` を整数カラムに移すような変換は `MigrationError` になり、元のテーブルは変わりません。
- 既定値は `default=` の値を使います。`default_factory` は行ごとに値が変わるため、既存行には使えません。
- 実行前にバックアップが必要な場合は `VACUUM INTO` を使ってください。
- 非同期版は `await db.migrate(...)` / `await db.plan_migration(...)` です。

### 推測できない変更を指定する

型から読み取れない変更は、利用者が書きます。

**カラム名の変更**は、モデルに `__nyan_renames__ = {"新しい名前": "古い名前"}` を書きます。指定がなければ、古いカラムの削除と新しいカラムの追加として扱われ、中身は引き継がれません。

```python
class User(BaseModel):
    __nyan_renames__ = {"email": "email_address"}
    id: int
    name: str
    email: str
```

**新しいカラムや型を変えるカラムの値**は、`fill=` で指定します。値そのものか、既存の行を受け取る関数を渡せます。関数に渡される行は、カラム名と保存されている値の辞書です。

```python
db.migrate(User, fill={
    "tier": lambda row: "pro" if row["age"] >= 20 else "free",   # 必須の新カラム
    "day": lambda row: int(row["day"].replace("/", "")),          # 型の変更(allow_destructive=True も必要)
})
```

- すでに移行済みのカラムに対する `__nyan_renames__` と `fill=` は無視されます。起動時のコードに残したままでも、再実行できます。
- `fill=` が返した値も、新しい型に収まっているかを確認します。収まらなければ `MigrationError` になり、元に戻ります。
- `fill=` を使った変更も、カラム削除や型変更を伴えば `allow_destructive=True` が必要です。

### 登録のときに自動で移行する

```python
db.register(User)                                   # 既定: 食い違えば SchemaMismatchError
db.register(User, on_mismatch="migrate")            # 安全な変更だけ自動で実行
db.register(User, on_mismatch="migrate", allow_destructive=True)   # 削除・型変更も許可
```

`on_mismatch="migrate"` でも、データが変わる変更には `allow_destructive=True` が必要です。`allow_destructive`、`backup`、`fill` は `migrate()` へそのまま渡されます。

### バックアップ

```python
db.migrate(User, allow_destructive=True, backup=True)          # app.db.bak-<日時> にコピー
db.migrate(User, allow_destructive=True, backup="before.db")   # 場所を指定
```

既定ではバックアップを取りません。SQLite の `VACUUM INTO` を、変更の前に実行します。

- 変更がないとき、または許可が足りずに止まるときは、バックアップを取りません。
- 保存先のファイルがすでにある場合は `MigrationError` になります。
- `:memory:` のデータベースと、`atomic()` の中では使えません。
- 取得したパスは、返り値の `plan.backup_path` で確認できます。
