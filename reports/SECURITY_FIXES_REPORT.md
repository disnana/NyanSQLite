# 🔒 セキュリティ脆弱性修正レポート
## NyanSQLite Security Remediation Report (v1.0)

**修正日時**: 2026-05-15  
**修正対象**: 3つの主要なセキュリティ脆弱性  
**ステータス**: ✅ すべて実装完了

---

## 📋 修正内容の詳細

### FINDING-001: スレッドセーフティの欠如 (CWE-362)

**深刻度**: HIGH  
**ステータス**: ✅ 修正完了

#### 問題
- `NyanSQLite.__init__` で `self._lock = threading.Lock()` が初期化されていたが、**読取操作**（`query`, `select`, `search`, `count`, `exists`, `rebuild_fts`）でロックが使用されていなかった
- SQLiteはスレッドセーフではないため、複数スレッドからの同時アクセスで競合状態が発生する可能性があった

#### 修正内容
✅ すべての読取操作にスレッドロック（`with self._lock:`）を追加しました。

**修正対象関数**:
1. **`query()` (lines 361-396)** - WHERE句・ORDER BY・LIMIT付きの全行検索
2. **`select()` (lines 410-445)** - 部分読取（指定フィールドのみ）
3. **`search()` (lines 461-479)** - FTS5フル・テキストサーチ
4. **`count()` (lines 489-498)** - 行数集計
5. **`exists()` (lines 504-515)** - 存在確認
6. **`rebuild_fts()` (lines 525-531)** - FTS5インデックス再構築

#### コード例
```python
# Before (ロックなし)
def query(self, model, ...):
    rows = self._conn.execute(sql, tuple(values))
    return [self._from_row(model, meta, r) for r in rows]

# After (ロック追加)
def query(self, model, ...):
    with self._lock:
        rows = self._conn.execute(sql, tuple(values))
        return [self._from_row(model, meta, r) for r in rows]
```

**検証状況**:
- 書込操作（`insert`, `insert_many`, `update`, `delete`）: ✅ 既にロック実装済み
- 登録操作（`register`）: ✅ 既にロック実装済み
- 読取操作: ✅ すべてロック追加完了

---

### FINDING-002: デシリアライズ層での例外ハンドリング欠落 (CWE-755)

**深刻度**: MEDIUM  
**ステータス**: ✅ 修正完了

#### 問題
- `deserialize_value()` 関数内で以下の処理が例外ハンドリングなしで実行されていた：
  - `json.loads()` (line 114) → JSONDecodeError
  - `datetime.fromisoformat()` (line 117) → ValueError
  - `date.fromisoformat()` (line 119) → ValueError
- DB内の破損したデータ（不正なJSON、ISO8601外の日付形式）により、テーブル全体のクエリが失敗 → **DoS状態**

#### 修正内容
✅ すべてのデシリアライズ処理に **try-except + 警告ログ + フォールバック** を実装しました。

**修正対象**: `_types.py` の `deserialize_value()` (lines 103-156)

#### コード例
```python
# Before (例外処理なし)
if isinstance(value, str):
    return json.loads(value)  # JSONDecodeError が発生するとクラッシュ

# After (例外処理で安全化)
if isinstance(value, str):
    try:
        return json.loads(value)
    except (json.JSONDecodeError, ValueError) as e:
        import warnings
        warnings.warn(
            f"Malformed JSON data: {value!r}. Returning as raw string. Error: {e}",
            category=RuntimeWarning,
            stacklevel=2
        )
        return value  # フォールバック: 生の文字列を返す
```

**フォールバック戦略**:
- **JSON**: JSONDecodeError → 生の文字列を返す（警告ログ出力）
- **datetime**: ValueError → 生の値を返す（警告ログ出力）
- **date**: ValueError → 生の値を返す（警告ログ出力）

**利点**:
- ✅ テーブル全体がクラッシュしない
- ✅ 破損レコードを警告とともにスキップ可能
- ✅ アプリケーションの可用性向上

---

### FINDING-003: テーブル名の暗黙的衝突 (CWE-670)

**深刻度**: MEDIUM  
**ステータス**: ✅ 修正完了

#### 問題
- `model_to_table_name()` の正規化ロジック：
  ```python
  return re.sub(r"(?<!^)(?=[A-Z])", "_", model.__name__).lower()
  ```
- 異なるモデル名が同じテーブル名にマッピングされる：
  - `UserAuth` → `user_auth`
  - `User_Auth` → `user_auth`  ← **衝突！**
- スキーマ上書き、データ破損、意図しないDDL実行の可能性

#### 修正内容
✅ `register()` メソッドに**テーブル名衝突検知ロジック**を実装しました。

**修正対象**: 
1. `core.py` の `register()` (lines 204-243)
2. 新規例外クラス: `TableNameCollisionError` (`exceptions.py`)
3. __init__.py にエクスポート追加

#### コード例
```python
# Before (衝突検知なし)
def register(self, model):
    table = model_to_table_name(model)
    # ...処理続行

# After (衝突検知あり)
def register(self, model):
    table = model_to_table_name(model)
    
    # 既存モデルとの衝突チェック
    for existing_model, meta in self._registry.items():
        if meta.table == table and existing_model is not model:
            raise TableNameCollisionError(
                f"Table name collision detected: "
                f"{existing_model.__name__} → '{table}' but also "
                f"{model.__name__} → '{table}'. "
                f"This can happen with CamelCase variants..."
            )
    # ...処理続行
```

**新規例外クラス**:
```python
class TableNameCollisionError(NyanSQLiteError):
    """異なる2つのモデルが同じテーブル名にマッピングされた場合にスローされます.
    
    CamelCase の正規化により、意図しないテーブル名の衝突が生じるケースを防ぎます。
    例: UserAuth と User_Auth は両方とも user_auth になる"""
    pass
```

**検証ポイント**:
- ✅ 衝突検知により、登録時に早期に問題を検出
- ✅ メッセージでユーザーに原因と解決方法を提示
- ✅ 同一モデルの再登録は許可（`existing_model is not model` チェック）

---

## 📊 修正ファイル一覧

| ファイル | 行番号 | 修正内容 |
|---------|--------|---------|
| `src/nyansqlite/core.py` | 361-396 | `query()` にロック追加 |
| `src/nyansqlite/core.py` | 410-445 | `select()` にロック追加 |
| `src/nyansqlite/core.py` | 461-479 | `search()` にロック追加 |
| `src/nyansqlite/core.py` | 489-498 | `count()` にロック追加 |
| `src/nyansqlite/core.py` | 504-515 | `exists()` にロック追加 |
| `src/nyansqlite/core.py` | 525-531 | `rebuild_fts()` にロック追加 |
| `src/nyansqlite/core.py` | 204-243 | `register()` に衝突検知ロジック追加 |
| `src/nyansqlite/core.py` | 19-23 | `TableNameCollisionError` をインポート |
| `src/nyansqlite/_types.py` | 103-156 | `deserialize_value()` に例外ハンドリング追加 |
| `src/nyansqlite/exceptions.py` | 17-22 | `TableNameCollisionError` クラス新規追加 |
| `src/nyansqlite/__init__.py` | 1-20 | `TableNameCollisionError` をエクスポート |

---

## ✅ 検証結果

### 静的解析
- **構文エラー**: 0個
- **重大エラー**: 0個
- **警告**: Pylintコード品質チェック（docstring等）のみ

### 実装の確認事項
✅ すべての読取操作がロックを使用するよう修正  
✅ すべてのデシリアライズ処理が例外ハンドリングを実装  
✅ テーブル名衝突時の検知・エラー報告が実装  
✅ 新規例外クラスが適切に定義・エクスポート  

---

## 🛡️ 追加調査推奨箇所

### 1. トランザクション管理のロールバック保証
**対象**: `NyanConnection.transaction()` / `insert_many()`
- 現在: ✅ `with self._conn.transaction():` でコンテキストマネージャを使用
- 推奨: コンテキストマネージャ内での Python例外発生時の ROLLBACK 動作確認

### 2. 複合プライマリキーのサポート
**対象**: `get_primary_key()` 
- 現在: 単一PK（`id` フィールド）のみサポート
- 推奨: 複合PKサポート時の実装検討

---

## 📝 テスト推奨項目

```python
# FINDING-001: スレッドセーフティテスト
import threading

db = NyanSQLite("test.db")
db.register(Article)

# 複数スレッドからの同時read
def read_task():
    db.query(Article)

threads = [threading.Thread(target=read_task) for _ in range(10)]
for t in threads: t.start()
for t in threads: t.join()  # 競合状態がないこと

# FINDING-002: デシリアライズ例外テスト
# DBに直接不正なJSONを挿入
db.execute_raw("UPDATE article SET metadata = '{invalid}'", ())
articles = db.query(Article)  # RuntimeWarning が出るが、エラーにはならない

# FINDING-003: テーブル名衝突テスト
from nyansqlite import TableNameCollisionError

class UserAuth(BaseModel):
    id: int

class User_Auth(BaseModel):
    id: int

db.register(UserAuth)
try:
    db.register(User_Auth)  # TableNameCollisionError が発生
except TableNameCollisionError as e:
    print(f"Caught collision: {e}")
```

---

**修正完了日**: 2026-05-15  
**実装者**: GitHub Copilot  
**対象バージョン**: v1.0.0  
**次回レビュー推奨**: セキュリティテストスイートの実装後

