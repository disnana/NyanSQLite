import pytest
import random
import string
import uuid
from nyansqlite import NyanSQLite

def randomname(n) -> str:
    """
    Generate a random string of ASCII letters and digits.

    Useful for creating random identifiers, table names, or other test data
    that requires unique random strings.

    Args:
        n (int): The length of the random string to generate.

    Returns:
        str: A random string of length n containing ASCII letters (a-z, A-Z) and digits (0-9).

    Example:
        >>> random_id = randomname(8)
        >>> len(random_id) == 8
        True
    """
    return ''.join(random.choices(string.ascii_letters + string.digits, k=n))


@pytest.fixture
def base_db(tmp_path):
    """
    Create a temporary NyanSQLite database for testing.

    This fixture provides an isolated database instance for each test using a temporary
    directory. The database file is created with a unique 8-character UUID-based name
    to minimize collision probability. The database is automatically closed after the
    test completes.

    Args:
        tmp_path (pathlib.Path): Pytest's built-in temporary directory path fixture.

    Yields:
        NyanSQLite: A connected database instance ready for testing.

    Example:
        >>> def test_database(db):
        ...     # db is an open NyanSQLite connection
        ...     assert db is not None
    """
    # 8文字のUUIDを使用（これだけでも1〜8文字のランダム英数字より遥かに被らない）
    file_name = f"{uuid.uuid4().hex[:8]}.db"
    db_path = tmp_path / file_name

    # 万が一のための衝突判定（uuidならまずこの中には入らない）
    while db_path.exists():
        file_name = f"{uuid.uuid4().hex[:8]}.db"
        db_path = tmp_path / file_name
    db = NyanSQLite(str(db_path))
    yield db
    db.close()