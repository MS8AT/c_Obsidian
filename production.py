"""Authenticated WSGI service. Serve through Gunicorn behind the included Caddy."""
from collections import defaultdict, deque
from contextlib import contextmanager
import base64
import hashlib
import hmac
from http import HTTPStatus
from http.cookies import CookieError, SimpleCookie
import json
import os
from pathlib import Path
import secrets
import sqlite3
import threading
import time
from urllib.parse import parse_qs

from auth_store import verify_password
from obsidian_core import BUILD_VERSION, LANGUAGES, MAX_IMAGE, VERSION, Vault, VaultConflict, VaultError
from prism_core import PrismStore
from prism import PRISM_CSP
from api_extensions import ApiActions, api_error_status

HERE = Path(__file__).resolve().parent
TTL = 8 * 3600
LOGIN_ATTEMPT_LIMIT = 10
LOGIN_WINDOW = 30 * 60
LOGIN_BLOCK = 30 * 60


class Application:
    def __init__(self, vault, state, domain='obsidian.ms8at.by', secure=True, writable=True):
        self.vault = Vault(vault)
        self.prism = PrismStore(self.vault.root)
        self.actions = ApiActions(self.vault, state)
        self.state = Path(state)
        self.state.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.domain = domain
        self.secure = secure
        self.origin = ('https' if secure else 'http') + '://' + domain
        self.writable = writable
        self.lock = threading.RLock()
        self.attempts = defaultdict(deque)
        self.blocked_until = {}
        self.database = self.state/'sessions.sqlite3'
        try:
            fd = os.open(self.database, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            os.close(fd)
        except FileExistsError:
            pass
        with self.connection() as db:
            db.execute('CREATE TABLE IF NOT EXISTS sessions (id TEXT PRIMARY KEY, username TEXT, expires INTEGER, csrf TEXT, version TEXT)')

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.database, timeout=10)
        try:
            with db:
                yield db
        finally:
            db.close()

    def accounts(self):
        try:
            return json.loads((self.state / 'accounts.json').read_text())
        except FileNotFoundError:
            return {}

    def issue_session(self, username):
        token = secrets.token_urlsafe(48)
        with self.connection() as db:
            db.execute('DELETE FROM sessions WHERE expires <= ?', (int(time.time()),))
            db.execute('INSERT INTO sessions VALUES (?,?,?,?,?)', (hashlib.sha256(token.encode()).hexdigest(), username, int(time.time())+TTL, secrets.token_urlsafe(24), hashlib.sha256(self.accounts()[username].encode()).hexdigest()))
        return token

    def session(self, environ):
        cookie = SimpleCookie()
        try:
            cookie.load(environ.get('HTTP_COOKIE', ''))
            value = cookie['obsidian_session'].value
            if not 30 <= len(value) <= 100:
                return None
            identity = hashlib.sha256(value.encode()).hexdigest()
            with self.connection() as db:
                row = db.execute('SELECT username,expires,csrf,version FROM sessions WHERE id=?', (identity,)).fetchone()
            if not row:
                return None
            payload = dict(zip(('user','expires','csrf','version'), row))
            payload['id'] = identity
            account = self.accounts().get(payload['user'])
            if not account or payload['expires'] <= time.time():
                return None
            if not hmac.compare_digest(payload['version'], hashlib.sha256(account.encode()).hexdigest()):
                return None
            return payload
        except (KeyError, ValueError, TypeError, CookieError):
            return None

    def __call__(self, environ, start_response):
        try:
            code, value, mime, extras = self.dispatch(environ)
        except VaultConflict as exc:
            code, value, mime, extras = 409, {'error': str(exc)}, 'application/json', []
        except VaultError as exc:
            code, value, mime, extras = api_error_status(exc), {'error': str(exc)}, 'application/json', []
        except (ValueError, KeyError, TypeError, UnicodeError):
            code, value, mime, extras = 400, {'error': 'invalid_body'}, 'application/json', []
        except (OSError, sqlite3.Error):
            code, value, mime, extras = 500, {'error': 'file_error'}, 'application/json', []
        raw = value if isinstance(value, bytes) else json.dumps(value, ensure_ascii=False).encode('utf-8')
        prism_preview = code == 200 and mime == 'text/html' and environ.get('PATH_INFO') == '/prism'
        headers = [('Content-Type', mime + ('; charset=utf-8' if mime.startswith(('text/', 'application/json', 'application/javascript')) else '')), ('Content-Length', str(len(raw))), ('Cache-Control', 'no-store'), ('X-Content-Type-Options', 'nosniff'), ('Referrer-Policy', 'no-referrer'), ('Content-Security-Policy', PRISM_CSP if prism_preview else "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' blob:; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'"), *extras]
        start_response(str(code) + ' ' + HTTPStatus(code).phrase, headers)
        return [raw]

    def body(self, environ):
        length = int(environ.get('CONTENT_LENGTH') or '0')
        if not 0 < length <= MAX_IMAGE * 2:
            raise VaultError('invalid_size')
        raw = environ['wsgi.input'].read(length)
        if len(raw) != length:
            raise VaultError('invalid_body')
        return raw

    def cookie(self, value, clear=False):
        return ('Set-Cookie', 'obsidian_session=' + value + '; Path=/; HttpOnly; SameSite=Lax; Max-Age=' + ('0' if clear else str(TTL)) + ('; Secure' if self.secure else ''))

    @staticmethod
    def login_remote(env):
        remote = env.get('REMOTE_ADDR', '')
        if remote in ('127.0.0.1', '::1'):
            remote = env.get('HTTP_X_FORWARDED_FOR', remote).split(',')[0].strip()
        return remote or 'unknown'

    def login_retry_after(self, remote, now):
        blocked_until = self.blocked_until.get(remote, 0)
        if blocked_until <= now:
            self.blocked_until.pop(remote, None)
            return None
        return max(1, int(blocked_until - now + 0.999999))

    def dispatch(self, env):
        path, method = env.get('PATH_INFO', '/'), env.get('REQUEST_METHOD', 'GET')
        host = env.get('HTTP_HOST', '')
        if path == '/api/health' and method == 'GET':
            return 200, {'ok': True, 'version': VERSION, 'build_version': BUILD_VERSION, 'auth': 'session'}, 'application/json', []
        if host != self.domain:
            return 403, {'error': 'invalid_host'}, 'application/json', []
        if env.get('HTTP_ORIGIN') not in (None, '', self.origin):
            return 403, {'error': 'invalid_origin'}, 'application/json', []
        session = self.session(env)
        if path in ('/login.js', '/style.css') and method == 'GET':
            return self.asset(path[1:])
        if path == '/login' and method == 'GET':
            return self.asset('login.html')
        if path == '/api/login' and method == 'POST':
            if env.get('CONTENT_TYPE', '').split(';')[0] != 'application/json':
                raise VaultError('json_required')
            with self.lock:
                remote = self.login_remote(env)
                now = time.monotonic()
                retry_after = self.login_retry_after(remote, now)
                if retry_after is not None:
                    return 429, {'error': 'try_later'}, 'application/json', [('Retry-After', str(retry_after))]
                attempts = self.attempts[remote]
                while attempts and attempts[0] <= now - LOGIN_WINDOW:
                    attempts.popleft()
                # Limit login bodies independently from image API requests.
                if int(env.get('CONTENT_LENGTH') or '0') > 4096:
                    raise VaultError('invalid_size')
                data = json.loads(self.body(env))
                if not isinstance(data, dict):
                    raise VaultError('invalid_body')
                username, password = data.get('username', ''), data.get('password', '')
                if not isinstance(username, str) or not isinstance(password, str) or len(password) > 256:
                    raise VaultError('invalid_body')
                attempts.append(now)
                stored = self.accounts().get(username)
                if not stored or not verify_password(password, stored):
                    if len(attempts) >= LOGIN_ATTEMPT_LIMIT:
                        self.blocked_until[remote] = now + LOGIN_BLOCK
                        return 429, {'error': 'try_later'}, 'application/json', [('Retry-After', str(LOGIN_BLOCK))]
                    return 401, {'error': 'invalid_credentials'}, 'application/json', []
                attempts.clear()
                self.blocked_until.pop(remote, None)
                return 200, {'ok': True}, 'application/json', [self.cookie(self.issue_session(username))]
        if not session:
            if path == '/':
                return 303, b'', 'text/plain', [('Location', '/login')]
            return 401, {'error': 'unauthorized'}, 'application/json', []
        if path == '/api/session' and method == 'GET':
            return 200, {'username': session['user'], 'csrf': session['csrf']}, 'application/json', []
        if method in ('POST', 'PUT'):
            csrf = env.get('HTTP_X_CSRF_TOKEN', '')
            if not hmac.compare_digest(csrf, session['csrf']):
                return 403, {'error': 'invalid_csrf'}, 'application/json', []
            if path == '/api/logout' and method == 'POST':
                with self.connection() as db:
                    db.execute('DELETE FROM sessions WHERE id=?', (session['id'],))
                return 200, {'ok': True}, 'application/json', [self.cookie('', clear=True)]
            read_only_route = path.endswith(('/evaluate', '/compare')) or path == '/api/prism/v1/import/validate'
            if not read_only_route and not self.writable:
                return 403, {'error': 'read_only'}, 'application/json', []
            if env.get('CONTENT_TYPE', '').split(';')[0] != 'application/json':
                raise VaultError('json_required')
            data = json.loads(self.body(env))
            with self.lock:
                extension = self.actions.write(method, path, data)
                if extension is not None:
                    return extension[0], extension[1], 'application/json', []
                if path == '/api/notes' and method == 'POST':
                    result = self.vault.create(data['path'], data['content'])
                elif path == '/api/notes/update' and method == 'PUT':
                    result = self.vault.update(data['path'], data['content'], data.get('expected_sha256'))
                elif path == '/api/images' and method == 'POST':
                    result = self.vault.add_image(data['path'], base64.b64decode(data['base64'], validate=True))
                elif path == '/api/prism/v1/cases' and method == 'POST':
                    result = self.prism.create(data, session['user'])
                elif path == '/api/prism/v1/example' and method == 'POST':
                    result = self.prism.create_example()
                elif path.startswith('/api/prism/v1/cases/'):
                    parts = path.strip('/').split('/')
                    if len(parts) == 6 and parts[5] == 'evaluate' and method == 'POST':
                        result = self.prism.evaluate(parts[4], data.get('scenario') or data.get('scenario_id'))
                    elif len(parts) == 6 and parts[5] == 'snapshot' and method == 'POST':
                        result = self.prism.snapshot(parts[4], data.get('revision'), actor=session['user'], operation_id=data.get('operation_id'))
                    elif len(parts) == 6 and parts[5] == 'compare' and method == 'POST':
                        result = self.prism.compare(parts[4], data)
                    elif len(parts) == 6 and parts[5] == 'challenge' and method == 'POST':
                        result = self.prism.challenge(parts[4], data, data.get('expected_revision'), session['user'])
                    elif len(parts) == 5 and method == 'PUT':
                        result = self.prism.update(parts[4], data.get('model', data), data.get('expected_revision'), session['user'], data.get('operation_id'))
                    else:
                        return 404, {'error': 'not_found'}, 'application/json', []
                elif path == '/api/prism/v1/import/validate' and method == 'POST':
                    result = self.prism.validate_import(data.get('package', data))
                elif path == '/api/prism/v1/import/commit' and method == 'POST':
                    result = self.prism.commit_import(data.get('package', {}), data.get('expected_package_sha256'), session['user'], data.get('operation_id'))
                else:
                    return 404, {'error': 'not_found'}, 'application/json', []
            return (200 if read_only_route or path.endswith('/snapshot') else 201), result, 'application/json', []
        if method != 'GET':
            return 405, {'error': 'method_not_allowed'}, 'application/json', [('Allow', 'GET, POST, PUT')]
        query = parse_qs(env.get('QUERY_STRING', ''))
        with self.lock:
            action = self.actions.read(path, query)
            if action is not None:
                return 200, action[0], action[1], []
            if path == '/prism':
                return 200, self.actions.prism.read()[0], 'text/html', []
            if path == '/api/status':
                return 200, {'version': VERSION, 'build_version': BUILD_VERSION, 'language': 'ru', 'languages': list(LANGUAGES), 'writable': self.writable, 'vault': self.vault.root.name, 'auth': 'session', 'username': session['user']}, 'application/json', []
            if path == '/api/image':
                data, mime = self.vault.image(query.get('path', [''])[0])
                return 200, data, mime, []
            if path == '/api/openapi':
                return 200, json.loads((HERE/'openapi.json').read_text()), 'application/json', []
            if path == '/api/prism/v1/cases':
                return 200, {'cases': self.prism.list_cases()}, 'application/json', []
            if path.startswith('/api/prism/v1/cases/'):
                parts = path.strip('/').split('/')
                if len(parts) == 5:
                    return 200, self.prism.get(parts[4]), 'application/json', []
                if len(parts) == 6 and parts[5] == 'history':
                    return 200, {'events': self.prism.history(parts[4])}, 'application/json', []
                if len(parts) == 6 and parts[5] == 'snapshot':
                    return 200, self.prism.read_snapshot(parts[4], int(query.get('revision', ['0'])[0]) or None), 'application/json', []
                if len(parts) == 6 and parts[5] == 'export':
                    return 200, self.prism.export_case(parts[4]), 'application/json', []
                if len(parts) == 6 and parts[5] == 'recovery':
                    return 200, {'pending': self.prism.recovery()}, 'application/json', []
        if path in ('/', '/index.html', '/app.js', '/prism.js', '/prism.css'):
            return self.asset('index.html' if path == '/' else path[1:])
        return 404, {'error': 'not_found'}, 'application/json', []

    def asset(self, name):
        mime = {'.html': 'text/html', '.js': 'application/javascript', '.css': 'text/css'}[Path(name).suffix]
        return 200, (HERE/'web'/name).read_bytes(), mime, []


def create_app():
    return Application(os.environ.get('OBSIDIAN_VAULT', '/vault'), os.environ.get('OBSIDIAN_STATE', '/state'), os.environ.get('OBSIDIAN_DOMAIN', 'obsidian.ms8at.by'), secure=os.environ.get('OBSIDIAN_SECURE', '1') == '1', writable=os.environ.get('OBSIDIAN_WRITE', '1') == '1')
