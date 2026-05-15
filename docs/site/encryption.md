# 暗号化ガイド（計画中）

現在、NyanSQLite v1.0.x 系では、透過的なデータベース暗号化のネイティブサポートは含まれていません。

## 現在の状況

NyanSQLiteは標準の SQLite データベースファイル（または APSW の機能範囲内）を使用しており、ライブラリレベルでの暗号化レイヤーは現在実装されていません。

### セキュリティの代替案

機密データを保存する必要がある場合は、アプリケーション側でデータを暗号化した後、その値をモデルのフィールドに渡すことを検討してください。

```python
from cryptography.fernet import Fernet
from pydantic import BaseModel
from nyansqlite import NyanSQLite

cipher = Fernet(Fernet.generate_key())

class SecretData(BaseModel):
    id: int
    encrypted_payload: str

# データを暗号化して保存
token = cipher.encrypt(b"my-secret-value").decode()
db.insert(SecretData(id=1, encrypted_payload=token))
```

## ロードマップ

将来のバージョンでは、以下のような透過的暗号化機能の導入を検討しています：

1. **SQLCipher のサポート**: SQLite 自体を暗号化する業界標準の拡張機能との統合。
2. **透過的フィールド暗号化**: Pydantic モデルのアノテーション（例: `Encrypted[str]`）による自動的なフィールドレベルの暗号化。

暗号化機能に関する進捗や特定の暗号化方式（AES-GCM, ChaCha20等）の要望がある場合は、GitHubのリポジトリにてお知らせください。
