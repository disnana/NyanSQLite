from typing import Optional

import pytest
from pydantic import BaseModel

from nyansqlite import Indexed, NyanSQLite, Searchable


class User(BaseModel):
    id: Optional[int] = None
    name: Indexed[str]
    age: int

@pytest.fixture
def db(tmp_path):
    db_path = tmp_path / "test.db"
    db = NyanSQLite(str(db_path))
    db.register(User)
    yield db
    db.close()

def test_create_and_read(db):
    """Test creating a record and then reading it."""
    # Create
    db.insert(User(id=1, name='Alice', age=30))
    db.insert(User(id=2, name='Bob', age=24))

    # Read all
    users = db.query(User)
    assert len(users) == 2

    # Check Alice
    alice = next(u for u in users if u.name == 'Alice')
    assert alice.age == 30

    # Check Bob
    bob = next(u for u in users if u.name == 'Bob')
    assert bob.age == 24

    # Read with condition
    user_by_name = db.query(User, name='Alice')
    assert len(user_by_name) == 1
    assert user_by_name[0].name == 'Alice'

    # Get single
    user = db.get(User, id=1)
    assert user is not None
    assert user.name == 'Alice'

def test_update(db):
    """Test updating an existing record."""
    db.insert(User(id=3, name='Charlie', age=35))
    initial_user = db.get(User, name='Charlie')
    assert initial_user is not None
    assert initial_user.age == 35

    # Update
    db.update(User, where={'name': 'Charlie'}, age=36)
    updated_user = db.get(User, name='Charlie')
    assert updated_user is not None
    assert updated_user.age == 36

def test_delete(db):
    """Test deleting a record."""
    db.insert(User(id=4, name='David', age=40))
    assert db.count(User) == 1

    # Delete
    db.delete(User, name='David')
    assert db.count(User) == 0

def test_read_empty(db):
    """Test reading from an empty table."""
    users = db.query(User)
    assert len(users) == 0

def test_exists(db):
    """Test exists check."""
    assert not db.exists(User, name='Eve')
    db.insert(User(id=5, name='Eve', age=20))
    assert db.exists(User, name='Eve')

def test_complex_query(db):
    """Test query with operators."""
    db.insert(User(id=10, name='Taro', age=20))
    db.insert(User(id=11, name='Jiro', age=30))
    db.insert(User(id=12, name='Saburo', age=40))

    # age >= 30
    results = db.query(User, age__gte=30)
    assert len(results) == 2

    # age < 30
    results = db.query(User, age__lt=30)
    assert len(results) == 1
    assert results[0].name == 'Taro'

def test_insert_many(db):
    """Test bulk insertion."""
    users = [
        User(id=20, name='User20', age=20),
        User(id=21, name='User21', age=21),
        User(id=22, name='User22', age=22),
    ]
    count = db.insert_many(users)
    assert count == 3
    assert db.count(User) == 3

    # Verify data
    results = db.query(User, order_by="id")
    assert results[0].name == 'User20'
    assert results[1].name == 'User21'
    assert results[2].name == 'User22'

def test_insert_many_empty(db):
    """Test bulk insertion with empty list."""
    count = db.insert_many([])
    assert count == 0
    assert db.count(User) == 0

def test_search_and_rebuild(db):
    """Test FTS5 search and rebuild_fts."""
    class Article(BaseModel):
        id: Optional[int] = None
        title: Searchable[str]
        content: Searchable[str]

    db.register(Article)

    articles = [
        Article(id=1, title="Python Guide", content="Learn Python basics"),
        Article(id=2, title="SQLite Tips", content="Advanced SQLite techniques"),
        Article(id=3, title="Coding", content="Write clean code"),
    ]
    db.insert_many(articles)

    # Search
    results = db.search(Article, "Python")
    assert len(results) == 1
    assert results[0].title == "Python Guide"

    # Rebuild FTS (no error should occur)
    db.rebuild_fts(Article)

    # Search again
    results = db.search(Article, "SQLite")
    assert len(results) == 1
    assert results[0].title == "SQLite Tips"
