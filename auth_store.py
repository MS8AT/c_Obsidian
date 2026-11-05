"""Account provisioning and updates: hidden input, atomic writes, salted hashes."""
import argparse
import getpass
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import secrets
import stat
import tempfile
import warnings

ITERATIONS = 600_000

MESSAGES = {
    'en': {'password': 'New password (hidden): ', 'confirm': 'Repeat password (hidden): ',
           'mismatch': 'Passwords differ; nothing changed.', 'hidden': 'A protected terminal is required; nothing changed.',
           'error': 'Account operation failed; check the state path, account name and permissions.'},
    'ru': {'password': 'Новый пароль (скрытый ввод): ', 'confirm': 'Повторите пароль (скрытый ввод): ',
           'mismatch': 'Пароли различаются; ничего не изменено.', 'hidden': 'Нужен терминал со скрытым вводом; ничего не изменено.',
           'error': 'Операция не выполнена: проверьте путь state, имя пользователя и права.'},
    'zh': {'password': '新密码（隐藏输入）：', 'confirm': '再次输入密码（隐藏输入）：',
           'mismatch': '两次密码不一致，未作任何更改。', 'hidden': '需要支持隐藏输入的终端，未作任何更改。',
           'error': '操作失败，请检查 state 路径、用户名及权限。'},
}


def hash_password(password):
    if not isinstance(password, str) or len(password) < 8 or len(password) > 256:
        raise ValueError('password_length')
    salt = secrets.token_bytes(24)
    digest = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, ITERATIONS)
    return 'pbkdf2_sha256$%d$%s$%s' % (ITERATIONS, salt.hex(), digest.hex())


def verify_password(password, encoded):
    try:
        algorithm, count, salt, expected = encoded.split('$')
        iterations = int(count)
        if algorithm != 'pbkdf2_sha256' or not 100_000 <= iterations <= 2_000_000:
            return False
        actual = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), bytes.fromhex(salt), iterations).hex()
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError, AttributeError):
        return False


def create_user(state, username, password):
    if not re.fullmatch(r'[A-Za-z0-9._-]{3,64}', username):
        raise ValueError('invalid_username')
    state = Path(state)
    state.mkdir(mode=0o700, parents=True, exist_ok=True)
    path = state / 'accounts.json'
    # Exclusive creation intentionally prevents overwriting a provisioned account.
    raw = json.dumps({username: hash_password(password)}).encode('utf-8')
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'wb') as handle:
        handle.write(raw)
    return {'username': username, 'created': True, 'password_stored': False}


def update_user(state, username, password, new_username=None):
    """Change one account atomically, preserving other accounts and ownership.

    Rename also requires a new password: a freshly salted hash revokes old
    sessions even if the account is later renamed back to its original name.
    """
    target = new_username if new_username is not None else username
    for name in (username, target):
        if not isinstance(name, str) or not re.fullmatch(r'[A-Za-z0-9._-]{3,64}', name):
            raise ValueError('invalid_username')
    encoded = hash_password(password)
    path = Path(state) / 'accounts.json'
    if path.is_symlink() or not stat.S_ISREG(path.stat().st_mode):
        raise ValueError('invalid_account_file')
    lock = path.with_name('.accounts-update.lock')
    lock_fd = os.open(lock, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    temporary = None
    try:
        os.close(lock_fd)
        original_stat = path.stat()
        original = path.read_bytes()
        accounts = json.loads(original)
        if not isinstance(accounts, dict) or username not in accounts:
            raise ValueError('user_not_found')
        if target != username and target in accounts:
            raise ValueError('username_already_exists')
        del accounts[username]
        accounts[target] = encoded
        fd, name = tempfile.mkstemp(prefix='.accounts-update-', dir=path.parent)
        temporary = Path(name)
        with os.fdopen(fd, 'w', encoding='utf-8') as handle:
            if hasattr(os, 'fchown'):
                os.fchown(handle.fileno(), original_stat.st_uid, original_stat.st_gid)
            json.dump(accounts, handle, ensure_ascii=False)
            handle.flush()
            os.fsync(handle.fileno())
        if path.is_symlink() or path.read_bytes() != original:
            raise ValueError('accounts_changed_concurrently')
        os.replace(temporary, path)
        return {'username': target, 'previous_username': username,
                'changed': True, 'password_stored': False}
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()
        lock.unlink()


def session_key(state):
    path = Path(state) / 'session.key'
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        pass
    else:
        with os.fdopen(fd, 'wb') as handle:
            handle.write(secrets.token_bytes(48))
    key = path.read_bytes()
    if len(key) != 48:
        raise ValueError('invalid_session_key')
    return key


def main():
    parser = argparse.ArgumentParser(description='Manage a c_Obsidian web account using a protected password prompt.')
    parser.add_argument('--state', type=Path, required=True)
    parser.add_argument('--username', required=True)
    parser.add_argument('--action', choices=('create', 'password', 'rename'), default='create')
    parser.add_argument('--new-username')
    parser.add_argument('--lang', choices=tuple(MESSAGES), default='en')
    args = parser.parse_args()
    if (args.action == 'rename') != (args.new_username is not None):
        parser.error('--new-username is required only for --action rename')
    messages = MESSAGES[args.lang]
    password = confirm = None
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', getpass.GetPassWarning)
            password = getpass.getpass(messages['password'])
            confirm = getpass.getpass(messages['confirm'])
        if password != confirm:
            raise SystemExit(messages['mismatch'])
        if args.action == 'create':
            result = create_user(args.state, args.username, password)
        else:
            result = update_user(args.state, args.username, password,
                                 args.new_username if args.action == 'rename' else None)
    except getpass.GetPassWarning:
        raise SystemExit(messages['hidden'])
    except (ValueError, OSError):
        raise SystemExit(messages['error'])
    finally:
        password = confirm = None
    print(json.dumps(result))


if __name__ == '__main__':
    main()
