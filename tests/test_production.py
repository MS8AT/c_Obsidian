import base64
from http.cookies import SimpleCookie
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from auth_store import create_user, hash_password, verify_password, update_user
from production import Application

PNG=base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a3ioAAAAASUVORK5CYII=')


class ProductionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.account_hash=hash_password('correct-test-password')

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='obsidian-production-test-')
        self.root=Path(self.temp.name)
        self.vault=self.root/'notes'
        self.vault.mkdir()
        self.state=self.root/'state'
        self.state.mkdir()
        (self.state/'accounts.json').write_text(json.dumps({'TestUser':self.account_hash}))
        self.app=Application(self.vault,self.state)
        self.cookie=''
        self.csrf=''

    def tearDown(self):
        self.temp.cleanup()

    def request(self,path,method='GET',body=None,headers=None,raw=None):
        route,_,query=path.partition('?')
        data=json.dumps(body).encode() if body is not None else raw or b''
        env={'REQUEST_METHOD':method,'PATH_INFO':route,'QUERY_STRING':query,'HTTP_HOST':'obsidian.ms8at.by','HTTP_COOKIE':self.cookie,'wsgi.input':io.BytesIO(data),'CONTENT_LENGTH':str(len(data)),'CONTENT_TYPE':'application/json','REMOTE_ADDR':'127.0.0.1'}
        if self.csrf:env['HTTP_X_CSRF_TOKEN']=self.csrf
        env.update(headers or {})
        result={}
        def start(status,response_headers):
            result['status']=int(status.split()[0])
            result['headers']=dict(response_headers)
        result['body']=b''.join(self.app(env,start))
        return result

    def login(self):
        result=self.request('/api/login','POST',{'username':'TestUser','password':'correct-test-password'})
        self.assertEqual(result['status'],200)
        cookie=SimpleCookie(result['headers']['Set-Cookie'])
        self.cookie='obsidian_session='+cookie['obsidian_session'].value
        self.csrf=json.loads(self.request('/api/session')['body'])['csrf']
        return result

    def test_authentication_on_every_vault_endpoint_and_public_pages(self):
        for path in ['/api/status','/api/session','/api/graph','/api/openapi','/api/note?path=Home.md','/api/image?path=assets/photo.png','/app.js','/index.html']:
            with self.subTest(path=path):self.assertEqual(self.request(path)['status'],401)
        for path in ['/api/health','/login','/login.js','/style.css']:
            with self.subTest(path=path):self.assertEqual(self.request(path)['status'],200)
        self.assertEqual(self.request('/')['status'],303)
        self.assertEqual(self.request('/api/login','POST',{'username':'TestUser','password':'wrong-test-password'})['status'],401)

    def test_login_session_cookie_csrf_and_persistent_logout(self):
        result=self.login()
        for flag in ['HttpOnly','Secure','SameSite=Lax']:
            self.assertIn(flag,result['headers']['Set-Cookie'])
        self.assertEqual(self.request('/api/status')['status'],200)
        saved=self.csrf
        self.csrf=''
        self.assertEqual(self.request('/api/notes','POST',{'path':'blocked.md','content':'x'})['status'],403)
        self.csrf=saved
        self.assertEqual(self.request('/api/logout','POST')['status'],200)
        self.assertEqual(self.request('/api/status')['status'],401)
        self.app=Application(self.vault,self.state)
        self.assertEqual(self.request('/api/status')['status'],401)

    def test_all_api_success_paths_and_file_boundaries(self):
        self.login()
        result=self.request('/api/notes','POST',{'path':'Inbox/Русский 中文.md','content':'# Hello 中文\n![[assets/photo.png]]'})
        self.assertEqual(result['status'],201)
        self.assertEqual(self.request('/api/notes','POST',{'path':'Inbox/Русский 中文.md','content':'overwrite'})['status'],400)
        self.assertEqual(self.request('/api/note?path=Inbox/Русский 中文.md')['status'],200)
        self.assertEqual(self.request('/api/images','POST',{'path':'assets/photo.png','base64':base64.b64encode(PNG).decode()})['status'],201)
        self.assertEqual(self.request('/api/image?path=assets/photo.png')['body'],PNG)
        for path in ['/','/index.html','/app.js','/api/status','/api/openapi','/api/graph','/api/session']:
            self.assertEqual(self.request(path)['status'],200)
        graph=json.loads(self.request('/api/graph')['body'])
        self.assertEqual(graph['summary']['images'],1)
        for path in ['../escape.md','Private/file.md','.obsidian/file.md','NUL.md','a.md:stream']:
            with self.subTest(path=path):self.assertEqual(self.request('/api/notes','POST',{'path':path,'content':'x'})['status'],400)
        self.assertEqual(self.request('/api/images','POST',{'path':'assets/bad.png','base64':'bad!'})['status'],400)
        self.assertEqual(self.request('/api/unknown')['status'],404)
        self.assertEqual(self.request('/api/graph','DELETE')['status'],405)
        self.assertEqual(self.request('/api/notes','POST',raw=b'not json')['status'],400)

    def test_host_origin_rate_limit_and_revoked_account(self):
        self.assertEqual(self.request('/api/login','POST',{'username':'TestUser','password':'correct-test-password'},headers={'HTTP_HOST':'evil.example'})['status'],403)
        self.assertEqual(self.request('/api/login','POST',{},headers={'HTTP_ORIGIN':'https://evil.example'})['status'],403)
        for _ in range(10):
            self.assertEqual(self.request('/api/login','POST',{'username':'missing','password':'test-password'})['status'],401)
        self.assertEqual(self.request('/api/login','POST',{'username':'TestUser','password':'correct-test-password'})['status'],429)
        self.app.attempts.clear()
        self.login()
        (self.state/'accounts.json').write_text('{}')
        self.assertEqual(self.request('/api/status')['status'],401)

    def test_readonly_session_allows_reads_and_blocks_creates(self):
        self.app.writable=False
        self.login()
        self.assertEqual(self.request('/api/graph')['status'],200)
        self.assertEqual(self.request('/api/notes','POST',{'path':'A.md','content':'x'})['status'],403)
        self.assertEqual(self.request('/api/images','POST',{})['status'],403)

    def test_salted_password_storage_and_exclusive_provisioning(self):
        state=self.root/'new-state'
        create_user(state,'ExampleUser','example-test-password')
        raw=(state/'accounts.json').read_text()
        self.assertNotIn('example-test-password',raw)
        encoded=json.loads(raw)['ExampleUser']
        self.assertTrue(verify_password('example-test-password',encoded))
        self.assertFalse(verify_password('different-test-password',encoded))
        self.assertNotEqual(encoded,hash_password('example-test-password'))
        with self.assertRaises(FileExistsError):create_user(state,'OtherUser','example-test-password')

    def test_password_update_and_rename_back_never_restore_old_session(self):
        self.login()
        saved_cookie = self.cookie
        update_user(self.state, 'TestUser', 'changed-test-password')
        self.assertEqual(self.request('/api/session')['status'], 401)
        update_user(self.state, 'TestUser', 'renamed-test-password', 'RenamedUser')
        update_user(self.state, 'RenamedUser', 'correct-test-password', 'TestUser')
        self.cookie = saved_cookie
        self.assertEqual(self.request('/api/session')['status'], 401)
        self.login()
        self.assertEqual(self.request('/api/session')['status'], 200)


if __name__=='__main__':unittest.main(verbosity=2)
