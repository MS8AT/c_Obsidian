import base64
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from obsidian_core import Vault, VaultError
from obsidian import Server

PNG = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a3ioAAAAASUVORK5CYII=')


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='c-obsidian-test-')
        self.root = Path(self.temp.name)
        self.vault = Vault(self.root)

    def tearDown(self):
        self.temp.cleanup()

    def note(self, path, body, kind='note'):
        return self.vault.create(path, '---\ncreated: 2026-01-01\ntype: '+kind+'\n---\n# '+Path(path).stem+'\n\n'+body)

    def test_five_levels_and_no_vault_mutation(self):
        self.note('Home.md', '[[Atlas]]', 'home')
        self.note('Atlas.md', '[[Map A]] [[Map B]]')
        self.note('Map A.md', '[[Linked]]', 'moc')
        self.note('Map B.md', '[[Linked]]', 'moc')
        self.note('Linked.md', 'ordinary text')
        self.note('Isolated.md', '```md\n[[Home]]\n```')
        before = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in self.root.rglob('*.md')}
        graph = self.vault.graph()
        levels = {n['id']: n['level'] for n in graph['notes']}
        self.assertEqual(levels, {'Home.md':5,'Atlas.md':4,'Map A.md':3,'Map B.md':3,'Linked.md':2,'Isolated.md':1})
        self.assertEqual(graph['summary']['unlinked'], 1)
        self.assertEqual(before, {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in self.root.rglob('*.md')})

    def test_unicode_relative_links_images_dates_and_ambiguous_names(self):
        self.note('主题/想法.md', '[[Обзор]] ![[assets/示例.png]] [other](../Other.md) [[Same]]')
        self.note('Обзор.md', '中文 English Русский')
        self.note('Other.md', '')
        self.note('One/Same.md', '')
        self.note('Two/Same.md', '')
        self.vault.add_image('assets/示例.png', PNG)
        graph = self.vault.graph()
        note = next(n for n in graph['notes'] if n['id']=='主题/想法.md')
        self.assertIn('Обзор.md', note['outgoing'])
        self.assertIn('Other.md', note['outgoing'])
        self.assertIn('Same', note['unresolved'])
        self.assertEqual(note['images'], ['assets/示例.png'])
        self.assertEqual(self.vault.image('assets/示例.png')[0], PNG)
        self.assertEqual(note['created'], '2026-01-01')

    def test_private_traversal_overwrite_and_active_image_are_rejected(self):
        for path in ['../escape.md','/absolute.md','C:/file.md','Private/a.md','x/Pass/a.md','.obsidian/a.md','a\\b.md','a.md:secret']:
            with self.subTest(path=path), self.assertRaises(VaultError):
                self.vault.create(path, 'forbidden')
        self.note('Keep.md', 'original')
        with self.assertRaises(VaultError):
            self.vault.create('Keep.md', 'overwrite')
        with self.assertRaises(VaultError):
            self.vault.add_image('assets/script.png', b'<svg onload="alert(1)"></svg>')
        (self.root/'Private').mkdir()
        (self.root/'Private'/'hidden.md').write_text('never read')
        self.assertEqual(len(self.vault.graph()['notes']), 1)

    def test_cache_does_not_keep_changed_or_deleted_notes(self):
        self.note('A.md','')
        self.note('B.md','')
        self.assertEqual(self.vault.graph()['summary']['unlinked'], 2)
        (self.root/'A.md').write_text('[[B]]', encoding='utf-8')
        self.assertEqual(self.vault.graph()['summary']['unlinked'], 0)
        (self.root/'B.md').unlink()
        graph = self.vault.graph()
        self.assertEqual(graph['summary']['notes'], 1)
        self.assertEqual(graph['summary']['unlinked'], 1)

    def test_protected_roots_casefold_links_and_partial_scan(self):
        (self.root/'Private'/'child').mkdir(parents=True)
        with self.assertRaises(VaultError):
            Vault(self.root/'Private'/'child')
        self.note('Folder/Target.MD', '')
        self.note('Source.md', '[[folder/target.md]]')
        graph=self.vault.graph()
        source=next(n for n in graph['notes'] if n['id']=='Source.md')
        self.assertEqual(source['outgoing'], ['Folder/Target.MD'])
        limited=Vault(self.root, limit=1).graph()
        self.assertIn('note_limit_reached', limited['warnings'])
        self.assertEqual(limited['summary']['notes'],1)

    def test_symlink_cannot_expose_outside_file(self):
        with tempfile.TemporaryDirectory() as elsewhere:
            outside = Path(elsewhere)/'outside.md'
            outside.write_text('secret')
            try:
                (self.root/'linked.md').symlink_to(outside)
            except OSError:
                self.skipTest('Creating symlinks not permitted on this host')
            self.assertEqual(self.vault.graph()['notes'], [])
            with self.assertRaises(VaultError):
                self.vault.read('linked.md')

    def test_http_auth_host_origin_readonly_and_writes(self):
        self.note('Hello.md','Русский English 中文')
        with Server(self.vault, writable=False) as server:
            thread=threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            def request(path, body=None, auth=True, **headers):
                if auth: headers['Authorization']='Bearer '+server.token
                data=None if body is None else json.dumps(body).encode()
                if data is not None: headers['Content-Type']='application/json'
                req=Request(server.origin+path,data=data,headers=headers)
                try:
                    with urlopen(req,timeout=5) as response:
                        return response.status, response.read(), response.headers
                except HTTPError as exc:
                    return exc.code, exc.read(), exc.headers
            try:
                self.assertEqual(request('/api/graph',auth=False)[0],401)
                self.assertEqual(request('/api/health',auth=False)[0],200)
                self.assertEqual(request('/api/openapi',auth=False)[0],401)
                self.assertEqual(json.loads(request('/api/openapi')[1])['openapi'],'3.1.0')
                self.assertEqual(request('/api/graph',Origin='https://untrusted.example')[0],403)
                self.assertEqual(request('/api/graph',Host='untrusted.example')[0],403)
                code,body,headers=request('/api/graph')
                self.assertEqual(code,200)
                self.assertEqual(json.loads(body)['summary']['notes'],1)
                self.assertIsNone(headers.get('Access-Control-Allow-Origin'))
                self.assertEqual(request('/api/notes',{'path':'New.md','content':'hello'})[0],403)
                server.writable=True
                self.assertEqual(request('/api/notes',{'path':'新笔记.md','content':'# Привет 中文'})[0],201)
                self.assertEqual(request('/api/notes',{'path':'新笔记.md','content':'overwrite'})[0],400)
                self.assertEqual(request('/api/notes',{'path':'../escape.md','content':'escape'})[0],400)
                self.assertEqual(request('/api/images',{'path':'assets/photo.png','base64':base64.b64encode(PNG).decode()})[0],201)
                self.assertEqual(request('/api/image?path=assets/photo.png')[1],PNG)
                self.assertEqual(request('/api/images',{'path':'assets/bad.png','base64':'!bad'})[0],400)
                self.assertEqual(request('/../../obsidian.py',auth=False)[0],404)
            finally:
                server.shutdown()
                thread.join(timeout=5)

    def test_cli_all_three_languages_and_unicode(self):
        self.note('Русский 中文.md','original')
        entry=str(Path(__file__).resolve().parents[1]/'obsidian.py')
        for language in ('ru','en','zh'):
            proc=subprocess.run([sys.executable,'-B',entry,'--lang',language,'--vault',str(self.root),'status'],capture_output=True,encoding='utf-8',check=True)
            result=json.loads(proc.stdout)
            self.assertEqual(result['summary']['notes'],1)
        proc=subprocess.run([sys.executable,'-B',entry,'--vault',str(self.root),'read','Русский 中文.md'],capture_output=True,encoding='utf-8',check=True)
        self.assertIn('original',json.loads(proc.stdout)['content'])


if __name__=='__main__':
    unittest.main(verbosity=2)
