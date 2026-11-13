import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


class HealthContractTests(unittest.TestCase):
    def test_health_is_public_and_reports_prism_build(self):
        from production import Application

        with tempfile.TemporaryDirectory(prefix='cobsidian-health-') as tmp:
            root = Path(tmp)
            (root / 'vault').mkdir()
            app = Application(root / 'vault', root / 'state', domain='obsidian.ms8at.by', secure=True)
            captured = {}

            def start_response(status, headers):
                captured['status'] = status

            environ = {
                'REQUEST_METHOD': 'GET',
                'PATH_INFO': '/api/health',
                'HTTP_HOST': 'obsidian.ms8at.by',
                'REMOTE_ADDR': '127.0.0.1',
                'CONTENT_LENGTH': '0',
                'wsgi.input': io.BytesIO(),
            }
            body = b''.join(app(environ, start_response))

        self.assertEqual(captured['status'], '200 OK')
        self.assertEqual(json.loads(body), {
            'ok': True,
            'version': '0.3.2',
            'build_version': '0.3.2-prism-api',
            'auth': 'session',
        })


if __name__ == '__main__':
    unittest.main()
