import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from production import Application


class LoginLockoutTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='cobsidian-auth-lockout-')
        root = Path(self.tmp.name)
        (root / 'vault').mkdir()
        (root / 'state').mkdir()
        (root / 'state' / 'accounts.json').write_text(
            json.dumps({'TestUser': 'synthetic-password-hash'}), encoding='utf-8'
        )
        self.app = Application(root / 'vault', root / 'state', domain='obsidian.ms8at.by', secure=True)

    def tearDown(self):
        self.tmp.cleanup()

    def login(self, password='wrong-password', remote='198.51.100.10'):
        raw = json.dumps({'username': 'TestUser', 'password': password}).encode('utf-8')
        captured = {}
        environ = {
            'REQUEST_METHOD': 'POST',
            'PATH_INFO': '/api/login',
            'HTTP_HOST': 'obsidian.ms8at.by',
            'REMOTE_ADDR': remote,
            'CONTENT_TYPE': 'application/json',
            'CONTENT_LENGTH': str(len(raw)),
            'wsgi.input': io.BytesIO(raw),
        }
        body = b''.join(self.app(environ, lambda status, headers: captured.update(status=status, headers=headers)))
        return captured['status'], dict(captured['headers']), json.loads(body)

    def test_tenth_wrong_password_starts_30_minute_lockout(self):
        with patch('production.verify_password', return_value=False), patch('production.time.monotonic', return_value=100.0):
            results = [self.login() for _ in range(10)]
            blocked = self.login()

        self.assertEqual([result[0] for result in results[:9]], ['401 Unauthorized'] * 9)
        self.assertEqual(results[9][0], '429 Too Many Requests')
        self.assertEqual(dict(results[9][1]).get('Retry-After'), '1800')
        self.assertEqual(blocked[0], '429 Too Many Requests')
        self.assertEqual(dict(blocked[1]).get('Retry-After'), '1800')
        self.assertEqual(blocked[2], {'error': 'try_later'})

    def test_lockout_expires_after_30_minutes(self):
        clock = [100.0] * 10 + [1900.1]
        with patch('production.verify_password', return_value=False), patch('production.time.monotonic', side_effect=clock):
            for _ in range(10):
                self.login()
            after_expiry = self.login()

        self.assertEqual(after_expiry[0], '401 Unauthorized')
        self.assertNotIn('Retry-After', after_expiry[1])
        self.assertEqual(after_expiry[2], {'error': 'invalid_credentials'})

    def test_successful_login_clears_failures_before_threshold(self):
        outcomes = [False] * 9 + [True, False]
        with patch('production.verify_password', side_effect=outcomes), patch('production.time.monotonic', return_value=100.0):
            failed = [self.login() for _ in range(9)]
            success = self.login(password='correct-password')
            next_failure = self.login()

        self.assertEqual([result[0] for result in failed], ['401 Unauthorized'] * 9)
        self.assertEqual(success[0], '200 OK')
        self.assertEqual(next_failure[0], '401 Unauthorized')


if __name__ == '__main__':
    unittest.main()
