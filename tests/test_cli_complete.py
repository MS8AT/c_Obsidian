import base64
import json
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
from urllib.request import urlopen
import unittest

ENTRY=Path(__file__).resolve().parents[1]/'obsidian.py'


class CompleteCliTests(unittest.TestCase):
    def test_every_cli_command_and_expected_failures(self):
        with tempfile.TemporaryDirectory(prefix='obsidian-cli-test-') as temp:
            root=Path(temp)
            vault=root/'vault'
            def run(*args,code=0):
                result=subprocess.run([sys.executable,'-B',str(ENTRY),'--vault',str(vault),*args],capture_output=True,encoding='utf-8')
                self.assertEqual(result.returncode,code,result.stderr)
                return json.loads(result.stdout) if result.returncode==0 else json.loads(result.stderr)
            self.assertTrue(run('init')['created'])
            self.assertEqual(run('status')['summary']['notes'],1)
            self.assertEqual(run('scan')['schema'],'c-obsidian.graph/v1')
            self.assertEqual(run('read','Home.md')['path'],'Home.md')
            draft=root/'draft.md';draft.write_text('# Привет 中文\n[[Home]]',encoding='utf-8')
            self.assertTrue(run('create','Inbox/新笔记.md','--content-file',str(draft))['created'])
            run('create','Inbox/新笔记.md','--content-file',str(draft),code=2)
            run('read','../escape.md',code=2)
            image=root/'sample.png';image.write_bytes(base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a3ioAAAAASUVORK5CYII='))
            self.assertEqual(run('photo',str(image),'--path','assets/photo.png')['embed'],'![[assets/photo.png]]')
            run('photo',str(image),'--path','assets/photo.png',code=2)
            run('init',code=2)
            for language in ['ru','en','zh']:
                result=subprocess.run([sys.executable,'-B',str(ENTRY),'--lang',language,'--help'],capture_output=True,encoding='utf-8')
                self.assertEqual(result.returncode,0)
                self.assertIn('serve',result.stdout)

    def test_serve_process_starts_and_answers_health(self):
        with tempfile.TemporaryDirectory(prefix='obsidian-serve-test-') as temp:
            with socket.socket() as reservation:
                reservation.bind(('127.0.0.1',0));port=reservation.getsockname()[1]
            process=subprocess.Popen([sys.executable,'-B',str(ENTRY),'--vault',temp,'serve','--port',str(port)],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
            try:
                deadline=time.monotonic()+10
                while True:
                    try:
                        with urlopen(f'http://127.0.0.1:{port}/api/health',timeout=1) as response:
                            self.assertTrue(json.load(response)['ok'])
                        break
                    except OSError:
                        if process.poll() is not None or time.monotonic()>deadline:
                            self.fail('Serve did not start')
                        time.sleep(.05)
            finally:
                process.terminate()
                process.communicate(timeout=5)


if __name__=='__main__':unittest.main(verbosity=2)
