import unittest
import os
from nyansqlite import NyanSQLite # Assuming NyanSQLite is the main class/module

class TestCRUD(unittest.TestCase):
    def setUp(self):
        """Set up a temporary database for testing."""
        self.db_name = 'test_crud.db'
        self.db = NyanSQLite(self.db_name)
        self.db.connect()
        self.db.execute("CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, name TEXT, age INTEGER)")

    def tearDown(self):
        """Close and delete the temporary database after testing."""
        self.db.close()
        if os.path.exists(self.db_name):
            os.remove(self.db_name)

    def test_create_and_read(self):
        """Test creating a record and then reading it."""
        # Create
        self.db.insert('users', {'name': 'Alice', 'age': 30})
        self.db.insert('users', {'name': 'Bob', 'age': 24})

        # Read
        users = self.db.select('users')
        self.assertEqual(len(users), 2)
        self.assertEqual(users[0]['name'], 'Alice')
        self.assertEqual(users[0]['age'], 30)
        self.assertEqual(users[1]['name'], 'Bob')
        self.assertEqual(users[1]['age'], 24)

        user_by_name = self.db.select('users', conditions={'name': 'Alice'})
        self.assertEqual(len(user_by_name), 1)
        self.assertEqual(user_by_name[0]['name'], 'Alice')

    def test_update(self):
        """Test updating an existing record."""
        self.db.insert('users', {'name': 'Charlie', 'age': 35})
        initial_user = self.db.select('users', conditions={'name': 'Charlie'})[0]
        self.assertEqual(initial_user['age'], 35)

        # Update
        self.db.update('users', {'age': 36}, conditions={'name': 'Charlie'})
        updated_user = self.db.select('users', conditions={'name': 'Charlie'})[0]
        self.assertEqual(updated_user['age'], 36)

    def test_delete(self):
        """Test deleting a record."""
        self.db.insert('users', {'name': 'David', 'age': 40})
        users_before_delete = self.db.select('users')
        self.assertEqual(len(users_before_delete), 1)

        # Delete
        self.db.delete('users', conditions={'name': 'David'})
        users_after_delete = self.db.select('users')
        self.assertEqual(len(users_after_delete), 0)

    def test_read_empty(self):
        """Test reading from an empty table."""
        users = self.db.select('users')
        self.assertEqual(len(users), 0)

if __name__ == '__main__':
    unittest.main()
