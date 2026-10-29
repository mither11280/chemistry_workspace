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
    def test_read_only_personal_work_requests_do_not_rewrite_database(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);make_fixture(root)
            self.run_server_test(root,r'''
job={'title':'Preserve stored work','question_ids':['fixture-q1'],'notes':'Original teacher note'}
post('/api/save',job);post('/api/draft',job)
before=server.DB.read_bytes()
for i in range(3):
 assert json.loads(get('/api/jobs'))[0]['notes']==job['notes']
 assert json.loads(get('/api/draft'))['question_ids']==job['question_ids']
 assert post('/api/import',{'code':post('/api/share',job)['code']})==job
assert server.DB.read_bytes()==before
''')
    def test_public_download_without_pdfs(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            for folder in ['indexes','schemas']:shutil.copytree(ROOT/folder,root/folder)
            self.run_server_test(root,r'''
public=json.loads((Path('indexes')/'question-index.json').read_text())
ready=[q for q in public['questions'] if q.get('metadata',{}).get('teaching',{}).get('status','ready')=='ready']
assert json.loads(get('/api/bank'))['total']==len(ready)
assert json.loads(get('/api/jobs'))==[]
r=json.loads(get('/api/questions?limit=8&paper=1&year=2025'))
assert r['total']==sum(q['paper']==1 and q['year']==2025 for q in ready)
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
    def test_report_and_bank_update_http_workflow(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);make_fixture(root)
            self.run_server_test(root,r'''
from copy import deepcopy
from bank.updates import build_package
from bank.format import sha256
job={'title':'Persist across bank update','question_ids':['fixture-q1'],'notes':'private teacher note'}
post('/api/save',job);post('/api/draft',job)
feedback=post('/api/report',{'question_id':'fixture-q1','category':'topics','description':'Wrong topic; local file /Users/teacher/private.pdf','ignored_personal_job':job})
assert feedback['issue_url'].startswith('https://github.com/mither11280/chemistry_workspace/issues/new?')
assert 'private teacher note' not in json.dumps(feedback)
assert '/Users/teacher' not in json.dumps(feedback)
index=deepcopy(server.CATALOG.index);index['revision']='http-update.1';index['questions'][0]['topics']=[]
package=root=server.ROOT/'update.qbank'
build_package(package,index,server.CATALOG.manifest,server.CATALOG.index,server.CATALOG.manifest,server.RESOURCES/'schemas','Fix classification')
request=urllib.request.Request(base+'/api/bank-update-upload',package.read_bytes(),headers={'X-Local-Request':'1','Content-Type':'application/octet-stream'})
preview=json.loads(urllib.request.urlopen(request).read())
assert json.loads(get('/api/bank'))['revision']=='example.1'
assert preview['sha256']==sha256(package)
post('/api/bank-update-install',{'token':preview['token'],'sha256':preview['sha256']})
assert json.loads(get('/api/bank'))['revision']=='http-update.1'
assert json.loads(get('/api/draft'))==job
assert json.loads(get('/api/jobs'))[0]['title']==job['title']
try:post('/api/calibrate',{});raise AssertionError('teacher should not see maintenance workbench')
except urllib.error.HTTPError as e:assert e.code==400
''')
