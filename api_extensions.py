"""Shared API extensions for the native 0.3 Prism application."""
import base64
import hashlib
import os
import re
import stat
import tempfile
from pathlib import Path
from obsidian_core import BUILD_VERSION, LANGUAGES, MAX_NOTE, MAX_IMAGE, IMAGE_TYPES, safe_path, VaultError
from prism import PrototypeStore

VIEWS = ('emergence', 'starfield', 'gravity', 'sensemakers', 'photos')


def note_source(vault, relative):
    path = safe_path(vault.root, relative)
    if path.suffix.lower() != '.md' or not path.is_file():
        raise VaultError('note_not_found')
    with path.open('rb') as handle:
        raw = handle.read(MAX_NOTE + 1)
    if len(raw) > MAX_NOTE:
        raise VaultError('note_too_large')
    return {'path': relative, 'content': raw.decode('utf-8-sig'),
            'sha256': hashlib.sha256(raw).hexdigest()}


def replace_content(vault, data, image=False):
    if not isinstance(data, dict):
        raise VaultError('invalid_body')
    relative = data.get('path')
    path = safe_path(vault.root, relative)
    if not path.is_file():
        raise VaultError('image_not_found' if image else 'note_not_found')
    if image:
        raw = base64.b64decode(data.get('base64', ''), validate=True)
        vault.check_image(path.suffix.lower(), raw)
        limit = MAX_IMAGE
    else:
        if path.suffix.lower() != '.md' or not isinstance(data.get('content'), str):
            raise VaultError('invalid_note')
        raw = data['content'].encode('utf-8')
        limit = MAX_NOTE
    if len(raw) > limit:
        raise VaultError('image_too_large' if image else 'note_too_large')
    expected = data.get('expected_sha256')
    if expected is not None and (not isinstance(expected, str) or not re.fullmatch('[0-9a-f]{64}', expected)):
        raise VaultError('invalid_revision')
    lock = path.with_name('.' + path.name + '.write-lock')
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as exc:
        raise VaultError('write_conflict') from exc
    temporary = None
    try:
        safe_path(vault.root, relative)
        original_mode = stat.S_IMODE(path.stat().st_mode)
        if path.stat().st_nlink != 1:
            raise VaultError('linked_path')
        with path.open('rb') as handle:
            previous = handle.read(limit + 1)
        if len(previous) > limit:
            raise VaultError('invalid_size')
        if expected is not None and hashlib.sha256(previous).hexdigest() != expected:
            raise VaultError('revision_conflict')
        with tempfile.NamedTemporaryFile(mode='wb', dir=path.parent,
                                         prefix='.c-obsidian-', delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(raw)
        temporary.chmod(original_mode)
        os.replace(temporary, path)
        vault.cache.pop(relative, None)
        return {'path': relative, 'sha256': hashlib.sha256(raw).hexdigest(), 'updated': True}
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        os.close(fd)
        lock.unlink()


class ApiActions:
    """Shared local/production data operations; no model or shell execution."""
    def __init__(self, vault, state):
        self.vault = vault
        self.prism = PrototypeStore(Path(state) / 'prism')

    def read(self, path, query):
        if path == '/api/prism/prototype':
            return self.prism.read(query.get('original', ['0'])[0] == '1')[1], 'application/json'
        if path == '/api/capabilities':
            return {'build_version': BUILD_VERSION, 'write_operations_require_write_mode': True,
                    'views': list(VIEWS), 'note_create': 'POST /api/notes',
                    'note_read': 'GET /api/note?path=...', 'note_edit': 'PUT /api/notes/update',
                    'image_upload': 'POST /api/images', 'image_read': 'GET /api/image?path=...',
                    'image_edit': 'PUT /api/images/update', 'image_info': 'GET /api/image/info?path=...',
                    'notes_and_search': 'GET /api/notes?q=...', 'graph_and_views': 'GET /api/graph?view=...&q=...&group=...&until=...&language=...',
                    'prism_read': 'GET /api/prism/prototype', 'prism_edit': 'PUT /api/prism/prototype',
                    'prism_original': 'GET /api/prism/prototype?original=1', 'prism_reset': 'POST /api/prism/reset',
                    'folder_import': 'Repeat POST /api/notes and POST /api/images for client-provided files; paths relative to current vault',
                    'examples': 'POST /api/notes and POST /api/images using the published example inputs',
                    'write_mode': 'Fixed by operator; cannot be elevated by API',
                    'presentation_only': ['open/close/cancel dialogs', 'native file picker', 'timeline playback timer'],
                    'prototype_local_controls': ['change condition', 'revert condition', 'node cards'],
                    'prototype_placeholders': ['other perspectives', 'challenge model'],
                    'prism_vault_integration': True,
                    'native_projects': {'list':'GET /api/prism/v1/cases','create':'POST /api/prism/v1/cases','edit':'PUT /api/prism/v1/cases/{case_id}','export':'GET /api/prism/v1/cases/{case_id}/export','history':'GET /api/prism/v1/cases/{case_id}/history','snapshot':'POST /api/prism/v1/cases/{case_id}/snapshot','evaluate':'POST /api/prism/v1/cases/{case_id}/evaluate','compare':'POST /api/prism/v1/cases/{case_id}/compare','challenge':'POST /api/prism/v1/cases/{case_id}/challenge','validate_import':'POST /api/prism/v1/import/validate','commit_import':'POST /api/prism/v1/import/commit'},
                    'html_reference_integrated_with_native_case': False}, 'application/json'
        if path == '/api/views':
            return {'views': list(VIEWS), 'native_prism_view': {'name':'prism','data':'/api/prism/v1/cases'}, 'groups': ['time', 'folder'],
                    'languages': list(LANGUAGES), 'query_parameters': ['view', 'q', 'group', 'until', 'language'],
                    'projection_changes_facts': False}, 'application/json'
        if path == '/api/note':
            return note_source(self.vault, query.get('path', [''])[0]), 'application/json'
        if path == '/api/image/info':
            relative = query.get('path', [''])[0]
            raw, mime = self.vault.image(relative)
            return {'path': relative, 'mime_type': mime, 'bytes': len(raw),
                    'sha256': hashlib.sha256(raw).hexdigest()}, 'application/json'
        if path in ('/api/notes', '/api/graph'):
            graph = self.vault.graph()
            view = query.get('view', ['emergence'])[0]
            group = query.get('group', ['time'])[0]
            language = query.get('language', ['ru'])[0]
            until = query.get('until', [''])[0]
            if view not in VIEWS or group not in ('time', 'folder') or language not in LANGUAGES:
                raise VaultError('invalid_projection')
            if until:
                from datetime import date
                if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', until):
                    raise VaultError('invalid_projection')
                try:date.fromisoformat(until)
                except ValueError as exc:raise VaultError('invalid_projection') from exc
            term = query.get('q', [''])[0].casefold()
            notes = [n for n in graph['notes'] if term in (n['title']+' '+n['id']+' '+' '.join(n['tags'])).casefold()
                     and (not until or bool(n['created']) and n['created'] <= until)
                     and (view != 'photos' or bool(n['images']))]
            if path == '/api/notes':
                return {'notes': notes, 'count': len(notes), 'warnings': graph['warnings']}, 'application/json'
            if query:
                ids = {n['id'] for n in notes}
                graph['source_summary'] = dict(graph['summary'])
                graph['notes'] = notes
                graph['edges'] = [e for e in graph['edges'] if e['source'] in ids and e['target'] in ids]
                graph['filtered_summary'] = {'notes': len(notes), 'links': len(graph['edges'])}
                graph['projection'] = {'view': view, 'group': group, 'language': language, 'until': until, 'q': term}
            return graph, 'application/json'
        return None

    def write(self, method, path, data):
        if not isinstance(data, dict):
            raise VaultError('invalid_body')
        if method == 'POST' and path == '/api/notes':
            return 201, self.vault.create(data['path'], data['content'])
        if method == 'POST' and path == '/api/images':
            return 201, self.vault.add_image(data['path'], base64.b64decode(data['base64'], validate=True))
        if method == 'PUT' and path == '/api/notes/update':
            return 201, replace_content(self.vault, data)
        if method == 'PUT' and path == '/api/images/update':
            return 200, replace_content(self.vault, data, image=True)
        if method == 'PUT' and path == '/api/prism/prototype':
            return 200, self.prism.write(data)
        if method == 'POST' and path == '/api/prism/reset':
            return 200, self.prism.write(data, reset=True)
        if path in ('/api/notes','/api/images','/api/notes/update','/api/images/update','/api/prism/prototype','/api/prism/reset'):
            return 405, {'error':'method_not_allowed'}
        return None


def api_error_status(error):
    return 409 if str(error) in ('revision_conflict', 'write_conflict') else 400
