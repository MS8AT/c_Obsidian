"""Native 0.3 project persistence, revision conflicts and portable exports."""
import copy
import hashlib
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import test_prism as fixtures
from auth_store import hash_password
from production import Application
from prism_core import PrismStore


class NativeProjectApiTests(unittest.TestCase):
    setUp=fixtures.PrismTests.setUp
    tearDown=fixtures.PrismTests.tearDown
    request=fixtures.PrismTests.request

    @classmethod
    def setUpClass(cls):
        cls.password_hash=hash_password('prism-isolated-test-password')

    def login(self):
        fixtures.PrismTests.login(self)
        self.csrf=json.loads(self.request('/api/session')['body'])['csrf']
        self.app.writable=True

    def send(self,path,body,method='POST'):
        r=self.request(path,method,body,HTTP_X_CSRF_TOKEN=self.csrf)
        return r['status'],json.loads(r['body'])

    def example(self):
        self.login();code,case=self.send('/api/prism/v1/example',{})
        self.assertEqual(code,201);return case

    def hashes(self):
        return {str(p.relative_to(self.vault)):hashlib.sha256(p.read_bytes()).hexdigest() for p in self.vault.rglob('*') if p.is_file()}

    def test_two_projects_are_independent_and_survive_restart(self):
        a=self.example();b=copy.deepcopy(a);b['id']='prm-project-b';b['title']='Project B'
        code,b=self.send('/api/prism/v1/cases',b);self.assertEqual(code,201)
        before_b=copy.deepcopy(b)
        node=next(n for n in a['nodes'] if n.get('kind')=='condition' and n.get('value') is True)
        node['value']=False
        code,a2=self.send('/api/prism/v1/cases/'+a['id'],{'model':a,'expected_revision':a['revision']},'PUT')
        self.assertEqual(code,201);self.assertEqual(a2['revision'],2)
        self.assertEqual(json.loads(self.request('/api/prism/v1/cases/'+b['id'])['body']),before_b)
        state=self.app.state;self.app=Application(self.vault,state)
        loaded=json.loads(self.request('/api/prism/v1/cases')['body'])['cases']
        self.assertEqual({m['id'] for m in loaded},{a['id'],b['id']})
        self.assertEqual(json.loads(self.request('/api/prism/v1/cases/'+a['id'])['body']),a2)
        history=json.loads(self.request('/api/prism/v1/cases/'+a['id']+'/history')['body'])['events']
        self.assertEqual([e['revision'] for e in history],[1,2])

    def test_readonly_get_snapshot_and_evaluate_do_not_write(self):
        case=self.example();before=self.hashes();self.app.writable=False
        result=self.request('/api/prism/v1/cases/'+case['id']+'/snapshot')
        self.assertEqual(result['status'],200);self.assertEqual(json.loads(result['body'])['revision'],1)
        self.assertEqual(self.send('/api/prism/v1/cases/'+case['id']+'/evaluate',{})[0],200)
        self.assertEqual(self.send('/api/prism/v1/cases/'+case['id']+'/compare',{})[0],200)
        self.assertEqual(self.send('/api/prism/v1/cases/'+case['id']+'/snapshot',{})[0],403)
        self.assertEqual(before,self.hashes())

    def test_stale_revision_boolean_and_pending_transaction_never_overwrite(self):
        case=self.example();path='/api/prism/v1/cases/'+case['id'];edited=copy.deepcopy(case);edited['title']='Revision two'
        self.assertEqual(self.send(path,{'model':edited,'expected_revision':1},'PUT')[0],201)
        before=self.hashes()
        self.assertEqual(self.send(path,{'model':case,'expected_revision':1},'PUT')[0],409)
        self.assertEqual(self.send(path,{'model':case,'expected_revision':True},'PUT')[0],409)
        self.assertEqual(before,self.hashes())
        marker=self.app.prism._transaction_path(case['id']);marker.write_text('{"operation_id":"other-writer"}')
        current=self.app.prism.get(case['id'])
        self.assertEqual(self.send(path,{'model':current,'expected_revision':2},'PUT')[0],409)
        self.assertEqual(marker.read_text(),'{"operation_id":"other-writer"}')

    def test_export_validate_import_preserves_semantics_and_detects_tampering(self):
        case=self.example();packet=json.loads(self.request('/api/prism/v1/cases/'+case['id']+'/export')['body'])
        code,checked=self.send('/api/prism/v1/import/validate',{'package':packet});self.assertEqual(code,200)
        self.assertEqual(self.send('/api/prism/v1/import/commit',{'package':packet,'expected_package_sha256':checked['package_sha256']})[0],409)
        for field in ['protocol','model_sha256','package_sha256']:
            broken=copy.deepcopy(packet);broken[field]='tampered'
            self.assertEqual(self.send('/api/prism/v1/import/validate',{'package':broken})[0],400)
        other=self.root/'import-vault';other.mkdir();store=PrismStore(other)
        result=store.commit_import(packet,checked['package_sha256'])
        self.assertEqual(result['nodes'],case['nodes']);self.assertEqual(result['rules'],case['rules'])
        self.assertEqual(result['question'],case['question']);self.assertEqual(result['revision'],1)
        self.assertEqual(store.get(result['id']),result)

    def test_scenario_saved_in_project_and_exported(self):
        case=self.example();node=next(n for n in case['nodes'] if n.get('kind')=='condition')
        case['scenarios']=[{'id':'scenario-a','title':'Saved A','base_revision':1,'overrides':[{'node_id':node['id'],'knowledge_status':'established','value':False,'origin':'assumption','provenance_mode':'assumption'}]}]
        code,updated=self.send('/api/prism/v1/cases/'+case['id'],{'model':case,'expected_revision':1},'PUT')
        self.assertEqual(code,201)
        code,evaluation=self.send('/api/prism/v1/cases/'+case['id']+'/evaluate',{'scenario_id':'scenario-a'})
        self.assertEqual(code,200);self.assertEqual(evaluation['snapshot']['revision'],2)
        exported=json.loads(self.request('/api/prism/v1/cases/'+case['id']+'/export')['body'])
        self.assertEqual(exported['model']['scenarios'],updated['scenarios'])
        self.assertEqual(exported['model']['scenarios'][0]['title'],'Saved A')

    def test_loopback_native_projects_have_same_revision_and_read_contract(self):
        import threading
        from http.client import HTTPConnection
        from obsidian import Server
        from obsidian_core import Vault
        with Server(Vault(self.vault),writable=True) as server:
            worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
            conn=HTTPConnection('127.0.0.1',server.server_port,timeout=5)
            def request(path,method='GET',body=None):
                data=json.dumps(body).encode() if body is not None else None
                conn.request(method,path,data,{'Authorization':'Bearer '+server.token,'Content-Type':'application/json'})
                result=conn.getresponse();return result.status,json.loads(result.read())
            try:
                code,a=request('/api/prism/v1/example','POST',{});self.assertEqual(code,201)
                b=copy.deepcopy(a);b['id']='prm-local-b';b['title']='Local B'
                self.assertEqual(request('/api/prism/v1/cases','POST',b)[0],201)
                self.assertEqual(len(request('/api/prism/v1/cases')[1]['cases']),2)
                before=self.hashes()
                self.assertEqual(request('/api/prism/v1/cases/'+a['id']+'/snapshot')[0],200)
                self.assertEqual(before,self.hashes())
                a['title']='Local A updated'
                self.assertEqual(request('/api/prism/v1/cases/'+a['id'],'PUT',{'model':a,'expected_revision':1})[0],201)
                self.assertEqual(request('/api/prism/v1/cases/'+a['id'],'PUT',{'model':a,'expected_revision':1})[0],409)
                server.writable=False
                self.assertEqual(request('/api/prism/v1/cases/'+a['id']+'/evaluate','POST',{})[0],200)
                self.assertEqual(request('/api/prism/v1/cases/'+a['id']+'/snapshot','POST',{})[0],403)
            finally:
                conn.close();server.shutdown();worker.join(timeout=5)
