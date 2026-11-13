"""Prototype bytes, access control and the HTML execution boundary."""
import hashlib
from http.client import HTTPConnection
import io
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from auth_store import hash_password
from obsidian import Server
from obsidian_core import Vault
from production import Application
from prism import prototype


AUTHOR_SHA256 = 'de791bff422ea20889d370d7770ce7c2f3fb8387112c8e9f35f411b8acebf03f'


class PrismTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.password_hash = hash_password('prism-isolated-test-password')

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='prism-test-')
        self.root = Path(self.temp.name)
        self.vault = self.root / 'vault'
        self.vault.mkdir()
        state = self.root / 'state'
        state.mkdir()
        (state / 'accounts.json').write_text(json.dumps({'TestUser': self.password_hash}))
        self.app = Application(self.vault, state, writable=False)
        self.cookie = ''

    def tearDown(self):
        self.temp.cleanup()

    def request(self, path, method='GET', data=None, **overrides):
        raw = json.dumps(data).encode() if data is not None else b''
        route, _, query = path.partition('?')
        env = {'PATH_INFO': route, 'QUERY_STRING': query, 'REQUEST_METHOD': method,
               'HTTP_HOST': 'obsidian.ms8at.by', 'HTTP_COOKIE': self.cookie,
               'CONTENT_TYPE': 'application/json', 'CONTENT_LENGTH': str(len(raw)),
               'wsgi.input': io.BytesIO(raw), 'REMOTE_ADDR': '127.0.0.1', **overrides}
        result = {}
        def start(status, headers):
            result.update(status=int(status.split()[0]), headers=dict(headers))
        result['body'] = b''.join(self.app(env, start))
        return result

    def login(self):
        result = self.request('/api/login', 'POST', {
            'username': 'TestUser', 'password': 'prism-isolated-test-password'})
        self.assertEqual(result['status'], 200)
        self.cookie = result['headers']['Set-Cookie'].split(';')[0]

    def test_original_bytes_and_api_export_are_identical(self):
        raw, meta = prototype()
        self.assertEqual(hashlib.sha256(raw).hexdigest(), AUTHOR_SHA256)
        self.login()
        result = self.request('/api/prism/prototype')
        self.assertEqual(result['status'], 200)
        exported = json.loads(result['body'])
        self.assertEqual(exported['content'].encode('utf-8'), raw)
        self.assertEqual(exported['sha256'], AUTHOR_SHA256)
        self.assertEqual(exported['bytes'], len(raw))
        self.assertFalse(exported['vault_integration'])
        preview = self.request(exported['preview_url'])
        self.assertEqual(preview['status'], 200)
        self.assertEqual(preview['body'], raw)
        self.assertIn('text/html', preview['headers']['Content-Type'])
        self.assertEqual(list(self.vault.iterdir()), [])

    def test_production_source_and_preview_need_a_live_session(self):
        for path in ['/prism', '/api/prism/prototype']:
            self.assertEqual(self.request(path)['status'], 401)
        self.login()
        (self.app.state / 'accounts.json').write_text('{}')
        for path in ['/prism', '/api/prism/prototype']:
            self.assertEqual(self.request(path)['status'], 401)

    def test_sandbox_is_limited_to_the_preview(self):
        self.login()
        policy = self.request('/prism')['headers']['Content-Security-Policy']
        self.assertIn('sandbox allow-scripts allow-modals', policy)
        self.assertNotIn('allow-same-origin', policy)
        self.assertNotIn('allow-top-navigation', policy)
        self.assertIn("connect-src 'none'", policy)
        self.assertIn("form-action 'none'", policy)
        self.assertIn("frame-ancestors 'self'", policy)
        for path in ['/', '/api/prism/prototype', '/login']:
            regular = self.request(path)['headers']['Content-Security-Policy']
            self.assertNotIn("'unsafe-inline'", regular)
            self.assertIn("frame-ancestors 'none'", regular)

    def test_prototype_rejects_wrong_host_origin_and_write_requests(self):
        self.login()
        for path in ['/prism', '/api/prism/prototype']:
            self.assertEqual(self.request(path, HTTP_HOST='other.example')['status'], 403)
            self.assertEqual(self.request(path, HTTP_ORIGIN='https://other.example')['status'], 403)
            self.assertEqual(self.request(path, 'PUT')['status'], 403)

    def test_loopback_auth_bytes_and_isolation(self):
        with Server(Vault(self.vault), writable=False) as server:
            worker = threading.Thread(target=server.serve_forever, daemon=True)
            worker.start()
            connection = HTTPConnection('127.0.0.1', server.server_port, timeout=5)
            try:
                connection.request('GET', '/prism')
                response = connection.getresponse()
                self.assertEqual(response.status, 401)
                response.read()
                connection.request('GET', '/api/prism/prototype')
                response = connection.getresponse()
                self.assertEqual(response.status, 401)
                response.read()
                connection.request('GET', '/api/prism/prototype', headers={
                    'Authorization': 'Bearer ' + server.token})
                response = connection.getresponse()
                self.assertEqual(response.status, 200)
                preview_cookie = response.getheader('Set-Cookie').split(';')[0]
                source = json.loads(response.read())
                connection.request('GET', '/api/status', headers={'Cookie': preview_cookie})
                response = connection.getresponse()
                self.assertEqual(response.status, 401)
                response.read()
                connection.request('GET', '/prism', headers={'Cookie': preview_cookie})
                response = connection.getresponse()
                self.assertEqual(response.status, 200)
                response.read()
                connection.request('GET', '/prism', headers={'Authorization': 'Bearer ' + server.token})
                response = connection.getresponse()
                self.assertEqual(response.status, 200)
                self.assertIn('sandbox allow-scripts', response.getheader('Content-Security-Policy'))
                self.assertEqual(response.read(), source['content'].encode('utf-8'))
            finally:
                connection.close()
                server.shutdown()
                worker.join(timeout=5)


if __name__ == '__main__':
    unittest.main()


class ApiParityTests(unittest.TestCase):
    setUp = PrismTests.setUp
    tearDown = PrismTests.tearDown
    request = PrismTests.request

    @classmethod
    def setUpClass(cls):
        cls.password_hash = hash_password('prism-isolated-test-password')

    def login(self):
        PrismTests.login(self)
        self.csrf = json.loads(self.request('/api/session')['body'])['csrf']
        self.app.writable = True

    def write(self, path, data, method='PUT'):
        return self.request(path, method, data, HTTP_X_CSRF_TOKEN=self.csrf)

    def test_production_editor_roundtrip_stale_revision_and_graph(self):
        self.login()
        self.assertEqual(self.write('/api/notes', {'path':'A.md','content':'# A\n'}, 'POST')['status'],201)
        (self.vault/'A.md').chmod(0o640)
        source = json.loads(self.request('/api/note?path=A.md')['body'])
        edit = {'path':'A.md','content':'# A\n\n[[B]]','expected_sha256':source['sha256']}
        self.assertEqual(self.write('/api/notes/update',edit)['status'],201)
        self.assertEqual((self.vault/'A.md').stat().st_mode & 0o777,0o640)
        self.assertEqual(self.write('/api/notes/update',edit)['status'],409)
        self.assertEqual(json.loads(self.request('/api/note?path=A.md')['body'])['content'],edit['content'])
        self.assertEqual(json.loads(self.request('/api/graph')['body'])['notes'][0]['unresolved'],['B'])
        self.assertEqual(self.request('/api/notes/update','PUT',edit)['status'],403)
        self.app.writable=False
        self.assertEqual(self.write('/api/notes/update',edit)['status'],403)

    def test_edit_preserves_unowned_lock_and_previous_temporary_file(self):
        self.login()
        self.write('/api/notes', {'path':'A.md','content':'# A'}, 'POST')
        foreign=self.vault/'.A.md.write-lock';foreign.write_bytes(b'other writer')
        previous=self.vault/'A.md.c-obsidian-tmp';previous.write_bytes(b'not ours')
        result=self.write('/api/notes/update',{'path':'A.md','content':'# Updated'})
        self.assertEqual(result['status'],409)
        self.assertEqual(foreign.read_bytes(),b'other writer')
        self.assertEqual(previous.read_bytes(),b'not ours')
        self.assertEqual((self.vault/'A.md').read_text(),'# A')

    def test_prism_upload_read_preview_restart_cas_reset_original(self):
        self.login()
        original=json.loads(self.request('/api/prism/prototype')['body'])
        content='<!doctype html><html><head><title>Edited</title></head><body>Custom<script>window.value=1</script></body></html>'
        result=self.write('/api/prism/prototype',{'content':content,'expected_sha256':original['sha256']})
        self.assertEqual(result['status'],200)
        current=json.loads(result['body']);self.assertTrue(current['modified'])
        self.assertEqual(self.request('/prism')['body'],content.encode())
        self.assertEqual(json.loads(self.request('/api/prism/prototype?original=1')['body'])['sha256'],AUTHOR_SHA256)
        self.assertEqual(self.write('/api/prism/prototype',{'content':content,'expected_sha256':original['sha256']})['status'],409)
        self.app=Application(self.vault,self.app.state)
        self.assertEqual(json.loads(self.request('/api/prism/prototype')['body'])['content'],content)
        reset=self.write('/api/prism/reset',{'expected_sha256':current['sha256']},'POST')
        self.assertEqual(reset['status'],200)
        self.assertEqual(json.loads(reset['body'])['sha256'],AUTHOR_SHA256)
        self.assertEqual(self.request('/prism')['body'],prototype()[0])
        self.assertNotIn("allow-same-origin",self.request('/prism')['headers']['Content-Security-Policy'])

    def test_prism_auth_csrf_readonly_validation_and_corrupt_state(self):
        content='<!doctype html><html><body>Test</body></html>'
        self.assertEqual(self.request('/api/prism/prototype','PUT',{})['status'],401)
        self.login();source=json.loads(self.request('/api/prism/prototype')['body'])
        body={'content':content,'expected_sha256':source['sha256']}
        self.assertEqual(self.request('/api/prism/prototype','PUT',body)['status'],403)
        self.assertEqual(self.write('/api/prism/prototype',{'content':content})['status'],400)
        self.assertEqual(self.write('/api/prism/prototype',{'content':'plain text','expected_sha256':source['sha256']})['status'],400)
        self.app.writable=False
        self.assertEqual(self.write('/api/prism/prototype',body)['status'],403)
        self.assertEqual(self.write('/api/prism/reset',{'expected_sha256':source['sha256']},'POST')['status'],403)
        self.app.writable=True
        self.assertEqual(self.write('/api/prism/prototype',body)['status'],200)
        marker=self.app.actions.prism.root/'current.json';marker.write_text('{broken')
        self.assertEqual(self.request('/api/prism/prototype')['status'],400)

    def test_image_upload_info_replace_and_signature_validation(self):
        import base64
        from test_production import PNG
        self.login();body={'path':'assets/test.png','base64':base64.b64encode(PNG).decode()}
        self.assertEqual(self.write('/api/images',body,'POST')['status'],201)
        info=json.loads(self.request('/api/image/info?path=assets/test.png')['body'])
        update={**body,'expected_sha256':info['sha256']}
        self.assertEqual(self.write('/api/images/update',update)['status'],200)
        self.assertEqual(self.write('/api/images/update',{**body,'expected_sha256':'0'*64})['status'],409)
        self.assertEqual(self.write('/api/images/update',{**body,'base64':base64.b64encode(b'<html>').decode()})['status'],400)
        self.assertEqual(self.request('/api/image?path=assets/test.png')['body'],PNG)

    def test_all_views_search_dates_and_capabilities_are_readable(self):
        self.login()
        for path,text in [('A.md','---\ncreated: 2026-01-01\n---\n# Alpha\n\n[[B]]'),('B.md','# Beta')]:
            self.write('/api/notes',{'path':path,'content':text},'POST')
        caps=json.loads(self.request('/api/capabilities')['body'])
        views=json.loads(self.request('/api/views')['body'])
        self.assertEqual(caps['views'],views['views'])
        for view in views['views']:
            result=self.request('/api/graph?view='+view+'&group=folder&language=ru')
            self.assertEqual(result['status'],200)
            self.assertEqual(json.loads(result['body'])['projection']['view'],view)
        self.assertEqual(json.loads(self.request('/api/notes?q=alpha')['body'])['count'],1)
        filtered=json.loads(self.request('/api/graph?until=2026-01-01')['body'])
        self.assertEqual([n['id'] for n in filtered['notes']],['A.md'])
        self.assertEqual(filtered['edges'],[])
        for query in ['view=missing','group=missing','language=missing','until=2026-02-31']:
            self.assertEqual(self.request('/api/graph?'+query)['status'],400)

    def test_invalid_input_never_turns_into_server_error(self):
        self.assertEqual(self.request('/api/login','POST',[])['status'],400)
        self.login()
        for path,method in [('/api/notes','POST'),('/api/images','POST'),('/api/notes/update','PUT'),('/api/images/update','PUT'),('/api/prism/prototype','PUT')]:
            self.assertEqual(self.write(path,[],method)['status'],400)
        self.assertEqual(self.write('/api/prism/prototype',{},'POST')['status'],405)

    def test_loopback_supports_same_edit_upload_reset_and_discovery_contract(self):
        with Server(Vault(self.vault),writable=True,state=self.root/'local-state') as server:
            worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
            conn=HTTPConnection('127.0.0.1',server.server_port,timeout=5)
            def request(path,method='GET',body=None,auth=True):
                raw=json.dumps(body).encode() if body is not None else None
                headers={'Content-Type':'application/json'}
                if auth:headers['Authorization']='Bearer '+server.token
                conn.request(method,path,raw,headers);response=conn.getresponse();data=response.read()
                return response.status,json.loads(data)
            try:
                for path in ['/api/views','/api/capabilities','/api/notes']:
                    self.assertEqual(request(path,auth=False)[0],401)
                    self.assertEqual(request(path)[0],200)
                self.assertEqual(request('/api/notes','POST',{'path':'A.md','content':'# A'})[0],201)
                source=request('/api/note?path=A.md')[1]
                self.assertEqual(request('/api/notes/update','PUT',{'path':'A.md','content':'# Edit','expected_sha256':source['sha256']})[0],201)
                self.assertEqual(request('/api/notes/update','PUT',{'path':'A.md','content':'# Stale','expected_sha256':source['sha256']})[0],409)
                original=request('/api/prism/prototype')[1]
                edit={'content':'<!doctype html><html><body>Uploaded</body></html>','expected_sha256':original['sha256']}
                code,current=request('/api/prism/prototype','PUT',edit);self.assertEqual(code,200)
                self.assertEqual(request('/api/prism/reset','POST',{'expected_sha256':current['sha256']})[1]['sha256'],AUTHOR_SHA256)
                self.assertEqual(request('/api/graph?view=invalid')[0],400)
            finally:
                conn.close();server.shutdown();worker.join(timeout=5)
