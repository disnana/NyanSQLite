# Encryption Guide (Planned)

NyanSQLite 1.1.5 does not include native support for transparent database encryption.

Use Python 3.10+ and `nyansqlite[encryption]` for the application-side example below. On Python 3.9, this extra does not install `cryptography`.

## Current Status

NyanSQLite uses standard SQLite database files (within the scope of APSW's capabilities), and a library-level encryption layer is not currently implemented.

### Security Alternatives

If you need to store sensitive data, consider encrypting the data at the application level before passing it to the model fields.

```python
from cryptography.fernet import Fernet
from pydantic import BaseModel
from nyansqlite import NyanSQLite

cipher = Fernet(Fernet.generate_key())

class SecretData(BaseModel):
    id: int
    encrypted_payload: str

# Encrypt and save data
token = cipher.encrypt(b"my-secret-value").decode()
db.insert(SecretData(id=1, encrypted_payload=token))
```

## Roadmap

Future versions are planned to include transparent encryption features such as:

1. **SQLCipher Support**: Integration with the industry-standard extension for encrypting the SQLite database itself.
2. **Transparent Field Encryption**: Automatic field-level encryption via Pydantic model annotations (e.g., `Encrypted[str]`).

Please let us know on the GitHub repository if you have any feedback or specific requests for encryption methods (AES-GCM, ChaCha20, etc.).
