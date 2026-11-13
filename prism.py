"""Read the bundled author's prototype; never execute or alter its source."""
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile

from obsidian_core import BUILD_VERSION, VaultError

MAX_HTML = 2 * 1024 * 1024


SOURCE = Path(__file__).resolve().parent / 'web' / 'prism-prototype.html'
FILENAME = 'Призма_различений_—_прототип_исправленный.html'
# The prototype has inline JS/CSS. Give only this document an opaque origin;
# it cannot read the parent's vault, session, DOM or network resources.
PRISM_CSP = (
    "sandbox allow-scripts allow-modals; default-src 'none'; "
    "script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src data:; "
    "connect-src 'none'; object-src 'none'; base-uri 'none'; "
    "frame-ancestors 'self'; form-action 'none'"
)


def prototype():
    raw = SOURCE.read_bytes()
    return raw, {
        'filename': FILENAME,
        'sha256': hashlib.sha256(raw).hexdigest(),
        'bytes': len(raw),
        'preview_url': '/prism',
        'content': raw.decode('utf-8'),
        'kind': 'standalone_prototype',
        'vault_integration': False,
    }


class PrototypeStore:
    """Editable copy in application state. The bundled original is immutable."""
    def __init__(self, root):
        self.root = Path(root)

    def read(self, original=False):
        raw, meta = prototype()
        marker = self.root / 'current.json'
        if not original and marker.exists():
            self._regular(marker)
            if marker.stat().st_size > 512:
                raise VaultError('invalid_prism_state')
            try:
                revision = json.loads(marker.read_text(encoding='utf-8'))['sha256']
            except (ValueError, KeyError, TypeError) as exc:
                raise VaultError('invalid_prism_state') from exc
            if not isinstance(revision, str) or not re.fullmatch('[0-9a-f]{64}', revision):
                raise VaultError('invalid_prism_state')
            path = self.root / (revision + '.html')
            self._regular(path)
            with path.open('rb') as handle:
                raw = handle.read(MAX_HTML + 1)
            if len(raw) > MAX_HTML or hashlib.sha256(raw).hexdigest() != revision:
                raise VaultError('invalid_prism_state')
            meta.update(content=raw.decode('utf-8'), sha256=revision, bytes=len(raw))
        meta['original_sha256'] = prototype()[1]['sha256']
        meta['modified'] = meta['sha256'] != meta['original_sha256']
        meta['build_version'] = BUILD_VERSION
        return raw, meta

    def _regular(self, path):
        if self.root.is_symlink() or path.is_symlink() or not path.is_file() or path.stat().st_nlink != 1:
            raise VaultError('invalid_prism_state')

    def write(self, data, reset=False):
        if not isinstance(data, dict) or set(data) - ({'expected_sha256'} if reset else {'content', 'expected_sha256'}):
            raise VaultError('invalid_body')
        expected = data.get('expected_sha256')
        if not isinstance(expected, str) or not re.fullmatch('[0-9a-f]{64}', expected):
            raise VaultError('expected_sha256_required')
        if reset:
            raw = prototype()[0]
        else:
            content = data.get('content')
            if not isinstance(content, str):
                raise VaultError('invalid_body')
            raw = content.encode('utf-8')
            if not 0 < len(raw) <= MAX_HTML:
                raise VaultError('html_too_large')
            if '<html' not in content.lower() or '</html>' not in content.lower():
                raise VaultError('invalid_html')
        if self.root.is_symlink():
            raise VaultError('invalid_prism_state')
        self.root.mkdir(parents=True, exist_ok=True)
        lock = self.root / 'write.lock'
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError as exc:
            raise VaultError('write_conflict') from exc
        try:
            if self.read()[1]['sha256'] != expected:
                raise VaultError('revision_conflict')
            digest = hashlib.sha256(raw).hexdigest()
            target = self.root / (digest + '.html')
            try:
                with target.open('xb') as handle:
                    handle.write(raw)
            except FileExistsError:
                self._regular(target)
                if target.read_bytes() != raw:
                    raise VaultError('invalid_prism_state')
            temporary = None
            try:
                with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=self.root,
                                                 prefix='.current-', delete=False) as handle:
                    temporary = Path(handle.name)
                    json.dump({'sha256': digest}, handle)
                os.replace(temporary, self.root / 'current.json')
            finally:
                if temporary is not None:
                    temporary.unlink(missing_ok=True)
            return self.read()[1]
        finally:
            os.close(fd)
            lock.unlink()
