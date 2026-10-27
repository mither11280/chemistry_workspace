"""Run a fresh checkout with no source files, then exercise explicit local PDF import."""
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from fixtures import ROOT,make_fixture

class FreshInstallTests(unittest.TestCase):
    def run_server_test(self,root,script):
        shutil.copytree(ROOT/'app',root/'app',ignore=shutil.ignore_patterns('__pycache__'),dirs_exist_ok=True)
        env=dict(os.environ);env.pop('QUESTION_BANK_DB',None);env['QUESTION_BANK_ROOT']=str(root)
        prefix=r'''
import json,sys,threading,urllib.request,urllib.error
from pathlib import Path
sys.path.insert(0,'app')
import server
http=server.ThreadingHTTPServer(('127.0.0.1',0),server.Handler)
threading.Thread(target=http.serve_forever,daemon=True).start()
base='http://127.0.0.1:'+str(http.server_port)
def get(path):return urllib.request.urlopen(base+path).read()
def post(path,data):
 request=urllib.request.Request(base+path,json.dumps(data).encode(),headers={'Content-Type':'application/json','X-Local-Request':'1'})
 return json.loads(urllib.request.urlopen(request).read())
'''
        wrapped=prefix+'\ntry:\n'+''.join('    '+line+'\n' for line in script.splitlines())+'finally:\n    http.shutdown()\n    http.server_close()\n'
        result=subprocess.run([sys.executable,'-c',wrapped],cwd=root,env=env,capture_output=True,text=True,timeout=45)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
    def test_public_download_without_pdfs(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            for folder in ['indexes','schemas']:shutil.copytree(ROOT/folder,root/folder)
            self.run_server_test(root,r'''
assert json.loads(get('/api/bank'))['total']==132
assert json.loads(get('/api/jobs'))==[]
r=json.loads(get('/api/questions?limit=8&paper=1&year=2025'))
assert r['total']==40
assert r['questions'][0]['availability']['question']['state']=='missing'
assert not (server.ROOT/'sources').exists()
qid=r['questions'][0]['id']
try:get('/preview/'+qid+'/question/0');raise AssertionError('should fail')
except urllib.error.HTTPError as e:assert e.code==409
job={'title':'Can save metadata without PDFs','question_ids':[qid],'notes':''}
post('/api/save',job)
assert len(json.loads(get('/api/jobs')))==1
assert post('/api/import',{'code':post('/api/share',job)['code']})==job
''')
    def test_import_http_preview_and_export(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);make_fixture(root)
            self.run_server_test(root,r'''
assert json.loads(get('/api/bank'))['total']==2
for name in ['original-qp.pdf','original-ms.pdf']:
 request=urllib.request.Request(base+'/api/source-upload?name='+name,(Path('fixture-input')/name).read_bytes(),headers={'Content-Type':'application/pdf','X-Local-Request':'1'})
 assert json.loads(urllib.request.urlopen(request).read())['state']=='ready'
assert get('/preview/fixture-q1/question/1').startswith(b'RIFF')
assert get('/preview/fixture-q1/answer/0').startswith(b'RIFF')
assert get('/page/fixture-qp/0').startswith(b'\x89PNG')
assert get('/source/fixture-qp').startswith(b'%PDF')
assert json.loads(get('/api/questions?search=CONTINUED'))['total']==1
job={'title':'Fresh import','question_ids':['fixture-q2','fixture-q1'],'notes':'Teacher notes'}
post('/api/draft',job);assert json.loads(get('/api/draft'))['title']==job['title']
post('/api/save',job)
assert len(json.loads(get('/api/jobs')))==1
for kind in ['questions','answers']:
 assert get(post('/api/export',{'job':job,'kind':kind})['url']).startswith(b'%PDF')
assert json.loads(get('/api/check'))['catalog']['integrity']=='ok'
assert post('/api/maintenance',{'action':'cache-clear'})['files']==0
''')
