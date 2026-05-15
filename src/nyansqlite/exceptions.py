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