import asyncio
from typing import Optional

import pytest
from pydantic import BaseModel

from conftest import randomname
from nyansqlite import Indexed, Searchable


class User(BaseModel):
    id: Optional[int] = None
    name: Indexed[str]
    age: int

# このファイル内でのみ有効な db フィクスチャを定義
@pytest.fixture
async def db(base_db_aio):
    """ベースの非同期DBインスタンスにUserを登録して提供する"""
    await base_db_aio.register(User)
    return base_db_aio

@pytest.mark.asyncio
async def test_create_and_read(db):
    """Test creating a record and then reading it."""
    # Create
    await db.insert(User(id=1, name='Alice', age=30))
    await db.insert(User(id=2, name='Bob', age=24))

    # Read all
    users = await db.query(User)
    assert len(users) == 2

    # Check Alice
    alice = next(u for u in users if u.name == 'Alice')
    assert alice.age == 30

    # Check Bob
    bob = next(u for u in users if u.name == 'Bob')
    assert bob.age == 24

    # Read with condition
    user_by_name = await db.query(User, name='Alice')
    assert len(user_by_name) == 1
    assert user_by_name[0].name == 'Alice'

    # Get single
    user = await db.get(User, id=1)
    assert user is not None
    assert user.name == 'Alice'

@pytest.mark.asyncio
async def test_update(db):
    """Test updating an existing record."""
    await db.insert(User(id=3, name='Charlie', age=35))
    initial_user = await db.get(User, name='Charlie')
    assert initial_user is not None
    assert initial_user.age == 35

    # Update
    await db.update(User, where={'name': 'Charlie'}, age=36)
    updated_user = await db.get(User, name='Charlie')
    assert updated_user is not None
    assert updated_user.age == 36

@pytest.mark.asyncio
async def test_delete(db):
    """Test deleting a record."""
    await db.insert(User(id=4, name='David', age=40))
    assert await db.count(User) == 1

    # Delete
    await db.delete(User, name='David')
    assert await db.count(User) == 0

@pytest.mark.asyncio
async def test_read_empty(db):
    """Test reading from an empty table."""
    users = await db.query(User)
    assert len(users) == 0

@pytest.mark.asyncio
async def test_exists(db):
    """Test exists check."""
    assert not await db.exists(User, name='Eve')
    await db.insert(User(id=5, name='Eve', age=20))
    assert await db.exists(User, name='Eve')

@pytest.mark.asyncio
async def test_complex_query(db):
    """Test query with operators."""
    await db.insert(User(id=10, name='Taro', age=20))
    await db.insert(User(id=11, name='Jiro', age=30))
    await db.insert(User(id=12, name='Saburo', age=40))

    # age >= 30
    results = await db.query(User, age__gte=30)
    assert len(results) == 2

    # age < 30
    results = await db.query(User, age__lt=30)
    assert len(results) == 1
    assert results[0].name == 'Taro'

    # age != 30
    results = await db.query(User, age__ne=30)
    assert len(results) == 2
    assert {r.name for r in results} == {'Taro', 'Saburo'}

    # age >= 20, age <= 30
    results = await db.query(User, age__gte=20, age__lte=30)
    assert len(results) == 2

    # is_null
    await db.insert(User(id=13, name='NullAge', age=0)) # age is int, so it can't be null in this schema usually, but let's test the syntax
    # Actually, User.age is int, pydantic might complain if it's None.
    # Let's use a model with Optional field for null test.

@pytest.mark.asyncio
async def test_null_queries(db):
    class Note(BaseModel):
        id: Optional[int] = None
        content: Optional[str] = None

    await db.register(Note)
    await db.insert(Note(id=1, content="hello"))
    await db.insert(Note(id=2, content=None))

    assert await db.count(Note, content__is_null=True) == 1
    assert await db.count(Note, content__is_null=False) == 1
    assert (await db.get(Note, content__is_null=True)).id == 2

@pytest.mark.asyncio
async def test_string_filters(db):
    """Test string format filters like 'age > 10'."""
    await db.insert(User(id=30, name='Filter1', age=10))
    await db.insert(User(id=31, name='Filter2', age=20))
    await db.insert(User(id=32, name='Filter3', age=30))

    # This is what we want to support
    results = await db.query(User, "age > 15")
    assert len(results) == 2
    assert {r.id for r in results} == {31, 32}

    results = await db.query(User, "age <= 20", "id > 30")
    assert len(results) == 1
    assert results[0].id == 31

    # Test with quotes
    await db.insert(User(id=33, name='Special One', age=50))
    assert await db.count(User, "name = 'Special One'") == 1
    assert await db.count(User, 'name = "Special One"') == 1

    # Test select with string filters
    names = await db.select(User, ["name"], "age > 40")
    assert len(names) == 1
    assert names[0]["name"] == "Special One"

@pytest.mark.asyncio
async def test_insert_many(db):
    """Test bulk insertion."""
    users = [
        User(id=20, name='User20', age=20),
        User(id=21, name='User21', age=21),
        User(id=22, name='User22', age=22),
    ]
    count = await db.insert_many(users)
    assert count == 3
    assert await db.count(User) == 3

    # Verify data
    results = await db.query(User, order_by="id")
    assert results[0].name == 'User20'
    assert results[1].name == 'User21'
    assert results[2].name == 'User22'

@pytest.mark.asyncio
async def test_insert_many_empty(db):
    """Test bulk insertion with empty list."""
    count = await db.insert_many([])
    assert count == 0
    assert await db.count(User) == 0

@pytest.mark.asyncio
async def test_search_and_rebuild(db):
    """Test FTS5 search and rebuild_fts."""
    class Article(BaseModel):
        id: Optional[int] = None
        title: Searchable[str]
        content: Searchable[str]

    await db.register(Article)

    articles = [
        Article(id=1, title="Python Guide", content="Learn Python basics"),
        Article(id=2, title="SQLite Tips", content="Advanced SQLite techniques"),
        Article(id=3, title="Coding", content="Write clean code"),
    ]
    await db.insert_many(articles)

    # Search
    results = await db.search(Article, "Python")
    assert len(results) == 1
    assert results[0].title == "Python Guide"

    # Rebuild FTS (no error should occur)
    await db.rebuild_fts(Article)

    # Search again
    results = await db.search(Article, "SQLite")
    assert len(results) == 1
    assert results[0].title == "SQLite Tips"


@pytest.mark.asyncio
async def test_concurrent_inserts(db):
    """大量の非同期タスクから同時に新規レコードを挿入しても、データの欠損やクラッシュが起きないか検証"""
    total_inserts = 200

    # 非同期タスクで実行する挿入タスク
    async def insert_task(i):
        # NyanSQLiteAIOの仕様に合わせて、i をそのままユニークな数値IDとして使う
        # name 側にランダム文字列を仕込む
        unique_id = i + 1000  # 他のテストデータと被らないようにオフセット
        unique_name = f"Name_{i}_{randomname(4)}"

        # insert を使用
        await db.insert(User(id=unique_id, name=unique_name, age=20 + (i % 50)))
        return unique_id

    # 200個の非同期タスクで並行して挿入を実行
    insert_tasks = [insert_task(i) for i in range(total_inserts)]
    inserted_ids = await asyncio.gather(*insert_tasks)

    # 【検証1】すべてのタスクが例外を出さずに正常終了したか
    assert len(inserted_ids) == total_inserts

    # 【検証2】保存したデータがすべてDBから正しく引けるか
    for user_id in inserted_ids:
        user = await db.get(User, id=user_id)  # getの引数仕様も id=user_id に修正
        assert user is not None
        assert user.id == user_id


@pytest.mark.asyncio
async def test_atomic_transaction(db):
    """Test db.atomic() context manager."""
    # Successful commit
    async with db.atomic():
        await db.insert(User(id=100, name='Alice_Atomic', age=30))
        await db.insert(User(id=101, name='Bob_Atomic', age=30))
    assert await db.count(User, age=30) == 2

    # Rollback on exception
    try:
        async with db.atomic():
            await db.insert(User(id=102, name='Rollback', age=40))
            raise ValueError("Intentional error")
    except ValueError:
        pass
    assert not await db.exists(User, name='Rollback')

@pytest.mark.asyncio
async def test_nested_atomic(db):
    """Test nested db.atomic() calls."""
    async with db.atomic():
        await db.insert(User(id=200, name='Outer', age=50))
        async with db.atomic():
            await db.insert(User(id=201, name='Inner', age=50))
        assert await db.count(User, age=50) == 2
    assert await db.count(User, age=50) == 2

    # Nested rollback
    try:
        async with db.atomic():
            await db.insert(User(id=202, name='Outer_Fail', age=60))
            async with db.atomic():
                await db.insert(User(id=203, name='Inner_Fail', age=60))
                raise ValueError("Nested error")
    except ValueError:
        pass

    assert await db.count(User, age=60) == 0

@pytest.mark.asyncio
async def test_context_manager_close():
    """Test NyanSQLiteAIO as a context manager (automatic close)."""
    from pathlib import Path
    db_path = Path("test_cm_aio.sqlite")
    # Ensure file is gone
    if db_path.exists():
        db_path.unlink()

    from nyansqlite import NyanSQLiteAIO
    async with NyanSQLiteAIO(str(db_path)) as db:
        await db.register(User)
        await db.insert(User(id=1, name='Alice', age=30))
    # Connection should be closed here
    # Check if we can still use it (it should fail)
    with pytest.raises(Exception):
        await db.count(User)
    if db_path.exists():
        # Cleanup
        try:
            db_path.unlink()
        except PermissionError:
            pass
