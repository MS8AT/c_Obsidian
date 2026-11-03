"""Password provisioning: getpass input, salted hashes only, no plaintext files."""
import argparse
import base64
import getpass
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import secrets

ITERATIONS = 600_000


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
    parser = argparse.ArgumentParser(description='Create a web account using a protected password prompt.')
    parser.add_argument('--state', type=Path, required=True)
    parser.add_argument('--username', required=True)
    args = parser.parse_args()
    password = getpass.getpass('Password (hidden): ')
    confirm = getpass.getpass('Repeat password (hidden): ')
    if password != confirm:
        raise SystemExit('Passwords differ; no account was created.')
    try:
        result = create_user(args.state, args.username, password)
    except (ValueError, FileExistsError) as exc:
        raise SystemExit(str(exc))
    finally:
        password = confirm = None
    print(json.dumps(result))


if __name__ == '__main__':
    main()
