import os
import unittest
from pydantic import BaseModel
from nyansqlite import NyanSQLite, Indexed

class User(BaseModel):
    id: int | None = None
    name: Indexed[str]
    age: int

class TestCRUD(unittest.TestCase):
    def setUp(self):
        """Set up a temporary database for testing."""
        self.db_name = 'test_crud.db'
        self.db = NyanSQLite(self.db_name)
        # Register the model to create the table automatically
        self.db.register(User)

    def tearDown(self):
        """Close and delete the temporary database after testing."""
        self.db.close()
        if os.path.exists(self.db_name):
            try:
                os.remove(self.db_name)
            except PermissionError:
                pass

    def test_create_and_read(self):
        """Test creating a record and then reading it."""
        # Create
        self.db.insert(User(id=1, name='Alice', age=30))
        self.db.insert(User(id=2, name='Bob', age=24))

        # Read all
        users = self.db.query(User)
        self.assertEqual(len(users), 2)
        
        # Check Alice
        alice = next(u for u in users if u.name == 'Alice')
        self.assertEqual(alice.age, 30)
        
        # Check Bob
        bob = next(u for u in users if u.name == 'Bob')
        self.assertEqual(bob.age, 24)

        # Read with condition
        user_by_name = self.db.query(User, name='Alice')
        self.assertEqual(len(user_by_name), 1)
        self.assertEqual(user_by_name[0].name, 'Alice')
        
        # Get single
        user = self.db.get(User, id=1)
        self.assertIsNotNone(user)
        self.assertEqual(user.name, 'Alice')

    def test_update(self):
        """Test updating an existing record."""
        self.db.insert(User(id=3, name='Charlie', age=35))
        initial_user = self.db.get(User, name='Charlie')
        self.assertIsNotNone(initial_user)
        self.assertEqual(initial_user.age, 35)

        # Update
        self.db.update(User, where={'name': 'Charlie'}, age=36)
        updated_user = self.db.get(User, name='Charlie')
        self.assertIsNotNone(updated_user)
        self.assertEqual(updated_user.age, 36)

    def test_delete(self):
        """Test deleting a record."""
        self.db.insert(User(id=4, name='David', age=40))
        self.assertEqual(self.db.count(User), 1)

        # Delete
        self.db.delete(User, name='David')
        self.assertEqual(self.db.count(User), 0)

    def test_read_empty(self):
        """Test reading from an empty table."""
        users = self.db.query(User)
        self.assertEqual(len(users), 0)

    def test_exists(self):
        """Test exists check."""
        self.assertFalse(self.db.exists(User, name='Eve'))
        self.db.insert(User(id=5, name='Eve', age=20))
        self.assertTrue(self.db.exists(User, name='Eve'))

    def test_complex_query(self):
        """Test query with operators."""
        self.db.insert(User(id=10, name='Taro', age=20))
        self.db.insert(User(id=11, name='Jiro', age=30))
        self.db.insert(User(id=12, name='Saburo', age=40))

        # age >= 30
        results = self.db.query(User, age__gte=30)
        self.assertEqual(len(results), 2)
        
        # age < 30
        results = self.db.query(User, age__lt=30)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].name, 'Taro')

if __name__ == '__main__':
    unittest.main()
