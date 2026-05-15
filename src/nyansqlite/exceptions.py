class NyanSQLiteError(Exception):
    """NyanSQLiteのベース例外クラス"""
    pass

class FieldNotFoundError(NyanSQLiteError):
    """モデルに存在しないフィールドが指定された場合にスローされます"""
    pass

class ModelNotRegisteredError(NyanSQLiteError):
    """db.register() されていないモデルを操作しようとした場合にスローされます"""
    pass

class SearchNotEnabledError(NyanSQLiteError):
    """Searchable[str] が定義されていないモデルで search() を実行した場合にスローされます"""
    pass

class TableNameCollisionError(NyanSQLiteError):
    """異なる2つのモデルが同じテーブル名にマッピングされた場合にスローされます.

    CamelCase の正規化により、意図しないテーブル名の衝突が生じるケースを防ぎます。
    例: UserAuth と User_Auth は両方とも user_auth になる"""
    pass


