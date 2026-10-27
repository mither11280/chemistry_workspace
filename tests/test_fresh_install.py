"""A download has no author-local data, runtime.json, or prebuilt desktop shell."""
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]

class FreshInstallTests(unittest.TestCase):
    def test_download_without_local_data(self):
        with tempfile.TemporaryDirectory(prefix='question-bank-fresh-') as tmp:
            root = Path(tmp)
            shutil.copytree(ROOT/'app', root/'app', ignore=shutil.ignore_patterns('__pycache__'))
            shutil.copytree(ROOT/'question_bank', root/'question_bank')
            env = dict(os.environ)
            env.pop('QUESTION_BANK_DB', None)
            result = subprocess.run([sys.executable, '-c', r'''
import json, sys, threading, urllib.request
sys.path.insert(0, 'app')
import server
assert server.BANK_ROOT == server.BUNDLED
assert not (server.DATA/'bank.json').exists()
assert not (server.DATA/'sources').exists()
http = server.ThreadingHTTPServer(('127.0.0.1', 0), server.Handler)
threading.Thread(target=http.serve_forever, daemon=True).start()
base = 'http://127.0.0.1:' + str(http.server_port)
def get(path):
    return urllib.request.urlopen(base + path).read()
def post(path, data):
    request = urllib.request.Request(base + path, json.dumps(data).encode(),
        headers={'Content-Type':'application/json','X-Local-Request':'1'})
    return json.loads(urllib.request.urlopen(request).read())
try:
    assert len(json.loads(get('/api/bank'))['questions']) == 132
    assert json.loads(get('/api/jobs')) == []
    job = {'title':'Fresh download', 'notes':'', 'question_ids':['cie-9701-m25-12-q3','cie-9701-m25-22-q4']}
    assert get('/preview/cie-9701-m25-12-q3/question/0').startswith(b'\x89PNG')
    assert get('/preview/cie-9701-m25-22-q4/answer/0').startswith(b'\x89PNG')
    assert get('/source/9701_m25_qp_12.pdf').startswith(b'%PDF')
    saved = post('/api/save', job)
    assert saved['question_ids'] == job['question_ids']
    assert len(json.loads(get('/api/jobs'))) == 1
    post('/api/draft', job)
    assert json.loads(get('/api/draft'))['title'] == job['title']
    code = post('/api/share', job)['code']
    assert post('/api/import', {'code':code}) == job
    for kind in ['questions','answers']:
        url = post('/api/export', {'job':job,'kind':kind})['url']
        assert get(url).startswith(b'%PDF')
    assert server.DB.exists()
finally:
    http.shutdown()
    http.server_close()
'''], cwd=root, env=env, timeout=45, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

if __name__ == '__main__':
    unittest.main()
