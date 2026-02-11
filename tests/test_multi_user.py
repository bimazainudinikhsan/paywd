import sys
import os
import json
import unittest
import shutil

# Add src to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))

from main import WDBot

class TestMultiUser(unittest.TestCase):
    def setUp(self):
        self.bot = WDBot()
        self.test_creds_path = 'config/credentials_test.json'
        self.bot.credentials_path = self.test_creds_path
        
        # Clean up start
        if os.path.exists(self.test_creds_path):
            os.remove(self.test_creds_path)

    def tearDown(self):
        # Clean up end
        if os.path.exists(self.test_creds_path):
            os.remove(self.test_creds_path)

    def test_add_new_user(self):
        print("\nTesting Add New User...")
        self.bot.update_user_credential("user1", "pass1")
        users = self.bot.load_all_credentials()
        self.assertEqual(len(users), 1)
        self.assertEqual(users[0]['username'], "user1")
        print("PASS: User added successfully")

    def test_update_existing_user(self):
        print("\nTesting Update Existing User...")
        self.bot.update_user_credential("user1", "pass1")
        self.bot.update_user_credential("user1", "pass1_new", "token123")
        
        users = self.bot.load_all_credentials()
        self.assertEqual(len(users), 1)
        self.assertEqual(users[0]['password'], "pass1_new")
        self.assertEqual(users[0]['token'], "token123")
        print("PASS: User updated successfully")

    def test_migration_legacy_dict(self):
        print("\nTesting Migration from Legacy Dict...")
        # Simulate legacy file
        legacy_data = {"username": "olduser", "password": "oldpass"}
        with open(self.test_creds_path, 'w') as f:
            json.dump(legacy_data, f)
            
        users = self.bot.load_all_credentials()
        self.assertEqual(len(users), 1)
        self.assertEqual(users[0]['username'], "olduser")
        print("PASS: Legacy dict migrated to list")

    def test_migration_users_key(self):
        print("\nTesting Migration from 'users' key...")
        # Simulate format with users key
        data = {"users": [{"username": "u1", "password": "p1"}]}
        with open(self.test_creds_path, 'w') as f:
            json.dump(data, f)
            
        users = self.bot.load_all_credentials()
        self.assertEqual(len(users), 1)
        self.assertEqual(users[0]['username'], "u1")
        print("PASS: 'users' key format loaded correctly")

    def test_context_aware_token_save(self):
        print("\nTesting Context Aware Token Save...")
        self.bot.update_user_credential("user1", "pass1")
        self.bot.current_username = "user1"
        
        # Simulate saving token
        self.bot.save_token("new_token_abc")
        
        users = self.bot.load_all_credentials()
        user = next(u for u in users if u['username'] == "user1")
        self.assertEqual(user['token'], "new_token_abc")
        print("PASS: Token saved to specific user context")

if __name__ == '__main__':
    unittest.main()
