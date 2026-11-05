import contextlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import auth_store


class AccountUpdateTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.state = Path(self.directory.name)
        auth_store.create_user(self.state, 'FirstUser', 'synthetic-old-password')
        self.path = self.state / 'accounts.json'
        accounts = json.loads(self.path.read_text())
        accounts['OtherUser'] = auth_store.hash_password('synthetic-other-password')
        self.path.write_text(json.dumps(accounts))
        self.original = self.path.read_bytes()

    def tearDown(self):
        self.directory.cleanup()

    def test_password_changes_only_selected_account(self):
        owner = self.path.stat()
        result = auth_store.update_user(self.state, 'FirstUser', 'synthetic-new-password')
        self.assertFalse(result['password_stored'])
        accounts = json.loads(self.path.read_text())
        self.assertEqual(accounts['OtherUser'], json.loads(self.original)['OtherUser'])
        self.assertTrue(auth_store.verify_password('synthetic-new-password', accounts['FirstUser']))
        self.assertFalse(auth_store.verify_password('synthetic-old-password', accounts['FirstUser']))
        self.assertNotIn(b'synthetic-new-password', self.path.read_bytes())
        if os.name == 'posix':
            self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(self.path.stat().st_uid, owner.st_uid)

    def test_rename_requires_new_hash_and_keeps_other_accounts(self):
        auth_store.update_user(self.state, 'FirstUser', 'synthetic-renamed-password', 'RenamedUser')
        accounts = json.loads(self.path.read_text())
        self.assertNotIn('FirstUser', accounts)
        self.assertTrue(auth_store.verify_password('synthetic-renamed-password', accounts['RenamedUser']))
        self.assertIn('OtherUser', accounts)

    def test_collision_missing_user_and_invalid_input_leave_original(self):
        for username, password, target in (
            ('FirstUser', 'synthetic-valid-password', 'OtherUser'),
            ('MissingUser', 'synthetic-valid-password', None),
            ('FirstUser', 'short', None),
            ('FirstUser', 'synthetic-valid-password', '../invalid'),
        ):
            with self.subTest(username=username, target=target):
                with self.assertRaises(ValueError):
                    auth_store.update_user(self.state, username, password, target)
                self.assertEqual(self.path.read_bytes(), self.original)

    def test_failed_replace_preserves_original_and_cleans_temporary(self):
        with patch('auth_store.os.replace', side_effect=OSError('synthetic-write-failure')):
            with self.assertRaises(OSError):
                auth_store.update_user(self.state, 'FirstUser', 'synthetic-new-password')
        self.assertEqual(self.path.read_bytes(), self.original)
        self.assertEqual(list(self.state.glob('.accounts-update*')), [])

    def test_existing_management_lock_is_not_removed(self):
        lock = self.state / '.accounts-update.lock'
        lock.write_text('synthetic-lock')
        with self.assertRaises(FileExistsError):
            auth_store.update_user(self.state, 'FirstUser', 'synthetic-new-password')
        self.assertTrue(lock.exists())
        self.assertEqual(self.path.read_bytes(), self.original)

    def test_mismatch_does_not_write_in_every_language(self):
        for language in ('ru', 'en', 'zh'):
            with self.subTest(language=language), patch('sys.argv', [
                    'auth_store.py', '--state', str(self.state), '--username', 'FirstUser',
                    '--action', 'password', '--lang', language]), patch(
                    'auth_store.getpass.getpass', side_effect=['synthetic-one', 'synthetic-two']):
                with self.assertRaises(SystemExit) as raised:
                    auth_store.main()
                self.assertEqual(str(raised.exception), auth_store.MESSAGES[language]['mismatch'])
                self.assertEqual(self.path.read_bytes(), self.original)

    def test_cli_never_prints_password_or_hash(self):
        output = io.StringIO()
        with patch('sys.argv', ['auth_store.py', '--state', str(self.state), '--username',
                'FirstUser', '--action', 'password']), patch('auth_store.getpass.getpass',
                side_effect=['synthetic-new-password'] * 2), contextlib.redirect_stdout(output):
            auth_store.main()
        self.assertNotIn('synthetic-new-password', output.getvalue())
        self.assertNotIn('pbkdf2', output.getvalue())
        self.assertTrue(json.loads(output.getvalue())['changed'])

    def test_no_echoing_fallback_when_terminal_is_unavailable(self):
        with patch('sys.argv', ['auth_store.py', '--state', str(self.state), '--username',
                'FirstUser', '--action', 'password']), patch('auth_store.getpass.getpass',
                side_effect=auth_store.getpass.GetPassWarning('synthetic-no-tty')):
            with self.assertRaises(SystemExit) as raised:
                auth_store.main()
        self.assertEqual(str(raised.exception), auth_store.MESSAGES['en']['hidden'])
        self.assertEqual(self.path.read_bytes(), self.original)


if __name__ == '__main__':
    unittest.main()
